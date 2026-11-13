package com.dracknoval.domux

import androidx.lifecycle.viewModelScope
import com.dracknoval.domux.data.AddReservationMessageRequest
import com.dracknoval.domux.data.CommonArea
import com.dracknoval.domux.data.CreateReservationRequest
import com.dracknoval.domux.data.Reservation
import com.dracknoval.domux.data.ReservationAvailabilityResponse
import com.dracknoval.domux.data.ResidentSummary
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.UpdateReservationStatusRequest
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Todo lo que la pantalla de Reservas necesita para dibujarse. */
data class ReservationsUiState(
    val reservations: List<Reservation> = emptyList(),
    val loading: Boolean = false,
    // También las reservas que la administración ya archivó. Nada se borra (ADR-013).
    val includeArchived: Boolean = false,
    // Zonas comunes con sus reglas (HU-055) y la que se está reservando.
    val areas: List<CommonArea> = emptyList(),
    val areaId: Int? = null,
    val date: String = "",
    val slot: String = "",
    val availability: ReservationAvailabilityResponse? = null,
    val availabilityLoading: Boolean = false,
    // Días del calendario sin ninguna franja libre y días de mantenimiento de la zona elegida.
    val fullDates: Set<String> = emptySet(),
    val closedDates: Set<String> = emptySet(),
    // Residente a nombre de quien reserva la administración.
    val resident: ResidentSummary? = null,
    val busy: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false,
    // Sube cada vez que el servidor acepta una reserva; el formulario lo mira para limpiarse.
    val created: Int = 0
) {
    /** La zona que se está reservando. */
    val area: CommonArea?
        get() = areas.firstOrNull { it.id == areaId }

    /** Franjas del día en la zona elegida, de la más temprana a la más tarde. */
    val slots: List<String>
        get() {
            val ofArea = area?.slots.orEmpty()
            if (ofArea.isNotEmpty()) return ofArea
            val reported = availability?.availableSlots.orEmpty() + availability?.occupiedSlots.orEmpty()
            return reported.sorted()
        }

    /** Cuántas franjas seguidas se reservan de una vez en la zona (al menos 1). */
    val maxConsecutive: Int
        get() = (availability?.maxConsecutiveSlots ?: area?.maxConsecutiveSlots ?: 1).coerceAtLeast(1)

    /** El rango del día completo, si la zona lo deja reservar. */
    val fullDaySlot: String?
        get() {
            val allowed = availability?.allowFullDay ?: area?.allowFullDay ?: false
            return if (allowed) availability?.fullDaySlot ?: area?.fullDaySlot else null
        }

    /** El día completo se puede elegir solo si todas sus franjas están libres. */
    val fullDayFree: Boolean
        get() = fullDaySlot != null && slots.isNotEmpty() &&
            slots.all { availability?.availableSlots?.contains(it) == true }

    /** true si la franja [time] queda dentro de lo elegido (una franja, varias o el día completo). */
    fun isChosen(time: String): Boolean {
        val chosen = slotRange(slot) ?: return false
        val candidate = slotRange(time) ?: return false
        return candidate.first >= chosen.first && candidate.second <= chosen.second
    }

    /** Cuántas franjas cubre lo elegido. */
    val chosenCount: Int
        get() = slots.count { isChosen(it) }
}

/** Inicio y fin en minutos de «HH:MM-HH:MM»; null si no tiene esa forma. */
fun slotRange(slot: String?): Pair<Int, Int>? {
    val parts = slot?.split("-")?.takeIf { it.size == 2 } ?: return null
    fun minutes(text: String): Int? {
        val (hours, mins) = text.split(":").takeIf { it.size == 2 } ?: return null
        return (hours.toIntOrNull() ?: return null) * 60 + (mins.toIntOrNull() ?: return null)
    }
    val start = minutes(parts[0]) ?: return null
    val end = minutes(parts[1]) ?: return null
    return start to end
}

/** «08:00-12:00» a partir de minutos. */
private fun rangeText(start: Int, end: Int): String =
    String.format(java.util.Locale.US, "%02d:%02d-%02d:%02d", start / 60, start % 60, end / 60, end % 60)

/**
 * ViewModel de las reservas de zonas comunes (HU-050 a HU-055): la lista, la reserva nueva con las
 * reglas de cada zona (horario, aforo, anticipación, límite semanal y día de mantenimiento) y las
 * acciones de la administración y del residente sobre una reserva.
 */
class ReservationsViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(ReservationsUiState())
    val state: StateFlow<ReservationsUiState> = _state.asStateFlow()

    // Cada carga lleva un número: una respuesta vieja que llega tarde se descarta.
    private var listTicket = 0
    private var availabilityTicket = 0
    private var calendarTicket = 0

    private var started = false
    private var residentHandled = false

    // Mes que se está viendo en el calendario; 0 mientras nadie lo haya movido.
    private var calendarYear = 0
    private var calendarMonth = 0

    override fun postMessage(text: String, isError: Boolean) {
        _state.update { it.copy(message = text, messageIsError = isError) }
    }

    override fun setBusy(busy: Boolean) {
        _state.update { it.copy(busy = busy) }
    }

    fun dismissMessage() {
        _state.update { it.copy(message = "") }
    }

    /** La pantalla se abrió: carga la lista y las zonas. Solo la primera vez. */
    fun start() {
        if (started) return
        started = true
        refresh()
        loadAreas()
    }

    /**
     * La administración llegó desde el perfil de un apartamento con un residente ya elegido: se
     * busca por su id y queda como destinatario de la reserva. Solo la primera vez, para no pisar
     * un cambio que se haya hecho después.
     */
    fun useResident(residentId: Int) {
        if (residentHandled || !Session.isAdmin) return
        residentHandled = true
        viewModelScope.launch {
            val response = attempt("No se pudo cargar el residente") {
                api.getResidents(auth(), id = residentId)
            } ?: return@launch
            val found = response.body()?.residents.orEmpty().firstOrNull { it.id == residentId }
            if (found == null) showError("No se encontró al residente. Elígelo de nuevo.")
            else _state.update { it.copy(resident = found) }
        }
    }

    fun selectResident(resident: ResidentSummary?) {
        _state.update { it.copy(resident = resident) }
    }

    // --- Lista -----------------------------------------------------------------------------

    fun refresh() {
        viewModelScope.launch { loadReservations() }
    }

    private suspend fun loadReservations() {
        val ticket = ++listTicket
        _state.update { it.copy(loading = true) }
        val archived = _state.value.includeArchived
        val response = attempt("No se pudieron cargar las reservas") {
            api.getReservations(auth(), if (archived) "true" else null)
        }
        if (ticket != listTicket) return
        val received = response?.body()?.let { it.reservations.orEmpty() }
        _state.update { it.copy(loading = false, reservations = received ?: it.reservations) }
    }

    fun setIncludeArchived(include: Boolean) {
        if (_state.value.includeArchived == include) return
        _state.update { it.copy(includeArchived = include) }
        refresh()
    }

    // --- Reserva nueva: zona, fecha y franja ---------------------------------------------------

    private fun loadAreas() {
        viewModelScope.launch {
            val response = attempt("No se pudieron cargar las zonas comunes") {
                api.getCommonAreas(auth())
            } ?: return@launch
            val areas = response.body()?.areas.orEmpty()
            _state.update { old ->
                val keep = old.areaId?.takeIf { id -> areas.any { it.id == id } }
                old.copy(areas = areas, areaId = keep ?: areas.firstOrNull()?.id)
            }
            reloadCalendar()
        }
    }

    fun selectArea(areaId: Int) {
        if (_state.value.areaId == areaId) return
        _state.update {
            it.copy(
                areaId = areaId,
                slot = "",
                availability = null,
                fullDates = emptySet(),
                closedDates = emptySet()
            )
        }
        reloadAvailability()
        reloadCalendar()
    }

    fun selectDate(date: String) {
        _state.update { it.copy(date = date, slot = "") }
        reloadAvailability()
    }

    /**
     * Toca una franja. Si la zona deja reservar varias seguidas, una franja pegada a lo elegido lo
     * alarga (hasta el máximo de la zona); tocar la primera o la última de lo elegido la quita, y
     * tocar una que no está pegada empieza de nuevo con esa.
     */
    fun selectSlot(time: String) {
        val current = _state.value
        val tapped = slotRange(time) ?: return
        val chosen = slotRange(current.slot)
        val next = when {
            chosen == null || current.slot == current.fullDaySlot -> time
            tapped.first >= chosen.first && tapped.second <= chosen.second -> when {
                tapped == chosen -> ""
                tapped.first == chosen.first -> rangeText(tapped.second, chosen.second)
                tapped.second == chosen.second -> rangeText(chosen.first, tapped.first)
                else -> time
            }
            current.maxConsecutive > 1 && (tapped.first == chosen.second || tapped.second == chosen.first) -> {
                val start = minOf(chosen.first, tapped.first)
                val end = maxOf(chosen.second, tapped.second)
                val count = current.slots.count { slot ->
                    val range = slotRange(slot)
                    range != null && range.first >= start && range.second <= end
                }
                if (count > current.maxConsecutive) {
                    showError("En ${current.area?.name ?: "esta zona"} se pueden reservar hasta ${current.maxConsecutive} franjas seguidas.")
                    return
                }
                rangeText(start, end)
            }
            else -> time
        }
        _state.update { it.copy(slot = next) }
    }

    /** Elige el día completo (o lo quita, si ya estaba elegido). */
    fun toggleFullDay() {
        val current = _state.value
        val whole = current.fullDaySlot ?: return
        _state.update { it.copy(slot = if (it.slot == whole) "" else whole) }
    }

    /** El calendario cambió de mes: se piden los días ocupados y cerrados de ese mes. */
    fun showMonth(year: Int, month: Int) {
        if (year == calendarYear && month == calendarMonth) return
        calendarYear = year
        calendarMonth = month
        reloadCalendar()
    }

    private fun reloadAvailability() {
        val current = _state.value
        val areaId = current.areaId
        val ticket = ++availabilityTicket
        if (areaId == null || current.date.isBlank()) {
            _state.update { it.copy(availability = null, availabilityLoading = false) }
            return
        }
        _state.update { it.copy(availability = null, availabilityLoading = true) }
        viewModelScope.launch {
            val response = attempt("No se pudo consultar la disponibilidad") {
                api.getReservationAvailability(auth(), areaId, current.date)
            }
            if (ticket != availabilityTicket) return@launch
            _state.update { it.copy(availabilityLoading = false, availability = response?.body()) }
        }
    }

    private fun reloadCalendar() {
        val areaId = _state.value.areaId ?: return
        val today = colombiaToday()
        val year = if (calendarYear > 0) calendarYear else today.take(4).toIntOrNull() ?: return
        val month = if (calendarMonth > 0) calendarMonth else today.substring(5, 7).toIntOrNull() ?: return
        val ticket = ++calendarTicket
        viewModelScope.launch {
            val response = attempt("No se pudo consultar el calendario") {
                api.getReservationCalendar(auth(), areaId, year, month)
            } ?: return@launch
            if (ticket != calendarTicket) return@launch
            val body = response.body() ?: return@launch
            val prefix = monthPrefix(year, month)
            _state.update { old ->
                old.copy(
                    fullDates = old.fullDates.filterNot { it.startsWith(prefix) }.toSet() + body.blockedDates.orEmpty(),
                    closedDates = old.closedDates.filterNot { it.startsWith(prefix) }.toSet() + body.closedDates.orEmpty()
                )
            }
        }
    }

    /** Después de reservar o cancelar cambian las franjas libres: se vuelven a pedir. */
    private fun refreshFormData() {
        reloadAvailability()
        reloadCalendar()
    }

    // --- Crear, aprobar, rechazar, cancelar y escribir ----------------------------------------------

    /**
     * Crea la reserva con la zona, la fecha y la franja elegidas. [attendees] va solo si la zona
     * tiene aforo: el servidor lo compara con el máximo (HU-055).
     */
    fun create(attendees: Int?, note: String?, mediaUrl: String?, mediaType: String?) {
        val current = _state.value
        val area = current.area
        if (area == null || current.date.isBlank() || current.slot.isBlank()) {
            showError("Elige la zona, la fecha y el horario.")
            return
        }
        val resident = current.resident
        if (Session.isAdmin && resident == null) {
            showError("Selecciona el residente.")
            return
        }
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudo crear la reserva") {
                    api.createReservation(
                        auth(),
                        CreateReservationRequest(
                            commonAreaId = area.id,
                            date = current.date,
                            timeSlot = current.slot,
                            residentId = if (Session.isAdmin) resident?.id else null,
                            message = note,
                            mediaUrl = mediaUrl,
                            mediaType = mediaType,
                            attendees = attendees
                        )
                    )
                }
            }
            if (response == null) {
                // Lo más común: la franja se ocupó mientras se llenaba el formulario.
                reloadAvailability()
                return@launch
            }
            _state.update { it.copy(created = it.created + 1, date = "", slot = "", availability = null) }
            showSuccess(
                if (Session.isAdmin) "Reserva creada a nombre del residente."
                else "Reserva enviada. Queda pendiente de que la administración la apruebe."
            )
            reloadCalendar()
            loadReservations()
        }
    }

    /** La administración aprueba (`aprobada`) o rechaza (`rechazada`) una reserva. */
    fun decide(reservation: Reservation, status: String) {
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo actualizar la reserva") {
                    api.updateReservationStatus(auth(), reservation.id, UpdateReservationStatusRequest(status))
                }
            } ?: return@launch
            showSuccess(if (status == "aprobada") "Reserva aprobada." else "Reserva rechazada.")
            loadReservations()
            if (status != "aprobada") refreshFormData()
        }
    }

    /**
     * Cancela la reserva. El residente solo puede hasta el plazo de la zona (HU-053): si ya pasó,
     * el servidor lo explica. En los dos casos se vuelve a pedir la lista, porque el plazo corre.
     */
    fun cancel(reservation: Reservation) {
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudo cancelar la reserva") { api.cancelReservation(auth(), reservation.id) }
            }
            if (response != null) {
                showSuccess("Reserva cancelada.")
                refreshFormData()
            }
            loadReservations()
        }
    }

    fun sendMessage(reservation: Reservation, text: String?, mediaUrl: String?, mediaType: String?) {
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo enviar el mensaje") {
                    api.addReservationMessage(
                        auth(),
                        reservation.id,
                        AddReservationMessageRequest(text, mediaUrl, mediaType)
                    )
                }
            } ?: return@launch
            showSuccess("Mensaje enviado.")
            loadReservations()
        }
    }
}
