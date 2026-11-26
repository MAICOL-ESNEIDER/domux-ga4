"""Revisa la base antes de preparar la exposición (solo lee: no cambia nada).

Con ``DOMUX_EXPO_ACCION=inspeccionar`` el servidor escribe, al arrancar, un resumen de lo que hay en
la base: cuántas filas tiene cada tabla y qué cosas NO son de las cuentas de prueba de DOMUX
(``seed.py`` y ``demo_data.py``). Sirve para decidir con la persona responsable qué se limpia antes
de cargar los datos de la exposición. Todas las líneas empiezan con «[EXPO]» para encontrarlas en
el registro del servidor.
"""

import logging
import os

from sqlalchemy import func, inspect

from demo_data import demo_account_vars
from extensions import db
from models import (
    Announcement,
    Apartment,
    CommonArea,
    ParkingSpot,
    Pqrs,
    StorageRoom,
    Tower,
    User,
)

logger = logging.getLogger(__name__)

ACTION_VAR = "DOMUX_EXPO_ACCION"


def requested_action():
    """La acción pedida con la variable de entorno (``inspeccionar``) o None."""
    value = os.environ.get(ACTION_VAR, "").strip().lower()
    return value or None


def _day(moment):
    return moment.strftime("%Y-%m-%d") if moment is not None else "sin fecha"


def _line(text):
    logger.warning("[EXPO] %s", text)


def table_counts():
    """Cuántas filas tiene cada tabla (sin la de versiones de la base)."""
    counts = {}
    for name in sorted(inspect(db.engine).get_table_names()):
        if name == "alembic_version":
            continue
        counts[name] = db.session.execute(db.text(f'select count(*) from "{name}"')).scalar()
    return counts


def report():
    """Arma las líneas del resumen. No cambia nada en la base."""
    demo_emails = set(demo_account_vars())
    lines = ["== Filas por tabla =="]
    lines += [f"{name}: {count}" for name, count in table_counts().items()]

    lines.append("== Usuarios que NO son de las cuentas de prueba de DOMUX ==")
    others = User.query.filter(~User.email.in_(demo_emails)).order_by(User.id).all()
    for user in others:
        apartment = user.apartment_ref
        place = f"{apartment.tower.name} {apartment.code}" if apartment is not None and apartment.tower else "sin apartamento"
        lines.append(f"id {user.id} · {user.role} · {user.email} · {place} · creado {_day(user.created_at)}")
    lines.append(f"Total: {len(others)} de {User.query.count()} usuarios")

    lines.append("== Torres y apartamentos ==")
    for tower in Tower.query.order_by(Tower.id).all():
        total = Apartment.query.filter_by(tower_id=tower.id).count()
        lines.append(f"{tower.name} · {tower.floors} pisos · {total} apartamentos · retirada: {bool(tower.retired_at)}")

    lines.append("== Parqueaderos, cuartos útiles y zonas comunes ==")
    lines.append("Parqueaderos: " + ", ".join(f"{s.code}({s.kind})" for s in ParkingSpot.query.order_by(ParkingSpot.id).all()))
    lines.append("Cuartos útiles: " + ", ".join(r.code for r in StorageRoom.query.order_by(StorageRoom.id).all()))
    lines.append("Zonas: " + ", ".join(a.name for a in CommonArea.query.order_by(CommonArea.id).all()))

    lines.append("== Comunicados (título · creado) ==")
    for item in Announcement.query.order_by(Announcement.id).limit(60).all():
        lines.append(f"{item.id} · {item.title[:60]} · {_day(item.created_at)}")

    lines.append("== PQRS por tipo y estado ==")
    for category, status, total in (
        db.session.query(Pqrs.category, Pqrs.status, func.count(Pqrs.id)).group_by(Pqrs.category, Pqrs.status).all()
    ):
        lines.append(f"{category} · {status}: {total}")
    return lines


def run_requested_action():
    """Hace lo que pide la variable: ``inspeccionar`` (solo lee) o ``cargar`` (solo agrega)."""
    action = requested_action()
    if action == "cargar":
        from expo_activity import add_expo_activity

        return add_expo_activity()
    if action != "inspeccionar":
        return False
    try:
        for text in report():
            _line(text)
    except Exception:
        db.session.rollback()
        logger.exception("[EXPO] No se pudo armar el resumen.")
        return False
    return True
