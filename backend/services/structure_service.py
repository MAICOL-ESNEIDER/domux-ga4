"""Estructura de la unidad: torres, apartamentos, parqueaderos y cuartos útiles.

Aquí están las reglas de HU-013 a HU-018 y HU-023; las rutas solo leen la
solicitud y responden. Nada se borra: lo que se quita queda retirado con la
fecha y quién lo hizo (ADR-013), y su código vuelve a quedar libre (RN-008).

Todas las funciones lanzan ApiError con un mensaje claro cuando un dato no es
válido o choca con otro. Ninguna guarda en la base (commit): lo hace la ruta,
para que el cambio y su anotación en la auditoría se guarden juntos.
"""

import re

from sqlalchemy.orm import selectinload

from errors import ApiError
from extensions import db
from models import (
    APARTMENT_LABEL_SEPARATOR,
    PARKING_KINDS,
    Apartment,
    ParkingSpot,
    ResidentialUnit,
    StorageRoom,
    Tower,
)
from services.audit_service import add_audit_log

#: Límites que evitan datos absurdos (un error de digitación, no una regla del conjunto).
MAX_FLOORS = 100
MAX_PER_FLOOR = 99


# ---------------------------------------------------------------------------
# Lectura de datos
# ---------------------------------------------------------------------------

def _text(value, label, max_length):
    """Lee un texto obligatorio: sin espacios de más y dentro del largo permitido."""
    if not isinstance(value, str) or not value.strip():
        raise ApiError(f"El campo '{label}' es obligatorio y no puede estar vacío.")
    text = " ".join(value.split())
    if len(text) > max_length:
        raise ApiError(f"El campo '{label}' no puede tener más de {max_length} caracteres.")
    return text


def _code(value, label="code"):
    """Lee un código (de apartamento, parqueadero o cuarto): en mayúsculas, así 'p-01' y 'P-01' son el mismo."""
    return _text(value, label, 20).upper()


def _whole_number(value, label, minimum, maximum):
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ApiError(
            f"El campo '{label}' debe ser un número entero entre {minimum} y {maximum}."
        )
    return value


def _id(value, label):
    if not isinstance(value, int) or isinstance(value, bool):
        raise ApiError(f"El campo '{label}' debe ser un número entero.")
    return value


def _list_in_spanish(items):
    """«a», «a y b», «a, b y c»."""
    items = [str(item) for item in items]
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} y {items[-1]}"


def natural_key(text):
    """Ordena «Torre 2» antes de «Torre 10» (los números se comparan como números)."""
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", text)]


# ---------------------------------------------------------------------------
# Torres (HU-013)
# ---------------------------------------------------------------------------

def active_towers():
    towers = Tower.query.filter(Tower.retired_at.is_(None)).all()
    return sorted(towers, key=lambda tower: natural_key(tower.name))


def find_tower(value):
    """La torre vigente con ese id; si no existe o está retirada, error 404."""
    tower = db.session.get(Tower, _id(value, "towerId"))
    if tower is None or tower.is_retired:
        raise ApiError("La torre no existe o ya fue retirada.", 404)
    return tower


def _require_free_tower_name(name, ignoring=None):
    for tower in active_towers():
        if tower is not ignoring and tower.name.casefold() == name.casefold():
            raise ApiError(f"Ya existe una torre llamada «{tower.name}».", 409)


def create_tower(data, actor):
    name = _text(data.get("name"), "name", 60)
    floors = _whole_number(data.get("floors"), "floors", 1, MAX_FLOORS)
    _require_free_tower_name(name)
    tower = Tower(name=name, floors=floors)
    db.session.add(tower)
    db.session.flush()
    add_audit_log("tower", tower.id, "created", {"name": name, "floors": floors}, actor=actor)
    return tower


def update_tower(tower, data, actor):
    before = {"name": tower.name, "floors": tower.floors}
    if "name" in data:
        name = _text(data["name"], "name", 60)
        _require_free_tower_name(name, ignoring=tower)
        tower.name = name
    if "floors" in data:
        floors = _whole_number(data["floors"], "floors", 1, MAX_FLOORS)
        highest = max((apartment.floor for apartment in tower.active_apartments), default=0)
        if floors < highest:
            raise ApiError(
                f"{tower.name} ya tiene apartamentos hasta el piso {highest}: "
                "no puede quedar con menos pisos.",
                409,
            )
        tower.floors = floors
    add_audit_log(
        "tower", tower.id, "updated",
        {"before": before, "after": {"name": tower.name, "floors": tower.floors}},
        actor=actor,
    )
    return tower


def retire_tower(tower, actor):
    """Retira una torre sin apartamentos vigentes; con apartamentos no se puede (409)."""
    count = len(tower.active_apartments)
    if count:
        raise ApiError(
            f"{tower.name} tiene {count} apartamento{'s' if count != 1 else ''} "
            f"vigente{'s' if count != 1 else ''}: retíralo{'s' if count != 1 else ''} primero.",
            409,
        )
    tower.retire(actor)
    add_audit_log("tower", tower.id, "retired", {"name": tower.name}, actor=actor)
    return tower


# ---------------------------------------------------------------------------
# Apartamentos (HU-014 y HU-023)
# ---------------------------------------------------------------------------

def floor_from_code(code):
    """El piso que sugiere un código numérico de tres o más cifras (301 es el piso 3)."""
    return int(code[:-2]) if code.isdigit() and len(code) >= 3 else None


def number_from_code(code):
    """El número del código, para ordenar y filtrar por rangos (A-101 → 101)."""
    digits = re.findall(r"\d+", code)
    return int(digits[-1]) if digits else None


def _floor_of(tower, value):
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= tower.floors:
        raise ApiError(
            f"El piso debe ser un número entre 1 y {tower.floors}, los pisos de {tower.name}."
        )
    return value


def _require_free_apartment_code(tower, code, ignoring=None):
    query = Apartment.query.filter_by(tower_id=tower.id, code=code, retired_at=None)
    if ignoring is not None:
        query = query.filter(Apartment.id != ignoring.id)
    if query.first() is not None:
        raise ApiError(f"El apartamento {code} ya existe en {tower.name}.", 409)


def _add_apartment(tower, code, floor):
    """Crea el apartamento junto con la ficha de su hogar (hay una por apartamento)."""
    apartment = Apartment(
        tower=tower, code=code, floor=floor, number=number_from_code(code),
        unit=ResidentialUnit(),
    )
    db.session.add(apartment)
    return apartment


def ensure_unit(apartment):
    """La ficha del hogar del apartamento; si por alguna razón faltara, se crea."""
    if apartment.unit is None:
        apartment.unit = ResidentialUnit()
    return apartment.unit


def find_apartment(value):
    """El apartamento vigente con ese id; si no existe o está retirado, error 404 (CA-HU-017-02)."""
    apartment = db.session.get(Apartment, _id(value, "apartmentId"))
    if apartment is None or apartment.is_retired:
        raise ApiError("El apartamento no existe o ya fue retirado.", 404)
    return apartment


def parse_apartment_text(text):
    """Separa «Torre 1 · Apto 101» (o «Torre 1 Apto 101») en (torre, código); None si no se entiende."""
    match = re.match(
        r"^\s*(?P<tower>.+?)\s*[·•|,;/–—-]?\s+(?:apto|apartamento|apt|ap)\.?\s*#?\s*"
        r"(?P<code>[A-Za-z0-9][A-Za-z0-9._/-]*)\s*$",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return None
    return " ".join(match.group("tower").split()), match.group("code").upper()


def apartment_by_text(text):
    """El apartamento vigente que nombra un texto como «Torre 1 · Apto 101», o None.

    Si la unidad tiene una sola torre también sirve «Apto 101» o solo «101».
    """
    if not isinstance(text, str):
        return None
    towers = active_towers()
    parsed = parse_apartment_text(text)
    if parsed is not None:
        tower_name, code = parsed
        wanted = {tower_name.casefold()}
        if tower_name.isdigit():
            wanted.add(f"torre {tower_name}")
        tower = next((tower for tower in towers if tower.name.casefold() in wanted), None)
    else:
        bare = re.match(
            r"^\s*(?:(?:apto|apartamento|apt|ap)\.?\s*#?\s*)?(?P<code>[A-Za-z0-9][A-Za-z0-9._/-]*)\s*$",
            text,
            re.IGNORECASE,
        )
        if bare is None or len(towers) != 1:
            return None
        tower, code = towers[0], bare.group("code").upper()
    if tower is None:
        return None
    return Apartment.query.filter_by(tower_id=tower.id, code=code, retired_at=None).first()


def apartment_from_payload(data):
    """El apartamento que indica una solicitud, por apartmentId o por el texto «Torre 1 · Apto 101».

    Devuelve None si la solicitud no indica ninguno; si indica uno que no
    existe, lanza error 404 (solo se vincula a un apartamento que existe).
    """
    if data.get("apartmentId") is not None:
        return find_apartment(data["apartmentId"])
    text = data.get("apartment")
    if text is None:
        return None
    if not isinstance(text, str):
        raise ApiError("El apartamento debe ser texto.")
    apartment = apartment_by_text(text)
    if apartment is None:
        raise ApiError(
            f"El apartamento «{text.strip()}» no existe: créalo antes en la estructura de la unidad.",
            404,
        )
    return apartment


def create_apartment(data, actor):
    tower = find_tower(data.get("towerId"))
    code = _code(data.get("code"))
    floor = data.get("floor")
    if floor is None:
        floor = floor_from_code(code)
        if floor is None:
            raise ApiError("Indica el piso del apartamento.")
    floor = _floor_of(tower, floor)
    _require_free_apartment_code(tower, code)
    apartment = _add_apartment(tower, code, floor)
    db.session.flush()
    add_audit_log(
        "apartment", apartment.id, "created",
        {"tower": tower.name, "code": code, "floor": floor}, actor=actor,
    )
    return apartment


def create_floor(data, actor):
    """Crea de una vez los apartamentos de un piso, con códigos seguidos (HU-023).

    El código es el piso seguido del número con dos cifras: el piso 3 con
    cuatro apartamentos da 301, 302, 303 y 304. Si alguno ya existe no se crea
    ninguno y el mensaje dice cuál se repite (CA-HU-023-02).
    """
    tower = find_tower(data.get("towerId"))
    floor = _floor_of(tower, data.get("floor"))
    first = _whole_number(data.get("from", 1), "from", 1, MAX_PER_FLOOR)
    if "to" in data and "count" in data:
        raise ApiError("Indica la cantidad (count) o el último número (to), no los dos.")
    if "to" in data:
        last = _whole_number(data["to"], "to", first, MAX_PER_FLOOR)
    elif "count" in data:
        count = _whole_number(data["count"], "count", 1, MAX_PER_FLOOR - first + 1)
        last = first + count - 1
    else:
        raise ApiError("Indica cuántos apartamentos tiene el piso (count).")

    codes = [f"{floor}{number:02d}" for number in range(first, last + 1)]
    taken = [
        code for (code,) in db.session.query(Apartment.code).filter(
            Apartment.tower_id == tower.id,
            Apartment.retired_at.is_(None),
            Apartment.code.in_(codes),
        )
    ]
    if taken:
        taken.sort(key=natural_key)
        plural = len(taken) > 1
        raise ApiError(
            f"No se creó ninguno: {'los apartamentos' if plural else 'el apartamento'} "
            f"{_list_in_spanish(taken)} ya {'existen' if plural else 'existe'} en {tower.name}.",
            409,
        )

    apartments = [_add_apartment(tower, code, floor) for code in codes]
    db.session.flush()
    add_audit_log(
        "tower", tower.id, "floor_created",
        {"tower": tower.name, "floor": floor, "codes": codes}, actor=actor,
    )
    return apartments


def update_apartment(apartment, data, actor):
    tower = apartment.tower
    if "towerId" in data and data["towerId"] != apartment.tower_id:
        raise ApiError(
            "Un apartamento no cambia de torre: retíralo y créalo en la otra."
        )
    before = {"code": apartment.code, "floor": apartment.floor}
    if "code" in data:
        code = _code(data["code"])
        if code != apartment.code:
            _require_free_apartment_code(tower, code, ignoring=apartment)
            apartment.code = code
            apartment.number = number_from_code(code)
    if "floor" in data:
        apartment.floor = _floor_of(tower, data["floor"])
    add_audit_log(
        "apartment", apartment.id, "updated",
        {"before": before, "after": {"code": apartment.code, "floor": apartment.floor}},
        actor=actor,
    )
    return apartment


def retire_apartment(apartment, actor):
    """Retira un apartamento sin residentes activos (409 si todavía vive alguien).

    Sus parqueaderos y cuartos útiles quedan libres para asignarlos a otro, y
    lo vigente de su ficha (integrantes, mascotas y vehículos) se retira con él
    para que sus placas puedan registrarse en otro apartamento.
    """
    residents = apartment.active_residents
    if residents:
        raise ApiError(
            f"{apartment.label} tiene {len(residents)} "
            f"residente{'s' if len(residents) != 1 else ''} "
            f"activo{'s' if len(residents) != 1 else ''}: "
            "desactívalos o pásalos a otro apartamento primero.",
            409,
        )
    released_parking = [spot.code for spot in apartment.active_parking_spots]
    released_storage = [room.code for room in apartment.active_storage_rooms]
    for spot in apartment.active_parking_spots:
        spot.apartment = None
    for room in apartment.active_storage_rooms:
        room.apartment = None
    retired_items = 0
    unit = apartment.unit
    if unit is not None:
        for item in (*unit.active_members, *unit.active_pets, *unit.active_vehicles):
            item.retire(actor)
            retired_items += 1
    apartment.retire(actor)
    add_audit_log(
        "apartment", apartment.id, "retired",
        {
            "label": apartment.label,
            "releasedParkingSpots": released_parking,
            "releasedStorageRooms": released_storage,
            "retiredHouseholdItems": retired_items,
        },
        actor=actor,
    )
    return apartment


def apartments_query(tower_id=None, search=None):
    """Apartamentos vigentes, por torre y piso; se puede filtrar por torre y por texto."""
    query = Apartment.query.join(Tower, Tower.id == Apartment.tower_id).filter(
        Apartment.retired_at.is_(None)
    )
    if tower_id is not None:
        query = query.filter(Apartment.tower_id == tower_id)
    if search:
        pattern = f"%{search}%"
        query = query.filter(db.or_(
            Apartment.code.ilike(pattern),
            (Tower.name + APARTMENT_LABEL_SEPARATOR + Apartment.code).ilike(pattern),
        ))
    return query.options(
        selectinload(Apartment.residents),
        selectinload(Apartment.parking_spots),
        selectinload(Apartment.storage_rooms),
    ).order_by(Apartment.tower_id, Apartment.floor, Apartment.number, Apartment.code)


# ---------------------------------------------------------------------------
# Parqueaderos (HU-015)
# ---------------------------------------------------------------------------

def _optional_apartment(value):
    return None if value is None else find_apartment(value)


def _require_free_parking_code(code, ignoring=None):
    query = ParkingSpot.query.filter_by(code=code, retired_at=None)
    if ignoring is not None:
        query = query.filter(ParkingSpot.id != ignoring.id)
    if query.first() is not None:
        raise ApiError(f"El parqueadero {code} ya existe.", 409)


def _parking_kind(value):
    if value not in PARKING_KINDS:
        raise ApiError("El tipo de parqueadero debe ser 'residente' o 'visitante'.")
    return value


def _check_parking_assignment(kind, apartment):
    if kind == "visitante" and apartment is not None:
        raise ApiError("Un parqueadero de visitantes no se asigna a un apartamento.")


def create_parking(data, actor):
    """Registra un parqueadero; el de visitantes empieza libre (CA-HU-015-01)."""
    code = _code(data.get("code"))
    kind = _parking_kind(data.get("type"))
    location = _text(data.get("location"), "location", 120)
    apartment = _optional_apartment(data.get("apartmentId"))
    _check_parking_assignment(kind, apartment)
    _require_free_parking_code(code)
    spot = ParkingSpot(code=code, kind=kind, location=location, apartment=apartment, occupied=False)
    db.session.add(spot)
    db.session.flush()
    add_audit_log(
        "parking_spot", spot.id, "created",
        {"code": code, "type": kind, "location": location,
         "apartment": apartment.label if apartment else None},
        actor=actor,
    )
    return spot


def update_parking(spot, data, actor):
    before = spot.to_dict()
    code, kind, location, apartment = spot.code, spot.kind, spot.location, spot.apartment
    if "code" in data:
        code = _code(data["code"])
        if code != spot.code:
            _require_free_parking_code(code, ignoring=spot)
    if "type" in data:
        kind = _parking_kind(data["type"])
    if "location" in data:
        location = _text(data["location"], "location", 120)
    if "apartmentId" in data:
        apartment = _optional_apartment(data["apartmentId"])
    _check_parking_assignment(kind, apartment)
    spot.code, spot.kind, spot.location, spot.apartment = code, kind, location, apartment
    add_audit_log(
        "parking_spot", spot.id, "updated",
        {"before": {key: before[key] for key in ("code", "type", "location", "apartment")},
         "after": {"code": code, "type": kind, "location": location,
                   "apartment": apartment.label if apartment else None}},
        actor=actor,
    )
    return spot


def retire_parking(spot, actor):
    if spot.occupied:
        raise ApiError(f"El parqueadero {spot.code} está ocupado en este momento.", 409)
    spot.retire(actor)
    add_audit_log("parking_spot", spot.id, "retired", {"code": spot.code}, actor=actor)
    return spot


def parking_query(kind=None, assigned=None, occupied=None, search=None):
    query = ParkingSpot.query.filter(ParkingSpot.retired_at.is_(None))
    if kind is not None:
        query = query.filter(ParkingSpot.kind == kind)
    if assigned is not None:
        query = query.filter(
            ParkingSpot.apartment_id.isnot(None) if assigned else ParkingSpot.apartment_id.is_(None)
        )
    if occupied is not None:
        query = query.filter(ParkingSpot.occupied.is_(occupied))
    if search:
        pattern = f"%{search}%"
        query = query.filter(db.or_(
            ParkingSpot.code.ilike(pattern), ParkingSpot.location.ilike(pattern)
        ))
    return query.order_by(ParkingSpot.kind, ParkingSpot.code)


def split_codes(text):
    """Separa «P-101, P-102» o «P-101 y P-102» en códigos en mayúsculas, sin repetir."""
    codes = []
    for part in re.split(r"[,;]|\s+y\s+", text or ""):
        if part.strip() and _code(part) not in codes:
            codes.append(_code(part))
    return codes


def assign_parking_codes(text, apartment):
    """Asigna al apartamento los parqueaderos de residente que nombra el texto (importador del censo).

    Los que no existen se crean con la ubicación «Por definir», para no perder
    el dato; uno de visitantes o ya asignado a otro apartamento se rechaza.
    """
    for code in split_codes(text):
        spot = ParkingSpot.query.filter_by(code=code, retired_at=None).first()
        if spot is None:
            db.session.add(ParkingSpot(
                code=code, kind="residente", location="Por definir", apartment=apartment,
                occupied=False,
            ))
        elif spot.kind != "residente":
            raise ApiError(f"El parqueadero {code} es de visitantes: no se asigna a un apartamento.")
        elif spot.apartment_id not in (None, apartment.id):
            raise ApiError(f"El parqueadero {code} ya está asignado a {spot.apartment.label}.", 409)
        else:
            spot.apartment = apartment


def assign_storage_codes(text, apartment):
    """Asigna al apartamento los cuartos útiles que nombra el texto; los que no existen se crean."""
    for code in split_codes(text):
        room = StorageRoom.query.filter_by(code=code, retired_at=None).first()
        if room is None:
            db.session.add(StorageRoom(code=code, apartment=apartment))
        elif room.apartment_id not in (None, apartment.id):
            raise ApiError(f"El cuarto útil {code} ya está asignado a {room.apartment.label}.", 409)
        else:
            room.apartment = apartment


# ---------------------------------------------------------------------------
# Cuartos útiles (HU-016)
# ---------------------------------------------------------------------------

def _require_free_storage_code(code, ignoring=None):
    query = StorageRoom.query.filter_by(code=code, retired_at=None)
    if ignoring is not None:
        query = query.filter(StorageRoom.id != ignoring.id)
    if query.first() is not None:
        raise ApiError(f"El cuarto útil {code} ya existe.", 409)


def create_storage_room(data, actor):
    code = _code(data.get("code"))
    apartment = _optional_apartment(data.get("apartmentId"))
    _require_free_storage_code(code)
    room = StorageRoom(code=code, apartment=apartment)
    db.session.add(room)
    db.session.flush()
    add_audit_log(
        "storage_room", room.id, "created",
        {"code": code, "apartment": apartment.label if apartment else None}, actor=actor,
    )
    return room


def update_storage_room(room, data, actor):
    before = {"code": room.code, "apartment": room.apartment.label if room.apartment else None}
    if "code" in data:
        code = _code(data["code"])
        if code != room.code:
            _require_free_storage_code(code, ignoring=room)
            room.code = code
    if "apartmentId" in data:
        room.apartment = _optional_apartment(data["apartmentId"])
    add_audit_log(
        "storage_room", room.id, "updated",
        {"before": before,
         "after": {"code": room.code,
                   "apartment": room.apartment.label if room.apartment else None}},
        actor=actor,
    )
    return room


def retire_storage_room(room, actor):
    room.retire(actor)
    add_audit_log("storage_room", room.id, "retired", {"code": room.code}, actor=actor)
    return room


def storage_rooms_query(assigned=None, search=None):
    query = StorageRoom.query.filter(StorageRoom.retired_at.is_(None))
    if assigned is not None:
        query = query.filter(
            StorageRoom.apartment_id.isnot(None) if assigned else StorageRoom.apartment_id.is_(None)
        )
    if search:
        query = query.filter(StorageRoom.code.ilike(f"%{search}%"))
    return query.order_by(StorageRoom.code)
