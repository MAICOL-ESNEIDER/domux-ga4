"""Ayudas de las pruebas para crear la estructura de la unidad (torres y apartamentos).

Un residente ya no se escribe con el texto de su apartamento: apunta a un
apartamento real (HU-017). Estas funciones crean la torre y el apartamento que
una prueba necesita, con la ficha del hogar, sin repetir el mismo código en cada
archivo.
"""

import re

from extensions import db
from models import Apartment, ParkingSpot, ResidentialUnit, StorageRoom, Tower

DEFAULT_TOWER = "Torre 1"
LABEL = re.compile(
    r"^\s*(?:(?P<tower>Torre\s*\d+)\s*[·\-,]?\s*)?(?:Apto\.?\s*)?(?P<code>[A-Za-z0-9]+)\s*$",
    re.IGNORECASE,
)


def tower_named(name, floors=10):
    """La torre vigente con ese nombre; se crea si todavía no existe."""
    with db.session.no_autoflush:  # el usuario que se está armando todavía no está en la sesión
        tower = Tower.query.filter_by(name=name, retired_at=None).first()
    if tower is None:
        tower = Tower(name=name, floors=floors)
        db.session.add(tower)
        db.session.flush()
    return tower


def apartment_in(tower_name, code, floor=None):
    """El apartamento vigente de esa torre y código; se crea, con su ficha, si no existe."""
    tower = tower_named(tower_name)
    with db.session.no_autoflush:
        apartment = Apartment.query.filter_by(tower_id=tower.id, code=code, retired_at=None).first()
    if apartment is None:
        apartment = Apartment(
            tower=tower,
            code=code,
            floor=floor or (int(code[:-2]) if code.isdigit() and len(code) >= 3 else 1),
            number=int(code) if code.isdigit() else None,
            unit=ResidentialUnit(),
        )
        db.session.add(apartment)
        db.session.flush()
    return apartment


def apartment_for(label):
    """El apartamento que nombra un texto como «Torre 2 · Apto 202» (sin torre, la Torre 1)."""
    match = LABEL.match(label)
    if match is None:
        raise ValueError(f"No se entiende el apartamento «{label}».")
    tower = " ".join((match.group("tower") or DEFAULT_TOWER).split()).title()
    return apartment_in(tower, match.group("code"))


def parking_spot(code, kind="residente", apartment=None, location="Sótano 1"):
    spot = ParkingSpot(code=code, kind=kind, location=location, apartment=apartment)
    db.session.add(spot)
    return spot


def storage_room(code, apartment=None):
    room = StorageRoom(code=code, apartment=apartment)
    db.session.add(room)
    return room
