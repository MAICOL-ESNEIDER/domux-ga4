package com.dracknoval.domux

import android.content.Context
import androidx.lifecycle.viewModelScope
import com.dracknoval.domux.data.LoginRequest
import com.dracknoval.domux.data.PushRegistration
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Todo lo que la pantalla de inicio de sesión necesita para dibujarse (HU-001). */
data class LoginUiState(
    val email: String = "",
    val password: String = "",
    // Se pone en true al tocar «Entrar»: desde ahí se marcan los campos vacíos.
    val attempted: Boolean = false,
    val busy: Boolean = false,
    // true cuando la sesión quedó abierta y guardada: la pantalla pasa al inicio.
    val loggedIn: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false
) {
    val emailMissing: Boolean get() = attempted && email.isBlank()
    val emailInvalid: Boolean get() = email.isNotBlank() && !email.trim().contains("@")
    val passwordMissing: Boolean get() = attempted && password.isBlank()
}

/**
 * ViewModel del inicio de sesión (HU-001). Es la misma pantalla para los 3 roles: el servidor dice
 * qué rol tiene la persona y el inicio le muestra lo suyo. La contraseña solo vive aquí mientras la
 * pantalla está abierta; no se guarda en el celular.
 */
class LoginViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(LoginUiState())
    val state: StateFlow<LoginUiState> = _state.asStateFlow()

    override fun postMessage(text: String, isError: Boolean) {
        _state.update { it.copy(message = text, messageIsError = isError) }
    }

    override fun setBusy(busy: Boolean) {
        _state.update { it.copy(busy = busy) }
    }

    fun dismissMessage() {
        _state.update { it.copy(message = "") }
    }

    fun onEmail(value: String) {
        _state.update { it.copy(email = value) }
    }

    fun onPassword(value: String) {
        _state.update { it.copy(password = value) }
    }

    /**
     * Pide la sesión al servidor. [appContext] es el de la aplicación (no el de la pantalla): solo se
     * usa para guardar la sesión cifrada y registrar el celular para las notificaciones.
     */
    fun login(appContext: Context) {
        _state.update { it.copy(attempted = true) }
        val current = _state.value
        val email = current.email.trim().lowercase()
        if (!email.contains("@") || current.password.isBlank()) {
            showError("Escribe un correo válido y tu contraseña.")
            return
        }
        if (current.busy) return
        dismissMessage()
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudo conectar con el servidor") { api.login(LoginRequest(email, current.password)) }
            } ?: return@launch
            val body = response.body()
            val user = body?.user
            val token = body?.token
            if (user == null || token.isNullOrBlank()) {
                showError("El servidor no envió los datos de la sesión. Intenta de nuevo.")
                return@launch
            }
            Session.token = token
            Session.updateFrom(user)
            Session.persist(appContext)
            PushRegistration.registerAfterAuthentication(appContext)
            _state.update { it.copy(password = "", loggedIn = true) }
        }
    }
}
