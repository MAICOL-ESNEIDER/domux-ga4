"""Vista liviana de los paquetes para la consulta de la web (HU-088) y lectura de su foto.

La lista de siempre (GET /api/packages) entrega todos los paquetes de una vez, cada uno con su foto en
base64: sirve para la portería y para un residente, pero no para consultar el historial completo. Aquí
está la otra vista que pide ``?view=summary``: filas sin la foto, paginadas, con lo que más urge primero
y con el número de paquetes de cada estado para el filtro. La foto se pide aparte cuando la página la
muestra.

Ninguna función de este archivo guarda en la base.
"""

from sqlalchemy import func, or_
from sqlalchemy.orm import aliased

from errors import ApiError
from extensions import db
from models import PackageItem, User, package_wait
from services.list_view import full_name
from services.media import decode_media
from time_utils import format_colombia, utc_now
from validators import VALID_PACKAGE_STATUSES

#: Los valores de ``status`` que no son un estado del paquete: los archivados y todos (también los
#: archivados). «papelera» es el nombre de antes de «Archivados»: se sigue aceptando para las
#: versiones de la app que todavía lo mandan.
TRASH_FILTER = "archivados"
LEGACY_TRASH_FILTER = "papelera"
ALL_FILTER = "todos"

_INVALID_STATUS = "Estado de paquete inválido"


# ---------------------------------------------------------------------------
# Lo que se pide en la URL
# ---------------------------------------------------------------------------

def parse_status(value, allow_all=False):
    """El estado pedido con ``?status=``: None (los no archivados), un estado, «archivados» o «todos».

    «todos» solo existe en la vista liviana (``allow_all``): reúne los de cualquier estado, también los
    archivados, para buscar un paquete sin saber dónde quedó. «papelera» vale lo mismo que
    «archivados». Un valor desconocido da un error 400.
    """
    if value in (None, ""):
        return None
    if value == LEGACY_TRASH_FILTER:
        return TRASH_FILTER
    if value in VALID_PACKAGE_STATUSES or value == TRASH_FILTER or (allow_all and value == ALL_FILTER):
        return value
    raise ApiError(_INVALID_STATUS)


def filter_status(query, status):
    """Aplica el estado a una consulta de paquetes: sin él salen los que no están archivados."""
    if status == ALL_FILTER:
        return query
    if status == TRASH_FILTER:
        return query.filter(PackageItem.is_deleted.is_(True))
    query = query.filter(PackageItem.is_deleted.is_(False))
    return query.filter(PackageItem.status == status) if status else query


def filter_search(query, search):
    """Aplica la búsqueda a una consulta de paquetes unida con su residente.

    Encuentra por el nombre del residente, su apartamento, la descripción, la transportadora, la guía o
    quien recibió el paquete.
    """
    if not search:
        return query
    pattern = f"%{search}%"
    return query.filter(or_(
        (User.name + " " + User.last_name).ilike(pattern),
        PackageItem.description.ilike(pattern),
        PackageItem.delivered_to.ilike(pattern),
        PackageItem.carrier.ilike(pattern),
        PackageItem.tracking_number.ilike(pattern),
        User.name.ilike(pattern),
        User.last_name.ilike(pattern),
        User.apartment.ilike(pattern),
    ))


# ---------------------------------------------------------------------------
# La lista liviana
# ---------------------------------------------------------------------------

def status_counts(query):
    """Cuántos paquetes hay de cada estado entre los que dejó la consulta (sin el filtro de estado).

    Son los números del filtro: los que esperan en portería, los que están por llegar, los entregados
    (los tres sin contar los archivados), los archivados y el total.
    """
    rows = (
        query.order_by(None)
        .with_entities(PackageItem.status, PackageItem.is_deleted, func.count(PackageItem.id))
        .group_by(PackageItem.status, PackageItem.is_deleted)
        .all()
    )
    live = {status: count for status, deleted, count in rows if not deleted}
    return {
        "waiting": live.get("pendiente", 0),
        "incoming": live.get("por_llegar", 0),
        "delivered": live.get("entregado", 0),
        "trash": sum(count for _status, deleted, count in rows if deleted),
        "all": sum(count for _status, _deleted, count in rows),
    }


def _order(status):
    """Los que esperan en portería, el que lleva más tiempo primero; lo demás, lo más reciente primero."""
    if status == "pendiente":
        return (func.coalesce(PackageItem.arrived_at, PackageItem.created_at).asc(), PackageItem.id.asc())
    if status == "entregado":
        return (func.coalesce(PackageItem.delivered_at, PackageItem.created_at).desc(), PackageItem.id.desc())
    if status == TRASH_FILTER:
        return (func.coalesce(PackageItem.deleted_at, PackageItem.created_at).desc(), PackageItem.id.desc())
    return (PackageItem.created_at.desc(), PackageItem.id.desc())


def _summary_row(row, now):
    minutes, alert = package_wait(row.status, row.is_deleted, row.arrived_at, now)
    return {
        "id": row.id,
        "residentId": row.resident_id,
        "residentName": full_name(row.resident_first_name, row.resident_last_name),
        "apartment": row.apartment,
        "description": row.description or "",
        "carrier": row.carrier,
        "trackingNumber": row.tracking_number,
        "status": row.status or "pendiente",
        "isDeleted": bool(row.is_deleted),
        "arrivedAt": format_colombia(row.arrived_at),
        "hoursWaiting": None if minutes is None else minutes // 60,
        "claimAlert": alert,
        "mediaType": row.media_type,
        "hasMedia": bool(row.has_media),
        "createdAt": format_colombia(row.created_at),
        "deliveredAt": format_colombia(row.delivered_at),
        "deliveredTo": row.delivered_to,
        "deliveredByName": full_name(row.deliverer_first_name, row.deliverer_last_name) or None,
        "registeredByName": full_name(row.guard_first_name, row.guard_last_name) or None,
    }


def summary_page(query, status, page, size):
    """Una página de la lista liviana: ``{packages, page, pageSize, total, totalPages}``.

    ``query`` es la consulta de paquetes unida con su residente, con la búsqueda y el estado ya puestos.
    Las filas se arman con solo las columnas que la lista muestra, así nunca se carga la foto.
    """
    guard, deliverer = aliased(User), aliased(User)
    total = query.count()
    rows = (
        query.outerjoin(guard, PackageItem.registered_by == guard.id)
        .outerjoin(deliverer, PackageItem.delivered_by_id == deliverer.id)
        .with_entities(
            PackageItem.id, PackageItem.resident_id, PackageItem.description, PackageItem.carrier,
            PackageItem.tracking_number, PackageItem.status, PackageItem.is_deleted, PackageItem.arrived_at,
            PackageItem.created_at, PackageItem.delivered_at, PackageItem.delivered_to, PackageItem.media_type,
            PackageItem.media_url.is_not(None).label("has_media"),
            User.name.label("resident_first_name"),
            User.last_name.label("resident_last_name"),
            User.apartment.label("apartment"),
            guard.name.label("guard_first_name"), guard.last_name.label("guard_last_name"),
            deliverer.name.label("deliverer_first_name"), deliverer.last_name.label("deliverer_last_name"),
        )
        .order_by(*_order(status))
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    now = utc_now()
    return {
        "packages": [_summary_row(row, now) for row in rows],
        "page": page,
        "pageSize": size,
        "total": total,
        "totalPages": (total + size - 1) // size,
    }


# ---------------------------------------------------------------------------
# Un paquete y su foto
# ---------------------------------------------------------------------------

def detail_dict(package):
    """El paquete como lo entrega la API, pero sin la foto: en lugar de ``mediaUrl`` lleva ``hasMedia``.

    Si está archivado dice quién lo archivó (``deletedByName``). La foto se pide aparte con
    ``attachment``.
    """
    data = package.to_dict()
    data["hasMedia"] = bool(data.pop("mediaUrl", None))
    deleter = db.session.get(User, package.deleted_by_id) if package.deleted_by_id else None
    data["deletedByName"] = deleter.full_name if deleter else None
    return data


def attachment(package_id):
    """La foto de un paquete, como ``(bytes, tipo)``, o None si no existe o no se puede mostrar."""
    row = db.session.query(PackageItem.media_url).filter(PackageItem.id == package_id).first()
    return decode_media(row.media_url) if row is not None else None
