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
    val firstName: String? = null
)

data class LoginResponse(val message: String?, val token: String?, val user: UserData?)
data class UserDataResponse(val message: String? = null, val user: UserData?)
data class PushTokenRequest(val token: String, val deviceId: String)
data class CreateUserRequest(
    val name: String,
    val email: String,
    val password: String,
    val role: String,
    val apartment: String?,
    val lastName: String = "",
    val phone: String = "",
    val documentId: String = "",
    val occupancyType: String = "propietario",
    val dataProcessingConsent: Boolean = false
)
data class UpdateUserRequest(
    val name: String? = null,
    val lastName: String? = null,
    val email: String? = null,
    val phone: String? = null,
    val documentId: String? = null,
    val role: String? = null,
    val apartment: String? = null,
    val occupancyType: String? = null,
    val isActive: Boolean? = null,
    val dataProcessingConsent: Boolean? = null
)
data class ResetPasswordRequest(val password: String)
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

data class PetData(
    val id: Int? = null,
    val name: String,
    val species: String,
    val breed: String,
    val ageYears: Int
)

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
    val funeralPlan: Boolean = false,
    val funeralProvider: String? = null,
    val members: List<HouseholdMemberData> = emptyList(),
    val pets: List<PetData> = emptyList(),
    val vehicles: List<VehicleData> = emptyList()
)

data class ResidentialUnitResponse(val unit: ResidentialUnitData?)
data class SaveResidentialUnitRequest(
    val apartment: String,
    val parkingIdentifier: String? = null,
    val storageIdentifier: String? = null,
    val petInsurance: Boolean = false,
    val petInsurer: String? = null,
    val funeralPlan: Boolean = false,
    val funeralProvider: String? = null,
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
    val occupancyType: String? = "propietario"
)
data class ResidentsListResponse(val residents: List<ResidentSummary>?)

data class Announcement(
    val id: Int,
    val title: String,
    val message: String,
    val createdAt: String?,
    val authorName: String?,
    val eventDate: String? = null,
    val eventTime: String? = null,
    val mediaUrl: String? = null,
    val mediaType: String? = null
)
data class AnnouncementsListResponse(val announcements: List<Announcement>?)
data class CreateAnnouncementRequest(
    val title: String,
    val message: String,
    val eventDate: String? = null,
    val eventTime: String? = null,
    val mediaUrl: String? = null,
    val mediaType: String? = null
)
data class CreateAnnouncementResponse(val message: String?, val announcement: Announcement?)

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
    val satisfactionUpdatedAt: String? = null
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

data class CommonArea(val id: Int, val name: String)
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
    val messages: List<ReservationMessageItem>? = null
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
    val mediaType: String? = null
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
    val blockedDates: List<String>?
)
data class CreateReservationResponse(val message: String?, val reservation: Reservation?)
data class ReservationAvailabilityResponse(
    val commonAreaId: Int,
    val date: String,
    val availableSlots: List<String>?,
    val occupiedSlots: List<String>?
)
data class UpdateReservationStatusRequest(val status: String)

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
    val deletedAt: String? = null
)
data class PackagesListResponse(val packages: List<PackageItem>?)
data class RegisterPackageRequest(
    val residentId: Int,
    val description: String?,
    val mediaUrl: String? = null,
    val mediaType: String? = null,
    val eventDate: String? = null,
    val eventTime: String? = null,
    val status: String = "pendiente"
)
data class RegisterPackageResponse(val message: String?, val packageItem: PackageItem?)
data class DeliverPackageRequest(val receivedBy: String)
data class UpdatePackageStatusRequest(val status: String)

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
    val events: List<VisitEvent>? = null
)
data class VisitsListResponse(val visits: List<Visit>?)
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
    val description: String? = null
)
data class RegisterVisitResponse(val message: String?, val visit: Visit?)
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
    val qrData: String? = null
)
data class VisitQrPassListResponse(val qrPasses: List<VisitQrPass>?)
data class CreateVisitQrPassRequest(
    val validFrom: String,
    val validUntil: String,
    val maxPeople: Int
)
data class VisitQrPassResponse(val qrPass: VisitQrPass?)
data class VisitQrInspectionResponse(
    val qrPass: VisitQrPass?,
    val residentName: String?,
    val apartment: String?,
    val inside: List<Visit>?,
    val canRegister: Boolean = false,
    val registeredVisits: List<Visit>? = null,
    val linkableVisits: List<Visit>? = null
)
data class QrVisitorEntryRequest(val visitorName: String? = null, val visitId: Int? = null)
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

data class ErrorResponse(val error: String?)

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
