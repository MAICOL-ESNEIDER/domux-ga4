"""Zonas comunes: crear, cambiar, cerrar con motivo, abrir y retirar (DEC-032).

La administración maneja las zonas de su unidad sin tocar el código: agrega las que tiene el conjunto,
cambia su nombre y sus reglas (zone_rules.py), las cierra cuando fallan (con el motivo que lo explica) y
retira las que ya no existen. Nada se borra: una zona retirada deja de ofrecerse, pero sus reservas viejas
siguen apuntando a ella (ADR-013).

Cuando una zona se cierra, las reservas que ya tenía se mantienen: solo se bloquean las nuevas y se avisa a
la administración cuántas quedaron, para que decida si cancela alguna desde Reservas.

Ninguna función guarda en la base (commit): lo hace la ruta, para que el cambio, su anotación en la
auditoría y los avisos se guarden juntos.
"""

from types import SimpleNamespace

from errors import ApiError
from extensions import db
from models import CommonArea, Reservation, User
from services.audit_service import add_audit_log
from services.notification_service import notify_user
from services.reservation_service import LIMIT_RESERVATION_STATUSES
from services.zone_rules import (
    as_sentence,
    default_zone_values,
    parse_closed_reason,
    parse_zone_rules,
)
from time_utils import colombia_today, utc_now


def _reservations_text(count):
    """«1 reserva próxima» o «3 reservas próximas», para los mensajes."""
    return f"{count} reserva próxima" if count == 1 else f"{count} reservas próximas"


def active_zones(include_retired=False):
    """Las zonas por nombre; las retiradas solo si se piden, y al final."""
    query = CommonArea.query
    if not include_retired:
        query = query.filter(CommonArea.retired_at.is_(None))
    return query.order_by(CommonArea.retired_at.isnot(None), CommonArea.name).all()


def upcoming_counts():
    """Cuántas reservas próximas tiene cada zona: ``{id de la zona: cantidad}``.

    Cuentan las pendientes, activas y aprobadas de hoy en adelante que no están archivadas. Son las
    que se ven afectadas si la zona se cierra o se retira.
    """
    today = colombia_today().isoformat()
    rows = (
        db.session.query(Reservation.common_area_id, db.func.count(Reservation.id))
        .filter(
            Reservation.date >= today,
            Reservation.status.in_(LIMIT_RESERVATION_STATUSES),
            Reservation.is_archived.is_(False),
        )
        .group_by(Reservation.common_area_id)
        .all()
    )
    return {area_id: count for area_id, count in rows}


def _require_active(area):
    """Una zona retirada ya no se cambia, ni se cierra ni se abre."""
    if area.is_retired:
        raise ApiError("Esa zona común fue retirada y ya no se puede cambiar.", 409)


def _ensure_name_free(name, exclude_id=None):
    """Dos zonas vigentes no pueden llamarse igual (sin importar mayúsculas); una retirada libera su nombre."""
    taken = {
        area.name.casefold()
        for area in active_zones()
        if area.id != exclude_id
    }
    if name.casefold() in taken:
        raise ApiError(f"Ya existe una zona común llamada «{name}».", 409)


def create_zone(data, actor):
    """Crea una zona nueva con el nombre y las reglas que lleguen; las demás quedan por defecto."""
    if "name" not in data:
        raise ApiError("El nombre de la zona es obligatorio.")
    values = default_zone_values()
    changes = parse_zone_rules(data, SimpleNamespace(**values), require_changes=False)
    _ensure_name_free(changes["name"])
    area = CommonArea(**{**values, **changes})
    db.session.add(area)
    db.session.flush()
    add_audit_log("common_area", area.id, "created", {"name": area.name, "rules": {
        column: value for column, value in changes.items() if column != "name"
    }}, actor=actor)
    return area


def update_zone(area, data, actor):
    """Cambia el nombre y las reglas de una zona; solo lo que llega. Las reservas que ya existen no se tocan."""
    _require_active(area)
    changes = parse_zone_rules(data, area)
    if "name" in changes:
        _ensure_name_free(changes["name"], exclude_id=area.id)
    before = {column: getattr(area, column) for column in changes}
    for column, value in changes.items():
        setattr(area, column, value)
    add_audit_log("common_area", area.id, "rules_changed", {"before": before, "after": changes}, actor=actor)
    return area


def close_zone(area, data, actor):
    """Cierra la zona con el motivo que verán quienes la consulten; devuelve ``(zona, reservas próximas)``.

    Cerrar una zona que ya está cerrada solo cambia el motivo. Las reservas que la zona ya tenía se
    mantienen: la administración recibe un aviso con cuántas son para que decida cuáles cancelar.
    """
    _require_active(area)
    reason = parse_closed_reason(data.get("reason"))
    pending = upcoming_counts().get(area.id, 0)
    if area.is_closed:
        before = area.closed_reason
        area.closed_reason = reason
        add_audit_log("common_area", area.id, "closure_reason_changed", {
            "before": before, "after": reason,
        }, actor=actor)
        return area, pending

    area.closed_at = utc_now()
    area.closed_reason = reason
    area.closed_by_id = actor.id
    add_audit_log("common_area", area.id, "closed", {"reason": reason, "upcomingReservations": pending}, actor=actor)
    if pending:
        if pending == 1:
            left = "Queda 1 reserva próxima y se mantiene; revísala en Reservas y cancélala si hace falta."
        else:
            left = (
                f"Quedan {_reservations_text(pending)} y se mantienen; "
                "revísalas en Reservas y cancela las que haga falta."
            )
        for admin in User.query.filter_by(role="ADMIN", is_active=True).all():
            notify_user(
                admin.id, "Zona común cerrada", f"Se cerró {area.name}: {as_sentence(reason)} {left}", "reservation",
            )
    return area, pending


def open_zone(area, actor):
    """Vuelve a abrir una zona cerrada: otra vez recibe reservas nuevas."""
    _require_active(area)
    if not area.is_closed:
        raise ApiError("Esa zona común ya está abierta.", 409)
    previous = area.closed_reason
    area.closed_at = None
    area.closed_reason = None
    area.closed_by_id = None
    add_audit_log("common_area", area.id, "opened", {"previousReason": previous}, actor=actor)
    return area


def retire_zone(area, actor):
    """Retira una zona que ya no existe en la unidad; con reservas próximas no se puede (409).

    Con reservas pendientes o aprobadas la administración primero las cancela (o cierra la zona mientras
    tanto): así nadie pierde una reserva sin que se le avise.
    """
    _require_active(area)
    pending = upcoming_counts().get(area.id, 0)
    if pending:
        raise ApiError(
            f"{area.name} tiene {_reservations_text(pending)}: cancélalas primero en Reservas "
            "o cierra la zona mientras tanto.",
            409,
        )
    area.retire(actor)
    add_audit_log("common_area", area.id, "retired", {"name": area.name}, actor=actor)
    return area
