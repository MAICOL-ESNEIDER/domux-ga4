// Models.kt — clases de datos (data class) que representan lo que la app ENVÍA y
// RECIBE del backend. Mismo patrón enseñado en GA1: una data class por estructura
// de JSON, con nombres de propiedad que coinciden EXACTAMENTE con las llaves del JSON.

package com.dracknoval.domux.data

// ======================= LOGIN =======================

// Lo que enviamos al iniciar sesión.
data class LoginRequest(
    val email: String,
    val password: String
)

// Datos del usuario autenticado (vienen dentro de LoginResponse y se usan en toda la app).
// role puede ser "ADMIN", "RESIDENT" o "GUARD".
// apartment solo aplica a residentes; en los demás roles llega null.
data class UserData(
    val id: Int,
    val name: String,
    val email: String,
    val role: String,
    val apartment: String?
)

// Lo que responde el backend si el login es correcto.
data class LoginResponse(
    val message: String?,
    val token: String?,
    val user: UserData?
)

// ======================= USUARIOS (solo Admin) =======================

// Lo que el admin envía para crear un residente o un guardia nuevo.
data class CreateUserRequest(
    val name: String,
    val email: String,
    val password: String,
    val role: String,           // "RESIDENT" o "GUARD"
    val apartment: String?      // obligatorio si role = "RESIDENT", si no, null
)

data class CreateUserResponse(
    val message: String?,
    val user: UserData?
)

data class UsersListResponse(
    val users: List<UserData>?
)

// Lista liviana de residentes (id + nombre + apto), usada por el guardia para elegir
// a quién le llegó un paquete o a quién visita alguien, y por el admin.
data class ResidentSummary(
    val id: Int,
    val name: String,
    val apartment: String?
)

data class ResidentsListResponse(
    val residents: List<ResidentSummary>?
)

// ======================= ANUNCIOS / AVISOS =======================

data class Announcement(
    val id: Int,
    val title: String,
    val message: String,
    val createdAt: String?,
    val authorName: String?
)

data class AnnouncementsListResponse(
    val announcements: List<Announcement>?
)

// Lo que el admin envía para publicar un anuncio nuevo.
data class CreateAnnouncementRequest(
    val title: String,
    val message: String
)

data class CreateAnnouncementResponse(
    val message: String?,
    val announcement: Announcement?
)

// ======================= PQRS =======================

data class Pqrs(
    val id: Int,
    val subject: String,
    val message: String,
    val status: String,          // "abierta" | "en_proceso" | "resuelta"
    val adminResponse: String?,
    val createdAt: String?,
    val residentName: String?
)

data class PqrsListResponse(
    val pqrs: List<Pqrs>?
)

// Lo que el residente envía para crear una PQRS.
data class CreatePqrsRequest(
    val subject: String,
    val message: String
)

data class CreatePqrsResponse(
    val message: String?,
    val pqrs: Pqrs?
)

// Lo que el admin envía para responder/actualizar el estado de una PQRS.
data class RespondPqrsRequest(
    val status: String,
    val adminResponse: String
)

// ======================= ZONAS COMUNES Y RESERVAS =======================

data class CommonArea(
    val id: Int,
    val name: String
)

data class CommonAreasListResponse(
    val areas: List<CommonArea>?
)

data class Reservation(
    val id: Int,
    val commonAreaId: Int,
    val commonAreaName: String?,
    val date: String,
    val timeSlot: String,
    val status: String,          // "activa" | "cancelada"
    val residentName: String?
)

data class ReservationsListResponse(
    val reservations: List<Reservation>?
)

data class CreateReservationRequest(
    val commonAreaId: Int,
    val date: String,
    val timeSlot: String
)

data class CreateReservationResponse(
    val message: String?,
    val reservation: Reservation?
)

// ======================= PAQUETES =======================

data class PackageItem(
    val id: Int,
    val description: String?,
    val status: String,          // "pendiente" | "entregado"
    val createdAt: String?,
    val deliveredAt: String?,
    val residentName: String?,
    val registeredByName: String?
)

data class PackagesListResponse(
    val packages: List<PackageItem>?
)

// Lo que el guardia envía al registrar un paquete nuevo.
data class RegisterPackageRequest(
    val residentId: Int,
    val description: String?
)

data class RegisterPackageResponse(
    val message: String?,
    val packageItem: PackageItem?
)

// ======================= VISITANTES / DOMICILIARIOS =======================

data class Visit(
    val id: Int,
    val visitorName: String,
    val type: String,            // "visitante" | "domiciliario"
    val createdAt: String?,
    val residentName: String?,
    val registeredByName: String?
)

data class VisitsListResponse(
    val visits: List<Visit>?
)

// Lo que el guardia envía al registrar un ingreso.
data class RegisterVisitRequest(
    val residentId: Int,
    val visitorName: String,
    val type: String
)

data class RegisterVisitResponse(
    val message: String?,
    val visit: Visit?
)

// ======================= RESPUESTA GENÉRICA DE ERROR =======================

// El backend responde { "error": "..." } cuando algo sale mal (401, 403, 404, 400...).
// La usamos para leer response.errorBody() y mostrar un mensaje humano en pantalla.
data class ErrorResponse(
    val error: String?
)

// Convierte cualquier respuesta NO exitosa de Retrofit en un mensaje legible,
// interpretando además los códigos que enseñamos en GA2/GA3 (401, 403, 404).
fun mensajeDeError(codigo: Int, cuerpoError: String?): String {
    val detalle = try {
        com.google.gson.Gson().fromJson(cuerpoError, ErrorResponse::class.java)?.error
    } catch (e: Exception) {
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
