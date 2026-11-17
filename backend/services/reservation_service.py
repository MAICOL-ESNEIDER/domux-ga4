"""Reservation schedule validation and availability queries."""

import re

from models import Reservation
from validators import STANDARD_TIME_SLOTS, VALID_TIME_SLOTS

ACTIVE_RESERVATION_STATUSES = ("activa", "aprobada")


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
