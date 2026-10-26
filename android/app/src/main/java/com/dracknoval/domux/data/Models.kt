package com.dracknoval.domux.data

data class LoginRequest(val email: String, val password: String)

data class UserData(
    val id: Int,
    val name: String,
    val email: String,
    val role: String,
    val apartment: String?,
    val lastName: String? = "",
    val fullName: String? = null,
    val phone: String? = "",
    val documentId: String? = "",
    val occupancyType: String? = "propietario",
    val isActive: Boolean = true,
    val createdAt: String? = null
)

data class LoginResponse(val message: String?, val token: String?, val user: UserData?)
data class CreateUserRequest(
    val name: String,
    val email: String,
    val password: String,
    val role: String,
    val apartment: String?,
    val lastName: String = "",
    val phone: String = "",
    val documentId: String = "",
    val occupancyType: String = "propietario"
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
    val isActive: Boolean? = null
)
data class ResetPasswordRequest(val password: String)
data class CreateUserResponse(val message: String?, val user: UserData?)
data class UsersListResponse(val users: List<UserData>?)
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
    val apartment: String? = null
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
data class RespondPqrsRequest(val status: String, val adminResponse: String)

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
    val apartment: String? = null
)
data class ReservationsListResponse(val reservations: List<Reservation>?)
data class CreateReservationRequest(
    val commonAreaId: Int,
    val date: String,
    val timeSlot: String,
    val residentId: Int? = null
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
    val eventTime: String? = null
)
data class PackagesListResponse(val packages: List<PackageItem>?)
data class RegisterPackageRequest(
    val residentId: Int,
    val description: String?,
    val mediaUrl: String? = null,
    val mediaType: String? = null,
    val eventDate: String? = null,
    val eventTime: String? = null
)
data class RegisterPackageResponse(val message: String?, val packageItem: PackageItem?)

data class Visit(
    val id: Int,
    val visitorName: String,
    val type: String,
    val createdAt: String?,
    val residentName: String?,
    val registeredByName: String?,
    val residentId: Int? = null,
    val apartment: String? = null,
    val visitorDocument: String? = ""
)
data class VisitsListResponse(val visits: List<Visit>?)
data class RegisterVisitRequest(
    val residentId: Int,
    val visitorName: String,
    val type: String,
    val visitorDocument: String? = null
)
data class RegisterVisitResponse(val message: String?, val visit: Visit?)

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
