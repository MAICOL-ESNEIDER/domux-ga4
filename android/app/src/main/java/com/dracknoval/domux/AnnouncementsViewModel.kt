package com.dracknoval.domux

import androidx.lifecycle.viewModelScope
import com.dracknoval.domux.data.Announcement
import com.dracknoval.domux.data.CreateAnnouncementRequest
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.TowerData
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Una de las cinco categorías de un comunicado (HU-058). [key] es el valor que viaja al servidor. */
data class AnnouncementCategory(val key: String, val label: String)

val announcementCategories = listOf(
    AnnouncementCategory("mantenimiento", "Mantenimiento"),
    AnnouncementCategory("urgente", "Urgente"),
    AnnouncementCategory("asamblea", "Asamblea"),
    AnnouncementCategory("seguridad", "Seguridad"),
    AnnouncementCategory("zonas_comunes", "Zonas comunes")
)

/** Todo lo que la pantalla de Anuncios necesita para dibujarse. */
data class AnnouncementsUiState(
    val items: List<Announcement> = emptyList(),
    val page: PageInfo = PageInfo(),
    val loading: Boolean = false,
    val loadingMore: Boolean = false,
    // false: los vigentes; true: los archivados, que ya pasaron su vencimiento (HU-060).
    val archived: Boolean = false,
    // Filtro por categoría (HU-058); sin valor, salen todas.
    val category: String? = null,
    // Solo los que el residente todavía no ha abierto (HU-059).
    val unreadOnly: Boolean = false,
    // Cuántos comunicados vigentes le faltan por leer al residente.
    val unreadCount: Int = 0,
    // Torres a las que se puede dirigir un comunicado (HU-061); solo las carga la administración.
    val towers: List<TowerData> = emptyList(),
    val busy: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false,
    // Sube cada vez que se publica un comunicado; el formulario lo mira para limpiarse.
    val published: Int = 0
)

/**
 * ViewModel de los comunicados (HU-058 a HU-062): lista de vigentes y archivados con filtros,
 * lectura del residente, publicación con categoría, torre y vencimiento, y retiro.
 * Retirar no borra: el comunicado queda guardado en el historial (TT-029 y ADR-013).
 */
class AnnouncementsViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(AnnouncementsUiState())
    val state: StateFlow<AnnouncementsUiState> = _state.asStateFlow()

    // Cada carga lleva un número: una respuesta vieja que llega tarde se descarta.
    private var listTicket = 0

    init {
        refresh()
        if (Session.isAdmin) loadTowers()
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

    // --- Lista ------------------------------------------------------------------------

    fun refresh() {
        viewModelScope.launch { loadList(1) }
    }

    private suspend fun loadList(page: Int, append: Boolean = false) {
        val ticket = ++listTicket
        _state.update { it.copy(loading = !append, loadingMore = append) }
        val current = _state.value
        val response = attempt("No se pudieron cargar los comunicados") {
            api.getAnnouncements(
                auth(),
                archived = if (current.archived) "true" else null,
                category = current.category,
                unread = if (current.unreadOnly) "true" else null,
                page = page,
                pageSize = PAGE_SIZE
            )
        }
        if (ticket != listTicket) return
        val body = response?.body()
        _state.update { old ->
            if (body == null) {
                old.copy(loading = false, loadingMore = false)
            } else {
                val received = body.announcements.orEmpty()
                old.copy(
                    loading = false,
                    loadingMore = false,
                    items = if (append) (old.items + received).distinctBy { it.id } else received,
                    page = PageInfo(body.page.coerceAtLeast(1), body.totalPages.coerceAtLeast(1), body.total),
                    unreadCount = body.unreadCount
                )
            }
        }
    }

    fun loadMore() {
        val current = _state.value
        if (current.loading || current.loadingMore || current.page.page >= current.page.totalPages) return
        viewModelScope.launch { loadList(current.page.page + 1, append = true) }
    }

    /** Vigentes o archivados. Los archivados ya no se pueden marcar como sin leer. */
    fun setArchived(archived: Boolean) {
        if (_state.value.archived == archived) return
        _state.update { it.copy(archived = archived, unreadOnly = if (archived) false else it.unreadOnly) }
        refresh()
    }

    fun setCategory(category: String?) {
        if (_state.value.category == category) return
        _state.update { it.copy(category = category) }
        refresh()
    }

    fun setUnreadOnly(unreadOnly: Boolean) {
        if (_state.value.unreadOnly == unreadOnly) return
        _state.update { it.copy(unreadOnly = unreadOnly) }
        refresh()
    }

    // --- Lectura (HU-059 y HU-062) -------------------------------------------------------

    /**
     * El residente abrió el comunicado: queda leído. Si no hay conexión no se avisa nada, porque
     * puede leerlo igual; se vuelve a intentar la próxima vez que lo abra.
     */
    fun markRead(announcement: Announcement) {
        if (announcement.isRead || !Session.isResident) return
        viewModelScope.launch {
            val response = try {
                api.markAnnouncementRead(auth(), announcement.id)
            } catch (exception: CancellationException) {
                throw exception
            } catch (_: Exception) {
                null
            }
            val body = response?.takeIf { it.isSuccessful }?.body() ?: return@launch
            _state.update { old ->
                old.copy(
                    unreadCount = body.unreadCount,
                    items = old.items.map { if (it.id == announcement.id) it.copy(isRead = true) else it }
                )
            }
        }
    }

    // --- Publicar y retirar ----------------------------------------------------------------

    private fun loadTowers() {
        viewModelScope.launch {
            val response = attempt("No se pudieron cargar las torres") {
                RetrofitClient.structureApi.getTowers(auth())
            } ?: return@launch
            _state.update { it.copy(towers = response.body()?.towers.orEmpty()) }
        }
    }

    fun publish(request: CreateAnnouncementRequest) {
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo publicar el comunicado") { api.createAnnouncement(auth(), request) }
            } ?: return@launch
            _state.update { it.copy(published = it.published + 1, archived = false, unreadOnly = false) }
            showSuccess("Comunicado publicado.")
            loadList(1)
        }
    }

    fun retire(announcement: Announcement) {
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo retirar el comunicado") { api.retireAnnouncement(auth(), announcement.id) }
            } ?: return@launch
            showSuccess("Comunicado retirado. Queda guardado en el historial.")
            loadList(1)
        }
    }

    companion object {
        /** Comunicados que se piden por página. */
        const val PAGE_SIZE = 20
    }
}
