"""Vista liviana de las reservas para la lista de la web (HU-079) y lectura de los adjuntos de su conversación.

La lista de siempre (GET /api/reservations) entrega todas las reservas de una vez, cada una con su
conversación y sus adjuntos en base64: sirve para el celular de un residente, pero no para una lista
de administración. Aquí está la otra vista que pide ``?view=summary``: filas sin conversación ni
adjuntos, paginadas y con lo que más urge primero, más el número de reservas de cada estado para las
pestañas. Los adjuntos se piden uno por uno cuando la página los muestra.

Ninguna función de este archivo guarda en la base.
"""

from sqlalchemy import and_, case, func, or_, select

from errors import ApiError
from extensions import db
from models import CommonArea, Reservation, ReservationMessage, User
from services.list_view import full_name
from services.media import decode_media
from services.reservation_service import PENDING_RESERVATION_STATUSES, reservation_conflicts
from time_utils import colombia_today, format_colombia
from validators import validate_iso_date

#: Los estados que se pueden pedir como filtro, además de «por_aprobar» (pendiente y activa, las que
#: esperan la decisión de la administración).
STATUS_FILTERS = ("pendiente", "activa", "aprobada", "rechazada", "cancelada")
PENDING_FILTER = "por_aprobar"


# ---------------------------------------------------------------------------
# Lo que se pide en la URL
# ---------------------------------------------------------------------------

def parse_status(value):
    """Los estados pedidos con ``?status=``: una tupla, o None si no se pidió ninguno.

    «por_aprobar» reúne los estados que esperan decisión; cualquier otro valor es un estado de reserva.
    """
    if value in (None, ""):
        return None
    if value == PENDING_FILTER:
        return PENDING_RESERVATION_STATUSES
    if value not in STATUS_FILTERS:
        raise ApiError(
            "El filtro 'status' debe ser por_aprobar, pendiente, activa, aprobada, rechazada o cancelada."
        )
    return (value,)


def parse_day(value, name):
    """Una fecha AAAA-MM-DD pedida en la URL, o None si no se pidió."""
    if value in (None, ""):
        return None
    if validate_iso_date(value):
        raise ApiError(f"El filtro '{name}' debe ser una fecha con formato AAAA-MM-DD.")
    return value


def filter_reservations(query, statuses=None, area_id=None, date_from=None, date_to=None, search=""):
    """Aplica los filtros a una consulta de reservas unida con su residente y su zona.

    Las fechas se guardan como texto AAAA-MM-DD, que ordena igual que el calendario, y los dos
    extremos cuentan (para ver un solo día se pide el mismo en los dos).
    """
    if date_from and date_to and date_from > date_to:
        raise ApiError("La fecha 'dateFrom' no puede ser posterior a 'dateTo'.")
    if statuses:
        query = query.filter(Reservation.status.in_(statuses))
    if area_id is not None:
        query = query.filter(Reservation.common_area_id == area_id)
    if date_from:
        query = query.filter(Reservation.date >= date_from)
    if date_to:
        query = query.filter(Reservation.date <= date_to)
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(
            CommonArea.name.ilike(pattern),
            User.name.ilike(pattern),
            User.last_name.ilike(pattern),
            (User.name + " " + User.last_name).ilike(pattern),
            User.apartment.ilike(pattern),
        ))
    return query


# ---------------------------------------------------------------------------
# La lista liviana
# ---------------------------------------------------------------------------

def status_counts(query):
    """Cuántas reservas hay de cada estado entre las que dejó la consulta (sin el filtro de estado).

    Son los números de las pestañas: por aprobar (pendientes y activas), aprobadas, rechazadas,
    canceladas y el total.
    """
    rows = (
        query.order_by(None)
        .with_entities(Reservation.status, func.count(Reservation.id))
        .group_by(Reservation.status)
        .all()
    )
    by_status = {status: count for status, count in rows}
    return {
        "pending": sum(by_status.get(status, 0) for status in PENDING_RESERVATION_STATUSES),
        "approved": by_status.get("aprobada", 0),
        "rejected": by_status.get("rechazada", 0),
        "cancelled": by_status.get("cancelada", 0),
        "all": sum(by_status.values()),
    }


def _order(today):
    """Primero las que esperan decisión, la de fecha más próxima primero; luego las aprobadas que
    todavía no llegan, también de la más próxima a la más lejana; al final lo demás, de la más
    reciente a la más antigua."""
    today_text = today.isoformat()
    waiting = Reservation.status.in_(PENDING_RESERVATION_STATUSES)
    coming = and_(Reservation.status == "aprobada", Reservation.date >= today_text)
    group = case((waiting, 0), (coming, 1), else_=2)
    upcoming = or_(waiting, coming)
    return (
        group,
        case((upcoming, Reservation.date)).asc(),
        case((upcoming, Reservation.time_slot)).asc(),
        case((upcoming, Reservation.id)).asc(),
        case((upcoming, None), else_=Reservation.date).desc(),
        case((upcoming, None), else_=Reservation.time_slot).desc(),
        Reservation.id.desc(),
    )


def _summary_row(row):
    return {
        "id": row.id,
        "commonAreaId": row.common_area_id,
        "commonAreaName": row.area_name,
        "date": row.date,
        "timeSlot": row.time_slot,
        "attendees": row.attendees,
        "status": row.status or "activa",
        "isArchived": bool(row.is_archived),
        "residentId": row.resident_id,
        "residentName": full_name(row.resident_first_name, row.resident_last_name),
        "apartment": row.apartment,
        "createdByAdministration": row.created_by_admin_id is not None,
        "messageCount": row.message_count or 0,
        "attachmentCount": row.attachment_count or 0,
        "createdAt": format_colombia(row.created_at),
    }


def summary_page(query, page, size):
    """Una página de la lista liviana: ``{reservations, page, pageSize, total, totalPages}``.

    ``query`` es la consulta de reservas unida con su residente y su zona, con los filtros ya puestos.
    Las filas se arman con solo las columnas que la lista muestra, así nunca se cargan las
    conversaciones ni los adjuntos.
    """
    total = query.count()
    messages = (
        select(func.count(ReservationMessage.id))
        .where(ReservationMessage.reservation_id == Reservation.id)
        .correlate(Reservation)
        .scalar_subquery()
    )
    attachments = (
        select(func.count(ReservationMessage.id))
        .where(ReservationMessage.reservation_id == Reservation.id, ReservationMessage.media_url.is_not(None))
        .correlate(Reservation)
        .scalar_subquery()
    )
    rows = (
        query.with_entities(
            Reservation.id, Reservation.common_area_id, Reservation.date, Reservation.time_slot,
            Reservation.attendees, Reservation.status, Reservation.is_archived, Reservation.resident_id,
            Reservation.created_by_admin_id, Reservation.created_at,
            CommonArea.name.label("area_name"),
            User.name.label("resident_first_name"),
            User.last_name.label("resident_last_name"),
            User.apartment.label("apartment"),
            messages.label("message_count"),
            attachments.label("attachment_count"),
        )
        .order_by(*_order(colombia_today()))
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return {
        "reservations": [_summary_row(row) for row in rows],
        "page": page,
        "pageSize": size,
        "total": total,
        "totalPages": (total + size - 1) // size,
    }


# ---------------------------------------------------------------------------
# Una reserva y los adjuntos de su conversación
# ---------------------------------------------------------------------------

def detail_dict(reservation):
    """La reserva con su conversación, como ``to_dict``, pero sin el contenido de los adjuntos.

    En lugar de ``mediaUrl`` cada mensaje trae ``hasMedia``; el archivo se pide aparte con
    ``attachment``. Además dice si, mientras la reserva espera decisión, su franja ya la ocupa otra
    reserva aprobada (RN-019): en ese caso no se puede aprobar.
    """
    data = reservation.to_dict()
    for message in data["messages"]:
        message["hasMedia"] = bool(message.pop("mediaUrl"))
    data["slotTaken"] = reservation.status in PENDING_RESERVATION_STATUSES and reservation_conflicts(
        reservation.common_area_id, reservation.date, reservation.time_slot, exclude_id=reservation.id,
    )
    return data


def attachment(reservation_id, message_id):
    """El adjunto de un mensaje de la conversación, como ``(bytes, tipo)``, o None si no existe o no se puede mostrar."""
    row = (
        db.session.query(ReservationMessage.media_url)
        .filter(ReservationMessage.reservation_id == reservation_id, ReservationMessage.id == message_id)
        .first()
    )
    return decode_media(row.media_url) if row is not None else None

