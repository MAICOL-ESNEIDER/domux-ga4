package com.dracknoval.domux

import android.util.Base64
import androidx.lifecycle.viewModelScope
import com.dracknoval.domux.data.DocumentOption
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.UnitDocument
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Un documento ya descargado y listo para el visor: su archivo como «data:…;base64,…». */
data class OpenedDocument(
    val title: String,
    val dataUrl: String,
    // «document» (un PDF) o «image»: así lo entiende el visor de adjuntos.
    val mediaType: String
)

/** Todo lo que la pantalla de Documentos necesita para dibujarse. */
data class DocumentsUiState(
    val documents: List<UnitDocument> = emptyList(),
    // Los tipos de documento en el orden del servidor, para agrupar la lista.
    val categories: List<DocumentOption> = emptyList(),
    // Los públicos (propietarios, arrendatarios...): la administración los ve escritos en cada documento.
    val audiences: List<DocumentOption> = emptyList(),
    val loading: Boolean = false,
    // El documento que se está descargando para abrirlo.
    val opening: Int? = null,
    // El documento abierto en el visor, si hay uno.
    val viewer: OpenedDocument? = null,
    val busy: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false
)

/**
 * ViewModel de los documentos de la unidad (DEC-032). Cada persona recibe solo los que la administración
 * le marcó; la administración los sube y los retira en la web. La lista no trae los archivos: el PDF o la
 * imagen se pide al abrir uno y se muestra dentro de la app, sin guardar nada en el celular.
 */
class DocumentsViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(DocumentsUiState())
    val state: StateFlow<DocumentsUiState> = _state.asStateFlow()

    // El último archivo abierto se queda en memoria con su versión: si se vuelve a abrir y no cambió,
    // no se descarga otra vez.
    private var lastOpened: Pair<String, OpenedDocument>? = null

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

    fun refresh() {
        viewModelScope.launch {
            _state.update { it.copy(loading = true) }
            val body = attempt("No se pudieron cargar los documentos") { api.getDocuments(auth()) }?.body()
            _state.update { old ->
                if (body == null) {
                    old.copy(loading = false)
                } else {
                    old.copy(
                        loading = false,
                        documents = body.documents.orEmpty(),
                        categories = body.categories.orEmpty(),
                        audiences = body.audiences.orEmpty()
                    )
                }
            }
        }
    }

    /** Pide el archivo del documento y lo abre en el visor; un solo documento a la vez. */
    fun open(document: UnitDocument) {
        if (_state.value.opening != null) return
        val cacheKey = "${document.id}:${document.version.orEmpty()}"
        lastOpened?.takeIf { it.first == cacheKey }?.let { cached ->
            _state.update { it.copy(viewer = cached.second, message = "") }
            return
        }
        viewModelScope.launch {
            _state.update { it.copy(opening = document.id, message = "") }
            try {
                val response = withBusy {
                    attempt("No se pudo abrir el documento") { api.getDocumentFile(auth(), document.id) }
                } ?: return@launch
                val bytes = withContext(Dispatchers.IO) { response.body()?.bytes() }
                if (bytes == null || bytes.isEmpty()) {
                    showError("No se pudo abrir el documento. Inténtalo de nuevo.")
                    return@launch
                }
                val mime = document.mimeType ?: response.headers()["Content-Type"] ?: "application/octet-stream"
                val encoded = withContext(Dispatchers.Default) { Base64.encodeToString(bytes, Base64.NO_WRAP) }
                val opened = OpenedDocument(
                    title = document.title,
                    dataUrl = "data:$mime;base64,$encoded",
                    mediaType = if (document.kind == "pdf" || mime == "application/pdf") "document" else "image"
                )
                lastOpened = cacheKey to opened
                _state.update { it.copy(viewer = opened) }
            } finally {
                _state.update { it.copy(opening = null) }
            }
        }
    }

    fun closeViewer() {
        _state.update { it.copy(viewer = null) }
    }
}
