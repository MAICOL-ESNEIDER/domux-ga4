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

/**
 * Rutas de la estructura de la unidad (API-EST-01 a API-EST-05); solo las usa el administrador.
 * Quitar algo no lo borra: queda retirado y deja de salir en las listas (ADR-013).
 */
interface StructureApiService {
    @GET("api/admin/towers")
    suspend fun getTowers(@Header("Authorization") auth: String): Response<TowersResponse>

    @POST("api/admin/towers")
    suspend fun createTower(
        @Header("Authorization") auth: String,
        @Body body: SaveTowerRequest
    ): Response<GenericMessageResponse>

    @PUT("api/admin/towers/{id}")
    suspend fun updateTower(
        @Header("Authorization") auth: String,
        @Path("id") id: Int,
        @Body body: SaveTowerRequest
    ): Response<GenericMessageResponse>

    @DELETE("api/admin/towers/{id}")
    suspend fun retireTower(
        @Header("Authorization") auth: String,
        @Path("id") id: Int
    ): Response<GenericMessageResponse>

    @GET("api/admin/apartments")
    suspend fun getApartments(
        @Header("Authorization") auth: String,
        @Query("towerId") towerId: Int? = null,
        @Query("search") search: String? = null,
        @Query("page") page: Int = 1,
        @Query("pageSize") pageSize: Int = 50
    ): Response<ApartmentsResponse>

    @POST("api/admin/apartments")
    suspend fun createApartment(
        @Header("Authorization") auth: String,
        @Body body: CreateApartmentRequest
    ): Response<GenericMessageResponse>

    // Crea los apartamentos de un piso de una vez (HU-023): 101, 102, 103...
    @POST("api/admin/apartments/batch")
    suspend fun createFloor(
        @Header("Authorization") auth: String,
        @Body body: CreateFloorRequest
    ): Response<FloorResponse>

    @PUT("api/admin/apartments/{id}")
    suspend fun updateApartment(
        @Header("Authorization") auth: String,
        @Path("id") id: Int,
        @Body body: UpdateApartmentRequest
    ): Response<GenericMessageResponse>

    @DELETE("api/admin/apartments/{id}")
    suspend fun retireApartment(
        @Header("Authorization") auth: String,
        @Path("id") id: Int
    ): Response<GenericMessageResponse>

    @GET("api/admin/parking-spots")
    suspend fun getParkingSpots(
        @Header("Authorization") auth: String,
        @Query("type") type: String? = null,
        @Query("search") search: String? = null,
        @Query("page") page: Int = 1,
        @Query("pageSize") pageSize: Int = 50
    ): Response<ParkingSpotsResponse>

    @POST("api/admin/parking-spots")
    suspend fun createParkingSpot(
        @Header("Authorization") auth: String,
        @Body body: SaveParkingSpotRequest
    ): Response<GenericMessageResponse>

    @PUT("api/admin/parking-spots/{id}")
    suspend fun updateParkingSpot(
        @Header("Authorization") auth: String,
        @Path("id") id: Int,
        @Body body: SaveParkingSpotRequest
    ): Response<GenericMessageResponse>

    @DELETE("api/admin/parking-spots/{id}")
    suspend fun retireParkingSpot(
        @Header("Authorization") auth: String,
        @Path("id") id: Int
    ): Response<GenericMessageResponse>

    @GET("api/admin/storage-rooms")
    suspend fun getStorageRooms(
        @Header("Authorization") auth: String,
        @Query("search") search: String? = null,
        @Query("page") page: Int = 1,
        @Query("pageSize") pageSize: Int = 50
    ): Response<StorageRoomsResponse>

    @POST("api/admin/storage-rooms")
    suspend fun createStorageRoom(
        @Header("Authorization") auth: String,
        @Body body: SaveStorageRoomRequest
    ): Response<GenericMessageResponse>

    @PUT("api/admin/storage-rooms/{id}")
    suspend fun updateStorageRoom(
        @Header("Authorization") auth: String,
        @Path("id") id: Int,
        @Body body: SaveStorageRoomRequest
    ): Response<GenericMessageResponse>

    @DELETE("api/admin/storage-rooms/{id}")
    suspend fun retireStorageRoom(
        @Header("Authorization") auth: String,
        @Path("id") id: Int
    ): Response<GenericMessageResponse>
}
