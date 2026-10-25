from datetime import datetime

from flask import Blueprint, g, jsonify, request

from auth import role_required, token_required
from errors import error_response
from extensions import db
from models import Notification, PackageItem, User, Visit
from services.notification_service import notify_user
from validators import (
    VALID_PACKAGE_STATUSES,
    require_non_empty_fields,
    validate_iso_date,
    validate_media_fields,
    validate_no_empty_strings,
    validate_time,
)

bp = Blueprint("security", __name__, url_prefix="/api")
VISIT_TYPES = ("visitante", "domiciliario", "contratista")


def _json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, error_response(400, "El cuerpo de la solicitud debe ser un objeto JSON válido.")
    message = validate_no_empty_strings(data)
    if message:
        return None, error_response(400, message)
    return data, None


def _package_metadata_error(data):
    if error := validate_media_fields(data):
        return error
    event_date = data.get("eventDate")
    if event_date is not None and (error := validate_iso_date(event_date)):
        return error
    event_time = data.get("eventTime")
    if event_time is not None and (error := validate_time(event_time)):
        return error
    return None


@bp.get("/packages")
@token_required
def get_packages():
    user = g.current_user
    query = PackageItem.query.join(User, PackageItem.resident_id == User.id)
    if user.role == "RESIDENT":
        query = query.filter(PackageItem.resident_id == user.id)
        requested_resident_id = request.args.get("residentId", type=int)
        if requested_resident_id is not None and requested_resident_id != user.id:
            return error_response(403, "No puedes consultar paquetes de otro residente")
    elif user.role not in ("ADMIN", "GUARD"):
        return error_response(403, "No tienes permiso para ver los paquetes")

    status = request.args.get("status")
    if status:
        if status not in VALID_PACKAGE_STATUSES:
            return error_response(400, "Estado de paquete inválido")
        query = query.filter(PackageItem.status == status)
    resident_id = request.args.get("residentId", type=int)
    if resident_id is not None and user.role != "RESIDENT":
        query = query.filter(PackageItem.resident_id == resident_id)
    search = (request.args.get("search") or request.args.get("q") or "").strip()
    if search:
        pattern = f"%{search}%"
        query = query.filter(db.or_(
            PackageItem.description.ilike(pattern),
            User.name.ilike(pattern),
            User.last_name.ilike(pattern),
            User.apartment.ilike(pattern),
        ))
    items = query.order_by(PackageItem.created_at.desc()).all()
    return jsonify({"packages": [item.to_dict() for item in items]})


@bp.post("/packages")
@token_required
@role_required("GUARD")
def register_package():
    data, failure = _json_body()
    if failure:
        return failure
    validation_error = require_non_empty_fields(
        data,
        (("description", "descripción"),),
    )
    if validation_error:
        return error_response(400, validation_error)
    if error := _package_metadata_error(data):
        return error_response(400, error)
    resident_id = data.get("residentId")
    if not isinstance(resident_id, int) or isinstance(resident_id, bool):
        return error_response(400, "Selecciona un residente válido")
    resident = User.query.filter_by(id=resident_id, role="RESIDENT").first()
    if resident is None:
        return error_response(400, "Selecciona un residente válido")

    package = PackageItem(
        resident_id=resident.id,
        registered_by=g.current_user.id,
        description=data["description"].strip(),
        media_url=data.get("mediaUrl"),
        media_type=data.get("mediaType"),
        event_date=data.get("eventDate"),
        event_time=data.get("eventTime"),
    )
    db.session.add(package)
    notify_user(
        resident.id,
        "Paquete registrado",
        f"Se registró un paquete para {resident.apartment or 'tu cuenta'}.",
        "package",
    )
    db.session.commit()
    return jsonify({"message": "Paquete registrado", "packageItem": package.to_dict()}), 201


@bp.put("/packages/<int:pkg_id>/deliver")
@token_required
@role_required("GUARD")
def deliver_package(pkg_id):
    package = db.session.get(PackageItem, pkg_id)
    if package is None:
        return error_response(404, "Paquete no encontrado")
    if package.status != "entregado":
        package.status = "entregado"
        package.delivered_at = datetime.utcnow()
        notify_user(
            package.resident_id,
            "Paquete entregado",
            f"Tu paquete ({package.description or 'sin descripción'}) fue entregado.",
            "package",
        )
        db.session.commit()
    return jsonify({"message": "Paquete marcado como entregado", "packageItem": package.to_dict()})


@bp.get("/visits")
@token_required
def get_visits():
    user = g.current_user
    if user.role == "RESIDENT":
        items = Visit.query.filter_by(
            resident_id=user.id
        ).order_by(Visit.created_at.desc()).all()
    elif user.role in ("ADMIN", "GUARD"):
        items = Visit.query.order_by(Visit.created_at.desc()).all()
    else:
        return error_response(403, "No tienes permiso para ver los ingresos")
    return jsonify({"visits": [item.to_dict() for item in items]})


@bp.post("/visits")
@token_required
@role_required("GUARD")
def register_visit():
    data, failure = _json_body()
    if failure:
        return failure
    validation_error = require_non_empty_fields(
        data,
        (("visitorName", "nombre del visitante"),),
    )
    if validation_error:
        return error_response(400, validation_error)
    resident_id = data.get("residentId")
    if not isinstance(resident_id, int) or isinstance(resident_id, bool):
        return error_response(400, "Selecciona un residente válido")
    resident = User.query.filter_by(id=resident_id, role="RESIDENT").first()
    visit_type = data.get("type")
    if resident is None or visit_type not in VISIT_TYPES:
        return error_response(400, "Datos incompletos para registrar el ingreso")

    document = data.get("visitorDocument")
    if document is not None and not isinstance(document, str):
        return error_response(400, "El documento del visitante debe ser texto")
    visit = Visit(
        resident_id=resident.id,
        registered_by=g.current_user.id,
        visitor_name=data["visitorName"].strip(),
        visitor_document=document.strip() if document else None,
        type=visit_type,
    )
    db.session.add(visit)
    db.session.commit()
    return jsonify({"message": "Ingreso registrado", "visit": visit.to_dict()}), 201


@bp.get("/notifications")
@token_required
def get_notifications():
    notifications = Notification.query.filter_by(
        user_id=g.current_user.id
    ).order_by(Notification.created_at.desc()).all()
    return jsonify({"notifications": [item.to_dict() for item in notifications]})


@bp.put("/notifications/<int:notification_id>/read")
@token_required
def mark_notification_read(notification_id):
    notification = db.session.get(Notification, notification_id)
    if notification is None:
        return error_response(404, "Notificación no encontrada")
    if notification.user_id != g.current_user.id:
        return error_response(403, "No puedes modificar una notificación ajena")
    notification.is_read = True
    db.session.commit()
    return jsonify({"message": "Notificación marcada como leída", "notification": notification.to_dict()})
