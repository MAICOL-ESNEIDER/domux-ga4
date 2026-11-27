"""Limpieza única de la base antes de la exposición (la pidió la persona responsable, 26/11/2026).

Se hace con ``DOMUX_EXPO_ACCION=limpiar`` y una sola vez (queda una marca en el registro de auditoría):

* borra las pruebas sueltas (2 comunicados, 2 PQRS con fotos que no tienen que ver con la unidad, 3
  paquetes «de prueba», 1 visita pendiente y los intentos de inicio de sesión fallidos);
* deja un solo ejemplo vencido de cada cosa (una PQRS, un paquete y una reserva) y borra el resto de
  lo vencido, y crea copias nuevas que siguen vigentes el día de la exposición (1 de diciembre).

Cada fila se busca por su texto y sus datos, no solo por su número: si algo no coincide, no se toca.
La base de Render es del plan gratis y no tiene copias automáticas, así que antes de borrar cada fila
queda escrita en el registro del servidor («[EXPO-RESPALDO]», sin las fotos) para poder reponerla.
"""

import json
import logging
from datetime import timedelta

from sqlalchemy import inspect as sa_inspect

from extensions import db
from models import (
    Announcement,
    AnnouncementRead,
    AuditLog,
    LoginAttempt,
    PackageItem,
    PackagePickupCode,
    Pqrs,
    PqrsMessage,
    Reservation,
    ReservationMessage,
    Visit,
    VisitEvent,
)
from services.pqrs_rules import make_radicado
from services.reservation_service import reservation_conflicts
from time_utils import utc_now

logger = logging.getLogger(__name__)

CLEANUP_VERSION = 1
MARKER_ENTITY = "limpieza_expo"
MARKER_ACTION = "limpieza_expo_aplicada"

TEST_ANNOUNCEMENTS = ("Se nos infiltró un dragón", "hi")
TEST_PQRS = ("hay una lagartija en mi piso", "basura")
OVERDUE_PQRS = ("Ruido en el apartamento de arriba", "Gotera en el techo del parqueadero", "Certificado de residencia")
TEST_PACKAGES = ("Paquete de prueba pendiente", "Paquete de prueba por llegar", "Paquete de prueba entregado")
OVERDUE_PACKAGES = ("Caja de Amazon", "Sobre de documentos")
# (zona, fecha vieja, estado) de lo que se renueva → fecha nueva. La del Salón social del 11/11 se queda.
RESERVATION_RENEWALS = {
    ("Salón social", "2026-11-21", "aprobada"): "2026-12-05",
    ("Cancha múltiple", "2026-11-17", "pendiente"): "2026-12-02",
    ("Zona BBQ", "2026-11-22", "rechazada"): "2026-12-03",
    ("Gimnasio", "2026-11-19", "cancelada"): "2026-12-04",
    ("Piscina", "2026-11-18", "aprobada"): "2026-12-01",
    ("Salón social", "2026-11-07", "aprobada"): "2026-12-12",
}
TEST_RESERVATIONS = (("Cancha múltiple", "2026-11-28", "cancelada"),)


def already_cleaned():
    for marker in AuditLog.query.filter_by(entity_type=MARKER_ENTITY, action=MARKER_ACTION).all():
        try:
            if json.loads(marker.details or "{}").get("version", 0) >= CLEANUP_VERSION:
                return True
        except (TypeError, ValueError, AttributeError):
            continue
    return False


def _backup(row):
    """Escribe en el registro del servidor todos los datos de la fila (sin archivos grandes)."""
    data = {}
    for column in sa_inspect(row).mapper.column_attrs:
        value = getattr(row, column.key)
        if isinstance(value, str) and len(value) > 600:
            value = f"[texto de {len(value)} letras omitido]"
        data[column.key] = value.isoformat() if hasattr(value, "isoformat") else value
    logger.warning("[EXPO-RESPALDO] %s %s", row.__tablename__, json.dumps(data, ensure_ascii=False, default=str))


def _delete(row):
    _backup(row)
    db.session.delete(row)


def _delete_announcements():
    for title in TEST_ANNOUNCEMENTS:
        for item in Announcement.query.filter_by(title=title).all():
            for read in AnnouncementRead.query.filter_by(announcement_id=item.id).all():
                _delete(read)
            _delete(item)


def _delete_pqrs(subject):
    for item in Pqrs.query.filter_by(subject=subject).all():
        _delete(item)


def _renew_pqrs(now):
    ages = {"Ruido en el apartamento de arriba": 20, "Gotera en el techo del parqueadero": 30,
            "Certificado de residencia": 4}
    for subject in OVERDUE_PQRS:
        for old in Pqrs.query.filter_by(subject=subject).all():
            created = now - timedelta(hours=ages[subject])
            new = Pqrs(
                resident_id=old.resident_id, category=old.category, subject=old.subject, message=old.message,
                status="abierta", media_url=old.media_url, media_type=old.media_type,
                media_downloadable=old.media_downloadable, created_at=created, updated_at=created,
                incident_date=(created - timedelta(days=1)).strftime("%Y-%m-%d") if old.category in ("Queja", "Reclamo", "Daño") else None,
                incident_time="20:30" if old.category in ("Queja", "Reclamo", "Daño") else None,
            )
            new.conversation.append(PqrsMessage(
                author_id=old.resident_id, author_role="RESIDENT", message=old.message, created_at=created,
            ))
            _delete(old)
            db.session.add(new)
            db.session.flush()
            new.radicado = make_radicado(new.id, created)


def _renew_packages(now):
    ages = {"Caja de Amazon": 3, "Sobre de documentos": 30}
    for description in OVERDUE_PACKAGES:
        for old in PackageItem.query.filter_by(description=description, status="pendiente").all():
            arrived = now - timedelta(hours=ages[description])
            new = PackageItem(
                resident_id=old.resident_id, registered_by=old.registered_by, description=old.description,
                carrier=old.carrier, tracking_number=old.tracking_number, status="pendiente",
                media_url=old.media_url, media_type=old.media_type, created_at=arrived, arrived_at=arrived,
            )
            for code in PackagePickupCode.query.filter_by(package_id=old.id).all():
                _delete(code)
            _delete(old)
            db.session.add(new)


def _delete_test_packages():
    for description in TEST_PACKAGES:
        for old in PackageItem.query.filter_by(description=description).all():
            for code in PackagePickupCode.query.filter_by(package_id=old.id).all():
                _delete(code)
            _delete(old)


def _renew_reservations(now):
    for old in Reservation.query.all():
        key = (old.common_area.name, old.date, old.status)
        if key in TEST_RESERVATIONS:
            _delete(old)
            continue
        new_day = RESERVATION_RENEWALS.get(key)
        if new_day is None:
            continue
        copy = Reservation(
            resident_id=old.resident_id, common_area_id=old.common_area_id, date=new_day, time_slot=old.time_slot,
            attendees=old.attendees, status=old.status, created_at=now - timedelta(days=1),
        )
        for message in old.messages:
            copy.messages.append(ReservationMessage(
                author_id=message.author_id, author_role=message.author_role, message=message.message,
                created_at=now - timedelta(hours=20),
            ))
        conflict = old.status in ("aprobada", "activa") and reservation_conflicts(old.common_area_id, new_day, old.time_slot)
        _delete(old)
        if not conflict:
            db.session.add(copy)


def _delete_test_visits():
    for visit in Visit.query.filter_by(visitor_name="Andres", approval_status="pendiente").all():
        for event in VisitEvent.query.filter_by(visit_id=visit.id).all():
            _delete(event)
        _delete(visit)


def _delete_login_attempts():
    for attempt in LoginAttempt.query.all():
        _delete(attempt)


def clean_for_expo():
    """Hace la limpieza una sola vez. Devuelve True si la hizo en esta llamada."""
    if already_cleaned():
        return False
    now = utc_now()
    try:
        _delete_announcements()
        for subject in TEST_PQRS:
            _delete_pqrs(subject)
        _renew_pqrs(now)
        _delete_test_packages()
        _renew_packages(now)
        _renew_reservations(now)
        _delete_test_visits()
        _delete_login_attempts()
        db.session.add(AuditLog(
            entity_type=MARKER_ENTITY, action=MARKER_ACTION, actor_role="SISTEMA",
            details=json.dumps({"version": CLEANUP_VERSION}),
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("[EXPO] No se pudo limpiar la base; quedó como estaba.")
        return False
    logger.warning("[EXPO] Limpieza de la exposición hecha.")
    return True
