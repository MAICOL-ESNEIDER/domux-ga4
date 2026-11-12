"""Resumen de lo pendiente para la administración (HU-081).

Es lo que muestra el inicio de la web: cuántas PQRS están abiertas y cuántas ya vencieron, cuántas
reservas esperan aprobación, cuántos paquetes llevan más de 48 horas en portería y cuántos avisos no
se han leído, más las filas más urgentes de cada lista. Todo se calcula al consultar (Render no tiene
un programador) y sin cargar los adjuntos de las PQRS, que pueden pesar varios megas.
"""

from datetime import timedelta

from sqlalchemy.orm import load_only

from models import UNCLAIMED_ORANGE_HOURS, Notification, PackageItem, Pqrs, Reservation
from services.alert_service import run_alerts
from services.pqrs_rules import RED, RUNNING_STATUSES, YELLOW, pqrs_semaphore
from services.reservation_service import PENDING_RESERVATION_STATUSES
from time_utils import colombia_today, to_colombia, utc_now

#: Cuántas filas trae cada lista del panel.
PANEL_ROWS = 8


def _urgent_pqrs():
    """Las PQRS en curso, de la más urgente a la menos urgente, con su semáforo.

    Devuelve ``(filas, abiertas, vencidas, por_vencer)``. Una PQRS vencida va antes que una que
    todavía tiene plazo, y entre las que tienen plazo van primero las que menos días hábiles
    tienen.
    """
    running = (
        Pqrs.query
        .options(load_only(
            Pqrs.id, Pqrs.radicado, Pqrs.subject, Pqrs.category, Pqrs.status, Pqrs.created_at,
            Pqrs.resident_id,
        ))
        .filter(Pqrs.status.in_(RUNNING_STATUSES), Pqrs.is_archived.is_(False))
        .all()
    )
    rated = []
    today = colombia_today()
    for item in running:
        if item.created_at is None:
            continue
        semaphore = pqrs_semaphore(to_colombia(item.created_at).date(), today, item.category)
        rated.append((semaphore["daysRemaining"], item.id, item, semaphore))
    rated.sort(key=lambda row: (row[0], row[1]))

    overdue = sum(1 for row in rated if row[3]["color"] == RED)
    due_soon = sum(1 for row in rated if row[3]["color"] == YELLOW)
    rows = []
    for _days, _id, item, semaphore in rated[:PANEL_ROWS]:
        resident = item.resident
        rows.append({
            "id": item.id,
            "radicado": item.radicado,
            "subject": item.subject or "",
            "category": item.category or "Petición",
            "status": item.status,
            "residentName": resident.full_name if resident else None,
            "apartment": resident.apartment if resident else None,
            "semaphore": semaphore["color"],
            "daysRemaining": semaphore["daysRemaining"],
            "dueDate": semaphore["dueDate"],
        })
    return rows, len(rated), overdue, due_soon


def _pending_reservations():
    """Las reservas por aprobar, las de fecha más próxima primero, y cuántas hay en total."""
    query = Reservation.query.filter(
        Reservation.status.in_(PENDING_RESERVATION_STATUSES),
        Reservation.is_archived.is_(False),
    )
    total = query.count()
    rows = []
    for item in query.order_by(Reservation.date, Reservation.created_at, Reservation.id).limit(PANEL_ROWS):
        resident = item.resident
        rows.append({
            "id": item.id,
            "commonAreaName": item.common_area.name if item.common_area else None,
            "date": item.date,
            "timeSlot": item.time_slot,
            "attendees": item.attendees,
            "residentName": resident.full_name if resident else None,
            "apartment": resident.apartment if resident else None,
        })
    return rows, total


def _unclaimed_packages():
    """Cuántos paquetes llevan más de 48 horas en portería y cuántos más de 72 (RN-018)."""
    now = utc_now()
    waiting = (
        PackageItem.query
        .options(load_only(
            PackageItem.id, PackageItem.status, PackageItem.is_deleted, PackageItem.arrived_at,
        ))
        .filter(
            PackageItem.status == "pendiente",
            PackageItem.is_deleted.is_(False),
            PackageItem.arrived_at.isnot(None),
            PackageItem.arrived_at <= now - timedelta(hours=UNCLAIMED_ORANGE_HOURS),
        )
        .all()
    )
    alerts = [item.claim_alert(now) for item in waiting]
    return sum(1 for alert in alerts if alert), sum(1 for alert in alerts if alert == "rojo")


def admin_summary(admin):
    """El resumen de lo pendiente que ve la administración en su inicio."""
    # Las alertas de vehículos y visitas se generan al consultar: así el contador de avisos
    # sin leer ya las incluye.
    run_alerts()
    pqrs_rows, pqrs_open, pqrs_overdue, pqrs_due_soon = _urgent_pqrs()
    reservation_rows, reservations_pending = _pending_reservations()
    packages_over_48, packages_over_72 = _unclaimed_packages()
    unread = Notification.query.filter_by(user_id=admin.id, is_read=False).count()
    return {
        "counts": {
            "pqrsOpen": pqrs_open,
            "pqrsOverdue": pqrs_overdue,
            "pqrsDueSoon": pqrs_due_soon,
            "reservationsPending": reservations_pending,
            "packagesOver48": packages_over_48,
            "packagesOver72": packages_over_72,
            "unreadNotifications": unread,
        },
        "urgentPqrs": pqrs_rows,
        "pendingReservations": reservation_rows,
    }
