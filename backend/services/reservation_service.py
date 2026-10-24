"""Reservation schedule validation and availability queries."""

from models import Reservation
from validators import VALID_TIME_SLOTS

ACTIVE_RESERVATION_STATUSES = ("activa", "aprobada")


def reservation_conflicts(common_area_id, date, time_slot, exclude_id=None):
    query = Reservation.query.filter(
        Reservation.common_area_id == common_area_id,
        Reservation.date == date,
        Reservation.time_slot == time_slot,
        Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
    )
    if exclude_id is not None:
        query = query.filter(Reservation.id != exclude_id)
    return query.first() is not None


def reservation_availability(common_area_id, date):
    occupied_slots = {
        slot
        for (slot,) in Reservation.query.with_entities(Reservation.time_slot).filter(
            Reservation.common_area_id == common_area_id,
            Reservation.date == date,
            Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
        ).all()
    }
    return {
        "availableSlots": [slot for slot in VALID_TIME_SLOTS if slot not in occupied_slots],
        "occupiedSlots": [slot for slot in VALID_TIME_SLOTS if slot in occupied_slots],
    }
