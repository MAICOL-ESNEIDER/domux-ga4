package com.dracknoval.domux

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.dracknoval.domux.data.ApartmentData
import com.dracknoval.domux.data.CreateApartmentRequest
import com.dracknoval.domux.data.CreateFloorRequest
import com.dracknoval.domux.data.ParkingSpotData
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.SaveParkingSpotRequest
import com.dracknoval.domux.data.SaveStorageRoomRequest
import com.dracknoval.domux.data.SaveTowerRequest
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.StorageRoomData
import com.dracknoval.domux.data.TowerData
import com.dracknoval.domux.data.UpdateApartmentRequest
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import retrofit2.Response

/** En qué página va una lista y cuántas hay. */
data class PageInfo(val page: Int = 1, val totalPages: Int = 1, val total: Int = 0)

/** Todo lo que la pantalla de estructura necesita para dibujarse. */
data class StructureUiState(
    val towers: List<TowerData> = emptyList(),
    val selectedTowerId: Int? = null,
    val apartments: List<ApartmentData> = emptyList(),
    val apartmentSearch: String = "",
    val apartmentPage: PageInfo = PageInfo(),
    val parkingSpots: List<ParkingSpotData> = emptyList(),
    // null = todos; «residente» o «visitante».
    val parkingKind: String? = null,
    val parkingPage: PageInfo = PageInfo(),
    val storageRooms: List<StorageRoomData> = emptyList(),
    val storagePage: PageInfo = PageInfo(),
    val loading: Boolean = false,
    val busy: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false
)

/**
 * ViewModel de la estructura de la unidad (UI-016): torres, apartamentos, parqueaderos y cuartos
 * útiles. Habla con el servidor y deja el resultado en [state]; la pantalla solo lo dibuja.
 * Quitar algo no lo borra: queda retirado (ADR-013).
 */
class StructureViewModel : ViewModel() {
    private val api = RetrofitClient.structureApi
    private val _state = MutableStateFlow(StructureUiState())
    val state: StateFlow<StructureUiState> = _state.asStateFlow()

    init {
        refreshAll()
    }

    private fun auth() = Session.bearer()

    fun dismissMessage() {
        _state.update { it.copy(message = "") }
    }

    private fun showError(text: String) {
        _state.update { it.copy(message = text, messageIsError = true) }
    }

    private fun showSuccess(text: String) {
        _state.update { it.copy(message = text, messageIsError = false) }
    }

    /** Hace la llamada; si falla (HTTP o red) deja el mensaje en pantalla y devuelve null. */
    private suspend fun <T> attempt(failure: String, request: suspend () -> Response<T>): Response<T>? {
        return try {
            val response = request()
            if (response.isSuccessful) {
                response
            } else {
                showError(mensajeDeError(response.code(), response.errorBody()?.string()))
                null
            }
        } catch (exception: CancellationException) {
            throw exception
        } catch (exception: Exception) {
            showError("$failure: ${exception.message}")
            null
        }
    }

    // --- Cargar las listas -------------------------------------------------------

    fun refreshAll() {
        viewModelScope.launch {
            _state.update { it.copy(loading = true) }
            reloadAll()
            _state.update { it.copy(loading = false) }
        }
    }

    private suspend fun reloadAll() {
        loadTowers()
        loadApartments()
        loadParking()
        loadStorage()
    }

    private suspend fun loadTowers() {
        val response = attempt("No se pudieron cargar las torres") { api.getTowers(auth()) } ?: return
        val towers = response.body()?.towers.orEmpty()
        _state.update { current ->
            // Se mantiene la torre elegida si todavía existe; si no, la primera.
            val selected = current.selectedTowerId?.takeIf { id -> towers.any { it.id == id } }
                ?: towers.firstOrNull()?.id
            current.copy(towers = towers, selectedTowerId = selected)
        }
    }

    private suspend fun loadApartments(page: Int = _state.value.apartmentPage.page) {
        val current = _state.value
        if (current.selectedTowerId == null) {
            _state.update { it.copy(apartments = emptyList(), apartmentPage = PageInfo()) }
            return
        }
        val response = attempt("No se pudieron cargar los apartamentos") {
            api.getApartments(
                auth = auth(),
                towerId = current.selectedTowerId,
                search = current.apartmentSearch.trim().ifEmpty { null },
                page = page
            )
        } ?: return
        val body = response.body()
        val totalPages = (body?.totalPages ?: 1).coerceAtLeast(1)
        if (page > totalPages) {
            // Se retiró lo último de esta página: se vuelve a la última que tiene datos.
            loadApartments(totalPages)
            return
        }
        _state.update {
            it.copy(
                apartments = body?.apartments.orEmpty(),
                apartmentPage = PageInfo(page, totalPages, body?.total ?: 0)
            )
        }
    }

    private suspend fun loadParking(page: Int = _state.value.parkingPage.page) {
        val current = _state.value
        val response = attempt("No se pudieron cargar los parqueaderos") {
            api.getParkingSpots(auth = auth(), type = current.parkingKind, page = page)
        } ?: return
        val body = response.body()
        val totalPages = (body?.totalPages ?: 1).coerceAtLeast(1)
        if (page > totalPages) {
            loadParking(totalPages)
            return
        }
        _state.update {
            it.copy(
                parkingSpots = body?.parkingSpots.orEmpty(),
                parkingPage = PageInfo(page, totalPages, body?.total ?: 0)
            )
        }
    }

    private suspend fun loadStorage(page: Int = _state.value.storagePage.page) {
        val response = attempt("No se pudieron cargar los cuartos útiles") {
            api.getStorageRooms(auth = auth(), page = page)
        } ?: return
        val body = response.body()
        val totalPages = (body?.totalPages ?: 1).coerceAtLeast(1)
        if (page > totalPages) {
            loadStorage(totalPages)
            return
        }
        _state.update {
            it.copy(
                storageRooms = body?.storageRooms.orEmpty(),
                storagePage = PageInfo(page, totalPages, body?.total ?: 0)
            )
        }
    }

    // --- Filtros y páginas -------------------------------------------------------

    fun selectTower(towerId: Int) {
        _state.update { it.copy(selectedTowerId = towerId, apartmentPage = PageInfo()) }
        viewModelScope.launch { loadApartments(1) }
    }

    fun searchApartments(text: String) {
        if (text == _state.value.apartmentSearch) return
        _state.update { it.copy(apartmentSearch = text, apartmentPage = PageInfo()) }
        viewModelScope.launch { loadApartments(1) }
    }

    fun goToApartmentPage(page: Int) {
        viewModelScope.launch { loadApartments(page) }
    }

    fun filterParking(kind: String?) {
        _state.update { it.copy(parkingKind = kind, parkingPage = PageInfo()) }
        viewModelScope.launch { loadParking(1) }
    }

    fun goToParkingPage(page: Int) {
        viewModelScope.launch { loadParking(page) }
    }

    fun goToStoragePage(page: Int) {
        viewModelScope.launch { loadStorage(page) }
    }

    // --- Cambios ---------------------------------------------------------------

    /**
     * Hace un cambio en el servidor. Si sale bien deja [success] como mensaje, vuelve a cargar
     * las listas (los conteos cambian) y avisa con [onSuccess]; si falla, el mensaje de error
     * queda en [state] y la ventana de quien llamó sigue abierta para corregir el dato.
     */
    private fun <T> change(
        failure: String,
        success: String,
        onSuccess: () -> Unit,
        request: suspend () -> Response<T>
    ) {
        viewModelScope.launch {
            _state.update { it.copy(busy = true, message = "") }
            val response = attempt(failure, request = request)
            if (response != null) {
                showSuccess(success)
                // La ventana se cierra enseguida; las listas se recargan mientras tanto.
                onSuccess()
                reloadAll()
            }
            _state.update { it.copy(busy = false) }
        }
    }

    fun createTower(name: String, floors: Int, onSuccess: () -> Unit) =
        change("No se pudo guardar la torre", "Torre guardada.", onSuccess) {
            api.createTower(auth(), SaveTowerRequest(name, floors))
        }

    fun updateTower(id: Int, name: String, floors: Int, onSuccess: () -> Unit) =
        change("No se pudo guardar la torre", "Torre guardada.", onSuccess) {
            api.updateTower(auth(), id, SaveTowerRequest(name, floors))
        }

    fun retireTower(id: Int) =
        change("No se pudo retirar la torre", "Torre retirada.", {}) {
            api.retireTower(auth(), id)
        }

    fun createApartment(towerId: Int, code: String, floor: Int?, onSuccess: () -> Unit) =
        change("No se pudo guardar el apartamento", "Apartamento guardado.", onSuccess) {
            api.createApartment(auth(), CreateApartmentRequest(towerId, code, floor))
        }

    fun updateApartment(id: Int, code: String, floor: Int, onSuccess: () -> Unit) =
        change("No se pudo guardar el apartamento", "Apartamento guardado.", onSuccess) {
            api.updateApartment(auth(), id, UpdateApartmentRequest(code, floor))
        }

    fun retireApartment(id: Int) =
        change("No se pudo retirar el apartamento", "Apartamento retirado.", {}) {
            api.retireApartment(auth(), id)
        }

    /** Crea los apartamentos de un piso de una vez (HU-023). Todo o nada: si uno ya existe, no crea ninguno. */
    fun createFloor(towerId: Int, floor: Int, count: Int, onSuccess: () -> Unit) {
        viewModelScope.launch {
            _state.update { it.copy(busy = true, message = "") }
            val response = attempt("No se pudo crear el piso") {
                api.createFloor(auth(), CreateFloorRequest(towerId, floor, count))
            }
            if (response != null) {
                showSuccess(response.body()?.message ?: "Apartamentos del piso guardados.")
                onSuccess()
                reloadAll()
            }
            _state.update { it.copy(busy = false) }
        }
    }

    fun createParking(code: String, type: String, location: String, apartmentId: Int?, onSuccess: () -> Unit) =
        change("No se pudo guardar el parqueadero", "Parqueadero guardado.", onSuccess) {
            api.createParkingSpot(auth(), SaveParkingSpotRequest(code, type, location, apartmentId))
        }

    fun updateParking(id: Int, code: String, type: String, location: String, apartmentId: Int?, onSuccess: () -> Unit) =
        change("No se pudo guardar el parqueadero", "Parqueadero guardado.", onSuccess) {
            api.updateParkingSpot(auth(), id, SaveParkingSpotRequest(code, type, location, apartmentId))
        }

    fun retireParking(id: Int) =
        change("No se pudo retirar el parqueadero", "Parqueadero retirado.", {}) {
            api.retireParkingSpot(auth(), id)
        }

    fun createStorage(code: String, apartmentId: Int?, onSuccess: () -> Unit) =
        change("No se pudo guardar el cuarto útil", "Cuarto útil guardado.", onSuccess) {
            api.createStorageRoom(auth(), SaveStorageRoomRequest(code, apartmentId))
        }

    fun updateStorage(id: Int, code: String, apartmentId: Int?, onSuccess: () -> Unit) =
        change("No se pudo guardar el cuarto útil", "Cuarto útil guardado.", onSuccess) {
            api.updateStorageRoom(auth(), id, SaveStorageRoomRequest(code, apartmentId))
        }

    fun retireStorage(id: Int) =
        change("No se pudo retirar el cuarto útil", "Cuarto útil retirado.", {}) {
            api.retireStorageRoom(auth(), id)
        }
}
