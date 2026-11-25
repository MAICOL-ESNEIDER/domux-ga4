// LegalAcceptScreen.kt — pantalla «Acepto». La primera vez que una persona entra (y cada vez que
// cambian los textos legales) debe leer y aceptar los términos de uso, la política de tratamiento
// de datos y la autorización para tratarlos (Ley 1581 de 2012). Hasta que acepte, la app no deja
// hacer nada más y el servidor tampoco: responde 403 «legalAcceptanceRequired».

package com.dracknoval.domux

import android.content.Context
import android.util.Log
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.dracknoval.domux.data.AcceptLegalRequest
import com.dracknoval.domux.data.LegalDocument
import com.dracknoval.domux.data.PushRegistration
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.ui.theme.DomuxColor
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Lo que la pantalla «Acepto» necesita para dibujarse. */
data class LegalAcceptUiState(
    // Los textos que se aceptan, completos y en el orden en que se muestran.
    val documents: List<LegalDocument> = emptyList(),
    // La versión de los textos que se cargaron: es la que se manda al aceptar.
    val version: String = "",
    val loading: Boolean = true,
    val busy: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false
)

/**
 * Carga los textos que debe aceptar la persona y guarda su aceptación. El servidor es quien dice si
 * hace falta aceptar y cuál es la versión; la app manda de vuelta la versión que se le mostró, y si
 * los textos cambiaron mientras tanto el servidor no guarda nada y se cargan de nuevo.
 */
class LegalAcceptViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(LegalAcceptUiState())
    val state: StateFlow<LegalAcceptUiState> = _state.asStateFlow()

    private var started = false

    override fun postMessage(text: String, isError: Boolean) {
        _state.update { it.copy(message = text, messageIsError = isError) }
    }

    override fun setBusy(busy: Boolean) {
        _state.update { it.copy(busy = busy) }
    }

    fun dismissMessage() {
        _state.update { it.copy(message = "") }
    }

    /** La pantalla lo llama al abrirse; solo carga la primera vez. */
    fun start() {
        if (started) return
        started = true
        load()
    }

    /** Pide la versión y los textos (también es el botón «Reintentar»). */
    fun load() {
        viewModelScope.launch {
            _state.update { it.copy(loading = true, message = "") }
            val status = attempt("No se pudieron cargar los textos legales") { api.getLegalAcceptance(auth()) }
                ?.body()
            if (status == null) {
                _state.update { it.copy(loading = false) }
                return@launch
            }
            if (!status.required) {
                // Ya había aceptado esta versión (por ejemplo, desde otro celular): se deja pasar.
                Session.legalAcceptanceRequired = false
                _state.update { it.copy(loading = false) }
                return@launch
            }
            val documents = mutableListOf<LegalDocument>()
            for (summary in status.documents.orEmpty()) {
                val document = attempt("No se pudo cargar «${summary.title}»") { api.getLegalDocument(summary.slug) }
                    ?.body()
                if (document == null) {
                    _state.update { it.copy(loading = false) }
                    return@launch
                }
                documents += document
            }
            _state.update { it.copy(documents = documents, version = status.version, loading = false) }
        }
    }

    /**
     * Manda la aceptación con la versión que se le mostró a la persona. Si sale bien, la sesión queda
     * al día y la pantalla se quita sola. Si los textos cambiaron (409), se cargan los nuevos.
     */
    fun accept(appContext: Context, onAccepted: () -> Unit) {
        val current = _state.value
        if (current.busy || current.loading || current.version.isBlank()) return
        dismissMessage()
        viewModelScope.launch {
            val response = withBusy {
                callRaw("No se pudo guardar tu aceptación") {
                    api.acceptLegal(auth(), AcceptLegalRequest(accepted = true, version = current.version))
                }
            } ?: return@launch
            if (response.code() == 409) {
                load()
                showError("Los textos legales cambiaron. Léelos de nuevo antes de aceptar.")
                return@launch
            }
            val user = response.body()?.user
            if (!response.isSuccessful || user == null) {
                showError("No se pudo guardar tu aceptación (${response.code()}). Intenta de nuevo.")
                return@launch
            }
            Session.updateFrom(user)
            Session.persist(appContext)
            PushRegistration.registerAfterAuthentication(appContext)
            onAccepted()
        }
    }

    /** Cierra la sesión sin aceptar: la próxima vez que entre se le vuelve a pedir. */
    fun logout(appContext: Context, onLoggedOut: () -> Unit) {
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
 * Pantalla completa que tapa la app hasta que la persona acepte los textos legales. No se puede
 * saltar: el botón de atrás no hace nada y el servidor tampoco deja usar lo demás.
 */
@Composable
fun LegalAcceptScreen(
    onAccepted: () -> Unit,
    onLoggedOut: () -> Unit,
    viewModel: LegalAcceptViewModel = viewModel()
) {
    val state by viewModel.state.collectAsState()
    val appContext = LocalContext.current.applicationContext
    var checked by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(Unit) { viewModel.start() }

    BackHandler(enabled = true) {}

    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            DomuxBrandMark(size = 56.dp)
            Text(
                "Antes de continuar, lee y acepta",
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.semantics { heading() }
            )
            Text(
                "Para usar DOMUX necesitamos tu autorización para guardar y usar tus datos personales, como " +
                    "lo pide la Ley 1581 de 2012. Lee los textos y, si estás de acuerdo, acepta.",
                color = DomuxColor.TextMuted,
                style = MaterialTheme.typography.bodyMedium
            )
            DomuxMessageBanner(state.message, state.messageIsError) { viewModel.dismissMessage() }

            when {
                state.loading -> CircularProgressIndicator()
                state.documents.isEmpty() -> {
                    OutlinedButton(
                        onClick = { viewModel.load() },
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(min = 48.dp)
                    ) { Text("Reintentar") }
                }
                else -> {
                    state.documents.forEach { document -> LegalAcceptDocument(document) }

                    Row(
                        Modifier
                            .fillMaxWidth()
                            .heightIn(min = 48.dp)
                            .toggleable(
                                value = checked,
                                role = Role.Checkbox,
                                onValueChange = { checked = it }
                            ),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Checkbox(checked = checked, onCheckedChange = null)
                        Text(
                            "Leí los textos y los acepto. Autorizo el tratamiento de mis datos personales. " +
                                "Si soy menor de edad, acepta mi representante legal.",
                            style = MaterialTheme.typography.bodyMedium,
                            modifier = Modifier.weight(1f)
                        )
                    }
                    Button(
                        onClick = { viewModel.accept(appContext, onAccepted) },
                        enabled = checked && !state.busy,
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(min = 48.dp)
                    ) {
                        Text(if (state.busy) "Guardando..." else "Acepto y continuar")
                    }
                }
            }
            TextButton(
                onClick = { viewModel.logout(appContext, onLoggedOut) },
                enabled = !state.busy,
                modifier = Modifier.heightIn(min = 48.dp)
            ) {
                Text("No acepto, cerrar sesión")
            }
            Spacer(Modifier.height(8.dp))
        }
    }
}

/** Un texto legal que se abre y se cierra: así los tres caben en la pantalla y se pueden leer completos. */
@Composable
private fun LegalAcceptDocument(document: LegalDocument) {
    var expanded by rememberSaveable(document.slug) { mutableStateOf(false) }
    DomuxCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                document.title,
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.semantics { heading() }
            )
            Text(document.summary, color = DomuxColor.TextSoft, style = MaterialTheme.typography.bodyMedium)
            if (expanded) {
                document.blocks.orEmpty().forEach { block -> LegalBlockText(block) }
            }
            TextButton(
                onClick = { expanded = !expanded },
                modifier = Modifier.heightIn(min = 48.dp)
            ) {
                Text(if (expanded) "Cerrar el texto" else "Leer el texto completo")
            }
        }
    }
}
