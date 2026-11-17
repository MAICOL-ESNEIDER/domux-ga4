package com.dracknoval.domux

import android.net.Uri
import androidx.lifecycle.viewModelScope
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.SearchGroup
import com.dracknoval.domux.data.SearchPlace
import com.dracknoval.domux.data.SearchResult
import com.dracknoval.domux.data.Session
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Las opciones de «Buscar en» antes de la primera búsqueda. El servidor manda las suyas en cada
 * respuesta (son las mismas): estas solo sirven para dibujar los botones desde el principio. La
 * portería no busca en PQRS.
 */
fun defaultSearchPlaces(): List<SearchPlace> = buildList {
    add(SearchPlace("todo", "Todo"))
    add(SearchPlace("personas", "Personas"))
    add(SearchPlace("apartamentos", "Apartamentos"))
    add(SearchPlace("vehiculos", "Vehículos"))
    if (!Session.isGuard) add(SearchPlace("pqrs", "PQRS"))
    add(SearchPlace("paquetes", "Paquetes"))
    add(SearchPlace("visitas", "Visitas"))
}

/** Todo lo que la pantalla del buscador necesita para dibujarse (HU-089). */
data class SearchUiState(
    val text: String = "",
    val place: String = "todo",
    val places: List<SearchPlace> = defaultSearchPlaces(),
    val groups: List<SearchGroup> = emptyList(),
    // El texto de la última búsqueda hecha (sin espacios): es el que se nombra en «No se encontró nada».
    val searchedText: String = "",
    // true cuando ya llegó una respuesta para el texto y el lugar de ahora.
    val searched: Boolean = false,
    val loading: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = true
) {
    /** Cuántos resultados hay en total, sumando todos los grupos. */
    val total: Int get() = groups.sumOf { it.items.orEmpty().size }

    /** true si ya hay algo escrito pero todavía no alcanza para buscar. */
    val tooShort: Boolean get() = text.trim().isNotEmpty() && text.trim().length < SearchViewModel.MIN_CHARS
}

/**
 * ViewModel del buscador general (HU-089), solo para la administración y la portería. La búsqueda
 * no tiene reglas propias: la hace el servidor (`GET /api/search`), la misma de la web, y aquí solo
 * se escribe el texto, se elige «Buscar en» y se muestran los grupos de resultados.
 *
 * Busca sola cuando la persona deja de escribir un momento, y de una vez al tocar «Buscar» en el
 * teclado o al cambiar «Buscar en». Si llega una búsqueda nueva, la anterior se cancela: nunca se
 * pinta una respuesta vieja sobre una nueva.
 */
class SearchViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(SearchUiState())
    val state: StateFlow<SearchUiState> = _state.asStateFlow()
    private var searchJob: Job? = null

    override fun postMessage(text: String, isError: Boolean) {
        _state.update { it.copy(message = text, messageIsError = isError) }
    }

    // El buscador no tiene botones que se toquen dos veces: «cargando» ya lo dice todo.
    override fun setBusy(busy: Boolean) {
        _state.update { it.copy(loading = busy) }
    }

    fun dismissMessage() {
        _state.update { it.copy(message = "") }
    }

    /** El texto cambió: se espera un instante a que la persona termine de escribir antes de buscar. */
    fun setText(value: String) {
        val text = value.take(MAX_CHARS)
        _state.update { it.copy(text = text, message = "") }
        searchJob?.cancel()
        if (text.trim().length < MIN_CHARS) {
            // Con muy poco texto no se muestra lo de una búsqueda anterior.
            _state.update { it.copy(groups = emptyList(), searched = false, loading = false) }
            return
        }
        searchJob = viewModelScope.launch {
            delay(DEBOUNCE_MILLIS)
            runSearch()
        }
    }

    /** «Buscar en»: cambia el lugar y busca de una vez si ya hay texto suficiente. */
    fun setPlace(value: String) {
        if (_state.value.place == value) return
        _state.update { it.copy(place = value, searched = false) }
        searchNow()
    }

    /** Busca ya, sin esperar (tecla «Buscar» del teclado). */
    fun searchNow() {
        searchJob?.cancel()
        if (_state.value.text.trim().length < MIN_CHARS) return
        searchJob = viewModelScope.launch { runSearch() }
    }

    /** Borra el texto y los resultados; el lugar elegido se queda. */
    fun clear() {
        searchJob?.cancel()
        _state.update { it.copy(text = "", groups = emptyList(), searched = false, loading = false, message = "") }
    }

    private suspend fun runSearch() {
        val current = _state.value
        val text = current.text.trim()
        _state.update { it.copy(loading = true, message = "") }
        val response = attempt("No se pudo buscar") { api.search(auth(), text, current.place) }
        val body = response?.body()
        _state.update { old ->
            if (body == null) {
                old.copy(loading = false)
            } else {
                old.copy(
                    loading = false,
                    searched = true,
                    searchedText = text,
                    groups = body.groups.orEmpty().filter { !it.items.isNullOrEmpty() },
                    places = body.places?.takeIf { it.isNotEmpty() } ?: old.places
                )
            }
        }
    }

    companion object {
        /** Lo mínimo que hay que escribir; el servidor pide lo mismo (2 letras, y 3 para una placa). */
        const val MIN_CHARS = 2
        const val MAX_CHARS = 100
        private const val DEBOUNCE_MILLIS = 400L
    }
}

/**
 * A dónde lleva tocar un resultado, escrito como la ruta de la app, o null si ese resultado solo
 * se lee (la portería no tiene pantalla de usuarios ni de apartamentos). Cada ruta abre la pantalla
 * con la búsqueda ya puesta o en la pestaña que corresponde.
 */
fun searchResultRoute(result: SearchResult): String? {
    val guard = Session.isGuard
    return when (result.type) {
        "personas" -> if (guard) null else "createUser?search=${Uri.encode(result.title)}"
        "apartamentos" -> if (guard) null else result.apartmentLabel?.takeIf { it.isNotBlank() }
            ?.let { "unitProfile/${Uri.encode(it)}" }
        // Un vehículo de residente se busca por placa en «Residentes»; el de un visitante que está
        // adentro se ve en el tablero de «Parqueaderos».
        "vehiculos" ->
            if (result.kind == "visitante") "vehicles" else "vehicles?tab=residentes&search=${Uri.encode(result.title)}"
        // El título de una PQRS es «radicado · asunto»: se busca por el radicado.
        "pqrs" -> "pqrs?search=${Uri.encode(result.title.substringBefore(" · ").trim())}"
        "paquetes" -> "registry?tab=paquetes&search=${Uri.encode(result.title)}"
        "visitas" -> "registry?tab=visitas&search=${Uri.encode(result.title)}"
        else -> null
    }
}
