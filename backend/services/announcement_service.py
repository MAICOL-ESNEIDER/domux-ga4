"""Comunicados: quién los ve, cuáles faltan por leer y cuántos apartamentos los leyeron.

Cubre las historias HU-058 (categorías), HU-059 (no leídos), HU-060 (vencimiento y
archivados), HU-061 (comunicados por torre) y HU-062 (conteo de lectura).
"""

from datetime import date

from sqlalchemy import select

from errors import ApiError
from extensions import db
from models import (
    ANNOUNCEMENT_CATEGORIES,
    Announcement,
    AnnouncementRead,
    Apartment,
    Tower,
    User,
)
from time_utils import colombia_today
from validators import validate_iso_date


def parse_category(value):
    """La categoría del comunicado (RN-026); sin una de las cinco, el comunicado no se publica."""
    if isinstance(value, str):
        key = value.strip().lower().replace(" ", "_")
        if key in ANNOUNCEMENT_CATEGORIES:
            return key
    names = ", ".join(label.lower() for label in ANNOUNCEMENT_CATEGORIES.values())
    raise ApiError(f"El comunicado necesita una categoría: {names}.")


def parse_tower_id(value):
    """La torre a la que va el comunicado; sin torre es para toda la unidad (HU-061)."""
    if value is None:
        return None
    tower = None if isinstance(value, bool) or not isinstance(value, int) else db.session.get(Tower, value)
    if tower is None or tower.is_retired:
        raise ApiError("Selecciona una torre válida para el comunicado.")
    return tower.id


def parse_expiry(value):
    """La fecha de vencimiento del comunicado (HU-060); sin fecha, nunca vence."""
    if value is None:
        return None
    error = validate_iso_date(value)
    if error:
        raise ApiError(error)
    expires_at = date.fromisoformat(value)
    if expires_at < colombia_today():
        raise ApiError("La fecha de vencimiento no puede ser anterior a hoy.")
    return expires_at


def visible_announcements(user):
    """Los comunicados que ese usuario puede ver, sin los retirados.

    La administración y la portería ven todos. Un residente ve los de toda la
    unidad y los de su torre (HU-061), nunca los de otra.
    """
    query = Announcement.query.filter(Announcement.retired_at.is_(None))
    if user.role != "RESIDENT":
        return query
    tower_id = user.apartment_ref.tower_id if user.apartment_ref else None
    if tower_id is None:
        return query.filter(Announcement.tower_id.is_(None))
    return query.filter(db.or_(Announcement.tower_id.is_(None), Announcement.tower_id == tower_id))


def current_only(query):
    """Deja los comunicados vigentes: sin vencimiento o con vencimiento de hoy en adelante."""
    return query.filter(db.or_(
        Announcement.expires_at.is_(None), Announcement.expires_at >= colombia_today()
    ))


def archived_only(query):
    """Deja los archivados: los que ya pasaron su fecha de vencimiento (HU-060)."""
    return query.filter(Announcement.expires_at < colombia_today())


def unread_only(query, user):
    """Deja los que el residente todavía no ha abierto (HU-059)."""
    read = select(AnnouncementRead.announcement_id).where(AnnouncementRead.user_id == user.id)
    return query.filter(Announcement.id.not_in(read))


def unread_count(user):
    """Cuántos comunicados vigentes tiene el residente sin leer; la portería y la administración no tienen."""
    if user.role != "RESIDENT":
        return 0
    return unread_only(current_only(visible_announcements(user)), user).count()


def _read_ids(user, announcement_ids):
    rows = db.session.query(AnnouncementRead.announcement_id).filter(
        AnnouncementRead.user_id == user.id,
        AnnouncementRead.announcement_id.in_(announcement_ids),
    ).all()
    return {announcement_id for (announcement_id,) in rows}


def _apartments_that_read(announcement_ids):
    rows = db.session.query(
        AnnouncementRead.announcement_id,
        db.func.count(db.func.distinct(AnnouncementRead.apartment_id)),
    ).filter(
        AnnouncementRead.announcement_id.in_(announcement_ids)
    ).group_by(AnnouncementRead.announcement_id).all()
    return dict(rows)


def reachable_apartments(tower_id):
    """Apartamentos a los que llega un comunicado: los que tienen residentes activos.

    Con torre, solo los de esa torre; sin torre, los de toda la unidad.
    """
    query = db.session.query(db.func.count(db.func.distinct(User.apartment_id))).join(
        Apartment, User.apartment_id == Apartment.id
    ).filter(
        User.role == "RESIDENT",
        User.is_active.is_(True),
        Apartment.retired_at.is_(None),
    )
    if tower_id is not None:
        query = query.filter(Apartment.tower_id == tower_id)
    return query.scalar() or 0


def announcement_payloads(items, user):
    """Los comunicados listos para responder, con lo que depende de quién los pide.

    Todos llevan ``isRead`` (los que no son residentes no tienen nada sin leer).
    La administración recibe además cuántos apartamentos lo leyeron y de cuántos
    (HU-062); los residentes nunca ven esos números.
    """
    ids = [item.id for item in items]
    read_ids = _read_ids(user, ids) if ids and user.role == "RESIDENT" else set()
    readers = _apartments_that_read(ids) if ids and user.role == "ADMIN" else {}
    reachable = {}
    payloads = []
    for item in items:
        data = item.to_dict()
        data["isRead"] = user.role != "RESIDENT" or item.id in read_ids
        if user.role == "ADMIN":
            if item.tower_id not in reachable:
                reachable[item.tower_id] = reachable_apartments(item.tower_id)
            data["readApartments"] = readers.get(item.id, 0)
            data["totalApartments"] = reachable[item.tower_id]
        payloads.append(data)
    return payloads


def mark_as_read(user, announcement):
    """Anota que el residente abrió el comunicado; si ya lo había leído, no hace nada."""
    already = AnnouncementRead.query.filter_by(
        announcement_id=announcement.id, user_id=user.id
    ).first()
    if already is None:
        db.session.add(AnnouncementRead(
            announcement_id=announcement.id,
            user_id=user.id,
            apartment_id=user.apartment_id,
        ))
