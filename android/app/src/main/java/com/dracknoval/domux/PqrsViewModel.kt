package com.dracknoval.domux

import androidx.lifecycle.viewModelScope
import com.dracknoval.domux.data.AddPqrsMessageRequest
import com.dracknoval.domux.data.BatchRespondPqrsRequest
import com.dracknoval.domux.data.CreatePqrsRequest
import com.dracknoval.domux.data.Pqrs
import com.dracknoval.domux.data.RatePqrsRequest
import com.dracknoval.domux.data.ResidentSummary
import com.dracknoval.domux.data.RespondPqrsRequest
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Las PQRS sin categoría se cuentan como peticiones, igual que en el servidor. */
const val PQRS_DEFAULT_CATEGORY = "Petición"

/** Todo lo que la pantalla de PQRS necesita para dibujarse. */
data class PqrsUiState(
    val items: List<Pqrs> = emptyList(),
    val loading: Boolean = false,
    // El servidor busca en el asunto, el mensaje, el nombre del residente y el radicado (HU-072).
    val search: String = "",
    val statusFilter: String? = null,
    val categoryFilter: String? = null,
    // También las PQRS que la administración ya archivó. Nada se borra (ADR-013).
    val includeArchived: Boolean = false,
    // La administración llegó desde el perfil de un apartamento: la lista muestra solo a ese residente.
    val residentFilterId: Int? = null,
    // Residente a nombre de quien la administración radica una PQRS.
    val resident: ResidentSummary? = null,
    // Selección para responder varias PQRS de una misma categoría a la vez.
    val selectedIds: Set<Int> = emptySet(),
    val selectedCategory: String? = null,
    val busy: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false,
    // Suben cada vez que el servidor acepta una PQRS nueva o una respuesta por lotes.
    val created: Int = 0,
    val batchDone: Int = 0
) {
    /** Las PQRS que pasan el filtro de estado y el de categoría. */
    val visibleItems: List<Pqrs>
        get() = items.filter { pqrs ->
            (statusFilter == null || pqrs.status == statusFilter) &&
                (categoryFilter == null || (pqrs.category ?: PQRS_DEFAULT_CATEGORY) == categoryFilter)
        }

    /** Cuántas de las PQRS que se ven están seleccionadas. */
    val selectedVisibleCount: Int
        get() = visibleItems.count { it.id in selectedIds }
}

/**
 * ViewModel de las PQRS (HU-072 y HU-073): lista con búsqueda por radicado, filtros y semáforo del
 * plazo, radicación de una PQRS nueva, respuesta de la administración (una a una o por lotes) y
 * seguimiento del residente. Nada se borra: archivar solo las oculta de la bandeja (ADR-013).
 */
class PqrsViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(PqrsUiState())
    val state: StateFlow<PqrsUiState> = _state.asStateFlow()

    // Cada carga lleva un número: una respuesta vieja que llega tarde se descarta.
    private var listTicket = 0

    private var started = false

    override fun postMessage(text: String, isError: Boolean) {
        _state.update { it.copy(message = text, messageIsError = isError) }
    }

    override fun setBusy(busy: Boolean) {
        _state.update { it.copy(busy = busy) }
    }

    fun dismissMessage() {
        _state.update { it.copy(message = "") }
    }

    /**
     * La pantalla se abrió. Si la administración llegó desde el perfil de un residente
     * ([targetResidentId]), la lista queda filtrada a él y queda elegido como destinatario de la
     * PQRS nueva. Solo la primera vez, para no pisar lo que se haya cambiado después.
     */
    fun start(targetResidentId: Int?) {
        if (started) return
        started = true
        val target = targetResidentId.takeIf { Session.isAdmin }
        _state.update { it.copy(residentFilterId = target) }
        refresh()
        if (target != null) loadTargetResident(target)
    }

    private fun loadTargetResident(residentId: Int) {
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

    // --- Lista y filtros -----------------------------------------------------------------------

    fun refresh() {
        viewModelScope.launch { loadList() }
    }

    private suspend fun loadList() {
        val ticket = ++listTicket
        _state.update { it.copy(loading = true) }
        val current = _state.value
        val response = attempt("No se pudieron cargar las PQRS") {
            api.getPqrs(
                auth(),
                search = current.search.ifEmpty { null },
                residentId = current.residentFilterId,
                includeArchived = if (current.includeArchived) "true" else null
            )
        }
        if (ticket != listTicket) return
        val received = response?.body()?.let { it.pqrs.orEmpty() }
        _state.update { old ->
            if (received == null) {
                old.copy(loading = false)
            } else {
                // Lo seleccionado que ya no está en la lista (porque se respondió) deja de estarlo.
                val kept = old.selectedIds.intersect(received.map { it.id }.toSet())
                old.copy(
                    loading = false,
                    items = received,
                    selectedIds = kept,
                    selectedCategory = if (kept.isEmpty()) null else old.selectedCategory
                )
            }
        }
    }

    fun setSearch(text: String) {
        if (_state.value.search == text) return
        _state.update { it.copy(search = text, selectedIds = emptySet(), selectedCategory = null) }
        refresh()
    }

    fun setIncludeArchived(include: Boolean) {
        if (_state.value.includeArchived == include) return
        _state.update { it.copy(includeArchived = include, selectedIds = emptySet(), selectedCategory = null) }
        refresh()
    }

    fun setStatusFilter(status: String?) {
        _state.update { it.copy(statusFilter = status) }
    }

    fun setCategoryFilter(category: String?) {
        _state.update { it.copy(categoryFilter = category, selectedIds = emptySet(), selectedCategory = null) }
    }

    /** Vuelve a ver las PQRS de todos los residentes. */
    fun clearResidentFilter() {
        if (_state.value.residentFilterId == null) return
        _state.update { it.copy(residentFilterId = null, selectedIds = emptySet(), selectedCategory = null) }
        refresh()
    }

    // --- Selección para responder por lotes (una sola categoría a la vez) -----------------------

    fun toggleSelected(pqrs: Pqrs, checked: Boolean) {
        val category = pqrs.category ?: PQRS_DEFAULT_CATEGORY
        _state.update { old ->
            val ids: Set<Int> = if (!checked) {
                old.selectedIds - pqrs.id
            } else if (old.selectedCategory != category) {
                setOf(pqrs.id)
            } else {
                old.selectedIds + pqrs.id
            }
            old.copy(selectedIds = ids, selectedCategory = if (ids.isEmpty()) null else category)
        }
    }

    fun toggleCategory(category: String, group: List<Pqrs>, checked: Boolean) {
        val groupIds = group.map { it.id }.toSet()
        _state.update { old ->
            val ids: Set<Int> = if (!checked) {
                old.selectedIds - groupIds
            } else if (old.selectedCategory != category) {
                groupIds
            } else {
                old.selectedIds + groupIds
            }
            old.copy(selectedIds = ids, selectedCategory = if (ids.isEmpty()) null else category)
        }
    }

    // --- Radicar, responder, conversar y calificar ---------------------------------------------

    /** Radica una PQRS. El servidor le da su radicado, que se muestra en el aviso (HU-072). */
    fun create(
        subject: String,
        detail: String,
        category: String,
        incidentDate: String?,
        incidentTime: String?,
        mediaUrl: String?,
        mediaType: String?
    ) {
        val resident = _state.value.resident
        if (Session.isAdmin && resident == null) {
            showError("Selecciona el residente.")
            return
        }
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudo enviar la PQRS") {
                    api.createPqrs(
                        auth(),
                        CreatePqrsRequest(
                            subject,
                            detail,
                            category,
                            incidentDate,
                            incidentTime,
                            mediaUrl,
                            mediaType,
                            if (Session.isAdmin) resident?.id else null
                        )
                    )
                }
            } ?: return@launch
            val radicado = response.body()?.pqrs?.radicado
            _state.update { it.copy(created = it.created + 1) }
            showSuccess(
                if (radicado.isNullOrBlank()) "PQRS enviada exitosamente."
                else "PQRS enviada exitosamente. Radicado: $radicado."
            )
            loadList()
        }
    }

    /** La administración responde y cambia el estado (`abierta`, `en_proceso` o `resuelta`). */
    fun respond(pqrs: Pqrs, status: String, text: String, mediaUrl: String?, mediaType: String?) {
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo actualizar la PQRS") {
                    api.respondPqrs(auth(), pqrs.id, RespondPqrsRequest(status, text, mediaUrl, mediaType))
                }
            } ?: return@launch
            showSuccess("PQRS actualizada.")
            loadList()
        }
    }

    /** La administración responde a todas las PQRS seleccionadas (de una misma categoría). */
    fun respondBatch(status: String, text: String, mediaUrl: String?, mediaType: String?) {
        val current = _state.value
        val ids = current.visibleItems.filter { it.id in current.selectedIds }.map { it.id }
        if (ids.isEmpty()) {
            showError("Selecciona al menos una PQRS.")
            return
        }
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudieron responder las PQRS") {
                    api.respondPqrsBatch(
                        auth(),
                        BatchRespondPqrsRequest(ids, status, text, mediaUrl, mediaType)
                    )
                }
            } ?: return@launch
            _state.update {
                it.copy(selectedIds = emptySet(), selectedCategory = null, batchDone = it.batchDone + 1)
            }
            showSuccess(response.body()?.message ?: "PQRS actualizadas.")
            loadList()
        }
    }

    /** El residente sigue la conversación de su PQRS. */
    fun reply(pqrs: Pqrs, text: String?, mediaUrl: String?, mediaType: String?) {
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo enviar el mensaje") {
                    api.addPqrsMessage(auth(), pqrs.id, AddPqrsMessageRequest(text, mediaUrl, mediaType))
                }
            } ?: return@launch
            showSuccess("Mensaje enviado.")
            loadList()
        }
    }

    /** El residente califica la solución de una PQRS resuelta. */
    fun rate(pqrs: Pqrs, rating: Int, comment: String?) {
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo guardar la calificación") {
                    api.ratePqrs(auth(), pqrs.id, RatePqrsRequest(rating, comment))
                }
            } ?: return@launch
            showSuccess("Calificación guardada.")
            loadList()
        }
    }
}
