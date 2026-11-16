"""La búsqueda y los filtros de la lista de usuarios (HU-075).

Recibe los parámetros de la dirección (``request.args``) y devuelve la consulta ya filtrada. Si un
parámetro no es válido lanza ``ApiError`` con el mensaje que ve el administrador.
"""

from errors import ApiError
from extensions import db
from models import (
    HouseholdMember,
    ParkingSpot,
    Pet,
    ResidentialUnit,
    ROLES,
    StorageRoom,
    User,
    Vehicle,
)
from time_utils import colombia_today
from validators import OCCUPANCY_TYPES, parse_optional_bool


def normalize_role(value):
    return value.strip().upper() if isinstance(value, str) else None


def _household_member_exists(*conditions):
    """Hay un miembro vigente en el hogar del usuario que cumple las condiciones."""
    return db.session.query(HouseholdMember.id).join(
        ResidentialUnit, HouseholdMember.unit_id == ResidentialUnit.id
    ).filter(
        ResidentialUnit.apartment_id == User.apartment_id,
        HouseholdMember.retired_at.is_(None),
        *conditions,
    ).exists()


def _by_text(query, search):
    """Busca en los datos de la persona, en su apartamento y en los miembros de su hogar."""
    pattern = f"%{search}%"
    member_match = _household_member_exists(db.or_(
        HouseholdMember.name.ilike(pattern),
        HouseholdMember.last_name.ilike(pattern),
        HouseholdMember.document_id.ilike(pattern),
    ))
    return query.filter(db.or_(
        User.name.ilike(pattern),
        (User.name + " " + User.last_name).ilike(pattern),
        User.last_name.ilike(pattern),
        User.email.ilike(pattern),
        User.phone.ilike(pattern),
        User.document_id.ilike(pattern),
        User.apartment.ilike(pattern),
        member_match,
    ))


def _by_role_and_occupancy(query, args):
    role = args.get("role")
    if role:
        normalized_role = normalize_role(role)
        if normalized_role not in ROLES:
            raise ApiError("Rol inválido.")
        query = query.filter(User.role == normalized_role)
    occupancy = args.get("occupancyType")
    if occupancy:
        if occupancy not in OCCUPANCY_TYPES:
            raise ApiError("Tipo de residente inválido.")
        query = query.filter(User.occupancy_type == occupancy, User.role == "RESIDENT")
    return query


def _by_apartment_range(query, args):
    apartment_from = args.get("apartmentFrom")
    apartment_to = args.get("apartmentTo")
    if apartment_from:
        if not apartment_from.isdigit():
            raise ApiError("El apartamento inicial debe ser numérico.")
        query = query.filter(User.apartment_number >= int(apartment_from))
    if apartment_to:
        if not apartment_to.isdigit():
            raise ApiError("El apartamento final debe ser numérico.")
        query = query.filter(User.apartment_number <= int(apartment_to))
    if apartment_from and apartment_to and int(apartment_from) > int(apartment_to):
        raise ApiError("El apartamento inicial no puede superar al final.")
    return query


def _household_checks():
    """Cada filtro «tiene ...» con la condición que lo comprueba en el hogar del usuario."""
    return (
        ("hasPets", db.session.query(Pet.id).join(
            ResidentialUnit, Pet.unit_id == ResidentialUnit.id
        ).filter(
            ResidentialUnit.apartment_id == User.apartment_id, Pet.retired_at.is_(None)
        ).exists()),
        ("hasVehicles", db.session.query(Vehicle.id).join(
            ResidentialUnit, Vehicle.unit_id == ResidentialUnit.id
        ).filter(
            ResidentialUnit.apartment_id == User.apartment_id, Vehicle.retired_at.is_(None)
        ).exists()),
        # Los parqueaderos y cuartos útiles se asignan al apartamento (HU-015 y HU-016).
        ("hasParking", db.session.query(ParkingSpot.id).filter(
            ParkingSpot.apartment_id == User.apartment_id,
            ParkingSpot.kind == "residente",
            ParkingSpot.retired_at.is_(None),
        ).exists()),
        ("hasStorage", db.session.query(StorageRoom.id).filter(
            StorageRoom.apartment_id == User.apartment_id,
            StorageRoom.retired_at.is_(None),
        ).exists()),
    )


def _by_household(query, args):
    for parameter, column in _household_checks():
        value, error = parse_optional_bool(args.get(parameter), parameter)
        if error:
            raise ApiError(error)
        if value is not None:
            query = query.filter(column if value else ~column, User.role == "RESIDENT")
    return query


def _by_active(query, args):
    active, error = parse_optional_bool(args.get("isActive"), "isActive")
    if error:
        raise ApiError(error)
    if active is not None:
        query = query.filter(User.is_active.is_(active))
    return query


def _age_limits(args):
    """La edad mínima y la máxima pedidas (cada una puede faltar) ya revisadas."""
    minimum, maximum = args.get("minAge"), args.get("maxAge")
    try:
        minimum = int(minimum) if minimum is not None else None
        maximum = int(maximum) if maximum is not None else None
    except ValueError:
        raise ApiError("Los límites de edad deben ser números.") from None
    limits = [limit for limit in (minimum, maximum) if limit is not None]
    if any(limit < 0 for limit in limits) or (len(limits) == 2 and minimum > maximum):
        raise ApiError("El rango de edad es inválido.")
    return minimum, maximum


def _years_before(today, years):
    try:
        return today.replace(year=today.year - years)
    except ValueError:  # 29 de febrero en un año que no es bisiesto
        return today.replace(year=today.year - years, day=28)


def _by_age(query, args):
    """Filtra por edad a la persona o a algún miembro de su hogar."""
    minimum, maximum = _age_limits(args)
    if minimum is None and maximum is None:
        return query
    today = colombia_today()
    user_conditions = [User.birth_date.isnot(None)]
    member_conditions = []
    if minimum is not None:
        latest = _years_before(today, minimum).isoformat()
        user_conditions.append(User.birth_date <= latest)
        member_conditions.append(HouseholdMember.birth_date <= latest)
    if maximum is not None:
        earliest = _years_before(today, maximum + 1).isoformat()
        user_conditions.append(User.birth_date > earliest)
        member_conditions.append(HouseholdMember.birth_date > earliest)
    return query.filter(
        db.or_(db.and_(*user_conditions), _household_member_exists(*member_conditions)),
        User.role == "RESIDENT",
    )


def filtered_users(args):
    """Los usuarios que cumplen todos los filtros que vienen en ``args``."""
    query = User.query
    search = (args.get("search") or "").strip()
    if search:
        query = _by_text(query, search)
    for apply_filter in (_by_role_and_occupancy, _by_apartment_range, _by_household, _by_active, _by_age):
        query = apply_filter(query, args)
    return query
