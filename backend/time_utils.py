"""Hora de Colombia para todo el servidor (ADR-011, TT-031 y DEF-002).

La base guarda las fechas y horas en UTC (hora universal), sin zona horaria. Lo
que se muestra y lo que se compara con «hoy» usa la hora de Colombia
(America/Bogota: UTC-5, sin horario de verano). Render corre en UTC, así que
date.today() daría el día siguiente después de las 7 de la noche: por eso las
rutas usan colombia_today() y nunca date.today().
"""

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

#: Zona horaria de la unidad residencial. En Windows la aporta el paquete tzdata.
COLOMBIA = ZoneInfo("America/Bogota")


def utc_now():
    """Fecha y hora actual en UTC y sin zona: así se guarda en la base."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def colombia_now():
    """Fecha y hora actual en Colombia."""
    return datetime.now(COLOMBIA)


def colombia_today():
    """La fecha de hoy en Colombia."""
    return colombia_now().date()


def to_colombia(value):
    """Pasa una hora guardada en UTC (sin zona) a la hora de Colombia."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).astimezone(COLOMBIA)


def format_colombia(value):
    """Una hora guardada en UTC como se muestra en la API: «2026-11-10 21:30» (hora de Colombia)."""
    return to_colombia(value).strftime("%Y-%m-%d %H:%M") if value else None


def colombia_day_to_utc(day):
    """El momento, en UTC y sin zona, en que empieza ese día en Colombia.

    Sirve para filtrar lo guardado en UTC por días de Colombia: las visitas del
    día D son las que van de colombia_day_to_utc(D) a colombia_day_to_utc(D + 1 día).
    """
    return datetime.combine(day, time.min, tzinfo=COLOMBIA).astimezone(timezone.utc).replace(tzinfo=None)
