package com.dracknoval.domux

import androidx.lifecycle.viewModelScope
import com.dracknoval.domux.data.DeliverPackageRequest
import com.dracknoval.domux.data.PackageItem
import com.dracknoval.domux.data.PickupCodeData
import com.dracknoval.domux.data.PickupLookupRequest
import com.dracknoval.domux.data.RegisterPackageRequest
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.UpdatePackageStatusRequest
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Lo que el guardia va a entregar: el paquete y, si lo encontró escaneando, el texto del QR leído. */
data class DeliveryTarget(val item: PackageItem, val scannedCode: String? = null)

/** Todo lo que las pantallas de paquetes necesitan para dibujarse. */
data class PackagesUiState(
    val packages: List<PackageItem> = emptyList(),
    // null = todos; «pendiente», «por_llegar», «entregado» o «papelera».
    val statusFilter: String? = null,
    val search: String = "",
    val loading: Boolean = false,
    val busy: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false,
    // La entrega que el guardia está confirmando (con o sin código de entrega).
    val delivery: DeliveryTarget? = null,
    // El código de entrega que el residente acaba de generar; se muestra una sola vez (HU-048).
    val pickupCode: PickupCodeData? = null,
    val pickupCodePackage: PackageItem? = null
)

/**
 * ViewModel de los paquetes (HU-047, HU-048 y HU-049): lista con filtros, registro con
 * transportadora y guía, entrega con código y papelera. Un paquete nunca se borra del todo
 * (DEC-090): la papelera solo lo esconde y se puede restaurar.
 */
class PackagesViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(PackagesUiState())
    val state: StateFlow<PackagesUiState> = _state.asStateFlow()

    // Cada carga lleva un número: si llega una respuesta vieja después de una más nueva, se descarta.
    private var loadTicket = 0

    init {
        refresh()
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

    // --- Lista -------------------------------------------------------------------

    fun refresh() {
        viewModelScope.launch { loadPackages() }
    }

    private suspend fun loadPackages() {
        val ticket = ++loadTicket
        _state.update { it.copy(loading = true) }
        val current = _state.value
        val response = attempt("No se pudieron cargar los paquetes") {
            api.getPackages(auth(), current.statusFilter, current.search.trim().ifEmpty { null })
        }
        if (ticket != loadTicket) return
        _state.update { it.copy(loading = false, packages = response?.body()?.packages ?: it.packages) }
    }

    fun setStatusFilter(status: String?) {
        if (_state.value.statusFilter == status) return
        _state.update { it.copy(statusFilter = status) }
        refresh()
    }

    fun setSearch(text: String) {
        if (_state.value.search == text) return
        _state.update { it.copy(search = text) }
        refresh()
    }

    // --- Registro, estado y papelera ---------------------------------------------

    fun register(request: RegisterPackageRequest, onSuccess: () -> Unit) {
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudo registrar el paquete") { api.registerPackage(auth(), request) }
            } ?: return@launch
            showSuccess(response.body()?.message ?: "Paquete registrado.")
            onSuccess()
            loadPackages()
        }
    }

    fun changeStatus(item: PackageItem, status: String) {
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudo actualizar el estado") {
                    api.updatePackageStatus(auth(), item.id, UpdatePackageStatusRequest(status))
                }
            } ?: return@launch
            showSuccess(response.body()?.message ?: "Estado del paquete actualizado.")
            loadPackages()
        }
    }

    fun moveToTrash(item: PackageItem) {
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudo mover el paquete") { api.deletePackage(auth(), item.id) }
            } ?: return@launch
            showSuccess(response.body()?.message ?: "Paquete movido a la papelera.")
            loadPackages()
        }
    }

    fun restore(item: PackageItem) {
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudo restaurar el paquete") { api.restorePackage(auth(), item.id) }
            } ?: return@launch
            showSuccess(response.body()?.message ?: "Paquete restaurado.")
            loadPackages()
        }
    }

    // --- Entrega con código (HU-048) ---------------------------------------------

    /** El guardia abre la entrega de un paquete de la lista (sin código escaneado). */
    fun startDelivery(item: PackageItem) {
        _state.update { it.copy(delivery = DeliveryTarget(item), message = "") }
    }

    fun cancelDelivery() {
        _state.update { it.copy(delivery = null, message = "") }
    }

    /**
     * El guardia escaneó un código de entrega: el servidor dice a qué paquete pertenece y,
     * si el código sirve todavía, se abre la entrega de ese paquete con el QR ya leído.
     */
    fun lookupPickupCode(raw: String) {
        if (!raw.startsWith(PICKUP_QR_PREFIX) || raw.length <= PICKUP_QR_PREFIX.length) {
            showError("El código leído no es un código de entrega de paquetes de DOMUX.")
            return
        }
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudo consultar el código") {
                    api.lookupPickupCode(auth(), PickupLookupRequest(raw))
                }
            } ?: return@launch
            val item = response.body()?.packageItem
            if (item == null) {
                showError("El servidor no encontró el paquete de este código.")
                return@launch
            }
            _state.update { it.copy(delivery = DeliveryTarget(item, raw), message = "") }
        }
    }

    /** Registra la entrega. pickupCode es el PIN escrito o el QR leído; va vacío si recoge su dueño. */
    fun deliver(target: DeliveryTarget, receivedBy: String, pin: String) {
        viewModelScope.launch {
            val code = target.scannedCode ?: pin.trim().ifEmpty { null }
            val response = withBusy {
                attempt("No se pudo entregar el paquete") {
                    api.deliverPackage(
                        auth(), target.item.id, DeliverPackageRequest(receivedBy.trim(), code)
                    )
                }
            } ?: return@launch
            _state.update { it.copy(delivery = null) }
            showSuccess(response.body()?.message ?: "Paquete entregado a ${receivedBy.trim()}.")
            loadPackages()
        }
    }

    // --- Código de entrega del residente (HU-048) --------------------------------

    fun createPickupCode(item: PackageItem) {
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudo generar el código de entrega") { api.createPickupCode(auth(), item.id) }
            } ?: return@launch
            val body = response.body()
            val code = body?.pickupCode
            if (code == null) {
                showError("El servidor no devolvió el código. Inténtalo de nuevo.")
                return@launch
            }
            _state.update { it.copy(pickupCode = code, pickupCodePackage = body?.packageItem ?: item) }
            loadPackages()
        }
    }

    fun closePickupCode() {
        _state.update { it.copy(pickupCode = null, pickupCodePackage = null) }
    }

    companion object {
        /** Lo que lleva el QR del código de entrega antes del texto secreto (igual que en el servidor). */
        const val PICKUP_QR_PREFIX = "DOMUX-PKG:"
    }
}
