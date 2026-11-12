"""Visitas: historial con filtros, estadía prevista y nombres de los visitantes del QR.

Aquí están las reglas nuevas de HU-030 a HU-033 (RN-012); las rutas de
routes/security.py solo leen la solicitud y responden. Las funciones lanzan
ApiError con un mensaje claro y ninguna hace commit.
"""

from datetime import date, timedelta

from sqlalchemy.orm import selectinload

from errors import ApiError
from extensions import db
from models import User, Visit, VisitEvent
from time_utils import colombia_day_to_utc

#: La estadía prevista puede ir de 1 minuto a 7 días (RN-012).
MAX_EXPECTED_STAY_MINUTES = 7 * 24 * 60

#: Largo máximo del nombre de un visitante, igual que el de la visita.
MAX_VISITOR_NAME_LENGTH = 120

VISIT_STATUSES = ("pendiente", "aprobada", "rechazada")


# ---------------------------------------------------------------------------
# Estadía prevista (HU-031)
# ---------------------------------------------------------------------------

def expected_stay(value):
    """Lee la estadía prevista en minutos; None si no se indicó. Un valor inválido da error 400."""
    if value is None:
        return None
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 1 <= value <= MAX_EXPECTED_STAY_MINUTES
    ):
        raise ApiError(
            f"La estadía prevista debe ser un número entero de minutos entre 1 y {MAX_EXPECTED_STAY_MINUTES} (7 días)."
        )
    return value


# ---------------------------------------------------------------------------
# Nombres de los visitantes de un QR (HU-033)
# ---------------------------------------------------------------------------

def clean_visitor_names(value, max_people):
    """Lee los nombres que el residente escribió al crear el QR.

    Devuelve una lista sin espacios de más ni nombres repetidos (sin importar
    mayúsculas). No puede haber más nombres que personas en el QR.
    """
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ApiError("Los nombres de los visitantes deben ser una lista de textos.")
    names = []
    for item in value:
        name = " ".join(item.split())
        if not name:
            continue
        if len(name) > MAX_VISITOR_NAME_LENGTH:
            raise ApiError(f"Cada nombre puede tener hasta {MAX_VISITOR_NAME_LENGTH} caracteres.")
        if name.casefold() not in {existing.casefold() for existing in names}:
            names.append(name)
    if len(names) > max_people:
        raise ApiError(
            f"Escribiste {len(names)} nombres pero el QR es para {max_people} "
            f"{'persona' if max_people == 1 else 'personas'}."
        )
    return names


def pending_visitor_names(qr_pass):
    """Los nombres del QR que todavía no tienen una visita registrada con ese nombre."""
    registered = {visit.visitor_name.casefold() for visit in qr_pass.visits}
    return [name for name in qr_pass.names if name.casefold() not in registered]


# ---------------------------------------------------------------------------
# Historial de visitas (HU-030 y HU-032)
# ---------------------------------------------------------------------------

def _day(value, label):
    """Lee una fecha AAAA-MM-DD de la URL; None si no viene."""
    if value in (None, ""):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is None or parsed.isoformat() != value:
        raise ApiError(f"El filtro '{label}' debe ser una fecha AAAA-MM-DD.")
    return parsed


def visits_query(
    user, status=None, search=None, apartment_id=None, date_from=None, date_to=None, inside=None
):
    """Las visitas que puede ver el usuario, con los filtros del historial (HU-030).

    El administrador y el guardia ven todas; el residente, solo las de su
    apartamento (CA-HU-030-02). date_from y date_to son días de Colombia,
    ambos incluidos. inside=True deja las que entraron y no tienen salida
    (HU-032), de la que lleva más tiempo dentro a la más reciente.
    """
    query = Visit.query.options(
        selectinload(Visit.resident),
        selectinload(Visit.guard),
        selectinload(Visit.events).selectinload(VisitEvent.actor),
    )
    if user.role == "RESIDENT":
        if user.apartment_id is None:
            query = query.filter(Visit.resident_id == user.id)
        else:
            household = db.session.query(User.id).filter(
                User.apartment_id == user.apartment_id, User.role == "RESIDENT"
            )
            query = query.filter(Visit.resident_id.in_(household))
    if status:
        if status not in VISIT_STATUSES:
            raise ApiError("Estado de visita inválido.")
        query = query.filter(Visit.approval_status == status)
    if apartment_id is not None:
        query = query.filter(Visit.resident_id.in_(
            db.session.query(User.id).filter(User.apartment_id == apartment_id)
        ))
    first_day, last_day = _day(date_from, "from"), _day(date_to, "to")
    if first_day and last_day and first_day > last_day:
        raise ApiError("La fecha inicial no puede ser posterior a la final.")
    if first_day:
        query = query.filter(Visit.created_at >= colombia_day_to_utc(first_day))
    if last_day:
        query = query.filter(Visit.created_at < colombia_day_to_utc(last_day + timedelta(days=1)))
    if inside is True:
        query = query.filter(Visit.entered_at.isnot(None), Visit.exited_at.is_(None))
    elif inside is False:
        query = query.filter(db.or_(Visit.entered_at.is_(None), Visit.exited_at.isnot(None)))
    if search:
        pattern = f"%{search}%"
        query = query.join(User, Visit.resident_id == User.id).filter(db.or_(
            Visit.visitor_name.ilike(pattern),
            User.name.ilike(pattern),
            User.last_name.ilike(pattern),
            User.apartment.ilike(pattern),
        ))
    if inside is True:
        return query.order_by(Visit.entered_at, Visit.id)
    return query.order_by(Visit.created_at.desc(), Visit.id.desc())
