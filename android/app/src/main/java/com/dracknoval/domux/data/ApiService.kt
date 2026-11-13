package com.dracknoval.domux.data

import okhttp3.ResponseBody
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

    // Cambio de guardia en la tablet de portería (HU-010): lista de guardias con PIN y cambio con PIN.
    @GET("api/auth/guards")
    suspend fun getGuards(@Header("Authorization") auth: String): Response<GuardsListResponse>

    @POST("api/auth/guard-shift")
    suspend fun guardShift(
        @Header("Authorization") auth: String,
        @Body body: GuardShiftRequest
    ): Response<GuardShiftResponse>

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

    // Datos de la unidad residencial (HU-077): nombre, NIT, dirección, teléfono de portería y logo.
    @GET("api/unit-info")
    suspend fun getComplexInfo(@Header("Authorization") auth: String): Response<ComplexInfoResponse>

    @GET("api/unit-info/logo")
    suspend fun getComplexLogo(@Header("Authorization") auth: String): Response<ResponseBody>

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

    @PUT("api/admin/users/{id}/pin")
    suspend fun setGuardPin(
        @Header("Authorization") auth: String,
        @Path("id") id: Int,
        @Body body: SetPinRequest
    ): Response<CreateUserResponse>

    // Con id devuelve solo a ese residente: así una pantalla que llega con el residente ya elegido
    // lo encuentra aunque no esté entre los primeros 30 de la lista.
    @GET("api/residents")
    suspend fun getResidents(
        @Header("Authorization") auth: String,
        @Query("search") search: String? = null,
        @Query("id") id: Int? = null
    ): Response<ResidentsListResponse>

    // El residente que portería eligió, con su teléfono (el servidor anota quién lo vio).
    @GET("api/residents/{id}/contact")
    suspend fun getResidentContact(
        @Header("Authorization") auth: String,
        @Path("id") id: Int
    ): Response<ResidentContactResponse>

    // Vigentes por defecto; con archived = "true", los que ya pasaron su vencimiento (HU-060).
    // unread = "true" deja solo los que el residente no ha abierto (HU-059).
    @GET("api/announcements")
    suspend fun getAnnouncements(
        @Header("Authorization") auth: String,
        @Query("archived") archived: String? = null,
        @Query("category") category: String? = null,
        @Query("unread") unread: String? = null,
        @Query("page") page: Int? = null,
        @Query("pageSize") pageSize: Int? = null
    ): Response<AnnouncementsListResponse>

    @POST("api/announcements")
    suspend fun createAnnouncement(
        @Header("Authorization") auth: String,
        @Body body: CreateAnnouncementRequest
    ): Response<CreateAnnouncementResponse>

    // El residente abrió el comunicado: queda leído (HU-059) y cuenta para la administración (HU-062).
    @POST("api/announcements/{id}/read")
    suspend fun markAnnouncementRead(
        @Header("Authorization") auth: String,
        @Path("id") id: Int
    ): Response<AnnouncementReadResponse>

    // Retira el anuncio: deja de verse en la app, pero no se borra (TT-029).
    @PUT("api/announcements/{id}/retire")
    suspend fun retireAnnouncement(
        @Header("Authorization") auth: String,
        @Path("id") id: Int
    ): Response<GenericMessageResponse>

    @GET("api/pqrs")
    suspend fun getPqrs(
        @Header("Authorization") auth: String,
        @Query("status") status: String? = null,
        @Query("category") category: String? = null,
        @Query("search") search: String? = null,
        @Query("residentId") residentId: Int? = null,
        @Query("includeArchived") includeArchived: String? = null
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
    suspend fun getReservations(
        @Header("Authorization") auth: String,
        @Query("includeArchived") includeArchived: String? = null
    ): Response<ReservationsListResponse>

    @GET("api/admin/census-template")
    suspend fun getCensusTemplate(
        @Header("Authorization") auth: String
    ): Response<ExcelFileResponse>

    @POST("api/admin/import-census")
    suspend fun importCensus(
        @Header("Authorization") auth: String,
        @Body body: ImportCensusRequest
    ): Response<ImportCensusResponse>

    @GET("api/admin/export/legal-report")
    suspend fun exportLegalReport(
        @Header("Authorization") auth: String
    ): Response<ExcelFileResponse>

    @POST("api/admin/archive-history")
    suspend fun archiveHistory(
        @Header("Authorization") auth: String
    ): Response<ExcelFileResponse>

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

    @PUT("api/packages/{id}/status")
    suspend fun updatePackageStatus(
        @Header("Authorization") auth: String,
        @Path("id") id: Int,
        @Body body: UpdatePackageStatusRequest
    ): Response<RegisterPackageResponse>

    @DELETE("api/packages/{id}")
    suspend fun deletePackage(
        @Header("Authorization") auth: String,
        @Path("id") id: Int
    ): Response<GenericMessageResponse>

    @PUT("api/packages/{id}/restore")
    suspend fun restorePackage(
        @Header("Authorization") auth: String,
        @Path("id") id: Int
    ): Response<RegisterPackageResponse>

    // El residente dueño genera el código (QR y PIN) para que otra persona recoja su paquete (HU-048).
    @POST("api/packages/{id}/pickup-code")
    suspend fun createPickupCode(
        @Header("Authorization") auth: String,
        @Path("id") id: Int
    ): Response<PickupCodeResponse>

    // El guardia escanea el QR del código y el servidor devuelve el paquete (el texto viaja en el cuerpo, no en la dirección).
    @POST("api/packages/pickup-lookup")
    suspend fun lookupPickupCode(
        @Header("Authorization") auth: String,
        @Body body: PickupLookupRequest
    ): Response<PickupLookupResponse>

    @GET("api/visits")
    suspend fun getVisits(
        @Header("Authorization") auth: String,
        @Query("search") search: String? = null,
        @Query("status") status: String? = null,
        @Query("apartmentId") apartmentId: Int? = null,
        @Query("from") dateFrom: String? = null,
        @Query("to") dateTo: String? = null,
        // «true» trae solo las visitas que entraron y siguen adentro (HU-032).
        @Query("inside") inside: String? = null,
        @Query("page") page: Int = 1,
        @Query("pageSize") pageSize: Int = 50
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
        @Path("id") id: Int,
        @Body body: VisitEntryRequest
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

    // --- Portería vehicular (HU-035 a HU-041) ---

    @GET("api/parking/visitor-spots")
    suspend fun getVisitorSpots(
        @Header("Authorization") auth: String
    ): Response<VisitorBoardResponse>

    @POST("api/vehicle-entries")
    suspend fun registerVehicleEntry(
        @Header("Authorization") auth: String,
        @Body body: RegisterVehicleEntryRequest
    ): Response<VehicleEntryResponse>

    @PUT("api/vehicle-entries/{id}/exit")
    suspend fun registerVehicleExit(
        @Header("Authorization") auth: String,
        @Path("id") id: Int
    ): Response<VehicleEntryResponse>

    @GET("api/vehicle-entries")
    suspend fun getVehicleEntries(
        @Header("Authorization") auth: String,
        // «true» trae solo los que siguen adentro; overdue = «true», solo los que pasaron el tiempo máximo.
        @Query("inside") inside: String? = null,
        @Query("overdue") overdue: String? = null,
        @Query("plate") plate: String? = null,
        @Query("apartmentId") apartmentId: Int? = null,
        @Query("page") page: Int = 1,
        @Query("pageSize") pageSize: Int = 25
    ): Response<VehicleEntriesListResponse>

    @GET("api/resident-vehicles")
    suspend fun searchResidentVehicles(
        @Header("Authorization") auth: String,
        @Query("search") search: String
    ): Response<ResidentVehiclesResponse>

    @POST("api/resident-vehicles/{plate}/movements")
    suspend fun registerResidentMovement(
        @Header("Authorization") auth: String,
        @Path("plate") plate: String,
        @Body body: VehicleMovementRequest
    ): Response<VehicleMovementResponse>

    @GET("api/notifications")
    suspend fun getNotifications(@Header("Authorization") auth: String): Response<NotificationsListResponse>

    @PUT("api/notifications/{id}/read")
    suspend fun markNotificationRead(
        @Header("Authorization") auth: String,
        @Path("id") id: Int
    ): Response<NotificationResponse>

    // --- Listas livianas para el inicio de cada rol (sin fotos ni conversaciones) ---

    // Lo pendiente de hoy para la administración: contadores, PQRS urgentes y reservas por aprobar (HU-081).
    @GET("api/admin/summary")
    suspend fun getAdminSummary(@Header("Authorization") auth: String): Response<AdminSummaryResponse>

    // Visitas en lista liviana: «pendiente» de hoy (esperando autorización) o las que están dentro.
    @GET("api/visits")
    suspend fun getVisitsSummary(
        @Header("Authorization") auth: String,
        @Query("status") status: String? = null,
        @Query("from") dateFrom: String? = null,
        @Query("inside") inside: String? = null,
        @Query("pageSize") pageSize: Int = 5,
        @Query("view") view: String = "summary"
    ): Response<VisitsListResponse>

    // Paquetes en lista liviana (sin la foto): «pendiente» son los que esperan en portería.
    @GET("api/packages")
    suspend fun getPackagesSummary(
        @Header("Authorization") auth: String,
        @Query("status") status: String? = null,
        @Query("pageSize") pageSize: Int = 5,
        @Query("view") view: String = "summary"
    ): Response<PackagesListResponse>

    // Comunicados en lista liviana (sin foto, video, audio ni PDF): los que el residente no ha leído.
    @GET("api/announcements")
    suspend fun getAnnouncementsSummary(
        @Header("Authorization") auth: String,
        @Query("unread") unread: String? = null,
        @Query("pageSize") pageSize: Int = 3,
        @Query("view") view: String = "summary"
    ): Response<AnnouncementsListResponse>

    // Reservas en lista liviana desde una fecha (las próximas del residente).
    @GET("api/reservations")
    suspend fun getReservationsSummary(
        @Header("Authorization") auth: String,
        @Query("dateFrom") dateFrom: String? = null,
        @Query("pageSize") pageSize: Int = 10,
        @Query("view") view: String = "summary"
    ): Response<ReservationsListResponse>

    // Marca como leídas todas las notificaciones de quien consulta, en una sola llamada (HU-064).
    @PUT("api/notifications/read-all")
    suspend fun markAllNotificationsRead(@Header("Authorization") auth: String): Response<ReadAllNotificationsResponse>
}

data class GenericMessageResponse(val message: String?)
