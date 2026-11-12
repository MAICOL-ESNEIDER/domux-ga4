package com.dracknoval.domux

import androidx.lifecycle.viewModelScope
import com.dracknoval.domux.data.CreateVisitQrPassRequest
import com.dracknoval.domux.data.QrVisitorEntryRequest
import com.dracknoval.domux.data.QrVisitorExitRequest
import com.dracknoval.domux.data.RegisterVisitRequest
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.Visit
import com.dracknoval.domux.data.VisitDecisionRequest
import com.dracknoval.domux.data.VisitEntryRequest
import com.dracknoval.domux.data.VisitExitRequest
import com.dracknoval.domux.data.VisitQrInspectionResponse
import com.dracknoval.domux.data.VisitQrPass
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Todo lo que las pantallas de visitas y de códigos QR necesitan para dibujarse. */
data class VisitsUiState(
    val visits: List<Visit> = emptyList(),
    val page: PageInfo = PageInfo(),
    // null = todas; «pendiente», «aprobada» o «rechazada».
    val statusFilter: String? = null,
    // Solo las que entraron y todavía no registran salida (HU-032).
    val insideOnly: Boolean = false,
    val search: String = "",
    // Fechas del historial en formato AAAA-MM-DD; vacías = sin límite (HU-030).
    val dateFrom: String = "",
    val dateTo: String = "",
    val loading: Boolean = false,
    val loadingMore: Boolean = false,
    val busy: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false,
    // Las visitas que siguen adentro; el guardia que entra al turno las ve al cambiar de guardia (HU-032).
    val insideAlert: List<Visit>? = null,
    // Códigos QR del residente (HU-027 y HU-033).
    val qrPasses: List<VisitQrPass> = emptyList(),
    val activeQrPass: VisitQrPass? = null,
    // El QR que el guardia escaneó y lo que el servidor dijo de él.
    val scannedToken: String? = null,
    val qrInspection: VisitQrInspectionResponse? = null
)

/**
 * ViewModel de las visitas (HU-027 y HU-030 a HU-033): historial con filtros y páginas,
 * entrada y salida con estadía prevista, alerta de visitas sin salida, y los códigos QR
 * (el residente los crea y comparte; el guardia los escanea).
 */
class VisitsViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(VisitsUiState())
    val state: StateFlow<VisitsUiState> = _state.asStateFlow()

    // Cada carga lleva un número: una respuesta vieja que llega tarde se descarta.
    private var loadTicket = 0

    init {
        refresh()
        if (Session.isResident) {
            viewModelScope.launch { loadQrPasses() }
        }
    }

    override fun postMessage(text: String, isError: Boolean) {
        _state.update { it.copy(message = text, messageIsError = isError) }
    }

    override fun setBusy(busy: Boolean) {
        _state.update { it.copy(busy = busy) }
    }

    fun dismissMessage() {
        _state.update { it.copy(message = "") }
    }

    // --- Historial con filtros (HU-030 y HU-032) ---------------------------------

    fun refresh() {
        viewModelScope.launch { loadVisits(1) }
    }

    private suspend fun loadVisits(page: Int, append: Boolean = false) {
        val ticket = ++loadTicket
        _state.update { it.copy(loading = !append, loadingMore = append) }
        val current = _state.value
        val response = attempt("No se pudieron cargar las visitas") {
            api.getVisits(
                auth(),
                search = current.search.trim().ifEmpty { null },
                status = current.statusFilter,
                dateFrom = current.dateFrom.ifBlank { null },
                dateTo = current.dateTo.ifBlank { null },
                inside = if (current.insideOnly) "true" else null,
                page = page
            )
        }
        if (ticket != loadTicket) return
        val body = response?.body()
        _state.update { old ->
            if (body == null) {
                old.copy(loading = false, loadingMore = false)
            } else {
                val received = body.visits.orEmpty()
                old.copy(
                    loading = false,
                    loadingMore = false,
                    // Si entró una visita nueva mientras se pasaba de página, no se repite ninguna.
                    visits = if (append) (old.visits + received).distinctBy { it.id } else received,
                    page = PageInfo(body.page, body.totalPages.coerceAtLeast(1), body.total)
                )
            }
        }
    }

    fun loadMore() {
        val current = _state.value
        if (current.loading || current.loadingMore || current.page.page >= current.page.totalPages) return
        viewModelScope.launch { loadVisits(current.page.page + 1, append = true) }
    }

    fun setStatusFilter(status: String?) {
        if (_state.value.statusFilter == status) return
        _state.update { it.copy(statusFilter = status) }
        refresh()
    }

    fun setInsideOnly(value: Boolean) {
        if (_state.value.insideOnly == value) return
        _state.update { it.copy(insideOnly = value) }
        refresh()
    }

    fun setSearch(text: String) {
        if (_state.value.search == text) return
        _state.update { it.copy(search = text) }
        refresh()
    }

    fun setDates(from: String, to: String) {
        if (_state.value.dateFrom == from && _state.value.dateTo == to) return
        _state.update { it.copy(dateFrom = from, dateTo = to) }
        refresh()
    }

    fun clearFilters() {
        _state.update {
            it.copy(statusFilter = null, insideOnly = false, search = "", dateFrom = "", dateTo = "")
        }
        refresh()
    }

    /** Después de cambiar de guardia: avisa de las visitas que entraron y siguen adentro (HU-032). */
    fun checkVisitsInside() {
        viewModelScope.launch {
            val response = attempt("No se pudieron consultar las visitas que siguen adentro") {
                api.getVisits(auth(), inside = "true", pageSize = 200)
            } ?: return@launch
            val inside = response.body()?.visits.orEmpty()
            _state.update { it.copy(insideAlert = inside.takeIf { list -> list.isNotEmpty() }) }
        }
    }

    fun dismissInsideAlert() {
        _state.update { it.copy(insideAlert = null) }
    }

    // --- Registro, autorización, entrada y salida --------------------------------

    fun registerVisit(request: RegisterVisitRequest, onSuccess: () -> Unit) {
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo registrar la visita") { api.registerVisit(auth(), request) }
            } ?: return@launch
            showSuccess("Registro enviado. El residente recibirá una solicitud para autorizar el ingreso.")
            onSuccess()
            loadVisits(1)
        }
    }

    fun decide(visit: Visit, decision: String) {
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo responder la solicitud") {
                    api.decideVisit(auth(), visit.id, VisitDecisionRequest(decision))
                }
            } ?: return@launch
            showSuccess(if (decision == "aprobada") "Acceso autorizado." else "Acceso rechazado.")
            loadVisits(1)
        }
    }

    fun authorizeByCall(visit: Visit) {
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo registrar la autorización") { api.authorizeVisitByCall(auth(), visit.id) }
            } ?: return@launch
            showSuccess("Autorización por llamada registrada.")
            loadVisits(1)
        }
    }

    /** Registra la entrada; stayMinutes es la estadía prevista que el guardia anotó (HU-031), o null. */
    fun registerEntry(visit: Visit, stayMinutes: Int?, onSuccess: () -> Unit) {
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo registrar la entrada") {
                    api.registerVisitEntry(auth(), visit.id, VisitEntryRequest(stayMinutes))
                }
            } ?: return@launch
            showSuccess("Entrada registrada.")
            onSuccess()
            loadVisits(1)
        }
    }

    fun registerExit(visit: Visit, returningToday: Boolean, onSuccess: () -> Unit) {
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo registrar la salida") {
                    api.registerVisitExit(auth(), visit.id, VisitExitRequest(returningToday))
                }
            } ?: return@launch
            showSuccess(
                if (returningToday) "Salida registrada; puede regresar hoy." else "Salida definitiva registrada."
            )
            onSuccess()
            loadVisits(1)
        }
    }

    // --- Códigos QR del residente (HU-027 y HU-033) ------------------------------

    private suspend fun loadQrPasses() {
        val response = attempt("No se pudieron cargar los códigos QR") { api.getVisitQrPasses(auth()) } ?: return
        val passes = response.body()?.qrPasses.orEmpty()
        _state.update { old ->
            // Si el QR que se está mostrando sigue en la lista, se muestra su versión nueva.
            old.copy(qrPasses = passes, activeQrPass = passes.firstOrNull { it.id == old.activeQrPass?.id })
        }
    }

    fun createQrPass(request: CreateVisitQrPassRequest, onSuccess: () -> Unit) {
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudo crear el QR") { api.createVisitQrPass(auth(), request) }
            } ?: return@launch
            val created = response.body()?.qrPass
            _state.update { it.copy(activeQrPass = created) }
            showSuccess("Código QR creado.")
            onSuccess()
            loadQrPasses()
            // La lista no trae siempre el mismo objeto; el recién creado sigue siendo el que se muestra.
            if (created != null) _state.update { it.copy(activeQrPass = created) }
        }
    }

    fun selectQrPass(pass: VisitQrPass?) {
        _state.update { it.copy(activeQrPass = pass) }
    }

    fun revokeQrPass(pass: VisitQrPass) {
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo revocar el QR") { api.revokeVisitQrPass(auth(), pass.id) }
            } ?: return@launch
            showSuccess("QR revocado.")
            loadQrPasses()
        }
    }

    // --- Ingreso y salida por QR en la portería ----------------------------------

    /** El guardia escaneó un QR de visitas; el texto empieza por «DOMUX:» y sigue el código. */
    fun onQrScanned(raw: String) {
        val token = raw.removePrefix(QR_PREFIX).takeIf { raw.startsWith(QR_PREFIX) && it.isNotBlank() }
        if (token == null) {
            showError("El código leído no es un QR válido de DOMUX.")
            return
        }
        viewModelScope.launch { inspectQr(token) }
    }

    private suspend fun inspectQr(token: String) {
        val response = attempt("No se pudo consultar el QR") { api.inspectVisitQr(auth(), token) } ?: return
        _state.update { it.copy(scannedToken = token, qrInspection = response.body()) }
    }

    fun clearScannedQr() {
        _state.update { it.copy(scannedToken = null, qrInspection = null) }
    }

    /** Entrada de una persona nueva por el QR escaneado (HU-033: el nombre puede venir de la lista del QR). */
    fun enterQrVisitor(name: String, stayMinutes: Int?, onSuccess: () -> Unit) {
        val token = _state.value.scannedToken ?: return
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo registrar el ingreso QR") {
                    api.enterVisitQr(
                        auth(), token, QrVisitorEntryRequest(visitorName = name.trim(), expectedStayMinutes = stayMinutes)
                    )
                }
            } ?: return@launch
            showSuccess("Entrada por QR registrada.")
            onSuccess()
            inspectQr(token)
            loadVisits(1)
        }
    }

    /** Vincula una visita ya registrada al QR y la hace entrar, o registra el reingreso de quien salió. */
    fun enterQrExistingVisit(visit: Visit, successMessage: String) {
        val token = _state.value.scannedToken ?: return
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo registrar el ingreso por QR") {
                    api.enterVisitQr(auth(), token, QrVisitorEntryRequest(visitId = visit.id))
                }
            } ?: return@launch
            showSuccess(successMessage)
            inspectQr(token)
            loadVisits(1)
        }
    }

    fun exitQrVisit(visit: Visit, returningToday: Boolean, onSuccess: () -> Unit) {
        val token = _state.value.scannedToken ?: return
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo registrar la salida QR") {
                    api.exitVisitQr(auth(), token, QrVisitorExitRequest(visit.id, returningToday))
                }
            } ?: return@launch
            showSuccess(
                if (returningToday) "Salida registrada; puede regresar hoy." else "Salida definitiva registrada."
            )
            onSuccess()
            inspectQr(token)
            loadVisits(1)
        }
    }

    companion object {
        /** Lo que lleva el QR de visitas antes del código (igual que en el servidor). */
        const val QR_PREFIX = "DOMUX:"
    }
}
