"""Vista liviana de los comunicados para la lista de la web (HU-080) y lectura de su adjunto.

La lista de siempre (GET /api/announcements) entrega en cada comunicado su foto, video o audio completo
en base64: sirve para el celular de un residente, pero no para una lista de administración. Aquí está
la otra vista que pide ``?view=summary``: filas sin el adjunto, paginadas y con el número de comunicados
vigentes y archivados para las pestañas. El adjunto se pide aparte cuando la página lo muestra.

Ninguna función de este archivo guarda en la base.
"""

from sqlalchemy import or_

from errors import ApiError
from extensions import db
from models import ANNOUNCEMENT_CATEGORIES, Announcement, Tower, User
from services.announcement_service import add_reader_data, archived_only, current_only
from services.list_view import full_name
from services.media import decode_media
from time_utils import colombia_today, format_colombia

#: Valor de ``towerId`` para pedir los comunicados de toda la unidad (los que no tienen torre).
WHOLE_UNIT = "unit"


# ---------------------------------------------------------------------------
# Lo que se pide en la URL
# ---------------------------------------------------------------------------

def parse_tower_filter(value):
    """La torre pedida con ``?towerId=``: None (cualquiera), «unit» (toda la unidad) o el número de una torre."""
    if value in (None, ""):
        return None
    if value == WHOLE_UNIT:
        return WHOLE_UNIT
    if value.isascii() and value.isdigit() and int(value) > 0:
        return int(value)
    raise ApiError(f"El filtro 'towerId' debe ser el número de una torre o la palabra {WHOLE_UNIT}.")


def filter_announcements(query, tower=None, search=""):
    """Aplica la torre y la búsqueda (en el título y en el mensaje) a una consulta de comunicados."""
    if tower == WHOLE_UNIT:
        query = query.filter(Announcement.tower_id.is_(None))
    elif tower is not None:
        query = query.filter(Announcement.tower_id == tower)
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(Announcement.title.ilike(pattern), Announcement.message.ilike(pattern)))
    return query


# ---------------------------------------------------------------------------
# La lista liviana
# ---------------------------------------------------------------------------

def tab_counts(query):
    """Cuántos comunicados vigentes y cuántos archivados hay entre los que dejó la consulta (sin la pestaña).

    Son los números de las dos pestañas: los vigentes (sin vencimiento o que vencen de hoy en adelante)
    y los archivados (los que ya pasaron su fecha de vencimiento).
    """
    return {
        "current": current_only(query).order_by(None).count(),
        "archived": archived_only(query).order_by(None).count(),
    }


def _summary_row(row, today):
    return {
        "id": row.id,
        "title": row.title or "",
        "message": row.message or "",
        "category": row.category,
        "categoryLabel": ANNOUNCEMENT_CATEGORIES.get(row.category),
        "towerId": row.tower_id,
        "towerName": row.tower_name,
        "expiresAt": row.expires_at.isoformat() if row.expires_at else None,
        "isExpired": row.expires_at is not None and row.expires_at < today,
        "eventDate": row.event_date,
        "eventTime": row.event_time,
        "mediaType": row.media_type,
        "hasMedia": bool(row.has_media),
        "createdAt": format_colombia(row.created_at),
        "authorName": full_name(row.author_first_name, row.author_last_name) or None,
        "isRetired": False,
    }


def summary_page(query, user, page, size):
    """Una página de la lista liviana: ``{announcements, page, pageSize, total, totalPages}``.

    ``query`` es la consulta de comunicados con los filtros y la pestaña ya puestos. Las filas se arman
    con solo las columnas que la lista muestra, así nunca se carga el adjunto. Llevan lo mismo que en la
    lista completa según quién las pide: ``isRead`` y, solo para la administración, cuántos apartamentos
    las leyeron y a cuántos llegan (HU-062).
    """
    total = query.count()
    rows = (
        query.outerjoin(Tower, Announcement.tower_id == Tower.id)
        .join(User, Announcement.author_id == User.id)
        .with_entities(
            Announcement.id, Announcement.title, Announcement.message, Announcement.category,
            Announcement.tower_id, Announcement.expires_at, Announcement.event_date,
            Announcement.event_time, Announcement.media_type, Announcement.created_at,
            Announcement.media_url.is_not(None).label("has_media"),
            Tower.name.label("tower_name"),
            User.name.label("author_first_name"),
            User.last_name.label("author_last_name"),
        )
        .order_by(Announcement.created_at.desc(), Announcement.id.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    today = colombia_today()
    return {
        "announcements": add_reader_data([_summary_row(row, today) for row in rows], user),
        "page": page,
        "pageSize": size,
        "total": total,
        "totalPages": (total + size - 1) // size,
    }


# ---------------------------------------------------------------------------
# Un comunicado y su adjunto
# ---------------------------------------------------------------------------

def without_media(data):
    """El comunicado como lo entrega la API, pero sin el adjunto: en lugar de ``mediaUrl`` lleva ``hasMedia``.

    El archivo se pide aparte con ``attachment``.
    """
    data = dict(data)
    data["hasMedia"] = bool(data.pop("mediaUrl", None))
    return data


def attachment(announcement_id):
    """El adjunto de un comunicado vigente, como ``(bytes, tipo)``, o None si no existe o no se puede mostrar."""
    row = (
        db.session.query(Announcement.media_url)
        .filter(Announcement.id == announcement_id, Announcement.retired_at.is_(None))
        .first()
    )
    return decode_media(row.media_url) if row is not None else None
