"""Bloqueo de cuentas tras intentos fallidos (HU-006, RN-002 y SEC-001).

Después de 5 intentos fallidos seguidos, la cuenta (o el PIN de un guardia) se
bloquea 15 minutos. Un inicio correcto antes del quinto intento pone el
contador en cero. Las funciones dejan los cambios en la sesión: quien las llama
hace el commit, porque una respuesta de error no guarda nada por sí sola.
"""

from datetime import timedelta
from math import ceil

from sqlalchemy.exc import IntegrityError

from extensions import db
from models import LoginAttempt
from time_utils import utc_now

#: Intentos fallidos seguidos que bloquean la cuenta y minutos que dura el bloqueo.
MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15

#: Qué se está protegiendo: la contraseña de una cuenta o el PIN de un guardia.
LOGIN = "login"
PIN = "pin"


def _find(kind, subject):
    return LoginAttempt.query.filter_by(kind=kind, subject=subject).first()


def _find_or_create(kind, subject):
    """Busca la fila de intentos; si no existe la crea (sin chocar con otra solicitud)."""
    row = _find(kind, subject)
    if row is None:
        try:
            with db.session.begin_nested():
                row = LoginAttempt(kind=kind, subject=subject, failed_count=0)
                db.session.add(row)
        except IntegrityError:
            # Otra solicitud la creó al mismo tiempo: se usa esa.
            row = _find(kind, subject)
    return row


def seconds_locked(kind, subject):
    """Segundos que faltan para que termine el bloqueo; 0 si no está bloqueado."""
    row = _find(kind, subject)
    if row is None or row.locked_until is None:
        return 0
    return max(0, ceil((row.locked_until - utc_now()).total_seconds()))


def register_failure(kind, subject):
    """Cuenta un intento fallido y bloquea al llegar al límite.

    Devuelve True si después de este intento quedó bloqueado. Si el bloqueo
    anterior ya terminó, el conteo empieza de cero.
    """
    now = utc_now()
    row = _find_or_create(kind, subject)
    if row.locked_until is not None and row.locked_until <= now:
        row.failed_count = 0
        row.locked_until = None
    row.failed_count += 1
    row.last_failed_at = now
    if row.failed_count >= MAX_FAILED_ATTEMPTS:
        row.locked_until = now + timedelta(minutes=LOCK_MINUTES)
    return row.locked_until is not None


def register_success(kind, subject):
    """Pone el contador en cero y quita el bloqueo (inicio correcto o clave restablecida)."""
    row = _find(kind, subject)
    if row is not None:
        row.failed_count = 0
        row.locked_until = None
