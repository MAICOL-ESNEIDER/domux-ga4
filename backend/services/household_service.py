"""Ficha del hogar: lee y revisa los miembros, las mascotas y los vehículos que envía la app o la web.

Cada ``parse_*`` recibe la lista tal como llegó en la solicitud y devuelve los datos ya limpios, con
los nombres de las columnas. Si algo no es válido lanza ``ApiError`` con el mensaje que ve la
persona (400, o 409 si una placa se repite). Nada de aquí toca la base de datos, salvo
``sync_items``, que aplica el resultado sin borrar nada (TT-032, DEC-090).
"""

from datetime import date

from errors import ApiError
from extensions import db
from time_utils import colombia_today
from validators import (
    HOUSEHOLD_RELATIONSHIPS,
    normalize_phone,
    require_non_empty_fields,
    validate_colombian_plate,
    validate_iso_date,
)

#: Salud de cada mascota (RN-028): nombre, llave del JSON y columna del «al día»
#: y de la fecha de la última aplicación.
PET_HEALTH_FIELDS = (
    ("vacunación", "vaccinesUpToDate", "vaccines_up_to_date",
     "lastVaccinationDate", "last_vaccination_date"),
    ("desparasitación", "dewormingUpToDate", "deworming_up_to_date",
     "lastDewormingDate", "last_deworming_date"),
)


def _is_int(value):
    """Un número entero de verdad (en Python un verdadero/falso también lo es, y aquí no vale)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _check_required(item, fields, prefix, index):
    required = require_non_empty_fields(item, fields)
    if required:
        raise ApiError(f"{prefix} #{index + 1}: {required}")


def _check_item_id(item, label, index):
    """Revisa el id opcional de un elemento de la ficha."""
    item_id = item.get("id")
    if item_id is not None and not _is_int(item_id):
        raise ApiError(f"El id de {label} #{index + 1} no es válido.")


def parse_members(raw_members):
    """Los miembros del hogar: nombre, documento, fecha de nacimiento y parentesco son obligatorios."""
    parsed = []
    for index, member in enumerate(raw_members):
        if not isinstance(member, dict):
            raise ApiError(f"El miembro #{index + 1} no es válido.")
        _check_required(
            member,
            (("name", "nombre"), ("documentId", "documento"), ("birthDate", "fecha de nacimiento"),
             ("relationship", "parentesco")),
            "Miembro", index,
        )
        _check_item_id(member, "el miembro", index)
        try:
            birth_date = date.fromisoformat(member["birthDate"])
        except ValueError:
            raise ApiError(f"La fecha de nacimiento del miembro #{index + 1} no es válida.") from None
        if birth_date.isoformat() != member["birthDate"] or birth_date > colombia_today():
            raise ApiError(f"La fecha de nacimiento del miembro #{index + 1} no es válida.")
        relationship = member["relationship"]
        if relationship not in HOUSEHOLD_RELATIONSHIPS:
            raise ApiError(f"El parentesco del miembro #{index + 1} no es válido.")
        other_relationship = member.get("otherRelationship")
        if relationship == "otro" and (
            not isinstance(other_relationship, str) or not other_relationship.strip()
        ):
            raise ApiError("Especifica el parentesco cuando se selecciona 'otro'.")
        for field in ("lastName", "phone"):
            if member.get(field) is not None and not isinstance(member[field], str):
                raise ApiError(f"El campo '{field}' del miembro debe ser texto.")
        phone, phone_error = normalize_phone(member.get("phone"), f"El teléfono del miembro #{index + 1}")
        if phone_error:
            raise ApiError(phone_error)
        parsed.append({
            "id": member.get("id"),
            "name": member["name"].strip(),
            "last_name": (member.get("lastName") or "").strip(),
            "document_id": member["documentId"].strip(),
            "birth_date": birth_date.isoformat(),
            "phone": phone or None,
            "relationship": relationship,
            "other_relationship": (other_relationship or "").strip() or None,
        })
    return parsed


def _pet_health(pet, index):
    """Vacunación y desparasitación de una mascota (RN-028, HU-021).

    Cada una dice si está al día y la fecha de la última (AAAA-MM-DD, no futura).
    Si está al día, la fecha es obligatoria.
    """
    fields = {}
    for label, flag_key, flag_column, date_key, date_column in PET_HEALTH_FIELDS:
        up_to_date = pet.get(flag_key, False)
        if not isinstance(up_to_date, bool):
            raise ApiError(f"Mascota #{index + 1}: indica si la {label} está al día (sí o no).")
        last_date = pet.get(date_key)
        if last_date is not None:
            if validate_iso_date(last_date) or last_date > colombia_today().isoformat():
                raise ApiError(f"Mascota #{index + 1}: la fecha de la última {label} no es válida.")
        elif up_to_date:
            raise ApiError(f"Mascota #{index + 1}: escribe la fecha de la última {label}.")
        fields[flag_column] = up_to_date
        fields[date_column] = last_date
    return fields


def parse_pets(raw_pets):
    """Las mascotas: nombre, especie, raza y edad son obligatorios, más su salud."""
    parsed = []
    for index, pet in enumerate(raw_pets):
        if not isinstance(pet, dict):
            raise ApiError(f"La mascota #{index + 1} no es válida.")
        _check_required(pet, (("name", "nombre"), ("species", "especie"), ("breed", "raza")), "Mascota", index)
        _check_item_id(pet, "la mascota", index)
        age = pet.get("ageYears")
        if not _is_int(age) or not 0 <= age <= 100:
            raise ApiError(f"La edad de la mascota #{index + 1} debe estar entre 0 y 100.")
        parsed.append({
            "id": pet.get("id"),
            "name": pet["name"].strip(),
            "species": pet["species"].strip(),
            "breed": pet["breed"].strip(),
            "age_years": age,
            **_pet_health(pet, index),
        })
    return parsed


def parse_vehicles(raw_vehicles):
    """Los vehículos: placa colombiana sin repetir en la unidad, tipo, marca y modelo, año y titular."""
    parsed = []
    seen_plates = set()
    for index, vehicle in enumerate(raw_vehicles):
        if not isinstance(vehicle, dict):
            raise ApiError(f"El vehículo #{index + 1} no es válido.")
        _check_required(
            vehicle,
            (("plate", "placa"), ("type", "tipo"), ("makeModel", "marca y modelo"),
             ("registeredOwner", "titular registrado")),
            "Vehículo", index,
        )
        _check_item_id(vehicle, "el vehículo", index)
        plate = vehicle["plate"].replace("-", "").replace(" ", "").upper()
        if error := validate_colombian_plate(plate):
            raise ApiError(error)
        if plate in seen_plates:
            raise ApiError(f"La placa {plate} está repetida en esta unidad.", 409)
        seen_plates.add(plate)
        if vehicle["type"] not in ("carro", "moto"):
            raise ApiError(f"El tipo del vehículo #{index + 1} debe ser carro o moto.")
        year = vehicle.get("year")
        if not _is_int(year) or not 1950 <= year <= colombia_today().year + 1:
            raise ApiError(f"El año del vehículo #{index + 1} no es válido.")
        if vehicle.get("color") is not None and not isinstance(vehicle["color"], str):
            raise ApiError("El campo 'color' del vehículo debe ser texto.")
        parsed.append({
            "id": vehicle.get("id"),
            "plate": plate,
            "vehicle_type": vehicle["type"],
            "make_model": vehicle["makeModel"].strip(),
            "year": year,
            "registered_owner": vehicle["registeredOwner"].strip(),
            "color": (vehicle.get("color") or "").strip() or None,
        })
    return parsed


def _natural_key(source, names):
    """Lo que identifica un registro que llega sin id: documento, placa o nombre y especie."""
    def value(name):
        raw = source[name] if isinstance(source, dict) else getattr(source, name)
        return str(raw).strip().lower()
    return tuple(value(name) for name in names)


def sync_items(model, unit, current, incoming, actor, natural_key=()):
    """Aplica una lista de la ficha del hogar sin borrar nada (TT-032, DEC-090).

    current son los registros vigentes del apartamento e incoming la lista que
    envió la app. Lo que llega con el id de un registro vigente (o sin id, pero
    con el mismo documento o la misma placa) se mantiene y se actualiza; lo
    nuevo se agrega; y lo vigente que ya no llega se retira con la fecha y
    quién lo hizo (``actor``). Devuelve cuántos se agregaron, se mantuvieron y se retiraron.
    """
    pending = {item.id: item for item in current}
    by_key = {_natural_key(item, natural_key): item for item in current} if natural_key else {}
    kept, added = [], []
    for fields in incoming:
        fields = dict(fields)
        item = pending.pop(fields.pop("id", None), None)
        if item is None and natural_key:
            match = by_key.get(_natural_key(fields, natural_key))
            if match is not None and match.id in pending:
                item = pending.pop(match.id)
        if item is None:
            added.append(fields)
        else:
            kept.append((item, fields))

    # Primero se retira lo que salió de la lista: así una placa que pasa a otro
    # registro no choca con el registro que se va.
    for item in pending.values():
        item.retire(actor)
    db.session.flush()
    for item, fields in kept:
        for name, value in fields.items():
            setattr(item, name, value)
    for fields in added:
        db.session.add(model(unit=unit, **fields))
    return {"added": len(added), "kept": len(kept), "retired": len(pending)}
