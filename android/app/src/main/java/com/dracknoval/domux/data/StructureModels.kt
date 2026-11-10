package com.dracknoval.domux.data

// Estructura de la unidad: torres, apartamentos, parqueaderos y cuartos útiles
// (HU-013 a HU-016 y HU-023). Los nombres siguen las respuestas de /api/admin/...

data class TowerData(
    val id: Int,
    val name: String,
    val floors: Int,
    val apartmentCount: Int = 0
)

data class ApartmentData(
    val id: Int,
    val towerId: Int,
    val tower: String,
    val code: String,
    val floor: Int,
    val number: Int? = null,
    // Texto listo para mostrar, como «Torre 1 · Apto 101».
    val label: String,
    val residentCount: Int = 0,
    val parkingSpots: List<String>? = null,
    val storageRooms: List<String>? = null
)

data class ParkingSpotData(
    val id: Int,
    val code: String,
    // «residente» o «visitante».
    val type: String,
    val location: String? = null,
    val apartmentId: Int? = null,
    val apartment: String? = null,
    val isOccupied: Boolean = false
)

data class StorageRoomData(
    val id: Int,
    val code: String,
    val apartmentId: Int? = null,
    val apartment: String? = null
)

/** Un apartamento elegido en un formulario: su id y el texto que se le muestra a la persona. */
data class ApartmentOption(val id: Int, val label: String)

fun ApartmentData.toOption() = ApartmentOption(id, label)

// --- Respuestas ---------------------------------------------------------------

data class TowersResponse(val towers: List<TowerData>?)

data class ApartmentsResponse(
    val apartments: List<ApartmentData>?,
    val page: Int = 1,
    val pageSize: Int = 50,
    val total: Int = 0,
    val totalPages: Int = 1
)

data class FloorResponse(val message: String?, val apartments: List<ApartmentData>?)

data class ParkingSpotsResponse(
    val parkingSpots: List<ParkingSpotData>?,
    val page: Int = 1,
    val pageSize: Int = 50,
    val total: Int = 0,
    val totalPages: Int = 1
)

data class StorageRoomsResponse(
    val storageRooms: List<StorageRoomData>?,
    val page: Int = 1,
    val pageSize: Int = 50,
    val total: Int = 0,
    val totalPages: Int = 1
)

// --- Solicitudes --------------------------------------------------------------
// Estas solicitudes se mandan con un Retrofit que sí envía los nulos (RetrofitClient.structureApi):
// un apartmentId nulo significa «sin apartamento» y es lo que deja libre un parqueadero.

data class SaveTowerRequest(val name: String, val floors: Int)

data class CreateApartmentRequest(val towerId: Int, val code: String, val floor: Int?)

// Al editar no se manda la torre: un apartamento no cambia de torre.
data class UpdateApartmentRequest(val code: String, val floor: Int)

data class CreateFloorRequest(val towerId: Int, val floor: Int, val count: Int)

data class SaveParkingSpotRequest(
    val code: String,
    val type: String,
    val location: String,
    val apartmentId: Int?
)

data class SaveStorageRoomRequest(val code: String, val apartmentId: Int?)
