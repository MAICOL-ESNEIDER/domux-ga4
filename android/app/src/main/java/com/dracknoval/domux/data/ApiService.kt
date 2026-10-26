package com.dracknoval.domux.data

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.HTTP
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query

interface ApiService {
    @POST("api/auth/login")
    suspend fun login(@Body body: LoginRequest): Response<LoginResponse>

    @GET("api/auth/session")
    suspend fun currentSession(@Header("Authorization") auth: String): Response<UserDataResponse>

    @POST("api/push-tokens")
    suspend fun registerPushToken(
        @Header("Authorization") auth: String,
        @Body body: PushTokenRequest
    ): Response<GenericMessageResponse>

    @HTTP(method = "DELETE", path = "api/push-tokens", hasBody = true)
    suspend fun deletePushToken(
        @Header("Authorization") auth: String,
        @Body body: PushTokenRequest
    ): Response<GenericMessageResponse>

    @GET("api/users")
    suspend fun getUsers(
        @Header("Authorization") auth: String,
        @Query("page") page: Int = 1,
        @Query("pageSize") pageSize: Int = 25,
        @Query("search") search: String? = null,
        @Query("role") role: String? = null,
        @Query("occupancyType") occupancyType: String? = null,
        @Query("apartmentFrom") apartmentFrom: String? = null,
        @Query("apartmentTo") apartmentTo: String? = null,
        @Query("hasPets") hasPets: String? = null,
        @Query("hasVehicles") hasVehicles: String? = null,
        @Query("hasParking") hasParking: String? = null,
        @Query("hasStorage") hasStorage: String? = null,
        @Query("minAge") minAge: String? = null,
        @Query("maxAge") maxAge: String? = null,
        @Query("isActive") isActive: String? = null
    ): Response<UsersListResponse>

    @GET("api/admin/units")
    suspend fun getUnit(
        @Header("Authorization") auth: String,
        @Query("apartment") apartment: String
    ): Response<ResidentialUnitResponse>

    @PUT("api/admin/units")
    suspend fun saveUnit(
        @Header("Authorization") auth: String,
        @Body body: SaveResidentialUnitRequest
    ): Response<ResidentialUnitResponse>

    @GET("api/profile")
    suspend fun getProfile(@Header("Authorization") auth: String): Response<UserDataResponse>

    @PUT("api/profile")
    suspend fun updateProfile(
        @Header("Authorization") auth: String,
        @Body body: ResidentProfileUpdateRequest
    ): Response<UserDataResponse>

    @GET("api/profile/unit")
    suspend fun getMyUnit(@Header("Authorization") auth: String): Response<ResidentialUnitResponse>

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
    suspend fun getResidents(
        @Header("Authorization") auth: String,
        @Query("search") search: String? = null
    ): Response<ResidentsListResponse>

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
        @Query("search") search: String? = null,
        @Query("residentId") residentId: Int? = null
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

    @POST("api/pqrs/{id}/messages")
    suspend fun addPqrsMessage(
        @Header("Authorization") auth: String,
        @Path("id") id: Int,
        @Body body: AddPqrsMessageRequest
    ): Response<CreatePqrsResponse>

    @PUT("api/pqrs/{id}/satisfaction")
    suspend fun ratePqrs(
        @Header("Authorization") auth: String,
        @Path("id") id: Int,
        @Body body: RatePqrsRequest
    ): Response<CreatePqrsResponse>

    @POST("api/pqrs/batch/respond")
    suspend fun respondPqrsBatch(
        @Header("Authorization") auth: String,
        @Body body: BatchRespondPqrsRequest
    ): Response<BatchRespondPqrsResponse>

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

    @GET("api/reservations/calendar")
    suspend fun getReservationCalendar(
        @Header("Authorization") auth: String,
        @Query("commonAreaId") commonAreaId: Int,
        @Query("year") year: Int,
        @Query("month") month: Int
    ): Response<ReservationCalendarResponse>

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

    @POST("api/reservations/{id}/messages")
    suspend fun addReservationMessage(
        @Header("Authorization") auth: String,
        @Path("id") id: Int,
        @Body body: AddReservationMessageRequest
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
        @Path("id") id: Int,
        @Body body: DeliverPackageRequest
    ): Response<RegisterPackageResponse>

    @GET("api/visits")
    suspend fun getVisits(
        @Header("Authorization") auth: String,
        @Query("search") search: String? = null,
        @Query("status") status: String? = null
    ): Response<VisitsListResponse>

    @POST("api/visits")
    suspend fun registerVisit(
        @Header("Authorization") auth: String,
        @Body body: RegisterVisitRequest
    ): Response<RegisterVisitResponse>

    @PUT("api/visits/{id}/decision")
    suspend fun decideVisit(
        @Header("Authorization") auth: String,
        @Path("id") id: Int,
        @Body body: VisitDecisionRequest
    ): Response<RegisterVisitResponse>

    @PUT("api/visits/{id}/authorize-call")
    suspend fun authorizeVisitByCall(
        @Header("Authorization") auth: String,
        @Path("id") id: Int
    ): Response<RegisterVisitResponse>

    @POST("api/visits/{id}/entry")
    suspend fun registerVisitEntry(
        @Header("Authorization") auth: String,
        @Path("id") id: Int
    ): Response<RegisterVisitResponse>

    @POST("api/visits/{id}/exit")
    suspend fun registerVisitExit(
        @Header("Authorization") auth: String,
        @Path("id") id: Int,
        @Body body: VisitExitRequest
    ): Response<RegisterVisitResponse>

    @GET("api/visits/qr-passes")
    suspend fun getVisitQrPasses(
        @Header("Authorization") auth: String
    ): Response<VisitQrPassListResponse>

    @POST("api/visits/qr-passes")
    suspend fun createVisitQrPass(
        @Header("Authorization") auth: String,
        @Body body: CreateVisitQrPassRequest
    ): Response<VisitQrPassResponse>

    @PUT("api/visits/qr-passes/{id}/revoke")
    suspend fun revokeVisitQrPass(
        @Header("Authorization") auth: String,
        @Path("id") id: Int
    ): Response<GenericMessageResponse>

    @GET("api/visits/qr/{token}")
    suspend fun inspectVisitQr(
        @Header("Authorization") auth: String,
        @Path("token") token: String
    ): Response<VisitQrInspectionResponse>

    @POST("api/visits/qr/{token}/entry")
    suspend fun enterVisitQr(
        @Header("Authorization") auth: String,
        @Path("token") token: String,
        @Body body: QrVisitorEntryRequest
    ): Response<RegisterVisitResponse>

    @POST("api/visits/qr/{token}/exit")
    suspend fun exitVisitQr(
        @Header("Authorization") auth: String,
        @Path("token") token: String,
        @Body body: QrVisitorExitRequest
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
