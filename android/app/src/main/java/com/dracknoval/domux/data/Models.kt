package com.dracknoval.domux.data

data class LoginRequest(val email: String, val password: String)

data class UserData(
    val id: Int,
    val name: String,
    val email: String,
    val role: String,
    val apartment: String?,
    val apartmentNumber: Int? = null,
    val lastName: String? = "",
    val fullName: String? = null,
    val phone: String? = "",
    val documentId: String? = "",
    val occupancyType: String? = "propietario",
    val isActive: Boolean = true,
    val createdAt: String? = null,
    val socialNetworks: String? = "",
    val dataProcessingConsent: Boolean = false,
    val firstName: String? = null,
    val birthDate: String? = null,
    val age: Int? = null,
    val isMinor: Boolean = false,
    val parentalConsent: Boolean = false,
    // El apartamento es una llave a la estructura de la unidad (HU-017); `apartment` es su texto.
    val apartmentId: Int? = null,
    // Solo los guardias tienen PIN para cambiar de turno (HU-010).
    val hasPin: Boolean = false
)

data class LoginResponse(val message: String?, val token: String?, val user: UserData?)
data class UserDataResponse(val message: String? = null, val user: UserData?)
data class PushTokenRequest(val token: String, val deviceId: String)
data class CreateUserRequest(
    val name: String,
    val email: String,
    val password: String,
    val role: String,
    val apartmentId: Int?,
    val lastName: String = "",
    val phone: String = "",
    val documentId: String = "",
    val occupancyType: String = "propietario",
    val dataProcessingConsent: Boolean = false,
    val birthDate: String? = null,
    val parentalConsent: Boolean? = null
)
data class UpdateUserRequest(
    val name: String? = null,
    val lastName: String? = null,
    val email: String? = null,
    val phone: String? = null,
    val documentId: String? = null,
    val role: String? = null,
    val apartmentId: Int? = null,
    val occupancyType: String? = null,
    val isActive: Boolean? = null,
    val dataProcessingConsent: Boolean? = null,
    val birthDate: String? = null,
    val parentalConsent: Boolean? = null
)
data class ResetPasswordRequest(val password: String)

// PIN de 4 dígitos del guardia (HU-010): el administrador lo asigna y el guardia lo usa en la tablet.
data class SetPinRequest(val pin: String)
data class GuardOption(val id: Int, val name: String)
data class GuardsListResponse(val guards: List<GuardOption>?)
data class GuardShiftRequest(val guardId: Int, val pin: String)
data class GuardShiftResponse(val message: String?, val token: String?, val user: UserData?)
data class CreateUserResponse(val message: String?, val user: UserData?)
data class UsersListResponse(
    val users: List<UserData>?,
    val page: Int = 1,
    val pageSize: Int = 25,
    val total: Int = 0,
    val totalPages: Int = 0
)

data class ResidentProfileUpdateRequest(
    val phone: String? = null,
    val email: String? = null,
    val socialNetworks: String? = null
)

data class HouseholdMemberData(
    val id: Int? = null,
    val name: String,
    val lastName: String? = null,
    val documentId: String,
    val birthDate: String,
    val phone: String? = null,
    val relationship: String,
    val otherRelationship: String? = null
)

/** Nombre y apellido del integrante; si no tiene apellido, solo el nombre. */
val HouseholdMemberData.fullName: String
    get() = listOfNotNull(name, lastName?.takeIf(String::isNotBlank)).joinToString(" ")

data class PetData(
    val id: Int? = null,
    val name: String,
    val species: String,
    val breed: String,
    val ageYears: Int,
    // Vacunación y desparasitación al día, con la fecha de la última (RN-028).
    val vaccinesUpToDate: Boolean = false,
    val lastVaccinationDate: String? = null,
    val dewormingUpToDate: Boolean = false,
    val lastDewormingDate: String? = null
)

/** Resumen de la salud de la mascota para mostrarlo en una línea. */
val PetData.healthSummary: String
    get() {
        val vaccines = if (vaccinesUpToDate) "vacunas al día" else "vacunas pendientes"
        val deworming = if (dewormingUpToDate) "desparasitación al día" else "desparasitación pendiente"
        return "$vaccines · $deworming"
    }

data class VehicleData(
    val id: Int? = null,
    val plate: String,
    val type: String,
    val makeModel: String,
    val year: Int,
    val registeredOwner: String,
    val color: String? = null
)

data class UnitResidentData(
    val id: Int,
    val name: String,
    val occupancyType: String?
)

data class ResidentialUnitData(
    val id: Int? = null,
    val apartment: String,
    val residents: List<UnitResidentData> = emptyList(),
    val parkingIdentifier: String? = null,
    val storageIdentifier: String? = null,
    val petInsurance: Boolean = false,
    val petInsurer: String? = null,
    val members: List<HouseholdMemberData> = emptyList(),
    val pets: List<PetData> = emptyList(),
    val vehicles: List<VehicleData> = emptyList()
)

data class ResidentialUnitResponse(val unit: ResidentialUnitData?)
// El parqueadero y el cuarto útil ya no se guardan aquí: se asignan en la estructura de la unidad.
data class SaveResidentialUnitRequest(
    val apartment: String,
    val petInsurance: Boolean = false,
    val petInsurer: String? = null,
    val members: List<HouseholdMemberData> = emptyList(),
    val pets: List<PetData> = emptyList(),
    val vehicles: List<VehicleData> = emptyList()
)
data class ResidentSummary(
    val id: Int,
    val name: String,
    val apartment: String?,
    val email: String? = "",
    val phone: String? = "",
    val occupancyType: String? = "propietario",
    val birthDate: String? = null,
    val age: Int? = null,
    val isMinor: Boolean = false,
    val parentalConsent: Boolean = false
)
data class ResidentsListResponse(val residents: List<ResidentSummary>?)

/**
 * Comunicado de la administración. Lleva categoría (HU-058), a veces torre (HU-061) y fecha de
 * vencimiento (HU-060). Los anteriores a esas historias no traen categoría.
 */
data class Announcement(
    val id: Int,
    val title: String,
    val message: String,
    val createdAt: String?,
    val authorName: String?,
    val eventDate: String? = null,
    val eventTime: String? = null,
    val mediaUrl: String? = null,
    val mediaType: String? = null,
    val category: String? = null,
    val categoryLabel: String? = null,
    val towerId: Int? = null,
    val towerName: String? = null,
    val expiresAt: String? = null,
    val isExpired: Boolean = false,
    // Solo el residente tiene comunicados sin leer (HU-059).
    val isRead: Boolean = false,
    // Solo la administración ve cuántos apartamentos lo leyeron y de cuántos (HU-062).
    val readApartments: Int? = null,
    val totalApartments: Int? = null
)
data class AnnouncementsListResponse(
    val announcements: List<Announcement>?,
    val page: Int = 1,
    val pageSize: Int = 50,
    val total: Int = 0,
    val totalPages: Int = 1,
    // Cuántos comunicados vigentes le faltan por leer al residente.
    val unreadCount: Int = 0
)
data class CreateAnnouncementRequest(
    val title: String,
    val message: String,
    // Una de las cinco categorías: mantenimiento, urgente, asamblea, seguridad o zonas_comunes.
    val category: String,
    // Sin torre, el comunicado es para toda la unidad.
    val towerId: Int? = null,
    // Último día vigente (AAAA-MM-DD); sin fecha, nunca vence.
    val expiresAt: String? = null,
    val eventDate: String? = null,
    val eventTime: String? = null,
    val mediaUrl: String? = null,
    val mediaType: String? = null
)
data class CreateAnnouncementResponse(val message: String?, val announcement: Announcement?)
data class AnnouncementReadResponse(
    val message: String?,
    val announcement: Announcement?,
    val unreadCount: Int = 0
)

data class Pqrs(
    val id: Int,
    val subject: String,
    val message: String,
    val status: String,
    val adminResponse: String?,
    val createdAt: String?,
    val residentName: String?,
    val residentId: Int? = null,
    val category: String? = "Petición",
    val incidentDate: String? = null,
    val incidentTime: String? = null,
    val mediaUrl: String? = null,
    val mediaType: String? = null,
    val apartment: String? = null,
    val createdByAdminId: Int? = null,
    val createdByAdministration: Boolean = false,
    val messages: List<PqrsMessageItem>? = null,
    val satisfactionRating: Int? = null,
    val satisfactionComment: String? = null,
    val satisfactionUpdatedAt: String? = null,
    val isArchived: Boolean = false,
    val archivedAt: String? = null,
    // Número único de la PQRS, como «PQRS-2026-000123» (HU-072).
    val radicado: String? = null,
    // Semáforo del plazo (HU-073): «verde», «amarillo» o «rojo»; sin valor si ya está resuelta.
    val semaphore: String? = null,
    // Días hábiles que faltan para vencer; negativo si ya venció.
    val daysRemaining: Int? = null,
    // Último día para responder (AAAA-MM-DD).
    val dueDate: String? = null
)
data class PqrsMessageItem(
    val id: Int,
    val pqrsId: Int,
    val authorId: Int?,
    val authorName: String?,
    val authorRole: String,
    val message: String?,
    val mediaUrl: String?,
    val mediaType: String?,
    val createdAt: String?
)
data class PqrsListResponse(val pqrs: List<Pqrs>?)
data class CreatePqrsRequest(
    val subject: String,
    val message: String,
    val category: String = "Petición",
    val incidentDate: String? = null,
    val incidentTime: String? = null,
    val mediaUrl: String? = null,
    val mediaType: String? = null,
    val residentId: Int? = null
)
data class CreatePqrsResponse(val message: String?, val pqrs: Pqrs?)
data class RespondPqrsRequest(
    val status: String,
    val adminResponse: String,
    val mediaUrl: String? = null,
    val mediaType: String? = null
)
data class AddPqrsMessageRequest(
    val message: String? = null,
    val mediaUrl: String? = null,
    val mediaType: String? = null
)
data class RatePqrsRequest(val rating: Int, val comment: String? = null)
data class BatchRespondPqrsRequest(
    val pqrsIds: List<Int>,
    val status: String,
    val message: String,
    val mediaUrl: String? = null,
    val mediaType: String? = null
)
data class BatchRespondPqrsResponse(
    val message: String?,
    val updatedCount: Int,
    val pqrsIds: List<Int>
)

/**
 * Zona común con sus reglas de reserva (HU-055): horario, aforo, anticipación, plazo de
 * cancelación y límite semanal. La administración las ajusta; la app las muestra y las respeta.
 */
data class CommonArea(
    val id: Int,
    val name: String,
    val openTime: String? = null,
    val closeTime: String? = null,
    val slotMinutes: Int = 0,
    // Las franjas del día, como «08:00-10:00», según el horario de la zona.
    val slots: List<String>? = null,
    // Máximo de personas; sin valor, la zona no lleva aforo.
    val capacity: Int? = null,
    val minAdvanceDays: Int = 0,
    val maxAdvanceDays: Int = 0,
    val cancelDeadlineDays: Int = 0,
    val weeklyLimit: Int = 0,
    // Día de la semana en que cierra por mantenimiento (0 es lunes); sin valor, no cierra.
    val maintenanceWeekday: Int? = null
)
data class CommonAreasListResponse(val areas: List<CommonArea>?)
data class Reservation(
    val id: Int,
    val commonAreaId: Int,
    val commonAreaName: String?,
    val date: String,
    val timeSlot: String,
    val status: String,
    val residentName: String?,
    val residentId: Int? = null,
    val apartment: String? = null,
    val createdByAdminId: Int? = null,
    val createdByAdministration: Boolean = false,
    val messages: List<ReservationMessageItem>? = null,
    val isArchived: Boolean = false,
    val archivedAt: String? = null,
    val requestedByMinor: Boolean = false,
    // Cuántas personas asistirán, si quien reservó lo dijo.
    val attendees: Int? = null,
    // Último día en que el residente puede cancelar (AAAA-MM-DD) y si todavía está a tiempo.
    val cancelUntil: String? = null,
    val canCancel: Boolean = false
)
data class ReservationMessageItem(
    val id: Int,
    val reservationId: Int,
    val authorId: Int?,
    val authorName: String?,
    val authorRole: String,
    val message: String?,
    val mediaUrl: String?,
    val mediaType: String?,
    val createdAt: String?
)
data class ReservationsListResponse(val reservations: List<Reservation>?)
data class CreateReservationRequest(
    val commonAreaId: Int,
    val date: String,
    val timeSlot: String,
    val residentId: Int? = null,
    val message: String? = null,
    val mediaUrl: String? = null,
    val mediaType: String? = null,
    val attendees: Int? = null
)
data class AddReservationMessageRequest(
    val message: String? = null,
    val mediaUrl: String? = null,
    val mediaType: String? = null
)
data class ReservationCalendarResponse(
    val commonAreaId: Int,
    val year: Int,
    val month: Int,
    // Días en que ya no queda ninguna franja libre.
    val blockedDates: List<String>?,
    // Días en que la zona cierra por mantenimiento.
    val closedDates: List<String>? = null
)
data class CreateReservationResponse(val message: String?, val reservation: Reservation?)
data class ReservationAvailabilityResponse(
    val commonAreaId: Int,
    val date: String,
    val availableSlots: List<String>?,
    val occupiedSlots: List<String>?,
    // La zona está cerrada ese día por mantenimiento.
    val closed: Boolean = false
)
data class UpdateReservationStatusRequest(val status: String)

data class ExcelFileResponse(
    val message: String? = null,
    val fileName: String,
    val mimeType: String? = null,
    val base64: String,
    val pqrsCount: Int? = null,
    val reservationsCount: Int? = null,
    val auditLogsCount: Int? = null,
    val archivedPqrsCount: Int? = null,
    val archivedReservationsCount: Int? = null
)

data class ImportCensusRequest(val fileBase64: String, val fileName: String)

data class ImportCensusResponse(
    val message: String?,
    val createdUsers: Int = 0,
    val updatedUsers: Int = 0,
    val unitsProcessed: Int = 0,
    val errors: List<String>? = null
)

data class PackageItem(
    val id: Int,
    val description: String?,
    val status: String,
    val createdAt: String?,
    val deliveredAt: String?,
    val residentName: String?,
    val registeredByName: String?,
    val residentId: Int? = null,
    val apartment: String? = null,
    val mediaUrl: String? = null,
    val mediaType: String? = null,
    val eventDate: String? = null,
    val eventTime: String? = null,
    val deliveredTo: String? = null,
    val isDeleted: Boolean = false,
    val deletedAt: String? = null,
    // Transportadora y número de guía (HU-047).
    val carrier: String? = null,
    val trackingNumber: String? = null,
    // Cuándo llegó a la portería y cuántas horas lleva sin reclamar; claimAlert es
    // «naranja» (más de 48 h), «rojo» (más de 72 h) o null (HU-049, RN-018).
    val arrivedAt: String? = null,
    val hoursWaiting: Int? = null,
    val claimAlert: String? = null,
    // El residente ya generó un código de entrega que sigue vigente (HU-048).
    val hasPickupCode: Boolean = false
)
data class PackagesListResponse(val packages: List<PackageItem>?)
data class RegisterPackageRequest(
    val residentId: Int,
    val description: String?,
    val mediaUrl: String? = null,
    val mediaType: String? = null,
    val eventDate: String? = null,
    val eventTime: String? = null,
    val status: String = "pendiente",
    val carrier: String? = null,
    val trackingNumber: String? = null
)
data class RegisterPackageResponse(val message: String?, val packageItem: PackageItem?)
// pickupCode es el PIN de 6 dígitos o el texto del QR del código de entrega (HU-048).
data class DeliverPackageRequest(val receivedBy: String, val pickupCode: String? = null)
data class UpdatePackageStatusRequest(val status: String)

// Código de entrega: el QR y el PIN solo llegan cuando el residente lo genera (HU-048).
data class PickupCodeData(val qrData: String, val pin: String)
data class PickupCodeResponse(
    val message: String?,
    val pickupCode: PickupCodeData?,
    val packageItem: PackageItem?
)
data class PickupLookupRequest(val code: String)
data class PickupLookupResponse(val packageItem: PackageItem?)

data class Visit(
    val id: Int,
    val visitorName: String,
    val type: String,
    val createdAt: String?,
    val residentName: String?,
    val registeredByName: String?,
    val residentId: Int? = null,
    val apartment: String? = null,
    val visitorDocument: String? = "",
    val visitorPhotoUrl: String? = null,
    val visitorPhotoType: String? = null,
    val mediaConsent: Boolean = false,
    val description: String? = null,
    val approvalStatus: String = "pendiente",
    val authorizationMethod: String? = null,
    val enteredAt: String? = null,
    val exitedAt: String? = null,
    val exitReturning: Boolean = false,
    val qrPassId: Int? = null,
    val events: List<VisitEvent>? = null,
    // Estadía que el guardia anotó (en minutos), cuánto lleva adentro y si ya se pasó (HU-031).
    val expectedStayMinutes: Int? = null,
    val insideMinutes: Int? = null,
    val isOverstay: Boolean = false
)
data class VisitsListResponse(
    val visits: List<Visit>?,
    val page: Int = 1,
    val pageSize: Int = 50,
    val total: Int = 0,
    val totalPages: Int = 1
)
data class VisitEvent(
    val id: Int,
    val type: String,
    val method: String,
    val actorName: String?,
    val returningToday: Boolean,
    val createdAt: String?
)
data class RegisterVisitRequest(
    val residentId: Int,
    val visitorName: String,
    val type: String,
    val visitorDocument: String? = null,
    val mediaConsent: Boolean = false,
    val mediaUrl: String? = null,
    val mediaType: String? = null,
    val description: String? = null,
    val expectedStayMinutes: Int? = null
)
data class RegisterVisitResponse(val message: String?, val visit: Visit?)
// El cuerpo de la entrada es opcional: solo trae la estadía prevista si el guardia la anota ahora.
data class VisitEntryRequest(val expectedStayMinutes: Int? = null)
data class VisitDecisionRequest(val decision: String)
data class VisitExitRequest(val returningToday: Boolean)
data class VisitQrPass(
    val id: Int,
    val residentId: Int,
    val validFrom: String,
    val validUntil: String,
    val maxPeople: Int,
    val registeredPeople: Int,
    val remainingPeople: Int,
    val revoked: Boolean,
    val token: String? = null,
    val qrData: String? = null,
    // Los nombres que el residente escribió al crear el QR (HU-033).
    val visitorNames: List<String>? = null
)
data class VisitQrPassListResponse(val qrPasses: List<VisitQrPass>?)
data class CreateVisitQrPassRequest(
    val validFrom: String,
    val validUntil: String,
    val maxPeople: Int,
    val visitorNames: List<String>? = null
)
data class VisitQrPassResponse(val qrPass: VisitQrPass?)
data class VisitQrInspectionResponse(
    val qrPass: VisitQrPass?,
    val residentName: String?,
    val apartment: String?,
    val inside: List<Visit>?,
    val canRegister: Boolean = false,
    val registeredVisits: List<Visit>? = null,
    val linkableVisits: List<Visit>? = null,
    // Los nombres del QR que todavía no tienen una visita registrada (HU-033).
    val pendingVisitorNames: List<String>? = null
)
data class QrVisitorEntryRequest(
    val visitorName: String? = null,
    val visitId: Int? = null,
    val expectedStayMinutes: Int? = null
)
data class QrVisitorExitRequest(val visitId: Int, val returningToday: Boolean)

data class NotificationItem(
    val id: Int,
    val userId: Int,
    val title: String,
    val message: String,
    val type: String,
    val isRead: Boolean,
    val createdAt: String?
)
data class NotificationsListResponse(val notifications: List<NotificationItem>?)
data class NotificationResponse(val message: String?, val notification: NotificationItem?)

// Algunos errores traen datos para actuar: el parqueadero libre que se sugiere cuando el elegido
// ya estaba ocupado, o que ya no queda ninguno libre (HU-039).
data class ErrorResponse(
    val error: String?,
    val noFreeSpots: Boolean? = null,
    val suggestedSpot: ParkingSpotData? = null
)

/** Lee los datos extra de un error; null si el cuerpo no se entiende. */
fun detalleDeError(cuerpoError: String?): ErrorResponse? = try {
    com.google.gson.Gson().fromJson(cuerpoError, ErrorResponse::class.java)
} catch (_: Exception) {
    null
}

fun mensajeDeError(codigo: Int, cuerpoError: String?): String {
    val detalle = try {
        com.google.gson.Gson().fromJson(cuerpoError, ErrorResponse::class.java)?.error
    } catch (_: Exception) {
        null
    }
    return when (codigo) {
        401 -> detalle ?: "Tu sesión venció o las credenciales no son válidas. Inicia sesión de nuevo."
        403 -> detalle ?: "No tienes permiso para hacer esta acción."
        404 -> detalle ?: "No se encontró lo que buscabas."
        409 -> detalle ?: "Ya existe un registro con esos datos."
        else -> detalle ?: "Ocurrió un error (código $codigo)."
    }
}
