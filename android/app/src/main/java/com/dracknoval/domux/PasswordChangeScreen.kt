// PasswordChangeScreen.kt — cambio obligatorio de contraseña. Aparece cuando el administrador le
// restableció la contraseña a la persona: esa contraseña es temporal y aquí pone una propia.

package com.dracknoval.domux

import android.content.Context
import android.util.Log
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.dracknoval.domux.data.ChangeOwnPasswordRequest
import com.dracknoval.domux.data.PushRegistration
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.ui.theme.DomuxColor
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

private const val OWN_PASSWORD_RULE =
    "Mínimo 8 caracteres con una mayúscula, una minúscula, un número y un carácter especial (@\$!%*?&#._-)."

/** Lo que la pantalla de cambio de contraseña necesita para dibujarse. */
data class PasswordChangeUiState(
    val current: String = "",
    val new: String = "",
    val repeat: String = "",
    // Se pone en true al tocar el botón: desde ahí se marcan los campos con problemas.
    val attempted: Boolean = false,
    val busy: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false
) {
    val currentMissing: Boolean get() = attempted && current.isBlank()
    val newMissing: Boolean get() = attempted && new.isBlank()
    val repeatMismatch: Boolean get() = repeat.isNotEmpty() && repeat != new
}

/**
 * Cambia la contraseña propia. Las contraseñas solo viven aquí mientras la pantalla está abierta;
 * no se guardan en el celular. El servidor revisa que la nueva sea fuerte y distinta de la actual.
 */
class PasswordChangeViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(PasswordChangeUiState())
    val state: StateFlow<PasswordChangeUiState> = _state.asStateFlow()

    override fun postMessage(text: String, isError: Boolean) {
        _state.update { it.copy(message = text, messageIsError = isError) }
    }

    override fun setBusy(busy: Boolean) {
        _state.update { it.copy(busy = busy) }
    }

    fun dismissMessage() {
        _state.update { it.copy(message = "") }
    }

    fun onCurrent(value: String) {
        _state.update { it.copy(current = value) }
    }

    fun onNew(value: String) {
        _state.update { it.copy(new = value) }
    }

    fun onRepeat(value: String) {
        _state.update { it.copy(repeat = value) }
    }

    /** Borra lo escrito, por ejemplo al cerrar sesión desde esta pantalla. */
    fun reset() {
        _state.value = PasswordChangeUiState()
    }

    /**
     * Manda el cambio. Si sale bien, el servidor cierra las sesiones viejas y entrega una nueva, que
     * se guarda aquí; [onChanged] lleva a la persona al inicio.
     */
    fun submit(appContext: Context, onChanged: () -> Unit) {
        _state.update { it.copy(attempted = true) }
        val current = _state.value
        if (current.current.isBlank() || current.new.isBlank()) {
            showError("Escribe tu contraseña actual y la nueva.")
            return
        }
        if (current.new != current.repeat) {
            showError("Las dos contraseñas nuevas no coinciden.")
            return
        }
        if (current.busy) return
        dismissMessage()
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudo cambiar la contraseña") {
                    api.changeOwnPassword(auth(), ChangeOwnPasswordRequest(current.current, current.new))
                }
            } ?: return@launch
            val body = response.body()
            val user = body?.user
            val token = body?.token
            if (user == null || token.isNullOrBlank()) {
                showError("El servidor no envió los datos de la sesión. Intenta de nuevo.")
                return@launch
            }
            reset()
            Session.token = token
            Session.updateFrom(user)
            Session.persist(appContext)
            PushRegistration.registerAfterAuthentication(appContext)
            onChanged()
        }
    }

    /** Cierra la sesión sin cambiar la contraseña: la próxima vez que entre se le vuelve a pedir. */
    fun logout(appContext: Context, onLoggedOut: () -> Unit) {
        reset()
        try {
            Session.clear(appContext)
        } catch (exception: Exception) {
            Log.e("DomuxSession", "Could not clear the session during logout.", exception)
            showError("No se pudo cerrar la sesión. Intenta de nuevo.")
            return
        }
        onLoggedOut()
    }
}

/**
 * Pantalla completa que tapa la app mientras la persona tenga una contraseña temporal. No se puede
 * saltar: el botón de atrás no hace nada y el servidor tampoco deja usar lo demás.
 */
@Composable
fun PasswordChangeScreen(
    onChanged: () -> Unit,
    onLoggedOut: () -> Unit,
    viewModel: PasswordChangeViewModel = viewModel()
) {
    val state by viewModel.state.collectAsState()
    val appContext = LocalContext.current.applicationContext
    // Mostrar u ocultar lo escrito es solo de la pantalla; por defecto va oculto.
    var showPasswords by rememberSaveable { mutableStateOf(false) }
    val hidden = if (showPasswords) VisualTransformation.None else PasswordVisualTransformation()

    BackHandler(enabled = true) {}

    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(24.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            DomuxBrandMark(size = 56.dp)
            Spacer(Modifier.height(16.dp))
            Text(
                "Cambia tu contraseña",
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.SemiBold
            )
            Spacer(Modifier.height(8.dp))
            Text(
                "La administración te restableció la contraseña. Antes de continuar, pon una que solo tú conozcas.",
                color = DomuxColor.TextMuted,
                style = MaterialTheme.typography.bodyMedium
            )
            Spacer(Modifier.height(20.dp))

            OutlinedTextField(
                value = state.current,
                onValueChange = viewModel::onCurrent,
                label = { Text("Contraseña actual") },
                singleLine = true,
                visualTransformation = hidden,
                isError = state.currentMissing,
                supportingText = {
                    Text(if (state.currentMissing) "Escribe la contraseña que te dieron" else "La que te dio la administración")
                },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Next),
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = state.new,
                onValueChange = viewModel::onNew,
                label = { Text("Contraseña nueva") },
                singleLine = true,
                visualTransformation = hidden,
                isError = state.newMissing,
                supportingText = { Text(OWN_PASSWORD_RULE) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Next),
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = state.repeat,
                onValueChange = viewModel::onRepeat,
                label = { Text("Repite la contraseña nueva") },
                singleLine = true,
                visualTransformation = hidden,
                isError = state.repeatMismatch,
                supportingText = { if (state.repeatMismatch) Text("No es igual a la contraseña nueva") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
                modifier = Modifier.fillMaxWidth()
            )
            TextButton(onClick = { showPasswords = !showPasswords }) {
                Text(if (showPasswords) "Ocultar las contraseñas" else "Mostrar las contraseñas")
            }
            Spacer(Modifier.height(12.dp))

            Button(
                onClick = { viewModel.submit(appContext, onChanged) },
                enabled = !state.busy,
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 48.dp)
            ) {
                Text(if (state.busy) "Guardando..." else "Cambiar la contraseña")
            }
            TextButton(
                onClick = { viewModel.logout(appContext, onLoggedOut) },
                enabled = !state.busy,
                modifier = Modifier.heightIn(min = 48.dp)
            ) {
                Text("Cerrar sesión")
            }

            if (state.message.isNotBlank()) {
                Spacer(Modifier.height(16.dp))
                DomuxMessageBanner(state.message, state.messageIsError) { viewModel.dismissMessage() }
            }
        }
    }
}
