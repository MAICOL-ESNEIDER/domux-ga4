package com.dracknoval.domux

import androidx.lifecycle.viewModelScope
import com.dracknoval.domux.data.NotificationItem
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Todo lo que el inicio necesita para dibujarse (HU-002 y HU-065). */
data class HomeUiState(
    val notifications: List<NotificationItem> = emptyList(),
    // Comunicados vigentes que el residente aún no ha abierto (HU-059).
    val unreadAnnouncements: Int = 0,
    // Aviso pequeño al final del inicio si no se pudo revisar si hay notificaciones nuevas.
    val syncProblem: String? = null,
    // true si el celular no deja mostrar avisos (Android 13 o más pide permiso).
    val permissionMissing: Boolean = false,
    val showNotifications: Boolean = false,
    val busy: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false
) {
    val unreadCount: Int get() = notifications.count { !it.isRead }
}

/**
 * ViewModel del inicio (HU-002 y HU-065): cada vez que la pantalla lo pide revisa las
 * notificaciones y los comunicados sin leer, y devuelve las notificaciones que llegaron desde la
 * vez anterior para que el celular las muestre como aviso.
 */
class HomeViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(HomeUiState())
    val state: StateFlow<HomeUiState> = _state.asStateFlow()

    // Las notificaciones que ya se vieron, de quien tiene la sesión ahora (en portería cambia con el
    // PIN del guardia). null mientras no se ha hecho la primera revisión: esas no se avisan.
    private var knownIds: Set<Int>? = null
    private var knownFor: Int? = null

    override fun postMessage(text: String, isError: Boolean) {
        _state.update { it.copy(message = text, messageIsError = isError) }
    }

    override fun setBusy(busy: Boolean) {
        _state.update { it.copy(busy = busy) }
    }

    fun dismissMessage() {
        _state.update { it.copy(message = "") }
    }

    fun openNotifications() {
        _state.update { it.copy(showNotifications = true, message = "") }
    }

    fun closeNotifications() {
        _state.update { it.copy(showNotifications = false) }
    }

    fun setPermissionMissing(missing: Boolean) {
        _state.update { it.copy(permissionMissing = missing) }
    }

    /**
     * Revisa notificaciones y comunicados. Devuelve las notificaciones sin leer que no estaban en la
     * revisión anterior. Si falla no molesta con avisos grandes: deja una línea al final del inicio y
     * se vuelve a intentar en la próxima vuelta.
     */
    suspend fun refresh(): List<NotificationItem> {
        if (knownFor != Session.userId) {
            knownIds = null
            knownFor = Session.userId
        }
        var fresh = emptyList<NotificationItem>()
        try {
            val response = api.getNotifications(auth())
            if (response.isSuccessful) {
                val items = response.body()?.notifications.orEmpty()
                val previous = knownIds
                if (previous != null) {
                    fresh = items.filter { !it.isRead && it.id !in previous }.distinctBy { it.id }
                }
                knownIds = previous.orEmpty() + items.map { it.id }
                _state.update { it.copy(notifications = items, syncProblem = null) }
            } else {
                _state.update { it.copy(syncProblem = "No se pudo revisar si tienes notificaciones nuevas.") }
            }
        } catch (exception: CancellationException) {
            throw exception
        } catch (_: Exception) {
            _state.update { it.copy(syncProblem = "Sin conexión: las notificaciones se revisarán cuando vuelva el internet.") }
        }
        if (Session.isResident) {
            // Con una sola fila basta: el servidor siempre responde cuántos comunicados le faltan por leer.
            try {
                val announcements = api.getAnnouncements(auth(), pageSize = 1)
                if (announcements.isSuccessful) {
                    _state.update { it.copy(unreadAnnouncements = announcements.body()?.unreadCount ?: 0) }
                }
            } catch (exception: CancellationException) {
                throw exception
            } catch (_: Exception) {
                // Si falla se conserva el número anterior y se vuelve a intentar en la próxima vuelta.
            }
        }
        return fresh
    }

    fun markRead(item: NotificationItem) {
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo marcar como leída") { api.markNotificationRead(auth(), item.id) }
            } ?: return@launch
            _state.update { current ->
                current.copy(notifications = current.notifications.map { if (it.id == item.id) it.copy(isRead = true) else it })
            }
        }
    }
}
