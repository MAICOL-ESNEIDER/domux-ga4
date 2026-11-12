package com.dracknoval.domux

import androidx.lifecycle.viewModelScope
import com.dracknoval.domux.data.AdminSummaryResponse
import com.dracknoval.domux.data.Announcement
import com.dracknoval.domux.data.NotificationItem
import com.dracknoval.domux.data.PackageItem
import com.dracknoval.domux.data.Reservation
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.Visit
import com.dracknoval.domux.data.VisitDecisionRequest
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import retrofit2.Response

/** Todo lo que el inicio necesita para dibujarse (HU-002, HU-065 y HU-081). */
data class HomeUiState(
    val notifications: List<NotificationItem> = emptyList(),
    // Aviso pequeño al final del inicio si no se pudo revisar si hay notificaciones nuevas.
    val syncProblem: String? = null,
    // true si el celular no deja mostrar avisos (Android 13 o más pide permiso).
    val permissionMissing: Boolean = false,
    val showNotifications: Boolean = false,
    // true hasta que llega la primera respuesta de lo pendiente.
    val dashboardLoading: Boolean = true,
    // Residente: lo que le espera (HU-002).
    val pendingVisits: List<Visit> = emptyList(),
    val waitingPackages: List<PackageItem> = emptyList(),
    val waitingPackagesTotal: Int = 0,
    val unreadAnnouncements: List<Announcement> = emptyList(),
    val unreadAnnouncementsTotal: Int = 0,
    val upcomingReservations: List<Reservation> = emptyList(),
    // Administración: lo que hay por atender hoy (HU-081).
    val adminSummary: AdminSummaryResponse? = null,
    // Portería: quién espera autorización y quién está dentro (HU-032).
    val guardPending: List<Visit> = emptyList(),
    val guardPendingTotal: Int = 0,
    val guardInside: List<Visit> = emptyList(),
    val guardInsideTotal: Int = 0,
    val busy: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false
) {
    val unreadCount: Int get() = notifications.count { !it.isRead }
}

/**
 * ViewModel del inicio. Cada vez que la pantalla lo pide revisa las notificaciones (y devuelve las
 * que llegaron desde la vez anterior, para que el celular las muestre como aviso) y lo pendiente
 * del rol: lo que le espera al residente, lo que hay por atender en la administración y lo que pasa
 * en la portería. Todo con listas livianas, sin fotos.
 */
class HomeViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(HomeUiState())
    val state: StateFlow<HomeUiState> = _state.asStateFlow()

    // Las notificaciones que ya se vieron, de quien tiene la sesión ahora (en portería cambia con el
    // PIN del guardia). null mientras no se ha hecho la primera revisión: esas no se avisan.
    private var knownIds: Set<Int>? = null
    private var knownFor: Int? = null

    override fun postMessage(text: String, isError: Boolean) {
        _state.update { it.copy(message = text, messageIsError = isError) }
    }

    override fun setBusy(busy: Boolean) {
        _state.update { it.copy(busy = busy) }
    }

    fun dismissMessage() {
        _state.update { it.copy(message = "") }
    }

    fun openNotifications() {
        _state.update { it.copy(showNotifications = true, message = "") }
    }

    fun closeNotifications() {
        _state.update { it.copy(showNotifications = false) }
    }

    fun setPermissionMissing(missing: Boolean) {
        _state.update { it.copy(permissionMissing = missing) }
    }

    /**
     * Revisa notificaciones y lo pendiente. Devuelve las notificaciones sin leer que no estaban en la
     * revisión anterior. Si algo falla no molesta con avisos grandes: deja una línea al final del
     * inicio y se vuelve a intentar en la próxima vuelta.
     */
    suspend fun refresh(): List<NotificationItem> {
        val fresh = refreshNotifications()
        refreshDashboard()
        return fresh
    }

    private suspend fun refreshNotifications(): List<NotificationItem> {
        if (knownFor != Session.userId) {
            knownIds = null
            knownFor = Session.userId
        }
        var fresh = emptyList<NotificationItem>()
        val response = quietly { api.getNotifications(auth()) }
        if (response != null) {
            val items = response.notifications.orEmpty()
            val previous = knownIds
            if (previous != null) {
                fresh = items.filter { !it.isRead && it.id !in previous }.distinctBy { it.id }
            }
            knownIds = previous.orEmpty() + items.map { it.id }
            _state.update { it.copy(notifications = items, syncProblem = null) }
        }
        return fresh
    }

    private suspend fun refreshDashboard() {
        when {
            Session.isAdmin -> quietly { api.getAdminSummary(auth()) }?.let { summary ->
                _state.update { it.copy(adminSummary = summary) }
            }
            Session.isGuard -> {
                val today = colombiaToday()
                val pending = quietly { api.getVisitsSummary(auth(), status = "pendiente", dateFrom = today, pageSize = 5) }
                val inside = quietly { api.getVisitsSummary(auth(), inside = "true", pageSize = 5) }
                _state.update { current ->
                    current.copy(
                        // Las que esperan son las que todavía no entraron.
                        guardPending = pending?.visits.orEmpty().filter { it.enteredAt == null },
                        guardPendingTotal = pending?.total ?: current.guardPendingTotal,
                        guardInside = inside?.visits ?: current.guardInside,
                        guardInsideTotal = inside?.total ?: current.guardInsideTotal
                    )
                }
            }
            else -> {
                val today = colombiaToday()
                val visits = quietly { api.getVisitsSummary(auth(), status = "pendiente", dateFrom = today, pageSize = 5) }
                val packages = quietly { api.getPackagesSummary(auth(), status = "pendiente", pageSize = 5) }
                val announcements = quietly { api.getAnnouncementsSummary(auth(), unread = "true", pageSize = 3) }
                val reservations = quietly { api.getReservationsSummary(auth(), dateFrom = today) }
                _state.update { current ->
                    current.copy(
                        pendingVisits = visits?.visits?.filter { it.enteredAt == null } ?: current.pendingVisits,
                        waitingPackages = packages?.packages ?: current.waitingPackages,
                        waitingPackagesTotal = packages?.let { maxOf(it.total, it.packages.orEmpty().size) }
                            ?: current.waitingPackagesTotal,
                        unreadAnnouncements = announcements?.announcements ?: current.unreadAnnouncements,
                        unreadAnnouncementsTotal = announcements?.unreadCount ?: current.unreadAnnouncementsTotal,
                        upcomingReservations = reservations?.reservations
                            ?.filter { it.status !in setOf("rechazada", "cancelada") }
                            ?.sortedWith(compareBy({ it.date }, { it.timeSlot }))
                            ?.take(3)
                            ?: current.upcomingReservations
                    )
                }
            }
        }
        _state.update { it.copy(dashboardLoading = false) }
    }

    /**
     * Una consulta del inicio que, si falla, no interrumpe: deja una línea pequeña al final y la
     * pantalla sigue con lo que ya tenía. Devuelve el cuerpo de la respuesta o null.
     */
    private suspend fun <T> quietly(request: suspend () -> Response<T>): T? {
        return try {
            val response = request()
            if (response.isSuccessful) {
                response.body()
            } else {
                _state.update { it.copy(syncProblem = "No se pudo actualizar todo lo del inicio. Se intenta de nuevo en un momento.") }
                null
            }
        } catch (exception: CancellationException) {
            throw exception
        } catch (exception: Exception) {
            _state.update { it.copy(syncProblem = "Sin conexión: el inicio se actualiza cuando vuelva el internet.") }
            null
        }
    }

    fun markRead(item: NotificationItem) {
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo marcar como leída") { api.markNotificationRead(auth(), item.id) }
            } ?: return@launch
            _state.update { current ->
                current.copy(notifications = current.notifications.map { if (it.id == item.id) it.copy(isRead = true) else it })
            }
        }
    }

    /** El residente deja entrar (o no) a quien lo busca en la portería. */
    fun decideVisit(visit: Visit, approve: Boolean) {
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo enviar tu respuesta a la portería") {
                    api.decideVisit(auth(), visit.id, VisitDecisionRequest(if (approve) "aprobada" else "rechazada"))
                }
            } ?: return@launch
            _state.update { current -> current.copy(pendingVisits = current.pendingVisits.filter { it.id != visit.id }) }
            showSuccess(
                if (approve) "Listo: la portería ya sabe que ${visit.visitorName} puede entrar."
                else "Listo: la portería ya sabe que no autorizaste la entrada de ${visit.visitorName}."
            )
        }
    }
}
