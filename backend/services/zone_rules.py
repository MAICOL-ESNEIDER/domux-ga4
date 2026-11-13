"""Reglas de las zonas comunes: franjas, aforo, anticipación y plazos (HU-055, RN-020 a RN-022).

Una reserva puede cubrir una franja, varias franjas seguidas (hasta el máximo de la zona) o, si la
zona lo permite, el día completo. Siempre se guarda como un rango «HH:MM-HH:MM».

Lo que cambia de un conjunto a otro (horario, aforo, anticipación y plazo de
cancelación) no está en el código: cada zona lo guarda y la administración lo
ajusta desde la web. Aquí están los valores por defecto, la revisión de los
cambios y los cálculos que no necesitan la base de datos.
"""

from datetime import timedelta

from business_days import is_holiday
from errors import ApiError
from validators import validate_time

#: Reglas de una zona que la administración todavía no ha ajustado.
DEFAULT_OPEN_TIME = "08:00"
DEFAULT_CLOSE_TIME = "22:00"
DEFAULT_SLOT_MINUTES = 120
DEFAULT_MIN_ADVANCE_DAYS = 0
DEFAULT_MAX_ADVANCE_DAYS = 60
#: Cancelación hasta 3 días antes de la fecha reservada (RN-020); cada zona puede bajarlo.
DEFAULT_CANCEL_DEADLINE_DAYS = 3
#: Reservas por semana que cada residente puede tener en una zona (antes eran 2 en total).
DEFAULT_WEEKLY_LIMIT = 2

#: Por defecto se reserva una franja a la vez y no el día completo; cada zona lo puede cambiar
#: (por ejemplo, el salón social se reserva todo el día y el BBQ hasta dos franjas seguidas).
DEFAULT_MAX_CONSECUTIVE_SLOTS = 1
DEFAULT_ALLOW_FULL_DAY = False

#: Duraciones de franja que la administración puede elegir, en minutos.
ALLOWED_SLOT_MINUTES = (30, 60, 90, 120, 180, 240)

WEEKDAY_NAMES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def _to_minutes(hour_text):
    hours, minutes = hour_text.split(":")
    return int(hours) * 60 + int(minutes)


def _to_hour_text(total_minutes):
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def zone_slots(open_time, close_time, slot_minutes):
    """Las franjas del día de una zona, como «08:00-10:00», desde la apertura hasta el cierre.

    Una franja que no cabe completa antes del cierre no se ofrece.
    """
    start = _to_minutes(open_time)
    end = _to_minutes(close_time)
    slots = []
    while start + slot_minutes <= end:
        slots.append(f"{_to_hour_text(start)}-{_to_hour_text(start + slot_minutes)}")
        start += slot_minutes
    return slots


#: Las franjas de una zona con el horario por defecto: de 08:00 a 22:00, de a 2 horas.
DEFAULT_SLOTS = tuple(zone_slots(DEFAULT_OPEN_TIME, DEFAULT_CLOSE_TIME, DEFAULT_SLOT_MINUTES))


def _slot_range(slot):
    """Inicio y fin de una franja «HH:MM-HH:MM», en minutos; None si no tiene ese formato."""
    try:
        start, end = slot.split("-")
        return _to_minutes(start), _to_minutes(end)
    except (AttributeError, ValueError):
        return None


def full_day_slot(open_time, close_time, slot_minutes):
    """El rango del día completo, como «08:00-22:00»: de la apertura al final de la última franja.

    Si al final del día sobra un pedazo donde no cabe una franja completa, ese pedazo no se reserva.
    None si la zona no tiene franjas.
    """
    slots = zone_slots(open_time, close_time, slot_minutes)
    if not slots:
        return None
    return f"{slots[0].split('-')[0]}-{slots[-1].split('-')[1]}"


def slot_span(open_time, close_time, slot_minutes, time_slot):
    """Cuántas franjas seguidas cubre «HH:MM-HH:MM» en una zona; None si no es un rango de la zona.

    El rango tiene que empezar donde empieza una franja y terminar donde termina otra (la misma o
    una posterior): «08:00-12:00» son dos franjas de 2 horas; «09:00-11:00» no es de la zona.
    """
    requested = _slot_range(time_slot)
    if requested is None:
        return None
    start, end = requested
    ranges = [_slot_range(slot) for slot in zone_slots(open_time, close_time, slot_minutes)]
    if end <= start or start not in {first for first, _ in ranges} or end not in {last for _, last in ranges}:
        return None
    return (end - start) // slot_minutes


def slots_overlap(first, second):
    """True si dos franjas se cruzan en algún minuto (RN-019).

    Dos franjas pegadas, como 10:00-12:00 y 12:00-14:00, no se cruzan. Así el cruce
    se revisa por horas y no por el texto: sigue bien aunque la zona cambie de horario.
    """
    first_range, second_range = _slot_range(first), _slot_range(second)
    if first_range is None or second_range is None:
        return first == second
    return first_range[0] < second_range[1] and second_range[0] < first_range[1]


def is_maintenance_day(maintenance_weekday, day):
    """True si ese día la zona está cerrada por mantenimiento (RN-021).

    La zona fija su día de mantenimiento (0 es lunes). Si ese día es festivo, el
    mantenimiento pasa al día siguiente.
    """
    if maintenance_weekday is None:
        return False
    if day.weekday() == maintenance_weekday:
        return not is_holiday(day)
    previous = day - timedelta(days=1)
    return previous.weekday() == maintenance_weekday and is_holiday(previous)


def days_text(days):
    """«1 día» o «3 días», para los mensajes."""
    return f"{days} día" if days == 1 else f"{days} días"


def human_date(day):
    """La fecha como la escribe un colombiano: 13/11/2026."""
    return f"{day.day:02d}/{day.month:02d}/{day.year}"


def _time_rule(value, label):
    error = validate_time(value)
    if error:
        raise ApiError(f"{label}: {error[0].lower()}{error[1:]}")
    return value


def _whole_rule(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ApiError(f"{label} debe ser un número entero entre {low} y {high}.")
    return value


def parse_zone_rules(data, area):
    """Revisa los cambios de reglas que pide la administración y devuelve {columna: valor}.

    Solo se cambian los datos que vienen en la solicitud. Los que llegan en
    ``null`` vuelven al valor por defecto (el aforo y el día de mantenimiento
    vuelven a «sin definir»). Después de revisar cada dato se comprueba que
    todos juntos tengan sentido: la zona tiene que abrir antes de cerrar, caber
    al menos una franja y el máximo de anticipación no puede ser menor que el mínimo.
    """
    changes = {}
    if "openTime" in data:
        changes["open_time"] = _time_rule(data["openTime"], "La hora de apertura")
    if "closeTime" in data:
        changes["close_time"] = _time_rule(data["closeTime"], "La hora de cierre")
    if "slotMinutes" in data:
        value = data["slotMinutes"]
        if isinstance(value, bool) or not isinstance(value, int) or value not in ALLOWED_SLOT_MINUTES:
            options = ", ".join(str(option) for option in ALLOWED_SLOT_MINUTES)
            raise ApiError(f"La duración de cada franja debe ser de {options} minutos.")
        changes["slot_minutes"] = value
    if "capacity" in data:
        value = data["capacity"]
        changes["capacity"] = None if value is None else _whole_rule(value, "El aforo", 1, 2000)
    if "minAdvanceDays" in data:
        changes["min_advance_days"] = _whole_rule(
            data["minAdvanceDays"], "La anticipación mínima", 0, 30
        )
    if "maxAdvanceDays" in data:
        changes["max_advance_days"] = _whole_rule(
            data["maxAdvanceDays"], "La anticipación máxima", 1, 365
        )
    if "cancelDeadlineDays" in data:
        value = data["cancelDeadlineDays"]
        changes["cancel_deadline_days"] = (
            DEFAULT_CANCEL_DEADLINE_DAYS
            if value is None
            else _whole_rule(value, "El plazo de cancelación", 1, DEFAULT_CANCEL_DEADLINE_DAYS)
        )
    if "weeklyLimit" in data:
        value = data["weeklyLimit"]
        changes["weekly_limit"] = (
            DEFAULT_WEEKLY_LIMIT if value is None else _whole_rule(value, "El límite semanal", 1, 14)
        )
    if "maintenanceWeekday" in data:
        value = data["maintenanceWeekday"]
        changes["maintenance_weekday"] = (
            None if value is None else _whole_rule(value, "El día de mantenimiento", 0, 6)
        )
    if "maxConsecutiveSlots" in data:
        value = data["maxConsecutiveSlots"]
        changes["max_consecutive_slots"] = (
            DEFAULT_MAX_CONSECUTIVE_SLOTS
            if value is None
            else _whole_rule(value, "El máximo de franjas seguidas", 1, 48)
        )
    if "allowFullDay" in data:
        value = data["allowFullDay"]
        if value is None:
            changes["allow_full_day"] = DEFAULT_ALLOW_FULL_DAY
        elif isinstance(value, bool):
            changes["allow_full_day"] = value
        else:
            raise ApiError("«Se puede reservar el día completo» debe ser sí o no.")
    if not changes:
        raise ApiError("Indica al menos una regla de la zona para cambiar.")

    def final(column):
        return changes[column] if column in changes else getattr(area, column)

    opens, closes = _to_minutes(final("open_time")), _to_minutes(final("close_time"))
    if closes <= opens:
        raise ApiError("La hora de cierre debe ser después de la hora de apertura.")
    if closes - opens < final("slot_minutes"):
        raise ApiError(
            f"Entre la apertura y el cierre debe caber al menos una franja de {final('slot_minutes')} minutos."
        )
    if final("max_advance_days") < final("min_advance_days"):
        raise ApiError("La anticipación máxima no puede ser menor que la mínima.")
    slots_per_day = len(zone_slots(final("open_time"), final("close_time"), final("slot_minutes")))
    if final("max_consecutive_slots") > slots_per_day:
        raise ApiError(
            f"La zona tiene {slots_per_day} franjas al día: el máximo de franjas seguidas no puede pasar de "
            f"{slots_per_day}."
        )
    return changes
