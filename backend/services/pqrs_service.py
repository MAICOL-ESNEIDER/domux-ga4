"""Vista liviana de las PQRS para la bandeja de la web (HU-078) y lectura de sus adjuntos.

La lista de siempre (GET /api/pqrs) entrega todas las PQRS de una vez, cada una con su conversación
y sus fotos en base64: sirve para el celular de un residente, pero no para una bandeja de
administración. Aquí está la otra vista que pide ``?view=summary``: filas sin conversación ni
adjuntos, paginadas y ordenadas por urgencia, con el plazo ya calculado. Los adjuntos se piden uno
por uno cuando la página los muestra.

Ninguna función de este archivo guarda en la base.
"""

from sqlalchemy import case, false, func, select

from errors import ApiError
from extensions import db
from models import Pqrs, PqrsMessage, User
from services.list_view import full_name
from services.media import decode_media
from services.pqrs_rules import GREEN, RED, RUNNING_STATUSES, YELLOW, running_semaphore
from time_utils import colombia_today, format_colombia

#: Los colores del semáforo que se pueden pedir como filtro.
SEMAPHORE_FILTERS = (GREEN, YELLOW, RED)


# ---------------------------------------------------------------------------
# Lo que se pide en la URL
# ---------------------------------------------------------------------------

def parse_semaphore(value):
    """El color de semáforo pedido con ``?semaphore=``, o None si no se pidió ninguno."""
    if value in (None, ""):
        return None
    if value not in SEMAPHORE_FILTERS:
        raise ApiError("El filtro 'semaphore' debe ser verde, amarillo o rojo.")
    return value


# ---------------------------------------------------------------------------
# La lista liviana
# ---------------------------------------------------------------------------

def filter_by_semaphore(query, color):
    """Deja solo las PQRS en curso que hoy tienen ese color de semáforo.

    El plazo corre en días hábiles y festivos de Colombia, que la base no sabe contar; por eso se
    calcula en Python sobre las PQRS en curso que ya pasaron los demás filtros (son pocas: las
    resueltas no tienen semáforo) y se filtra por su id.
    """
    today = colombia_today()
    rows = (
        query.filter(Pqrs.status.in_(RUNNING_STATUSES))
        .with_entities(Pqrs.id, Pqrs.status, Pqrs.created_at, Pqrs.category)
        .all()
    )
    matching = []
    for row in rows:
        semaphore = running_semaphore(row.status, row.created_at, row.category, today)
        if semaphore is not None and semaphore["color"] == color:
            matching.append(row.id)
    return query.filter(Pqrs.id.in_(matching)) if matching else query.filter(false())


def _urgency_order():
    """Primero lo que sigue sin resolverse, de la más antigua (la más urgente) a la más nueva; después
    las resueltas, de la más reciente a la más antigua."""
    running = Pqrs.status.in_(RUNNING_STATUSES)
    return (
        case((running, 0), else_=1),
        case((running, Pqrs.created_at)).asc(),
        case((running, Pqrs.id)).asc(),
        case((running, None), else_=Pqrs.created_at).desc(),
        Pqrs.id.desc(),
    )


def _summary_row(row, today):
    semaphore = running_semaphore(row.status, row.created_at, row.category, today)
    # La solicitud y su primer mensaje guardan el mismo adjunto: se cuenta una sola vez.
    attachments = max(row.message_media or 0, 1 if row.has_media else 0)
    return {
        "id": row.id,
        "radicado": row.radicado,
        "category": row.category or "Petición",
        "subject": row.subject or "",
        "status": row.status or "abierta",
        "isArchived": bool(row.is_archived),
        "semaphore": semaphore["color"] if semaphore else None,
        "daysRemaining": semaphore["daysRemaining"] if semaphore else None,
        "dueDate": semaphore["dueDate"] if semaphore else None,
        "residentId": row.resident_id,
        "residentName": full_name(row.resident_first_name, row.resident_last_name),
        "apartment": row.apartment,
        "createdByAdministration": row.created_by_admin_id is not None,
        "hasMedia": attachments > 0,
        "attachmentCount": attachments,
        "createdAt": format_colombia(row.created_at),
        "updatedAt": format_colombia(row.updated_at),
    }


def summary_page(query, page, size):
    """Una página de la lista liviana: ``{pqrs, page, pageSize, total, totalPages}``.

    ``query`` es la consulta de PQRS unida con su residente y con los filtros ya puestos. Las filas se
    arman con solo las columnas que la bandeja muestra, así nunca se cargan las fotos ni los textos
    largos de cientos de PQRS.
    """
    total = query.count()
    message_media = (
        select(func.count(PqrsMessage.id))
        .where(PqrsMessage.pqrs_id == Pqrs.id, PqrsMessage.media_url.is_not(None))
        .correlate(Pqrs)
        .scalar_subquery()
    )
    rows = (
        query.with_entities(
            Pqrs.id, Pqrs.radicado, Pqrs.category, Pqrs.subject, Pqrs.status, Pqrs.is_archived,
            Pqrs.resident_id, Pqrs.created_by_admin_id, Pqrs.created_at, Pqrs.updated_at,
            Pqrs.media_url.is_not(None).label("has_media"),
            message_media.label("message_media"),
            User.name.label("resident_first_name"),
            User.last_name.label("resident_last_name"),
            User.apartment.label("apartment"),
        )
        .order_by(*_urgency_order())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    today = colombia_today()
    return {
        "pqrs": [_summary_row(row, today) for row in rows],
        "page": page,
        "pageSize": size,
        "total": total,
        "totalPages": (total + size - 1) // size,
    }


# ---------------------------------------------------------------------------
# Una PQRS y sus adjuntos
# ---------------------------------------------------------------------------

def detail_dict(pqrs):
    """La PQRS con su conversación, como ``to_dict``, pero sin el contenido de los adjuntos.

    En lugar de ``mediaUrl`` la solicitud y cada mensaje traen ``hasMedia``; el archivo se pide
    aparte con ``attachment``.
    """
    data = pqrs.to_dict()
    data["hasMedia"] = bool(data.pop("mediaUrl"))
    for message in data["messages"]:
        message["hasMedia"] = bool(message.pop("mediaUrl"))
    return data


def attachment(pqrs_id, message_id=None):
    """El adjunto de la solicitud (sin ``message_id``) o de uno de sus mensajes, como ``(bytes, tipo)``.

    Devuelve None si no existe o no se puede mostrar.
    """
    if message_id is None:
        row = db.session.query(Pqrs.media_url).filter(Pqrs.id == pqrs_id).first()
    else:
        row = (
            db.session.query(PqrsMessage.media_url)
            .filter(PqrsMessage.pqrs_id == pqrs_id, PqrsMessage.id == message_id)
            .first()
        )
    return decode_media(row.media_url) if row is not None else None
