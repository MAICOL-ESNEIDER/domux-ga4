"""Radicado y semáforo de plazos de las PQRS (HU-072, HU-073 y RN-025).

Son funciones puras, sin base de datos, para que el modelo y las rutas las usen
sin ciclos de importación.
"""

from business_days import add_business_days, business_days_between
from time_utils import to_colombia

#: Plazo en días hábiles para responder una PQRS (HU-073). La RN-025 lo deja «por
#: tipo»: hoy todos los tipos usan 15; si un tipo necesita otro plazo, se agrega
#: en PQRS_TERM_BY_CATEGORY y nada más cambia.
PQRS_TERM_BUSINESS_DAYS = 15
PQRS_TERM_BY_CATEGORY = {}

#: Con estos días hábiles o menos para vencer, el semáforo pasa a amarillo.
PQRS_WARNING_BUSINESS_DAYS = 5

GREEN = "verde"
YELLOW = "amarillo"
RED = "rojo"

#: Estados en los que la PQRS sigue corriendo contra el plazo; la resuelta ya no.
RUNNING_STATUSES = ("abierta", "en_proceso")


def make_radicado(pqrs_id, created_at):
    """Número de radicado de una PQRS: «PQRS-2026-000123» (año de Colombia y número propio).

    Como lleva el id de la PQRS, nunca se repite.
    """
    return f"PQRS-{to_colombia(created_at).year}-{pqrs_id:06d}"


def pqrs_term_days(category):
    """Plazo, en días hábiles, de una PQRS de ese tipo."""
    return PQRS_TERM_BY_CATEGORY.get(category, PQRS_TERM_BUSINESS_DAYS)


def pqrs_semaphore(created_day, today, category=None):
    """Semáforo de una PQRS que sigue sin resolverse (RN-025).

    ``created_day`` es el día de Colombia en que se radicó y ``today`` el día de
    hoy. El plazo corre en días hábiles: no cuentan sábados, domingos ni festivos
    y el día de radicación tampoco. Devuelve un diccionario con:

    * ``color``: verde si faltan más de 5 días hábiles, amarillo si faltan 5 o
      menos (incluido el último día) y rojo si el plazo ya venció.
    * ``daysRemaining``: días hábiles que faltan; negativo si ya venció.
    * ``dueDate``: último día para responder, en formato AAAA-MM-DD.
    """
    due_day = add_business_days(created_day, pqrs_term_days(category))
    if today <= due_day:
        remaining = business_days_between(today, due_day)
    else:
        remaining = -business_days_between(due_day, today)
    if remaining < 0:
        color = RED
    elif remaining <= PQRS_WARNING_BUSINESS_DAYS:
        color = YELLOW
    else:
        color = GREEN
    return {"color": color, "daysRemaining": remaining, "dueDate": due_day.isoformat()}
