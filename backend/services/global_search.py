"""El buscador general con el filtro «Buscar en» (HU-089).

Un solo buscador para la web de administración y para la app (administración y portería): busca
en un solo lugar personas, apartamentos, vehículos por placa, PQRS por radicado o asunto, paquetes y
visitas, y devuelve los resultados agrupados por tipo, ya con el texto que se muestra.

La portería busca con las mismas reglas que en el resto de la app: solo residentes activos, por
nombre, documento o apartamento (nunca por correo, SEC-015), sin PQRS, sin teléfonos ni correos y
como mucho 5 resultados por grupo.
"""

from sqlalchemy import or_

from errors import ApiError
from models import Apartment, PackageItem, Pqrs, Tower, User, Vehicle, Visit, VisitorVehicleEntry
from validators import normalize_plate

#: Dónde se puede buscar, en el orden del filtro «Buscar en».
SEARCH_PLACES = {
    "todo": "Todo",
    "personas": "Personas",
    "apartamentos": "Apartamentos",
    "vehiculos": "Vehículos",
    "pqrs": "PQRS",
    "paquetes": "Paquetes",
    "visitas": "Visitas",
}

#: La portería no atiende PQRS, así que no las busca.
GUARD_PLACES = ("personas", "apartamentos", "vehiculos", "paquetes", "visitas")
ADMIN_PLACES = ("personas", "apartamentos", "vehiculos", "pqrs", "paquetes", "visitas")

MIN_CHARS = 2
MIN_PLATE_CHARS = 3

#: Cuántos resultados por grupo: pocos al buscar en todo, más al elegir un solo lugar. La portería,
#: como en su buscador de residentes, ve como mucho 5.
LIMIT_EVERYWHERE = 5
LIMIT_ONE_PLACE = 20
GUARD_LIMIT = 5

ROLE_LABELS = {"ADMIN": "Administración", "GUARD": "Portería", "RESIDENT": "Residente"}
OCCUPANCY_LABELS = {"propietario": "Propietario", "arrendatario": "Arrendatario", "residente": "Residente"}
PQRS_STATUS_LABELS = {"abierta": "Abierta", "en_proceso": "En proceso", "resuelta": "Resuelta"}
PACKAGE_STATUS_LABELS = {"por_llegar": "Por llegar", "pendiente": "En portería", "entregado": "Entregado"}
PACKAGE_ALERT_LABELS = {"naranja": "Más de 48 h sin reclamar", "rojo": "Más de 72 h sin reclamar"}
VISIT_TYPE_LABELS = {"visitante": "Visitante", "domiciliario": "Domiciliario", "contratista": "Contratista"}
VEHICLE_TYPE_LABELS = {"carro": "Carro", "moto": "Moto"}


def places_for(role):
    """Las opciones del filtro «Buscar en» que tiene ese rol, empezando por «Todo»."""
    allowed = GUARD_PLACES if role == "GUARD" else ADMIN_PLACES
    return [{"value": value, "label": SEARCH_PLACES[value]} for value in ("todo", *allowed)]


def _like(text):
    """El patrón «contiene» con los comodines de LIKE escapados: «50%» busca el texto «50%»."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _matches(pattern, *columns):
    return or_(*(column.ilike(pattern, escape="\\") for column in columns))


def _join(*parts):
    return " · ".join(part for part in parts if part)


def _item(kind, record_id, title, subtitle, apartment_id=None, variant=None, apartment_label=None):
    return {
        "type": kind,
        "id": record_id,
        "title": title,
        "subtitle": subtitle,
        "apartmentId": apartment_id,
        "apartmentLabel": apartment_label,
        "kind": variant,
    }


def _cut(rows, limit):
    """Los primeros ``limit`` y si había más (se pide uno de más para saberlo)."""
    return rows[:limit], len(rows) > limit


# --- Cada lugar -------------------------------------------------------------------------------

def _people(text, user, limit):
    pattern = _like(text)
    full_name = User.name + " " + User.last_name
    if user.role == "GUARD":
        query = User.query.filter(User.role == "RESIDENT", User.is_active.is_(True)).filter(
            _matches(pattern, User.name, User.last_name, full_name, User.document_id, User.apartment)
        )
    else:
        query = User.query.filter(_matches(
            pattern, User.name, User.last_name, full_name, User.email, User.phone, User.document_id, User.apartment,
        ))
    rows, more = _cut(query.order_by(User.name, User.last_name, User.id).limit(limit + 1).all(), limit)
    items = []
    for person in rows:
        if user.role == "GUARD":
            subtitle = person.apartment or "Sin apartamento"
        else:
            role = OCCUPANCY_LABELS.get(person.occupancy_type) if person.role == "RESIDENT" else None
            subtitle = _join(
                role or ROLE_LABELS.get(person.role, person.role), person.apartment,
                None if person.is_active else "Cuenta desactivada",
            )
        items.append(_item("personas", person.id, person.full_name, subtitle, person.apartment_id,
                           apartment_label=person.apartment))
    return items, more


def _apartments(text, user, limit):
    pattern = _like(text)
    query = (
        Apartment.query.join(Tower, Apartment.tower_id == Tower.id)
        .filter(Apartment.retired_at.is_(None), Tower.retired_at.is_(None))
        .filter(_matches(
            pattern, Apartment.code, Tower.name + " " + Apartment.code, Tower.name + " · Apto " + Apartment.code,
        ))
        .order_by(Tower.name, Apartment.number, Apartment.id)
    )
    rows, more = _cut(query.limit(limit + 1).all(), limit)
    items = []
    for apartment in rows:
        count = len(apartment.active_residents)
        subtitle = "Sin residentes" if count == 0 else f"{count} residente{'s' if count != 1 else ''}"
        items.append(_item("apartamentos", apartment.id, apartment.label, subtitle, apartment.id,
                           apartment_label=apartment.label))
    return items, more


def _vehicles(text, user, limit):
    plate = normalize_plate(text)
    if len(plate) < MIN_PLATE_CHARS:
        return [], False
    residents = (
        Vehicle.query.filter(Vehicle.retired_at.is_(None))
        .filter(Vehicle.plate.contains(plate, autoescape=True))
        .order_by(Vehicle.plate, Vehicle.id).limit(limit + 1).all()
    )
    visitors = (
        VisitorVehicleEntry.query.filter(VisitorVehicleEntry.exited_at.is_(None))
        .filter(VisitorVehicleEntry.plate.contains(plate, autoescape=True))
        .order_by(VisitorVehicleEntry.entered_at.desc(), VisitorVehicleEntry.id).limit(limit + 1).all()
    )
    items = []
    for vehicle in residents:
        apartment = vehicle.unit.apartment_ref if vehicle.unit is not None else None
        subtitle = _join(
            VEHICLE_TYPE_LABELS.get(vehicle.vehicle_type, vehicle.vehicle_type), vehicle.make_model,
            apartment.label if apartment is not None else None,
        )
        items.append(_item("vehiculos", vehicle.id, vehicle.plate, subtitle,
                           apartment.id if apartment is not None else None, "residente",
                           apartment.label if apartment is not None else None))
    for entry in visitors:
        apartment = entry.apartment
        subtitle = _join(
            "Visitante adentro", apartment.label if apartment is not None else None,
            f"Parqueadero {entry.spot.code}" if entry.spot is not None else None,
        )
        items.append(_item("vehiculos", entry.id, entry.plate, subtitle, entry.apartment_id, "visitante",
                           apartment.label if apartment is not None else None))
    return items[:limit], len(residents) > limit or len(visitors) > limit or len(items) > limit


def _pqrs(text, user, limit):
    pattern = _like(text)
    query = (
        Pqrs.query.join(User, Pqrs.resident_id == User.id)
        .filter(_matches(pattern, Pqrs.radicado, Pqrs.subject, User.name + " " + User.last_name))
        .order_by(Pqrs.created_at.desc(), Pqrs.id.desc())
    )
    rows, more = _cut(query.limit(limit + 1).all(), limit)
    items = []
    for pqrs in rows:
        resident = pqrs.resident
        subtitle = _join(
            pqrs.category, PQRS_STATUS_LABELS.get(pqrs.status, pqrs.status),
            resident.full_name if resident is not None else None,
        )
        title = _join(pqrs.radicado, pqrs.subject)
        items.append(_item("pqrs", pqrs.id, title, subtitle, resident.apartment_id if resident is not None else None,
                           apartment_label=resident.apartment if resident is not None else None))
    return items, more


def _packages(text, user, limit):
    pattern = _like(text)
    query = (
        PackageItem.query.join(User, PackageItem.resident_id == User.id)
        .filter(PackageItem.is_deleted.is_(False))
        .filter(_matches(
            pattern, PackageItem.description, PackageItem.carrier, PackageItem.tracking_number,
            PackageItem.delivered_to, User.name + " " + User.last_name, User.apartment,
        ))
        .order_by(PackageItem.created_at.desc(), PackageItem.id.desc())
    )
    rows, more = _cut(query.limit(limit + 1).all(), limit)
    items = []
    for package in rows:
        resident = package.resident
        alert = package.claim_alert() if package.status == "pendiente" else None
        subtitle = _join(
            PACKAGE_STATUS_LABELS.get(package.status, package.status), PACKAGE_ALERT_LABELS.get(alert),
            resident.full_name if resident is not None else None,
            resident.apartment if resident is not None else None,
        )
        items.append(_item("paquetes", package.id, package.description, subtitle,
                           resident.apartment_id if resident is not None else None,
                           apartment_label=resident.apartment if resident is not None else None))
    return items, more


def _visit_state(visit):
    if visit.entered_at is not None and visit.exited_at is None:
        return "Adentro"
    if visit.exited_at is not None:
        return "Ya salió"
    return {"pendiente": "Esperando autorización", "rechazada": "Rechazada"}.get(visit.approval_status, "Aprobada")


def _visits(text, user, limit):
    pattern = _like(text)
    query = (
        Visit.query.join(User, Visit.resident_id == User.id)
        .filter(_matches(
            pattern, Visit.visitor_name, Visit.visitor_document, User.name + " " + User.last_name, User.apartment,
        ))
        .order_by(Visit.created_at.desc(), Visit.id.desc())
    )
    rows, more = _cut(query.limit(limit + 1).all(), limit)
    items = []
    for visit in rows:
        resident = visit.resident
        subtitle = _join(
            VISIT_TYPE_LABELS.get(visit.type, visit.type), _visit_state(visit),
            resident.apartment if resident is not None else None,
        )
        items.append(_item("visitas", visit.id, visit.visitor_name, subtitle,
                           resident.apartment_id if resident is not None else None,
                           apartment_label=resident.apartment if resident is not None else None))
    return items, more


SEARCHERS = {
    "personas": _people,
    "apartamentos": _apartments,
    "vehiculos": _vehicles,
    "pqrs": _pqrs,
    "paquetes": _packages,
    "visitas": _visits,
}


def search(text, place, user):
    """Busca ``text`` en ``place`` (o en todo lo que el rol puede ver) y agrupa los resultados."""
    text = (text or "").strip()[:100]
    place = (place or "todo").strip().lower()
    if place not in SEARCH_PLACES:
        raise ApiError("No se puede buscar ahí. Elige una opción de «Buscar en».")
    allowed = GUARD_PLACES if user.role == "GUARD" else ADMIN_PLACES
    if place != "todo" and place not in allowed:
        raise ApiError("La portería no busca en las PQRS.", 403)
    result = {"query": text, "in": place, "places": places_for(user.role), "tooShort": len(text) < MIN_CHARS, "groups": []}
    if result["tooShort"]:
        return result
    chosen = allowed if place == "todo" else (place,)
    if user.role == "GUARD":
        limit = GUARD_LIMIT
    else:
        limit = LIMIT_EVERYWHERE if place == "todo" else LIMIT_ONE_PLACE
    for kind in chosen:
        items, more = SEARCHERS[kind](text, user, limit)
        if items:
            result["groups"].append({"type": kind, "label": SEARCH_PLACES[kind], "items": items, "more": more})
    return result
