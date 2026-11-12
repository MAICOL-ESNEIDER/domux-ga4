"""Días hábiles y festivos de Colombia (HU-073, RN-021 y RN-025).

Un día hábil es de lunes a viernes y no es festivo. Los festivos se calculan con
la ley Emiliani (Ley 51 de 1983), así no hay que cargar una lista nueva cada año:

* Caen siempre en su fecha: 1 de enero, 1 de mayo, 20 de julio, 7 de agosto,
  8 y 25 de diciembre.
* Se pasan al lunes siguiente (o se quedan si ya son lunes): Reyes Magos,
  San José, San Pedro y San Pablo, Asunción, Día de la Raza, Todos los Santos e
  Independencia de Cartagena.
* Dependen de la Pascua: Jueves y Viernes Santo (en su día) y, pasados al lunes,
  la Ascensión, Corpus Christi y el Sagrado Corazón.
"""

from datetime import date, timedelta
from functools import lru_cache

#: Festivos que caen siempre en su fecha: (mes, día).
_FIXED_HOLIDAYS = ((1, 1), (5, 1), (7, 20), (8, 7), (12, 8), (12, 25))

#: Festivos que se pasan al lunes siguiente (ley Emiliani): (mes, día).
_MOVED_TO_MONDAY = ((1, 6), (3, 19), (6, 29), (8, 15), (10, 12), (11, 1), (11, 11))

#: Festivos de la Pascua que se pasan al lunes: días después del Domingo de Pascua
#: de la Ascensión, Corpus Christi y el Sagrado Corazón.
_EASTER_MOVED_TO_MONDAY = (39, 60, 68)


def easter_sunday(year):
    """Domingo de Pascua de ese año (algoritmo gregoriano de Meeus, Jones y Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741  (nombre del algoritmo original)
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _monday_on_or_after(day):
    """El mismo día si es lunes; si no, el lunes que sigue."""
    return day + timedelta(days=(7 - day.weekday()) % 7)


@lru_cache(maxsize=32)
def colombian_holidays(year):
    """Los festivos de Colombia de ese año, como un conjunto de fechas."""
    easter = easter_sunday(year)
    holidays = {date(year, month, day) for month, day in _FIXED_HOLIDAYS}
    holidays.update(
        _monday_on_or_after(date(year, month, day)) for month, day in _MOVED_TO_MONDAY
    )
    holidays.update((easter - timedelta(days=3), easter - timedelta(days=2)))
    holidays.update(
        _monday_on_or_after(easter + timedelta(days=days)) for days in _EASTER_MOVED_TO_MONDAY
    )
    return frozenset(holidays)


def is_holiday(day):
    """True si el día es festivo en Colombia."""
    return day in colombian_holidays(day.year)


def is_business_day(day):
    """True si es un día hábil: de lunes a viernes y no festivo."""
    return day.weekday() < 5 and not is_holiday(day)


def business_days_between(start, end):
    """Días hábiles que hay después de ``start`` y hasta ``end`` (``end`` cuenta, ``start`` no).

    Si ``end`` no es posterior a ``start``, no hay ninguno.
    """
    count = 0
    day = start
    while day < end:
        day += timedelta(days=1)
        if is_business_day(day):
            count += 1
    return count


def add_business_days(start, days):
    """El día en que se cumplen ``days`` días hábiles después de ``start``."""
    day = start
    pending = days
    while pending > 0:
        day += timedelta(days=1)
        if is_business_day(day):
            pending -= 1
    return day
