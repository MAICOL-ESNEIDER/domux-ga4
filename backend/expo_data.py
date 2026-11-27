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
    PackageItem,
    Pqrs,
    Reservation,
    StorageRoom,
    Tower,
    User,
    Vehicle,
    Visit,
    VisitQrPass,
    VisitorVehicleEntry,
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


def _file(url, kind):
    """«sin archivo» o el tipo y el tamaño aproximado de lo que se guardó."""
    if not url:
        return "sin archivo"
    return f"{kind or '?'} {len(url) // 1365} KB"


def detail_lines():
    """Una línea por cada PQRS, reserva, paquete, visita, vehículo y pase QR (para decidir qué limpiar)."""
    lines = ["== PQRS (una por línea) =="]
    for item in Pqrs.query.order_by(Pqrs.id).all():
        lines.append(
            f"id {item.id} · {item.category} · {item.status} · «{item.subject[:50]}» · residente {item.resident_id} · "
            f"creada {_day(item.created_at)} · {_file(item.media_url, item.media_type)} · archivada {item.is_archived}"
        )
    lines.append("== Reservas (una por línea) ==")
    for item in Reservation.query.order_by(Reservation.id).all():
        lines.append(
            f"id {item.id} · {item.common_area.name} · {item.date} {item.time_slot} · {item.status} · "
            f"residente {item.resident_id} · creada {_day(item.created_at)} · archivada {item.is_archived}"
        )
    lines.append("== Paquetes (uno por línea) ==")
    for item in PackageItem.query.order_by(PackageItem.id).all():
        lines.append(
            f"id {item.id} · «{(item.description or '')[:40]}» · {item.status} · llegó {_day(item.arrived_at or item.created_at)} · "
            f"entregado {_day(item.delivered_at)} · residente {item.resident_id} · {_file(item.media_url, item.media_type)} · "
            f"borrado {item.is_deleted}"
        )
    lines.append("== Visitas (una por línea) ==")
    for item in Visit.query.order_by(Visit.id).all():
        lines.append(
            f"id {item.id} · {item.visitor_name} · {item.type} · {item.approval_status} · entró {_day(item.entered_at)} · "
            f"salió {_day(item.exited_at)} · creada {_day(item.created_at)}"
        )
    lines.append("== Pases QR ==")
    for item in VisitQrPass.query.order_by(VisitQrPass.id).all():
        lines.append(f"id {item.id} · {item.valid_from} a {item.valid_until} · {item.max_people} personas · revocado {item.revoked}")
    lines.append("== Vehículos y entradas de visitantes ==")
    for item in Vehicle.query.order_by(Vehicle.id).all():
        lines.append(f"vehículo id {item.id} · {item.plate}")
    for item in VisitorVehicleEntry.query.order_by(VisitorVehicleEntry.id).all():
        lines.append(f"entrada de visitante id {item.id} · creada {_day(getattr(item, 'created_at', None))}")
    return lines


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
    lines += detail_lines()
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
