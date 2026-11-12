package com.dracknoval.domux

import androidx.lifecycle.viewModelScope
import com.dracknoval.domux.data.ParkingSpotData
import com.dracknoval.domux.data.RegisterVehicleEntryRequest
import com.dracknoval.domux.data.ResidentVehicleItem
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.VehicleMovementRequest
import com.dracknoval.domux.data.Visit
import com.dracknoval.domux.data.VisitorBoardResponse
import com.dracknoval.domux.data.VisitorVehicleEntryData
import com.dracknoval.domux.data.detalleDeError
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * El parqueadero elegido ya estaba ocupado, o ya no queda ninguno libre (HU-039). Guarda la
 * solicitud original para repetirla con el parqueadero sugerido o sin parqueadero.
 */
data class SpotConflict(
    val message: String,
    val suggestedSpot: ParkingSpotData?,
    val request: RegisterVehicleEntryRequest
)

/** Todo lo que la pantalla de Vehículos necesita para dibujarse. */
data class VehiclesUiState(
    // Parqueaderos de visitantes libres y ocupados (HU-037).
    val board: VisitorBoardResponse? = null,
    val boardLoading: Boolean = false,
    // Visitas autorizadas que todavía no han salido: el vehículo se registra a nombre de una (RN-010).
    val candidates: List<Visit> = emptyList(),
    val candidatesLoading: Boolean = false,
    // Vehículos de residentes encontrados por placa (HU-040).
    val residentVehicles: List<ResidentVehicleItem> = emptyList(),
    val residentSearched: Boolean = false,
    val residentLoading: Boolean = false,
    // Historial de entradas de vehículos visitantes (HU-041).
    val entries: List<VisitorVehicleEntryData> = emptyList(),
    val entriesPage: PageInfo = PageInfo(),
    val entriesLoading: Boolean = false,
    val entriesLoadingMore: Boolean = false,
    val entriesInsideOnly: Boolean = false,
    val entriesOverdueOnly: Boolean = false,
    val entriesPlate: String = "",
    val busy: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false,
    val spotConflict: SpotConflict? = null,
    // Sube cada vez que se registra una entrada; el formulario lo mira para limpiarse.
    val entryRegistrations: Int = 0
)

/**
 * ViewModel de la portería vehicular (HU-035 a HU-041): tablero de parqueaderos de visitantes,
 * entrada y salida de sus vehículos, movimientos de vehículos de residentes e historial.
 * Nada se borra: cada entrada y cada movimiento quedan guardados (ADR-013).
 */
class VehiclesViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(VehiclesUiState())
    val state: StateFlow<VehiclesUiState> = _state.asStateFlow()

    // Cada carga lleva un número: una respuesta vieja que llega tarde se descarta.
    private var entriesTicket = 0
    private var candidatesTicket = 0

    init {
        refreshBoard()
        refreshEntries()
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

    // --- Tablero de parqueaderos (HU-037) ----------------------------------------

    fun refreshBoard() {
        viewModelScope.launch { loadBoard() }
    }

    private suspend fun loadBoard() {
        _state.update { it.copy(boardLoading = true) }
        val response = attempt("No se pudieron cargar los parqueaderos") { api.getVisitorSpots(auth()) }
        _state.update { it.copy(boardLoading = false, board = response?.body() ?: it.board) }
    }

    // --- Visitas a las que se les puede registrar un vehículo ---------------------

    fun loadCandidates(search: String) {
        viewModelScope.launch {
            val ticket = ++candidatesTicket
            _state.update { it.copy(candidatesLoading = true) }
            val response = attempt("No se pudieron cargar las visitas autorizadas") {
                api.getVisits(
                    auth(),
                    search = search.trim().ifEmpty { null },
                    status = "aprobada",
                    pageSize = 100
                )
            }
            if (ticket != candidatesTicket) return@launch
            // Una visita que ya registró su salida no puede traer vehículo (el servidor lo rechaza).
            val visits = response?.body()?.visits.orEmpty().filter { it.exitedAt == null }
            _state.update {
                it.copy(
                    candidatesLoading = false,
                    candidates = if (response == null) it.candidates else visits
                )
            }
        }
    }

    // --- Entrada y salida de vehículos visitantes (HU-035, HU-036, HU-038 y HU-039) ---

    /**
     * Registra la entrada. Sin parqueadero elegido el servidor toma el primero libre. Si el elegido
     * ya estaba ocupado, o no queda ninguno libre, el error trae lo que se puede hacer y se
     * guarda en [VehiclesUiState.spotConflict] para que el guardia decida.
     */
    fun registerEntry(request: RegisterVehicleEntryRequest) {
        viewModelScope.launch {
            val response = withBusy {
                callRaw("No se pudo registrar la entrada del vehículo") {
                    api.registerVehicleEntry(auth(), request)
                }
            } ?: return@launch
            if (response.isSuccessful) {
                _state.update { it.copy(spotConflict = null, entryRegistrations = it.entryRegistrations + 1) }
                showSuccess(response.body()?.message ?: "Entrada registrada.")
                loadBoard()
                loadEntries(1)
                return@launch
            }
            val errorText = response.errorBody()?.string()
            val detail = detalleDeError(errorText)
            if (response.code() == 409 && detail != null && detail.noFreeSpots != null) {
                val conflict = SpotConflict(
                    message = detail.error ?: mensajeDeError(409, errorText),
                    suggestedSpot = detail.suggestedSpot,
                    request = request
                )
                _state.update { it.copy(spotConflict = conflict) }
                // El tablero que se estaba viendo ya no es el real.
                loadBoard()
            } else {
                showError(mensajeDeError(response.code(), errorText))
            }
        }
    }

    /** Repite el registro con el parqueadero que el servidor sugirió. */
    fun retryWithSuggestedSpot() {
        val conflict = _state.value.spotConflict ?: return
        val spot = conflict.suggestedSpot ?: return
        registerEntry(conflict.request.copy(spotId = spot.id, withoutSpot = null))
    }

    /** Repite el registro sin parqueadero, algo que el guardia decide cuando no queda ninguno libre. */
    fun retryWithoutSpot() {
        val conflict = _state.value.spotConflict ?: return
        registerEntry(conflict.request.copy(spotId = null, withoutSpot = true))
    }

    fun dismissConflict() {
        _state.update { it.copy(spotConflict = null) }
    }

    fun registerExit(entry: VisitorVehicleEntryData) {
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudo registrar la salida del vehículo") {
                    api.registerVehicleExit(auth(), entry.id)
                }
            } ?: return@launch
            showSuccess(response.body()?.message ?: "Salida registrada.")
            loadBoard()
            loadEntries(1)
        }
    }

    // --- Historial de entradas (HU-041) ---------------------------------------------

    fun refreshEntries() {
        viewModelScope.launch { loadEntries(1) }
    }

    private suspend fun loadEntries(page: Int, append: Boolean = false) {
        val ticket = ++entriesTicket
        _state.update { it.copy(entriesLoading = !append, entriesLoadingMore = append) }
        val current = _state.value
        val response = attempt("No se pudo cargar el historial de vehículos") {
            api.getVehicleEntries(
                auth(),
                inside = if (current.entriesInsideOnly) "true" else null,
                overdue = if (current.entriesOverdueOnly) "true" else null,
                plate = current.entriesPlate.trim().ifEmpty { null },
                page = page
            )
        }
        if (ticket != entriesTicket) return
        val body = response?.body()
        _state.update { old ->
            if (body == null) {
                old.copy(entriesLoading = false, entriesLoadingMore = false)
            } else {
                val received = body.vehicleEntries.orEmpty()
                old.copy(
                    entriesLoading = false,
                    entriesLoadingMore = false,
                    entries = if (append) (old.entries + received).distinctBy { it.id } else received,
                    entriesPage = PageInfo(body.page, body.totalPages.coerceAtLeast(1), body.total)
                )
            }
        }
    }

    fun loadMoreEntries() {
        val current = _state.value
        if (current.entriesLoading || current.entriesLoadingMore ||
            current.entriesPage.page >= current.entriesPage.totalPages
        ) {
            return
        }
        viewModelScope.launch { loadEntries(current.entriesPage.page + 1, append = true) }
    }

    /** Todos, solo los que siguen adentro, o solo los que pasaron el tiempo máximo (HU-041). */
    fun setEntriesFilter(insideOnly: Boolean, overdueOnly: Boolean) {
        val current = _state.value
        if (current.entriesInsideOnly == insideOnly && current.entriesOverdueOnly == overdueOnly) return
        _state.update { it.copy(entriesInsideOnly = insideOnly, entriesOverdueOnly = overdueOnly) }
        refreshEntries()
    }

    fun setEntriesPlate(text: String) {
        if (_state.value.entriesPlate == text) return
        _state.update { it.copy(entriesPlate = text) }
        refreshEntries()
    }

    // --- Vehículos de residentes (HU-040) -----------------------------------------

    fun searchResidentVehicles(text: String) {
        if (text.trim().length < MIN_PLATE_SEARCH) {
            showError("Escribe al menos $MIN_PLATE_SEARCH caracteres de la placa.")
            return
        }
        viewModelScope.launch {
            _state.update { it.copy(residentLoading = true) }
            val response = attempt("No se pudieron buscar los vehículos") {
                api.searchResidentVehicles(auth(), text.trim())
            }
            _state.update {
                it.copy(
                    residentLoading = false,
                    residentSearched = response != null || it.residentSearched,
                    residentVehicles = response?.body()?.vehicles ?: it.residentVehicles
                )
            }
        }
    }

    fun registerResidentMovement(vehicle: ResidentVehicleItem, type: String) {
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudo registrar el movimiento") {
                    api.registerResidentMovement(auth(), vehicle.plate, VehicleMovementRequest(type))
                }
            } ?: return@launch
            val body = response.body()
            val message = body?.message ?: "Movimiento registrado."
            // Si repite el movimiento anterior se guarda igual, pero el guardia debe enterarse.
            showSuccess(body?.warning?.let { "$message Ojo: $it" } ?: message)
            val updated = body?.vehicle
            if (updated != null) {
                _state.update { old ->
                    old.copy(residentVehicles = old.residentVehicles.map { if (it.id == updated.id) updated else it })
                }
            }
        }
    }

    companion object {
        /** Mínimo de caracteres para buscar una placa (igual que en el servidor). */
        const val MIN_PLATE_SEARCH = 2
    }
}
