package com.dracknoval.domux.pantallas

import com.dracknoval.domux.data.AdminPendingReservation
import com.dracknoval.domux.data.AdminSummaryCounts
import com.dracknoval.domux.data.AdminSummaryResponse
import com.dracknoval.domux.data.AdminUrgentPqrs
import com.dracknoval.domux.data.Announcement
import com.dracknoval.domux.data.AnnouncementsListResponse
import com.dracknoval.domux.data.ApiService
import com.dracknoval.domux.data.ComplexInfo
import com.dracknoval.domux.data.ComplexInfoResponse
import com.dracknoval.domux.data.NotificationItem
import com.dracknoval.domux.data.NotificationsListResponse
import com.dracknoval.domux.data.PackageItem
import com.dracknoval.domux.data.PackagesListResponse
import com.dracknoval.domux.data.Reservation
import com.dracknoval.domux.data.ReservationsListResponse
import com.dracknoval.domux.data.SearchGroup
import com.dracknoval.domux.data.SearchResponse
import com.dracknoval.domux.data.SearchResult
import com.dracknoval.domux.data.Visit
import com.dracknoval.domux.data.VisitsListResponse
import com.dracknoval.domux.defaultSearchPlaces
import com.google.gson.Gson
import retrofit2.Response
import java.lang.reflect.InvocationHandler
import java.lang.reflect.Method
import java.lang.reflect.ParameterizedType
import java.lang.reflect.Proxy
import java.lang.reflect.WildcardType

/**
 * Una conexión «de mentira» con el servidor para las pruebas de pantallas: contesta al instante con
 * datos de ejemplo (la unidad inventada de la versión reducida) y nunca sale a internet.
 *
 * Cada llamada de [ApiService] devuelve el dato que se arma aquí según su nombre. Lo que todavía no
 * tiene dato de ejemplo contesta «vacío» (sin errores), para que la pantalla se dibuje igual.
 * Las fechas son fijas: así las fotos no cambian de un día a otro.
 */
object DatosDeMentira {

    fun api(): ApiService = Proxy.newProxyInstance(
        ApiService::class.java.classLoader,
        arrayOf(ApiService::class.java),
        InvocationHandler { proxy, metodo, argumentos ->
            val argumentosSeguros: Array<out Any?> = argumentos ?: emptyArray<Any?>()
            when (metodo.name) {
                "toString" -> "ApiService de mentira"
                "hashCode" -> System.identityHashCode(proxy)
                "equals" -> proxy === argumentosSeguros.firstOrNull()
                else -> Response.success(cuerpoPara(metodo, argumentosSeguros))
            }
        }
    ) as ApiService

    private fun cuerpoPara(metodo: Method, argumentos: Array<out Any?>): Any? = when (metodo.name) {
        "getComplexInfo" -> ComplexInfoResponse(unidad())
        "getNotifications" -> NotificationsListResponse(notificaciones())
        "getAdminSummary" -> resumenDeAdministracion()
        // getVisitsSummary(auth, status, dateFrom, inside, pageSize, view): la cuarta dice si piden las que están dentro.
        "getVisitsSummary" ->
            if (argumentos.getOrNull(3) == "true") {
                VisitsListResponse(visitasAdentro(), total = 1)
            } else {
                VisitsListResponse(visitasQueEsperan(), total = 2)
            }
        "getPackagesSummary" -> PackagesListResponse(paquetes(), total = 2)
        "getAnnouncementsSummary" -> AnnouncementsListResponse(comunicados(), total = 2, unreadCount = 2)
        "getReservationsSummary" -> ReservationsListResponse(reservas())
        // search(auth, text, place)
        "search" -> busqueda(argumentos.getOrNull(1) as? String ?: "", argumentos.getOrNull(2) as? String)
        else -> cuerpoVacio(metodo)
    }

    /**
     * Lo que contesta una llamada que todavía no tiene dato de ejemplo: un objeto «vacío» del tipo
     * que la llamada espera (o nada, si no se puede armar). En una función «suspend» el último
     * parámetro es la continuación, y ahí está escrito el tipo de la respuesta.
     */
    private fun cuerpoVacio(metodo: Method): Any? {
        val continuacion = metodo.genericParameterTypes.lastOrNull() as? ParameterizedType ?: return null
        val argumento = continuacion.actualTypeArguments.firstOrNull() ?: return null
        val respuesta = (argumento as? WildcardType)?.lowerBounds?.firstOrNull() ?: argumento
        val tipoDelCuerpo = (respuesta as? ParameterizedType)?.actualTypeArguments?.firstOrNull() ?: return null
        return try {
            Gson().fromJson<Any?>("{}", tipoDelCuerpo)
        } catch (_: Exception) {
            null
        }
    }

    // --- Datos de ejemplo (la unidad inventada: torres 1 y 2, apartamentos 101, 201, 202...) ---

    private fun unidad() = ComplexInfo(
        name = "Altos de DOMUX",
        address = "Calle 10 # 20-30, Medellín",
        portalPhone = "604 555 0100"
    )

    private fun notificaciones() = listOf(
        NotificationItem(
            id = 1, userId = 1, title = "Reserva aprobada",
            message = "Tu reserva del Salón social para el 21/11/2026 fue aprobada.",
            type = "reserva", isRead = false, createdAt = "2026-11-19T09:30:00"
        ),
        NotificationItem(
            id = 2, userId = 1, title = "Paquete en portería",
            message = "Llegó un paquete de Servientrega a tu nombre.",
            type = "paquete", isRead = false, createdAt = "2026-11-18T16:10:00"
        ),
        NotificationItem(
            id = 3, userId = 1, title = "Comunicado nuevo",
            message = "Corte de agua el sábado 21/11 de 8:00 a 12:00.",
            type = "comunicado", isRead = true, createdAt = "2026-11-17T08:00:00"
        )
    )

    private fun resumenDeAdministracion() = AdminSummaryResponse(
        counts = AdminSummaryCounts(
            pqrsOpen = 7, pqrsOverdue = 2, pqrsDueSoon = 3,
            reservationsPending = 4, packagesOver48 = 3, packagesOver72 = 1, unreadNotifications = 2
        ),
        urgentPqrs = listOf(
            AdminUrgentPqrs(
                id = 12, radicado = "PQRS-2026-000012", subject = "Ruido en la torre 2 después de las 10 p. m.",
                category = "Queja", residentName = "Carlos Pérez", apartment = "Torre 2 · Apto 202",
                semaphore = "rojo", daysRemaining = -1
            ),
            AdminUrgentPqrs(
                id = 15, radicado = "PQRS-2026-000015", subject = "Bombillo dañado en el pasillo del piso 2",
                category = "Petición", residentName = "Gustavo Restrepo Arango", apartment = "Torre 1 · Apto 201",
                semaphore = "amarillo", daysRemaining = 2
            )
        ),
        pendingReservations = listOf(
            AdminPendingReservation(
                id = 42, commonAreaName = "Piscina", date = "2026-11-23", timeSlot = "10:00-12:00",
                attendees = 6, residentName = "Diana Ríos Zapata", apartment = "Torre 2 · Apto 202"
            ),
            AdminPendingReservation(
                id = 43, commonAreaName = "Salón social", date = "2026-11-28", timeSlot = "14:00-18:00",
                attendees = 25, residentName = "Natalia Correa Giraldo", apartment = "Torre 2 · Apto 101"
            )
        )
    )

    private fun visitasQueEsperan() = listOf(
        Visit(
            id = 11, visitorName = "Laura Restrepo", type = "visitante", createdAt = "2026-11-20T10:05:00",
            residentName = "María Gómez", registeredByName = "Guardia Principal", residentId = 6,
            apartment = "Torre 1 · Apto 101", expectedStayMinutes = 120
        ),
        Visit(
            id = 12, visitorName = "Andrés Ocampo (Rappi)", type = "domiciliario", createdAt = "2026-11-20T10:20:00",
            residentName = "María Gómez", registeredByName = "Guardia Principal", residentId = 6,
            apartment = "Torre 1 · Apto 101"
        )
    )

    private fun visitasAdentro() = listOf(
        Visit(
            id = 13, visitorName = "Carlos Vélez", type = "contratista", createdAt = "2026-11-20T08:30:00",
            residentName = "Carlos Pérez", registeredByName = "Guardia Principal", residentId = 9,
            apartment = "Torre 2 · Apto 202", approvalStatus = "aprobada", enteredAt = "2026-11-20T08:40:00",
            expectedStayMinutes = 180, insideMinutes = 95
        )
    )

    private fun paquetes() = listOf(
        PackageItem(
            id = 31, description = "Caja mediana", status = "pendiente", createdAt = "2026-11-18T16:10:00",
            deliveredAt = null, residentName = "María Gómez", registeredByName = "Guardia Principal",
            residentId = 6, apartment = "Torre 1 · Apto 101", carrier = "Servientrega",
            trackingNumber = "SV-100234", arrivedAt = "2026-11-18T16:10:00", hoursWaiting = 50, claimAlert = "naranja"
        ),
        PackageItem(
            id = 32, description = "Sobre de documentos", status = "pendiente", createdAt = "2026-11-20T09:00:00",
            deliveredAt = null, residentName = "María Gómez", registeredByName = "Guardia Principal",
            residentId = 6, apartment = "Torre 1 · Apto 101", carrier = "Coordinadora",
            trackingNumber = "CO-558120", arrivedAt = "2026-11-20T09:00:00", hoursWaiting = 6
        )
    )

    private fun comunicados() = listOf(
        Announcement(
            id = 21, title = "Corte de agua el sábado",
            message = "El sábado 21 de noviembre no habrá agua de 8:00 a 12:00 por el lavado de los tanques.",
            createdAt = "2026-11-17T08:00:00", authorName = "Administración Domux",
            category = "mantenimiento", categoryLabel = "Mantenimiento"
        ),
        Announcement(
            id = 22, title = "Asamblea general de copropietarios",
            message = "Se cita a la asamblea general para revisar el presupuesto del próximo año.",
            createdAt = "2026-11-16T15:00:00", authorName = "Administración Domux",
            eventDate = "2026-11-28", eventTime = "18:00", category = "asamblea", categoryLabel = "Asamblea"
        )
    )

    private fun reservas() = listOf(
        Reservation(
            id = 41, commonAreaId = 1, commonAreaName = "Salón social", date = "2026-11-21",
            timeSlot = "14:00-18:00", status = "aprobada", residentName = "María Gómez", residentId = 6,
            apartment = "Torre 1 · Apto 101", canCancel = true
        ),
        Reservation(
            id = 44, commonAreaId = 2, commonAreaName = "Piscina", date = "2026-11-23",
            timeSlot = "10:00-12:00", status = "pendiente", residentName = "María Gómez", residentId = 6,
            apartment = "Torre 1 · Apto 101", canCancel = true
        )
    )

    private fun busqueda(texto: String, lugar: String?) = SearchResponse(
        query = texto,
        place = lugar ?: "todo",
        places = defaultSearchPlaces(),
        tooShort = false,
        groups = listOf(
            SearchGroup(
                type = "personas", label = "Personas", more = false,
                items = listOf(
                    SearchResult("personas", 6, "María Gómez", "Residente · propietaria", 1, "Torre 1 · Apto 101", null),
                    SearchResult("personas", 17, "Mariana Ruiz Cano", "Residente · arrendataria", 8, "Torre 2 · Apto 301", null)
                )
            ),
            SearchGroup(
                type = "apartamentos", label = "Apartamentos", more = false,
                items = listOf(
                    SearchResult("apartamentos", 1, "Torre 1 · Apto 101", "3 personas · 2 vehículos", 1, "Torre 1 · Apto 101", null)
                )
            ),
            SearchGroup(
                type = "vehiculos", label = "Vehículos", more = false,
                items = listOf(
                    SearchResult("vehiculos", 7, "MAR123", "Mazda 3 · María Gómez", 1, "Torre 1 · Apto 101", "residente")
                )
            ),
            SearchGroup(
                type = "pqrs", label = "PQRS", more = true,
                items = listOf(
                    SearchResult("pqrs", 12, "PQRS-2026-000012 · Ruido en la torre 2", "Queja · en proceso", 5, "Torre 2 · Apto 202", null)
                )
            )
        )
    )
}
