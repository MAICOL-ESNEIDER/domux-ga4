"""Radicado y semáforo de plazos de las PQRS (HU-072, HU-073 y RN-025).

Son funciones sin consultas propias, para que el modelo y las rutas las usen sin ciclos de importación.
Los plazos salen de las reglas de la unidad (services/unit_rules.py), que la administración puede
cambiar; si se las pasa como ``rules`` no consultan nada (así se prueban sin base de datos).
"""

from business_days import add_business_days, business_days_between
from services.unit_rules import current_rules
from time_utils import colombia_today, to_colombia

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


def pqrs_term_days(category, rules=None):
    """Plazo, en días hábiles, de una PQRS de ese tipo: el que fijó la administración (RN-025)."""
    return (rules or current_rules()).pqrs_term_for(category)


def pqrs_semaphore(created_day, today, category=None, rules=None):
    """Semáforo de una PQRS que sigue sin resolverse (RN-025).

    ``created_day`` es el día de Colombia en que se radicó y ``today`` el día de
    hoy. El plazo corre en días hábiles: no cuentan sábados, domingos ni festivos
    y el día de radicación tampoco. Los días del plazo y del aviso son los de las
    reglas de la unidad (por defecto, 15 y 5). Devuelve un diccionario con:

    * ``color``: verde si faltan más días hábiles que los del aviso, amarillo si
      faltan esos o menos (incluido el último día) y rojo si el plazo ya venció.
    * ``daysRemaining``: días hábiles que faltan; negativo si ya venció.
    * ``dueDate``: último día para responder, en formato AAAA-MM-DD.
    """
    rules = rules or current_rules()
    due_day = add_business_days(created_day, rules.pqrs_term_for(category))
    if today <= due_day:
        remaining = business_days_between(today, due_day)
    else:
        remaining = -business_days_between(due_day, today)
    if remaining < 0:
        color = RED
    elif remaining <= rules.pqrs_warning_days:
        color = YELLOW
    else:
        color = GREEN
    return {"color": color, "daysRemaining": remaining, "dueDate": due_day.isoformat()}


def running_semaphore(status, created_at, category=None, today=None):
    """Semáforo de una PQRS según como está guardada, o None si su plazo ya no corre.

    ``created_at`` es la hora de radicación como se guarda (UTC, sin zona) y ``today`` el día de
    Colombia (por defecto, hoy). Una PQRS resuelta deja de correr contra el plazo, así que no tiene
    semáforo. La usan el modelo, el panel y la bandeja de la web, para que los tres cuenten igual.
    """
    if status not in RUNNING_STATUSES or created_at is None:
        return None
    return pqrs_semaphore(to_colombia(created_at).date(), today or colombia_today(), category)
