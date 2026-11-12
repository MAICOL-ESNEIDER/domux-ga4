"""Portería vehicular: vehículos de visitantes con parqueadero y vehículos de residentes.

Aquí están las reglas de HU-035 a HU-041 (RN-013, RN-014 y RN-015); las rutas
solo leen la solicitud y responden. Nada se borra: cada entrada y cada
movimiento quedan como historial (ADR-013).

Todas las funciones lanzan ApiError con un mensaje claro cuando algo no es
válido o choca con otra cosa. Ninguna hace commit: lo hace la ruta, para que
todo lo que cambió se guarde junto o no se guarde nada.

Dos guardias pueden registrar vehículos al mismo tiempo, así que ocupar y
liberar un parqueadero se hace con una sola instrucción UPDATE que pregunta y
cambia a la vez («pásalo a ocupado solo si seguía libre»). Así la base de datos
deja pasar a uno solo y el otro recibe un parqueadero distinto (RN-013).
"""

from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from config import visitor_parking_max_days
from errors import ApiError
from extensions import db
from models import (
    MOVEMENT_TYPES,
    ParkingSpot,
    Vehicle,
    VehicleMovement,
    Visit,
    VisitorVehicleEntry,
)
from time_utils import utc_now
from validators import normalize_plate, validate_colombian_plate

#: Cuántos vehículos de residentes devuelve la búsqueda por placa.
RESIDENT_SEARCH_LIMIT = 20

#: Mínimo de caracteres para buscar una placa: con menos saldrían casi todos los vehículos.
MIN_PLATE_SEARCH = 2


# ---------------------------------------------------------------------------
# Lectura de datos
# ---------------------------------------------------------------------------

def clean_plate(value):
    """Lee una placa de la solicitud: sin espacios ni guiones, en mayúsculas y colombiana."""
    if value is None:
        raise ApiError("La placa es obligatoria.")
    if (error := validate_colombian_plate(value)) is not None:
        raise ApiError(error)
    return normalize_plate(value)


def _whole_id(value, label):
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ApiError(f"El campo '{label}' debe ser un número entero positivo.")
    return value


def _flag(value, label):
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ApiError(f"El campo '{label}' debe ser verdadero o falso.")
    return value


# ---------------------------------------------------------------------------
# Parqueaderos de visitantes (HU-037)
# ---------------------------------------------------------------------------

def visitor_spots_query():
    """Los parqueaderos de visitantes vigentes, en orden de código."""
    return ParkingSpot.query.filter(
        ParkingSpot.kind == "visitante", ParkingSpot.retired_at.is_(None)
    ).order_by(ParkingSpot.code)


def free_visitor_spots(excluding_id=None):
    """Los parqueaderos de visitantes libres; el primero es el que se sugiere."""
    query = visitor_spots_query().filter(ParkingSpot.occupied.is_(False))
    if excluding_id is not None:
        query = query.filter(ParkingSpot.id != excluding_id)
    return query.all()


def _set_occupied(spot_id, occupied):
    """Cambia el parqueadero a ocupado (o libre) solo si estaba en el estado contrario.

    Devuelve True si el cambio lo hizo esta solicitud. Es una sola instrucción
    UPDATE: si dos guardias eligen el mismo parqueadero a la vez, la base deja
    pasar a uno solo y al otro le devuelve False (RN-013).
    """
    result = db.session.execute(
        update(ParkingSpot)
        .where(
            ParkingSpot.id == spot_id,
            ParkingSpot.occupied.is_(not occupied),
            ParkingSpot.retired_at.is_(None),
        )
        .values(occupied=occupied)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def _no_free_spots_error():
    return ApiError(
        "No hay parqueaderos de visitantes libres. Puedes registrar la entrada sin parqueadero.",
        409,
        noFreeSpots=True,
        suggestedSpot=None,
    )


def _spot_taken_error(spot):
    """El parqueadero elegido ya estaba ocupado: se rechaza y se sugiere otro libre (HU-039)."""
    others = free_visitor_spots(excluding_id=spot.id)
    if not others:
        return ApiError(
            f"El parqueadero {spot.code} ya está ocupado y no hay otros de visitantes libres. "
            "Puedes registrar la entrada sin parqueadero.",
            409,
            noFreeSpots=True,
            suggestedSpot=None,
        )
    return ApiError(
        f"El parqueadero {spot.code} ya está ocupado. Te sugerimos el {others[0].code}.",
        409,
        noFreeSpots=False,
        suggestedSpot=others[0].to_dict(),
    )


def visitor_board(now=None):
    """La vista de ocupación de los parqueaderos de visitantes (HU-037).

    Trae cada parqueadero con la entrada que lo ocupa (placa, apartamento y tiempo),
    cuántos hay libres y ocupados, el que se sugiere y los vehículos que están
    adentro sin parqueadero.
    """
    now = now or utc_now()
    spots = visitor_spots_query().all()
    inside = VisitorVehicleEntry.query.filter(VisitorVehicleEntry.exited_at.is_(None)).all()
    by_spot = {entry.spot_id: entry for entry in inside if entry.spot_id is not None}
    items = []
    for spot in spots:
        item = spot.to_dict()
        entry = by_spot.get(spot.id)
        item["entry"] = entry.to_dict(now) if entry else None
        items.append(item)
    free = [spot for spot in spots if not spot.occupied]
    return {
        "spots": items,
        "total": len(spots),
        "free": len(free),
        "occupied": len(spots) - len(free),
        "suggestedSpotId": free[0].id if free else None,
        "withoutSpot": [entry.to_dict(now) for entry in inside if entry.spot_id is None],
        "overdue": sum(1 for entry in inside if entry.is_overdue(now)),
        "maxDays": visitor_parking_max_days(),
    }


# ---------------------------------------------------------------------------
# Entrada y salida de vehículos visitantes (HU-035, HU-036, HU-038 y HU-039)
# ---------------------------------------------------------------------------

def _visit_for_entry(visit_id):
    """La visita a la que pertenece el vehículo: debe estar autorizada y no haber salido (RN-010)."""
    visit = db.session.get(Visit, _whole_id(visit_id, "visitId"))
    if visit is None:
        raise ApiError("La visita no existe.", 404)
    if visit.approval_status != "aprobada":
        raise ApiError(
            "La visita no está autorizada: el residente, una llamada o un QR vigente "
            "deben autorizarla antes de registrar el vehículo.",
            409,
        )
    if visit.exited_at is not None:
        raise ApiError(
            "Esta visita ya registró su salida: registra de nuevo su entrada "
            "antes de ingresar el vehículo.",
            409,
        )
    return visit


def _chosen_spot(spot_id):
    spot = db.session.get(ParkingSpot, _whole_id(spot_id, "spotId"))
    if spot is None or spot.is_retired:
        raise ApiError("El parqueadero no existe o ya fue retirado.", 404)
    if spot.kind != "visitante":
        raise ApiError(f"El parqueadero {spot.code} no es de visitantes.")
    return spot


def _assign_spot(data):
    """Ocupa el parqueadero que corresponde y lo devuelve; None si se registra sin parqueadero.

    Con spotId se usa ese; si ya estaba ocupado se rechaza y se sugiere otro libre.
    Sin spotId se toma el primero libre. Con withoutSpot el vehículo entra sin
    parqueadero, algo que el guardia decide cuando no queda ninguno libre.
    """
    without_spot = _flag(data.get("withoutSpot"), "withoutSpot")
    spot_id = data.get("spotId")
    if without_spot and spot_id is not None:
        raise ApiError("Indica un parqueadero o que el vehículo entra sin parqueadero, no las dos cosas.")
    if without_spot:
        return None
    if spot_id is not None:
        spot = _chosen_spot(spot_id)
        if not _set_occupied(spot.id, True):
            raise _spot_taken_error(spot)
        db.session.expire(spot)
        return spot
    for spot in free_visitor_spots():
        if _set_occupied(spot.id, True):
            db.session.expire(spot)
            return spot
    raise _no_free_spots_error()


def register_visitor_entry(data, guard):
    """Registra la entrada de un vehículo visitante y le asigna parqueadero (HU-035 y HU-036).

    El vehículo pertenece a una visita autorizada (RN-010). Antes de guardar se
    comprueba que el parqueadero siga libre y que la placa no esté ya adentro
    (RN-013); si dos guardias chocan, los índices únicos de la base lo impiden.
    """
    plate = clean_plate(data.get("plate"))
    visit = _visit_for_entry(data.get("visitId"))
    open_entry = VisitorVehicleEntry.query.filter_by(plate=plate, exited_at=None).first()
    if open_entry is not None:
        where = f" en el parqueadero {open_entry.spot.code}" if open_entry.spot else ""
        raise ApiError(f"El vehículo {plate} ya figura adentro{where}.", 409)
    spot = _assign_spot(data)
    entry = VisitorVehicleEntry(
        plate=plate,
        visit_id=visit.id,
        apartment_id=visit.resident.apartment_id if visit.resident else None,
        spot_id=spot.id if spot else None,
        entered_at=utc_now(),
        registered_by=guard.id,
    )
    db.session.add(entry)
    try:
        db.session.flush()
    except IntegrityError as error:
        # Otra solicitud ganó la carrera justo antes: se deshace todo y se explica.
        db.session.rollback()
        raise _entry_conflict(plate, spot) from error
    return entry


def _entry_conflict(plate, spot):
    if VisitorVehicleEntry.query.filter_by(plate=plate, exited_at=None).first() is not None:
        return ApiError(f"El vehículo {plate} ya figura adentro.", 409)
    if spot is not None:
        spot = db.session.get(ParkingSpot, spot.id)
        return _spot_taken_error(spot)
    return ApiError("No se pudo registrar la entrada: inténtalo de nuevo.", 409)


def register_visitor_exit(entry, guard):
    """Registra la salida de un vehículo visitante y deja libre su parqueadero (HU-038, RN-014).

    La salida se marca solo si la entrada seguía abierta: si otro guardia la
    cerró un instante antes, no se libera dos veces un parqueadero que ya
    pudo asignarse a otro vehículo.
    """
    result = db.session.execute(
        update(VisitorVehicleEntry)
        .where(VisitorVehicleEntry.id == entry.id, VisitorVehicleEntry.exited_at.is_(None))
        .values(exited_at=utc_now(), exited_by_id=guard.id)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise ApiError("Este vehículo ya registró su salida.", 409)
    if entry.spot_id is not None:
        _set_occupied(entry.spot_id, False)
    db.session.expire(entry)
    return entry


def entries_query(inside=None, overdue=None, plate=None, apartment_id=None, now=None):
    """Historial de entradas de vehículos visitantes, de la más reciente a la más antigua (HU-041)."""
    query = VisitorVehicleEntry.query
    if inside is True:
        query = query.filter(VisitorVehicleEntry.exited_at.is_(None))
    elif inside is False:
        query = query.filter(VisitorVehicleEntry.exited_at.isnot(None))
    if overdue:
        cutoff = (now or utc_now()) - _max_stay()
        query = query.filter(
            VisitorVehicleEntry.exited_at.is_(None), VisitorVehicleEntry.entered_at <= cutoff
        )
    if plate:
        query = query.filter(VisitorVehicleEntry.plate.contains(normalize_plate(plate), autoescape=True))
    if apartment_id is not None:
        query = query.filter(VisitorVehicleEntry.apartment_id == apartment_id)
    return query.order_by(VisitorVehicleEntry.entered_at.desc(), VisitorVehicleEntry.id.desc())


def entry_counts(plate=None, apartment_id=None, now=None):
    """Cuántas entradas hay en cada situación entre las de esa placa y ese apartamento (HU-088).

    Son los números de la consulta de la web: los que siguen adentro, los que ya pasaron el tiempo
    máximo, los que ya salieron y el total. Los vencidos también cuentan entre los que están adentro.
    """
    def count(**filters):
        return entries_query(plate=plate, apartment_id=apartment_id, now=now, **filters).order_by(None).count()

    return {
        "inside": count(inside=True),
        "overdue": count(overdue=True),
        "exited": count(inside=False),
        "all": count(),
    }


def _max_stay():
    """Cuánto puede quedarse un vehículo visitante: 3 días o el plazo de la unidad (RN-015)."""
    return timedelta(days=visitor_parking_max_days())


# ---------------------------------------------------------------------------
# Vehículos de residentes (HU-040)
# ---------------------------------------------------------------------------

def _last_movements(vehicle_ids):
    """El último movimiento de cada vehículo: {id del vehículo: movimiento}."""
    if not vehicle_ids:
        return {}
    latest = (
        db.session.query(
            VehicleMovement.vehicle_id, db.func.max(VehicleMovement.id).label("last_id")
        )
        .filter(VehicleMovement.vehicle_id.in_(vehicle_ids))
        .group_by(VehicleMovement.vehicle_id)
        .subquery()
    )
    rows = VehicleMovement.query.join(latest, VehicleMovement.id == latest.c.last_id).all()
    return {movement.vehicle_id: movement for movement in rows}


def resident_vehicle_dict(vehicle, last_movement):
    """El vehículo con su apartamento y si está adentro, según su último movimiento."""
    unit = vehicle.unit
    return {
        **vehicle.to_dict(),
        "apartmentId": unit.apartment_id,
        "apartment": unit.apartment,
        "isInside": last_movement is not None and last_movement.movement_type == "entrada",
        "lastMovementType": last_movement.movement_type if last_movement else None,
        "lastMovementAt": last_movement.to_dict()["createdAt"] if last_movement else None,
    }


def search_resident_vehicles(text):
    """Busca vehículos vigentes de residentes por una parte de la placa (HU-040)."""
    plate_text = normalize_plate(text) if isinstance(text, str) else ""
    if len(plate_text) < MIN_PLATE_SEARCH:
        raise ApiError(f"Escribe al menos {MIN_PLATE_SEARCH} caracteres de la placa.")
    vehicles = (
        Vehicle.query.filter(Vehicle.retired_at.is_(None))
        .filter(Vehicle.plate.contains(plate_text, autoescape=True))
        .order_by(Vehicle.plate)
        .limit(RESIDENT_SEARCH_LIMIT)
        .all()
    )
    last = _last_movements([vehicle.id for vehicle in vehicles])
    return [resident_vehicle_dict(vehicle, last.get(vehicle.id)) for vehicle in vehicles]


def register_resident_movement(plate_text, movement_type, guard):
    """Registra la entrada o la salida de un vehículo de residente con la hora del servidor.

    Devuelve (vehículo, movimiento, aviso). Si el movimiento repite el anterior
    (dos entradas seguidas, por ejemplo) se guarda igual, para no frenar la
    portería, y el aviso se lo cuenta al guardia.
    """
    plate = clean_plate(plate_text)
    if movement_type not in MOVEMENT_TYPES:
        raise ApiError("El tipo de movimiento debe ser 'entrada' o 'salida'.")
    vehicle = Vehicle.query.filter_by(plate=plate, retired_at=None).first()
    if vehicle is None:
        raise ApiError(f"No hay un vehículo de residente con la placa {plate}.", 404)
    previous = _last_movements([vehicle.id]).get(vehicle.id)
    warning = None
    if previous is not None and previous.movement_type == movement_type:
        warning = f"El vehículo ya tenía registrada una {movement_type}; se guardó de todas formas."
    elif previous is None and movement_type == "salida":
        warning = "El vehículo no tenía una entrada registrada; se guardó la salida de todas formas."
    movement = VehicleMovement(
        vehicle_id=vehicle.id, plate=plate, movement_type=movement_type, registered_by=guard.id
    )
    db.session.add(movement)
    db.session.flush()
    return vehicle, movement, warning
