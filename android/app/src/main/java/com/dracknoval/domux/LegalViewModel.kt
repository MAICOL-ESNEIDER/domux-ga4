package com.dracknoval.domux

import androidx.lifecycle.viewModelScope
import com.dracknoval.domux.data.LegalDocument
import com.dracknoval.domux.data.LegalDocumentSummary
import com.dracknoval.domux.data.RetrofitClient
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Todo lo que la pantalla de documentos legales necesita para dibujarse. */
data class LegalUiState(
    // La lista de documentos (cuando la pantalla se abre sin pedir uno en particular).
    val documents: List<LegalDocumentSummary> = emptyList(),
    // El documento que se está leyendo; queda vacío mientras llega o si no se pudo cargar.
    val document: LegalDocument? = null,
    val loading: Boolean = true,
    val message: String = "",
    val messageIsError: Boolean = false
)

/**
 * ViewModel de los documentos legales (política de datos, términos, cookies...): carga la lista o
 * el texto de uno. Son públicos, así que no usan la sesión y se pueden leer antes de iniciar sesión.
 */
class LegalViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(LegalUiState())
    val state: StateFlow<LegalUiState> = _state.asStateFlow()

    // El documento que se pidió («» = la lista). Sirve para cargar solo la primera vez y para reintentar.
    private var requested: String? = null

    override fun postMessage(text: String, isError: Boolean) {
        _state.update { it.copy(message = text, messageIsError = isError) }
    }

    // Aquí «ocupado» es lo mismo que «cargando»: la pantalla no tiene botones que se puedan tocar dos veces.
    override fun setBusy(busy: Boolean) {
        _state.update { it.copy(loading = busy) }
    }

    fun dismissMessage() {
        _state.update { it.copy(message = "") }
    }

    /** La pantalla lo llama con el documento de la ruta («» para la lista); solo carga la primera vez. */
    fun start(slug: String) {
        if (requested == slug) return
        requested = slug
        load()
    }

    /** Vuelve a pedir lo que la pantalla muestra (el botón «Reintentar» cuando falló la conexión). */
    fun load() {
        val slug = requested ?: return
        viewModelScope.launch {
            _state.update { it.copy(message = "") }
            withBusy {
                if (slug.isEmpty()) {
                    val response = attempt("No se pudieron cargar los documentos") { api.getLegalDocuments() }
                    _state.update { current ->
                        current.copy(documents = response?.body()?.documents?.let(::forCurrentRole) ?: current.documents)
                    }
                } else {
                    val response = attempt("No se pudo cargar el documento") { api.getLegalDocument(slug) }
                    _state.update { current -> current.copy(document = response?.body() ?: current.document) }
                }
            }
        }
    }
}


/**
 * Los documentos que le tocan a quien tiene la sesión: los de todos y los de su rol (el compromiso de la
 * portería solo lo ve la portería). Sin sesión, antes de entrar, se ven todos.
 */
fun forCurrentRole(documents: List<LegalDocumentSummary>, role: String? = com.dracknoval.domux.data.Session.role): List<LegalDocumentSummary> =
    if (role.isNullOrBlank()) documents
    else documents.filter { it.audience.isNullOrEmpty() || role in it.audience }
