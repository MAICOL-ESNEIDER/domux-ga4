package com.dracknoval.domux

import android.content.Context
import androidx.lifecycle.ViewModel
import com.dracknoval.domux.data.RecentAccount
import com.dracknoval.domux.data.RecentAccountsStore
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

/** Lo que la pantalla de Preferencias dibuja además del tamaño del texto (que vive en AppPreferences). */
data class PreferencesUiState(
    // Las cuentas recordadas en este celular: solo el correo y el nombre, nunca la contraseña.
    val accounts: List<RecentAccount> = emptyList(),
    val message: String = ""
)

/**
 * ViewModel de Preferencias: lee las cuentas recordadas en este celular y las quita de una
 * en una o todas. No habla con el servidor: todo se guarda y se borra en el celular.
 */
class PreferencesViewModel : ViewModel() {
    private val _state = MutableStateFlow(PreferencesUiState())
    val state: StateFlow<PreferencesUiState> = _state.asStateFlow()

    fun load(appContext: Context) {
        _state.update { it.copy(accounts = RecentAccountsStore.read(appContext)) }
    }

    fun forget(appContext: Context, account: RecentAccount) {
        val remaining = RecentAccountsStore.forget(appContext, account.email)
        _state.update {
            it.copy(accounts = remaining, message = "Se quitó a ${account.displayName} de este celular.")
        }
    }

    fun forgetAll(appContext: Context) {
        val remaining = RecentAccountsStore.forgetAll(appContext)
        _state.update { it.copy(accounts = remaining, message = "Se quitaron todas las cuentas de este celular.") }
    }

    fun dismissMessage() {
        _state.update { it.copy(message = "") }
    }
}
