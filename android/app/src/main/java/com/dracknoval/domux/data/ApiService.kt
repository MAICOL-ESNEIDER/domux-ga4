// ApiService.kt — la "lista de servicios" que ofrece el backend de Domux.
// Mismo patrón de GA1-GA3: una interfaz con las anotaciones de Retrofit, funciones
// "suspend" y Response<T> como envoltura (para poder revisar isSuccessful/code()).

package com.dracknoval.domux.data

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path

interface ApiService {

    // --------- Autenticación (no requiere token) ---------
    @POST("api/auth/login")
    suspend fun login(@Body body: LoginRequest): Response<LoginResponse>

    // --------- Usuarios (solo Admin) ---------
    @GET("api/users")
    suspend fun getUsers(@Header("Authorization") auth: String): Response<UsersListResponse>

    @POST("api/users")
    suspend fun createUser(
        @Header("Authorization") auth: String,
        @Body body: CreateUserRequest
    ): Response<CreateUserResponse>

    // Lista liviana de residentes: la usan Admin y Guardia (para elegir a quién
    // asignar un paquete o una visita).
    @GET("api/residents")
    suspend fun getResidents(@Header("Authorization") auth: String): Response<ResidentsListResponse>

    // --------- Anuncios (todos los roles autenticados) ---------
    @GET("api/announcements")
    suspend fun getAnnouncements(@Header("Authorization") auth: String): Response<AnnouncementsListResponse>

    @POST("api/announcements")
    suspend fun createAnnouncement(
        @Header("Authorization") auth: String,
        @Body body: CreateAnnouncementRequest
    ): Response<CreateAnnouncementResponse>

    // --------- PQRS ---------
    // Admin ve todas, Residente ve solo las suyas (el backend decide según el token).
    @GET("api/pqrs")
    suspend fun getPqrs(@Header("Authorization") auth: String): Response<PqrsListResponse>

    @POST("api/pqrs")
    suspend fun createPqrs(
        @Header("Authorization") auth: String,
        @Body body: CreatePqrsRequest
    ): Response<CreatePqrsResponse>

    @PUT("api/pqrs/{id}/respond")
    suspend fun respondPqrs(
        @Header("Authorization") auth: String,
        @Path("id") id: Int,
        @Body body: RespondPqrsRequest
    ): Response<CreatePqrsResponse>

    // --------- Zonas comunes y reservas ---------
    @GET("api/common-areas")
    suspend fun getCommonAreas(@Header("Authorization") auth: String): Response<CommonAreasListResponse>

    @GET("api/reservations")
    suspend fun getReservations(@Header("Authorization") auth: String): Response<ReservationsListResponse>

    @POST("api/reservations")
    suspend fun createReservation(
        @Header("Authorization") auth: String,
        @Body body: CreateReservationRequest
    ): Response<CreateReservationResponse>

    @PUT("api/reservations/{id}/cancel")
    suspend fun cancelReservation(
        @Header("Authorization") auth: String,
        @Path("id") id: Int
    ): Response<CreateReservationResponse>

    // --------- Paquetes ---------
    @GET("api/packages")
    suspend fun getPackages(@Header("Authorization") auth: String): Response<PackagesListResponse>

    @POST("api/packages")
    suspend fun registerPackage(
        @Header("Authorization") auth: String,
        @Body body: RegisterPackageRequest
    ): Response<RegisterPackageResponse>

    @PUT("api/packages/{id}/deliver")
    suspend fun deliverPackage(
        @Header("Authorization") auth: String,
        @Path("id") id: Int
    ): Response<RegisterPackageResponse>

    // --------- Visitantes / domiciliarios ---------
    @GET("api/visits")
    suspend fun getVisits(@Header("Authorization") auth: String): Response<VisitsListResponse>

    @POST("api/visits")
    suspend fun registerVisit(
        @Header("Authorization") auth: String,
        @Body body: RegisterVisitRequest
    ): Response<RegisterVisitResponse>
}
