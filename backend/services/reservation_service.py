"""Reservation schedule validation and availability queries."""

import logging
import re
from datetime import date as calendar_date, timedelta

from extensions import db
from models import Reservation
from services.notification_service import notify_user
from time_utils import COLOMBIA_TIMEZONE, now_colombia
from validators import STANDARD_TIME_SLOTS, VALID_TIME_SLOTS

ACTIVE_RESERVATION_STATUSES = ("pendiente_pago", "activa", "aprobada")
EXPIRABLE_RESERVATION_STATUSES = ACTIVE_RESERVATION_STATUSES + ("pendiente",)
logger = logging.getLogger(__name__)


def finalize_expired_reservations(now=None):
    """Synchronize reservation payment and scheduled-expiration states."""
    if now is None:
        now = now_colombia()
    elif now.tzinfo is not None:
        now = now.astimezone(COLOMBIA_TIMEZONE).replace(tzinfo=None)

    today = now.date()
    current_minute = now.hour * 60 + now.minute
    finalized_count = 0
    has_changes = False
    reservations = Reservation.query.filter(
        Reservation.status.in_(EXPIRABLE_RESERVATION_STATUSES)
    ).all()

    for reservation in reservations:
        payment_remaining = None
        if reservation.status == "pendiente_pago" and reservation.payment_deadline:
            deadline = reservation.payment_deadline
            if deadline.tzinfo:
                deadline = deadline.astimezone(COLOMBIA_TIMEZONE).replace(tzinfo=None)
            remaining = deadline - now
            if remaining.total_seconds() <= 0:
                reservation.status = "expirada"
                notify_user(
                    reservation.resident_id,
                    "Reserva expirada",
                    "Tu reserva expiró por falta de confirmación de pago y el horario fue liberado.",
                    "reservation",
                )
                finalized_count += 1
                has_changes = True
                continue
            payment_remaining = remaining

        try:
            reservation_date = calendar_date.fromisoformat(reservation.date)
        except (TypeError, ValueError):
            logger.warning(
                "Skipping reservation %s with invalid date %r.",
                reservation.id,
                reservation.date,
            )
            continue

        expired = reservation_date < today
        if reservation_date == today:
            time_range = time_slot_to_minutes(reservation.time_slot)
            if time_range is None:
                logger.warning(
                    "Skipping reservation %s with invalid time slot %r.",
                    reservation.id,
                    reservation.time_slot,
                )
                continue
            expired = time_range[1] <= current_minute

        if expired and reservation.status in ACTIVE_RESERVATION_STATUSES:
            reservation.status = "finalizada"
            finalized_count += 1
            has_changes = True
            continue

        if (
            reservation.status == "pendiente_pago"
            and payment_remaining is not None
            and payment_remaining <= timedelta(minutes=120)
            and not reservation.payment_reminder_sent
        ):
            reservation.payment_reminder_sent = True
            notify_user(
                reservation.resident_id,
                "Pago de reserva próximo a expirar",
                "Tu pago de reserva expirará en menos de 2 horas. "
                "Confirma con administración para no perder tu horario.",
                "reservation",
            )
            has_changes = True

    if has_changes:
        db.session.commit()
    return finalized_count


def time_slot_to_minutes(time_slot):
    """Convert an HH:MM-HH:MM range to minute offsets, or return None if invalid."""
    if not isinstance(time_slot, str) or not re.fullmatch(
        r"\d{2}:\d{2}-\d{2}:\d{2}", time_slot
    ):
        return None
    try:
        start, end = time_slot.split("-")
        start_hour, start_minute = (int(part) for part in start.split(":"))
        end_hour, end_minute = (int(part) for part in end.split(":"))
        start_minutes = start_hour * 60 + start_minute
        end_minutes = end_hour * 60 + end_minute
    except (AttributeError, TypeError, ValueError):
        return None
    if (
        not 0 <= start_hour <= 23
        or not 0 <= end_hour <= 24
        or not 0 <= start_minute < 60
        or not 0 <= end_minute < 60
        or (end_hour == 24 and end_minute != 0)
        or end_minutes <= start_minutes
    ):
        return None
    return start_minutes, end_minutes


def time_slots_overlap(first, second):
    """Return whether two valid time ranges overlap."""
    first_range = time_slot_to_minutes(first)
    second_range = time_slot_to_minutes(second)
    return bool(
        first_range
        and second_range
        and first_range[0] < second_range[1]
        and first_range[1] > second_range[0]
    )


def reservation_conflicts(common_area_id, date, time_slot, exclude_id=None):
    query = Reservation.query.with_entities(Reservation.time_slot).filter(
        Reservation.common_area_id == common_area_id,
        Reservation.date == date,
        Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
        Reservation.is_archived.is_(False),
    )
    if exclude_id is not None:
        query = query.filter(Reservation.id != exclude_id)
    return any(time_slots_overlap(time_slot, existing) for (existing,) in query.all())


def reservation_availability(common_area_id, date):
    reserved_slots = [
        slot
        for (slot,) in Reservation.query.with_entities(Reservation.time_slot).filter(
            Reservation.common_area_id == common_area_id,
            Reservation.date == date,
            Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
            Reservation.is_archived.is_(False),
        ).all()
    ]
    occupied_slots = [
        slot for slot in VALID_TIME_SLOTS
        if any(time_slots_overlap(slot, reserved) for reserved in reserved_slots)
    ]
    return {
        "availableSlots": [slot for slot in VALID_TIME_SLOTS if slot not in occupied_slots],
        "occupiedSlots": occupied_slots,
    }
