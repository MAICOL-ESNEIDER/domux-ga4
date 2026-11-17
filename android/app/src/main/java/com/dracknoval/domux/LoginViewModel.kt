package com.dracknoval.domux

import android.content.Context
import androidx.lifecycle.viewModelScope
import com.dracknoval.domux.data.LoginRequest
import com.dracknoval.domux.data.PushRegistration
import com.dracknoval.domux.data.RecentAccount
import com.dracknoval.domux.data.RecentAccountsStore
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.UserData
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
    val messageIsError: Boolean = false,
    // «Cuentas recientes en este celular»: solo el correo y el nombre, nunca la contraseña.
    val accountsLoaded: Boolean = false,
    val recentAccounts: List<RecentAccount> = emptyList(),
    // true mientras se ve la lista de cuentas; false mientras se ve el formulario.
    val showingAccounts: Boolean = false,
    // La cuenta que se tocó en la lista: el formulario la muestra en lugar del campo del correo.
    val chosenAccount: RecentAccount? = null,
    // La casilla «Recordar mi correo en este celular»: empieza sin marcar.
    val rememberEmail: Boolean = false,
    // La última cuenta quitada y el puesto que tenía, para el botón «Deshacer».
    val removedAccount: RecentAccount? = null,
    val removedIndex: Int = 0
) {
    val emailMissing: Boolean get() = attempted && email.isBlank()
    val emailInvalid: Boolean get() = email.isNotBlank() && !email.trim().contains("@")
    val passwordMissing: Boolean get() = attempted && password.isBlank()
}

/**
 * ViewModel del inicio de sesión (HU-001). Es la misma pantalla para los 3 roles: el servidor dice
 * qué rol tiene la persona y el inicio le muestra lo suyo. La contraseña solo vive aquí mientras la
 * pantalla está abierta; no se guarda en el celular. Lo único que puede quedar guardado es el correo
 * y el nombre, y solo si la persona marca «Recordar mi correo en este celular» ([RecentAccountsStore]).
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

    fun onRememberEmail(value: Boolean) {
        _state.update { it.copy(rememberEmail = value) }
    }

    /**
     * Lee las cuentas recordadas una sola vez (al girar la pantalla no se vuelve a la lista). Si hay
     * alguna, la pantalla empieza mostrando la lista; si no, el formulario de siempre.
     */
    fun loadRecentAccounts(appContext: Context) {
        if (_state.value.accountsLoaded) return
        val accounts = RecentAccountsStore.read(appContext)
        _state.update {
            it.copy(accountsLoaded = true, recentAccounts = accounts, showingAccounts = accounts.isNotEmpty())
        }
    }

    /** Se tocó una cuenta de la lista: queda puesto su correo y solo falta la contraseña. */
    fun chooseAccount(account: RecentAccount) {
        _state.update {
            it.copy(
                chosenAccount = account,
                email = account.email,
                password = "",
                attempted = false,
                showingAccounts = false,
                removedAccount = null,
                message = ""
            )
        }
    }

    /** «Usar otra cuenta»: el formulario de siempre, con la casilla de recordar sin marcar. */
    fun useAnotherAccount() {
        _state.update {
            it.copy(
                chosenAccount = null,
                email = "",
                password = "",
                attempted = false,
                rememberEmail = false,
                showingAccounts = false,
                removedAccount = null,
                message = ""
            )
        }
    }

    /** «Cambiar» o «Volver a las cuentas recientes»: se vuelve a la lista sin dejar nada escrito. */
    fun backToAccounts() {
        _state.update {
            it.copy(
                chosenAccount = null,
                email = "",
                password = "",
                attempted = false,
                showingAccounts = it.recentAccounts.isNotEmpty(),
                message = ""
            )
        }
    }

    /** La X de una cuenta: se quita de este celular, con la opción de deshacerlo enseguida. */
    fun forgetAccount(appContext: Context, account: RecentAccount) {
        val index = _state.value.recentAccounts.indexOfFirst { it.email.equals(account.email, ignoreCase = true) }
        val remaining = RecentAccountsStore.forget(appContext, account.email)
        _state.update {
            it.copy(
                recentAccounts = remaining,
                removedAccount = account,
                removedIndex = index.coerceAtLeast(0),
                // Si era la última, se pasa al formulario de siempre.
                showingAccounts = remaining.isNotEmpty(),
                rememberEmail = false
            )
        }
    }

    fun undoForgetAccount(appContext: Context) {
        val removed = _state.value.removedAccount ?: return
        val accounts = RecentAccountsStore.restore(appContext, removed, _state.value.removedIndex)
        _state.update {
            it.copy(
                recentAccounts = accounts,
                removedAccount = null,
                showingAccounts = accounts.isNotEmpty(),
                chosenAccount = null,
                email = "",
                password = "",
                attempted = false
            )
        }
    }

    fun dismissRemovedNotice() {
        _state.update { it.copy(removedAccount = null) }
    }

    /**
     * Pide la sesión al servidor. [appContext] es el de la aplicación (no el de la pantalla): solo se
     * usa para guardar la sesión cifrada, recordar el correo si se pidió y registrar el celular para
     * las notificaciones.
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
            // Solo después de entrar bien: una cuenta elegida de la lista sube de primera, y una
            // escrita a mano se guarda solo si se marcó la casilla.
            if (current.chosenAccount != null || current.rememberEmail) {
                RecentAccountsStore.remember(appContext, RecentAccount(email, nameOf(user)))
            }
            PushRegistration.registerAfterAuthentication(appContext)
            _state.update { it.copy(password = "", loggedIn = true) }
        }
    }

    // El servidor manda el nombre completo en «fullName» y también en «name» (que ya quedó en la sesión).
    private fun nameOf(user: UserData): String =
        user.fullName?.trim()?.takeIf { it.isNotBlank() } ?: Session.userName.orEmpty().trim()
}
