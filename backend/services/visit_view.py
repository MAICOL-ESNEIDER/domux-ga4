"""Vista liviana de las visitas para la consulta de la web (HU-088) y lectura de la foto del visitante.

La lista de siempre (GET /api/visits) entrega cada visita con la foto del visitante en base64 y con
todos sus eventos: sirve para la portería, pero no para consultar el historial completo. Aquí está la
otra vista que pide ``?view=summary``: filas sin la foto ni los eventos, paginadas y con el número de
visitas de cada estado para las pestañas. La foto se pide aparte cuando la página la muestra.

Ninguna función de este archivo guarda en la base.
"""

from sqlalchemy import func
from sqlalchemy.orm import aliased

from extensions import db
from models import User, Visit, visit_stay
from services.list_view import full_name
from services.media import decode_media
from time_utils import format_colombia, utc_now


# ---------------------------------------------------------------------------
# La lista liviana
# ---------------------------------------------------------------------------

def counts(query):
    """Cuántas visitas hay de cada estado entre las que dejó la consulta (sin el filtro de estado ni de «dentro»).

    Son los números de las pestañas: las que están dentro ahora (entraron y no han salido), las que
    esperan autorización, las aprobadas, las rechazadas y el total. Las que están dentro también cuentan
    entre las aprobadas.
    """
    base = query.order_by(None)
    by_status = dict(
        base.with_entities(Visit.approval_status, func.count(Visit.id)).group_by(Visit.approval_status).all()
    )
    inside = base.filter(Visit.entered_at.isnot(None), Visit.exited_at.is_(None)).count()
    return {
        "inside": inside,
        "pending": by_status.get("pendiente", 0),
        "approved": by_status.get("aprobada", 0),
        "rejected": by_status.get("rechazada", 0),
        "all": sum(by_status.values()),
    }


def _summary_row(row, now):
    is_inside, inside_minutes, is_overstay = visit_stay(
        row.entered_at, row.exited_at, row.expected_stay_minutes, now
    )
    return {
        "id": row.id,
        "residentId": row.resident_id,
        "residentName": full_name(row.resident_first_name, row.resident_last_name),
        "apartment": row.apartment,
        "visitorName": row.visitor_name or "",
        "type": row.type or "",
        "description": row.description,
        "approvalStatus": row.approval_status,
        "authorizationMethod": row.authorization_method,
        "enteredAt": format_colombia(row.entered_at),
        "exitedAt": format_colombia(row.exited_at),
        "isInside": is_inside,
        "insideMinutes": inside_minutes,
        "expectedStayMinutes": row.expected_stay_minutes,
        "isOverstay": is_overstay,
        "qrPassId": row.qr_pass_id,
        "hasPhoto": bool(row.has_photo),
        "createdAt": format_colombia(row.created_at),
        "registeredByName": full_name(row.guard_first_name, row.guard_last_name) or None,
    }


def summary_page(query, inside, page, size):
    """Una página de la lista liviana: ``{visits, page, pageSize, total, totalPages}``.

    ``query`` es la consulta de visitas con los filtros ya puestos (``visit_service.filtered_visits``).
    Salen de la más reciente a la más antigua; con ``inside`` verdadero, de la que lleva más tiempo dentro
    a la más reciente. Las filas se arman con solo las columnas que la lista muestra, así nunca se carga
    la foto ni los eventos.
    """
    resident, guard = aliased(User), aliased(User)
    total = query.count()
    order = (Visit.entered_at, Visit.id) if inside is True else (Visit.created_at.desc(), Visit.id.desc())
    rows = (
        query.join(resident, Visit.resident_id == resident.id)
        .outerjoin(guard, Visit.registered_by == guard.id)
        .with_entities(
            Visit.id, Visit.resident_id, Visit.visitor_name, Visit.type, Visit.description,
            Visit.approval_status, Visit.authorization_method, Visit.entered_at, Visit.exited_at,
            Visit.expected_stay_minutes, Visit.qr_pass_id, Visit.created_at,
            db.and_(Visit.visitor_photo_url.is_not(None), Visit.media_consent.is_(True)).label("has_photo"),
            resident.name.label("resident_first_name"),
            resident.last_name.label("resident_last_name"),
            resident.apartment.label("apartment"),
            guard.name.label("guard_first_name"),
            guard.last_name.label("guard_last_name"),
        )
        .order_by(*order)
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    now = utc_now()
    return {
        "visits": [_summary_row(row, now) for row in rows],
        "page": page,
        "pageSize": size,
        "total": total,
        "totalPages": (total + size - 1) // size,
    }


# ---------------------------------------------------------------------------
# Una visita y la foto del visitante
# ---------------------------------------------------------------------------

def detail_dict(visit):
    """La visita como la entrega la API, pero sin la foto: en lugar de ``visitorPhotoUrl`` lleva ``hasPhoto``.

    Trae sus eventos (solicitud, autorización, entrada y salida) y ``isInside`` (entró y no ha salido),
    igual que las filas de la lista. La foto se pide aparte con ``photo``; ``hasPhoto`` solo es verdadero
    si hay foto y el visitante dio su consentimiento para guardarla.
    """
    data = visit.to_dict()
    data["hasPhoto"] = bool(data.pop("visitorPhotoUrl", None)) and bool(visit.media_consent)
    data["isInside"] = visit.is_inside
    return data


def photo(visit_id):
    """La foto del visitante, como ``(bytes, tipo)``, o None si no hay, no tiene consentimiento o no se puede mostrar.

    La foto solo se guarda con el consentimiento del visitante; aquí se vuelve a revisar antes de entregarla.
    """
    row = (
        db.session.query(Visit.visitor_photo_url, Visit.media_consent)
        .filter(Visit.id == visit_id)
        .first()
    )
    if row is None or not row.media_consent:
        return None
    return decode_media(row.visitor_photo_url)
