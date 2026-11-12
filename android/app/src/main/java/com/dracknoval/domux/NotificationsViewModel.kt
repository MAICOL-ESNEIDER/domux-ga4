package com.dracknoval.domux

import androidx.lifecycle.viewModelScope
import com.dracknoval.domux.data.NotificationItem
import com.dracknoval.domux.data.RetrofitClient
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Todo lo que la bandeja de notificaciones necesita para dibujarse (HU-064). */
data class NotificationsUiState(
    val items: List<NotificationItem> = emptyList(),
    val loading: Boolean = true,
    // true: solo las que faltan por leer.
    val unreadOnly: Boolean = false,
    val busy: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false
) {
    val unreadCount: Int get() = items.count { !it.isRead }
    val visible: List<NotificationItem> get() = if (unreadOnly) items.filter { !it.isRead } else items
}

/**
 * ViewModel de la bandeja de notificaciones (HU-064): carga las de quien tiene la sesión, marca
 * una o todas como leídas y deja el aviso en verde o en rojo según el resultado.
 */
class NotificationsViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(NotificationsUiState())
    val state: StateFlow<NotificationsUiState> = _state.asStateFlow()

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

    fun setUnreadOnly(value: Boolean) {
        _state.update { it.copy(unreadOnly = value) }
    }

    fun refresh() {
        viewModelScope.launch {
            _state.update { it.copy(loading = true) }
            val response = attempt("No se pudieron cargar las notificaciones") { api.getNotifications(auth()) }
            _state.update { current ->
                current.copy(loading = false, items = response?.body()?.notifications ?: current.items)
            }
        }
    }

    fun markRead(item: NotificationItem) {
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo marcar como leída") { api.markNotificationRead(auth(), item.id) }
            } ?: return@launch
            _state.update { current ->
                current.copy(items = current.items.map { if (it.id == item.id) it.copy(isRead = true) else it })
            }
        }
    }

    fun markAllRead() {
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudieron marcar como leídas") { api.markAllNotificationsRead(auth()) }
            } ?: return@launch
            _state.update { current -> current.copy(items = current.items.map { it.copy(isRead = true) }) }
            showSuccess(response.body()?.message ?: "Ya no tienes notificaciones sin leer.")
        }
    }
}
