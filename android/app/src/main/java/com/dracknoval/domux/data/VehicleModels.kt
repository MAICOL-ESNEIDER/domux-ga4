package com.dracknoval.domux.data

// Modelos de la portería vehicular (HU-035 a HU-041). Los nombres de los campos son
// exactamente los que responde el servidor (routes/vehicles.py).

/** Entrada de un vehículo visitante: placa, visita, parqueadero y cuánto lleva adentro. */
data class VisitorVehicleEntryData(
    val id: Int,
    val plate: String,
    val visitId: Int = 0,
    val visitorName: String? = null,
    val residentName: String? = null,
    val apartmentId: Int? = null,
    val apartment: String? = null,
    val spotId: Int? = null,
    val spotCode: String? = null,
    val spotLocation: String? = null,
    val enteredAt: String? = null,
    val exitedAt: String? = null,
    val isInside: Boolean = true,
    val parkedMinutes: Int = 0,
    // Días máximos de parqueo de un visitante (RN-015) y si esta entrada ya los pasó.
    val maxDays: Int = 3,
    val isOverdue: Boolean = false,
    val registeredByName: String? = null,
    val exitedByName: String? = null
)

/** Un parqueadero de visitantes y, si está ocupado, la entrada que lo ocupa (HU-037). */
data class VisitorSpotItem(
    val id: Int,
    val code: String,
    val type: String = "visitante",
    val location: String? = null,
    val apartmentId: Int? = null,
    val apartment: String? = null,
    val isOccupied: Boolean = false,
    val entry: VisitorVehicleEntryData? = null
)

/** El tablero de parqueaderos de visitantes: libres, ocupados, el sugerido y los que entraron sin parqueadero. */
data class VisitorBoardResponse(
    val spots: List<VisitorSpotItem>? = null,
    val total: Int = 0,
    val free: Int = 0,
    val occupied: Int = 0,
    val suggestedSpotId: Int? = null,
    val withoutSpot: List<VisitorVehicleEntryData>? = null,
    val overdue: Int = 0,
    val maxDays: Int = 3
)

/**
 * Registro de entrada. Sin spotId el servidor toma el primer parqueadero libre;
 * con withoutSpot = true el vehículo entra sin parqueadero (HU-036 y HU-039).
 */
data class RegisterVehicleEntryRequest(
    val plate: String,
    val visitId: Int,
    val spotId: Int? = null,
    val withoutSpot: Boolean? = null
)

data class VehicleEntryResponse(val message: String? = null, val vehicleEntry: VisitorVehicleEntryData? = null)

data class VehicleEntriesListResponse(
    val vehicleEntries: List<VisitorVehicleEntryData>? = null,
    val page: Int = 1,
    val pageSize: Int = 25,
    val total: Int = 0,
    val totalPages: Int = 1
)

/** Vehículo de un residente, con su apartamento y si está adentro según su último movimiento (HU-040). */
data class ResidentVehicleItem(
    val id: Int,
    val plate: String,
    val type: String = "",
    val makeModel: String = "",
    val year: Int = 0,
    val registeredOwner: String = "",
    val color: String? = null,
    val apartmentId: Int? = null,
    val apartment: String? = null,
    val isInside: Boolean = false,
    val lastMovementType: String? = null,
    val lastMovementAt: String? = null
)

data class ResidentVehiclesResponse(val vehicles: List<ResidentVehicleItem>? = null)

/** type es «entrada» o «salida». */
data class VehicleMovementRequest(val type: String)

data class VehicleMovementData(
    val id: Int,
    val vehicleId: Int = 0,
    val plate: String = "",
    val type: String = "",
    val createdAt: String? = null,
    val registeredByName: String? = null
)

/** warning avisa al guardia si el movimiento repite el anterior; el movimiento se guarda igual. */
data class VehicleMovementResponse(
    val message: String? = null,
    val movement: VehicleMovementData? = null,
    val vehicle: ResidentVehicleItem? = null,
    val warning: String? = null
)
