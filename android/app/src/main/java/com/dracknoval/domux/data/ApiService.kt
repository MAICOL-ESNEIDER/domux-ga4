package com.dracknoval.domux.data

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query

interface ApiService {
    @POST("api/auth/login")
    suspend fun login(@Body body: LoginRequest): Response<LoginResponse>

    @GET("api/users")
    suspend fun getUsers(@Header("Authorization") auth: String): Response<UsersListResponse>

    @POST("api/users")
    suspend fun createUser(
        @Header("Authorization") auth: String,
        @Body body: CreateUserRequest
    ): Response<CreateUserResponse>

    @PUT("api/users/{id}")
    suspend fun updateUser(
        @Header("Authorization") auth: String,
        @Path("id") id: Int,
        @Body body: UpdateUserRequest
    ): Response<CreateUserResponse>

    @PUT("api/users/{id}/password")
    suspend fun resetUserPassword(
        @Header("Authorization") auth: String,
        @Path("id") id: Int,
        @Body body: ResetPasswordRequest
    ): Response<GenericMessageResponse>

    @GET("api/residents")
    suspend fun getResidents(@Header("Authorization") auth: String): Response<ResidentsListResponse>

    @GET("api/announcements")
    suspend fun getAnnouncements(@Header("Authorization") auth: String): Response<AnnouncementsListResponse>

    @POST("api/announcements")
    suspend fun createAnnouncement(
        @Header("Authorization") auth: String,
        @Body body: CreateAnnouncementRequest
    ): Response<CreateAnnouncementResponse>

    @DELETE("api/announcements/{id}")
    suspend fun deleteAnnouncement(
        @Header("Authorization") auth: String,
        @Path("id") id: Int
    ): Response<GenericMessageResponse>

    @GET("api/pqrs")
    suspend fun getPqrs(
        @Header("Authorization") auth: String,
        @Query("status") status: String? = null,
        @Query("category") category: String? = null,
        @Query("search") search: String? = null
    ): Response<PqrsListResponse>

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

    @GET("api/common-areas")
    suspend fun getCommonAreas(@Header("Authorization") auth: String): Response<CommonAreasListResponse>

    @GET("api/reservations")
    suspend fun getReservations(@Header("Authorization") auth: String): Response<ReservationsListResponse>

    @GET("api/reservations/availability")
    suspend fun getReservationAvailability(
        @Header("Authorization") auth: String,
        @Query("commonAreaId") commonAreaId: Int,
        @Query("date") date: String
    ): Response<ReservationAvailabilityResponse>

    @POST("api/reservations")
    suspend fun createReservation(
        @Header("Authorization") auth: String,
        @Body body: CreateReservationRequest
    ): Response<CreateReservationResponse>

    @PUT("api/reservations/{id}/status")
    suspend fun updateReservationStatus(
        @Header("Authorization") auth: String,
        @Path("id") id: Int,
        @Body body: UpdateReservationStatusRequest
    ): Response<CreateReservationResponse>

    @PUT("api/reservations/{id}/cancel")
    suspend fun cancelReservation(
        @Header("Authorization") auth: String,
        @Path("id") id: Int
    ): Response<CreateReservationResponse>

    @GET("api/packages")
    suspend fun getPackages(
        @Header("Authorization") auth: String,
        @Query("status") status: String? = null,
        @Query("search") search: String? = null,
        @Query("residentId") residentId: Int? = null
    ): Response<PackagesListResponse>

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

    @GET("api/visits")
    suspend fun getVisits(@Header("Authorization") auth: String): Response<VisitsListResponse>

    @POST("api/visits")
    suspend fun registerVisit(
        @Header("Authorization") auth: String,
        @Body body: RegisterVisitRequest
    ): Response<RegisterVisitResponse>

    @GET("api/notifications")
    suspend fun getNotifications(@Header("Authorization") auth: String): Response<NotificationsListResponse>

    @PUT("api/notifications/{id}/read")
    suspend fun markNotificationRead(
        @Header("Authorization") auth: String,
        @Path("id") id: Int
    ): Response<NotificationResponse>
}

data class GenericMessageResponse(val message: String?)
