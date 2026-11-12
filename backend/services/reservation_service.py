"""Franjas, cruces y límites de las reservas de zonas comunes (HU-050 a HU-055, RN-019 a RN-022).

Las reglas de cada zona (horario, aforo, anticipación y plazos) están guardadas en la
zona; aquí solo se aplican.
"""

import calendar
from collections import defaultdict
from datetime import date, timedelta

from models import Reservation
from services.zone_rules import is_maintenance_day, slots_overlap

#: Las que ocupan la franja: las pendientes todavía no (RN-019).
ACTIVE_RESERVATION_STATUSES = ("activa", "aprobada")

#: Las que cuentan para los límites diario y semanal del residente.
LIMIT_RESERVATION_STATUSES = ("pendiente", "activa", "aprobada")


def reservation_conflicts(common_area_id, day, time_slot, exclude_id=None):
    """True si la franja se cruza con otra reserva activa o aprobada de la zona (RN-019).

    Se compara por horas, no por el texto: aunque la zona cambie de horario, dos
    franjas que se pisan siguen contando como cruce.
    """
    query = Reservation.query.with_entities(Reservation.time_slot).filter(
        Reservation.common_area_id == common_area_id,
        Reservation.date == day,
        Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
    )
    if exclude_id is not None:
        query = query.filter(Reservation.id != exclude_id)
    return any(slots_overlap(time_slot, taken) for (taken,) in query.all())


def _taken_slots(common_area_id, day):
    return [
        slot
        for (slot,) in Reservation.query.with_entities(Reservation.time_slot).filter(
            Reservation.common_area_id == common_area_id,
            Reservation.date == day,
            Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
        ).all()
    ]


def reservation_availability(area, day):
    """Franjas libres y ocupadas de la zona ese día (ISO AAAA-MM-DD).

    Si la zona está cerrada por mantenimiento (RN-021), no ofrece ninguna franja.
    """
    if is_maintenance_day(area.maintenance_weekday, date.fromisoformat(day)):
        return {"availableSlots": [], "occupiedSlots": [], "closed": True}
    taken = _taken_slots(area.id, day)
    occupied = [slot for slot in area.slots if any(slots_overlap(slot, other) for other in taken)]
    return {
        "availableSlots": [slot for slot in area.slots if slot not in occupied],
        "occupiedSlots": occupied,
        "closed": False,
    }


def month_calendar(area, year, month):
    """Días del mes que no se pueden reservar: los llenos y los cerrados (RN-020 y RN-021).

    Un día está lleno cuando ya no queda ninguna franja libre; mientras quede una,
    el calendario solo bloquea las horas ocupadas. Devuelve (llenos, cerrados) como
    listas de fechas ISO ordenadas.
    """
    prefix = f"{year:04d}-{month:02d}-"
    taken_by_day = defaultdict(list)
    for day, slot in Reservation.query.with_entities(Reservation.date, Reservation.time_slot).filter(
        Reservation.common_area_id == area.id,
        Reservation.date.like(f"{prefix}%"),
        Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
    ).all():
        taken_by_day[day].append(slot)
    slots = area.slots
    full = sorted(
        day
        for day, taken in taken_by_day.items()
        if slots and all(any(slots_overlap(slot, other) for other in taken) for slot in slots)
    )
    closed = [
        date(year, month, number).isoformat()
        for number in range(1, calendar.monthrange(year, month)[1] + 1)
        if is_maintenance_day(area.maintenance_weekday, date(year, month, number))
    ]
    return full, closed


def weekly_reservation_count(resident_id, common_area_id, day):
    """Reservas del residente en esa zona, en la semana (de lunes a domingo) de ``day``."""
    week_start = day - timedelta(days=day.weekday())
    week_end = week_start + timedelta(days=6)
    return Reservation.query.filter(
        Reservation.resident_id == resident_id,
        Reservation.common_area_id == common_area_id,
        Reservation.date.between(week_start.isoformat(), week_end.isoformat()),
        Reservation.status.in_(LIMIT_RESERVATION_STATUSES),
        Reservation.is_archived.is_(False),
    ).count()
