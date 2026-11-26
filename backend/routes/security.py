import json
import secrets
from datetime import date, timedelta

from flask import Blueprint, g, jsonify, request

from auth import role_required, token_required
from errors import error_response
from extensions import db
from models import (
    Notification,
    DevicePushToken,
    PackageItem,
    User,
    Visit,
    VisitEvent,
    VisitQrPass,
)
from services.notification_service import notify_role, notify_user
from services.reservation_service import finalize_expired_reservations
from time_utils import now_colombia
from validators import (
    VALID_PACKAGE_STATUSES,
    parse_bool,
    require_non_empty_fields,
    validate_iso_date,
    validate_media_fields,
    validate_media_url,
    validate_no_empty_strings,
    validate_time,
)

bp = Blueprint("security", __name__, url_prefix="/api")
VISIT_TYPES = ("visitante", "domiciliario", "contratista")


def _json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, error_response(400, "El cuerpo de la solicitud debe ser un objeto JSON válido.")
    document = data.get("visitorDocument")
    if request.path == "/api/visits" and isinstance(document, str) and not document.strip():
        data = dict(data)
        data.pop("visitorDocument")
    message = validate_no_empty_strings(data)
    if message:
        return None, error_response(400, message)
    if "mediaUrl" in data and (
        media_error := validate_media_url(data["mediaUrl"])
    ):
        return None, error_response(400, media_error)
    return data, None


def _package_metadata_error(data):
    if error := validate_media_fields(data):
        return error
    event_date = data.get("eventDate")
    if event_date is not None and (error := validate_iso_date(event_date)):
        return error
    if event_date is not None and event_date < now_colombia().date().isoformat():
        return "La fecha del evento no puede ser anterior a hoy."
    if event_date is not None and event_date > now_colombia().date().isoformat():
        return "La fecha del evento debe ser hoy."
    event_time = data.get("eventTime")
    if event_time is not None and (error := validate_time(event_time)):
        return error
    return None


def _cleanup_expired_packages():
    now = now_colombia()
    expired_packages = PackageItem.query.filter(
        PackageItem.status == "entregado",
        PackageItem.is_deleted.is_(False),
        PackageItem.delivered_at < now - timedelta(days=7),
    ).all()
    for package in expired_packages:
        package.is_deleted = True
        package.deleted_at = now
    if expired_packages:
        db.session.commit()


@bp.post("/notifications/device-token")
@bp.post("/push-tokens")
@token_required
def register_push_token():
    data, failure = _json_body()
    if failure:
        return failure
    token = data.get("token")
    device_id = data.get("deviceId")
    if not isinstance(token, str) or not token.strip() or len(token) > 255:
        return error_response(400, "El token FCM no es válido.")
    if device_id is not None and (
        not isinstance(device_id, str) or not device_id.strip() or len(device_id) > 120
    ):
        return error_response(400, "El identificador del dispositivo no es válido.")
    normalized_token = token.strip()
    normalized_device_id = device_id.strip() if device_id else None
    if normalized_device_id:
        DevicePushToken.query.filter(
            DevicePushToken.user_id == g.current_user.id,
            DevicePushToken.device_id == normalized_device_id,
            DevicePushToken.token != normalized_token,
        ).delete(synchronize_session=False)
    record = DevicePushToken.query.filter_by(token=normalized_token).first()
    if record is None:
        record = DevicePushToken(
            user_id=g.current_user.id,
            token=normalized_token,
            device_id=normalized_device_id,
        )
        db.session.add(record)
    else:
        record.user_id = g.current_user.id
        record.device_id = normalized_device_id or record.device_id
    db.session.commit()
    return jsonify({"message": "Dispositivo registrado para notificaciones push."}), 201


@bp.delete("/push-tokens")
@token_required
def delete_push_token():
    data, failure = _json_body()
    if failure:
        return failure
    token = data.get("token")
    if not isinstance(token, str) or not token.strip():
        return error_response(400, "El token FCM es obligatorio.")
    DevicePushToken.query.filter_by(
        user_id=g.current_user.id,
        token=token.strip(),
    ).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({"message": "Dispositivo eliminado de notificaciones push."})


@bp.get("/packages")
@token_required
def get_packages():
    _cleanup_expired_packages()
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
    if status == "por_llegar":
        status = "pendiente"
    if status == "papelera":
        query = query.filter(PackageItem.is_deleted.is_(True))
    elif status is None or status in VALID_PACKAGE_STATUSES:
        query = query.filter(PackageItem.is_deleted.is_(False))
        if status is not None:
            query = query.filter(PackageItem.status == status)
    else:
        return error_response(400, "Estado de paquete inválido")
    resident_id = request.args.get("residentId", type=int)
    if resident_id is not None and user.role != "RESIDENT":
        query = query.filter(PackageItem.resident_id == resident_id)
    search = (request.args.get("search") or request.args.get("q") or "").strip()
    if search:
        pattern = f"%{search}%"
        query = query.filter(db.or_(
            (User.name + " " + User.last_name).ilike(pattern),
            PackageItem.description.ilike(pattern),
            PackageItem.delivered_to.ilike(pattern),
            User.name.ilike(pattern),
            User.last_name.ilike(pattern),
            User.apartment.ilike(pattern),
        ))
    items = query.order_by(PackageItem.created_at.desc()).all()
    return jsonify({"packages": [item.to_dict() for item in items]})


@bp.post("/packages")
@token_required
@role_required("GUARD", "ADMIN")
def register_package():
    data, failure = _json_body()
    if failure:
        return failure
    status = data.get("status", "pendiente")
    if status == "por_llegar":
        status = "pendiente"
    if status != "pendiente":
        return error_response(400, "Estado de paquete inválido")
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

    now = now_colombia()
    package = PackageItem(
        resident_id=resident.id,
        registered_by=g.current_user.id,
        description=data["description"].strip(),
        status=status,
        media_url=data.get("mediaUrl"),
        media_type=data.get("mediaType"),
        event_date=now.date().isoformat(),
        event_time=now.strftime("%H:%M"),
        created_at=now,
    )
    db.session.add(package)
    notify_user(
        resident.id,
        "Paquete registrado",
        f"Se registró un paquete para {resident.full_name} "
        f"({resident.apartment or 'sin apartamento'}).",
        "package",
    )
    db.session.commit()
    return jsonify({"message": "Paquete registrado", "packageItem": package.to_dict()}), 201


@bp.put("/packages/<int:pkg_id>/status")
@token_required
@role_required("GUARD", "ADMIN")
def update_package_status(pkg_id):
    data, failure = _json_body()
    if failure:
        return failure
    status = data.get("status")
    if status == "por_llegar":
        status = "pendiente"
    if status != "pendiente":
        return error_response(400, "Estado de paquete inválido")
    package = db.session.get(PackageItem, pkg_id)
    if package is None:
        return error_response(404, "Paquete no encontrado")
    if package.status != status:
        package.status = status
        if status == "pendiente":
            notify_user(
                package.resident_id,
                "Paquete disponible",
                "Tu paquete ya se encuentra en portería",
                "package",
            )
        db.session.commit()
    return jsonify({"message": "Estado del paquete actualizado.", "packageItem": package.to_dict()})


@bp.delete("/packages/<int:pkg_id>")
@token_required
@role_required("GUARD", "ADMIN")
def delete_package(pkg_id):
    package = db.session.get(PackageItem, pkg_id)
    if package is None:
        return error_response(404, "Paquete no encontrado")
    force = (request.args.get("force") or "").lower() == "true"
    if package.is_deleted or force:
        return error_response(
            403,
            "Por reglas operativas e integridad de la información, los registros "
            "de paquetería no pueden eliminarse definitivamente; solo pueden archivarse.",
        )
    package.is_deleted = True
    package.deleted_at = now_colombia()
    package.deleted_by_id = g.current_user.id
    db.session.commit()
    return jsonify({
        "message": "Paquete movido a la papelera.",
        "packageItem": package.to_dict(),
    })


@bp.put("/packages/<int:pkg_id>/restore")
@token_required
@role_required("GUARD", "ADMIN")
def restore_package(pkg_id):
    package = db.session.get(PackageItem, pkg_id)
    if package is None:
        return error_response(404, "Paquete no encontrado")
    package.is_deleted = False
    package.deleted_at = None
    package.deleted_by_id = None
    db.session.commit()
    return jsonify({"message": "Paquete restaurado.", "packageItem": package.to_dict()})


@bp.put("/packages/<int:pkg_id>/deliver")
@token_required
@role_required("GUARD")
def deliver_package(pkg_id):
    data, failure = _json_body()
    if failure:
        return failure
    package = db.session.get(PackageItem, pkg_id)
    if package is None:
        return error_response(404, "Paquete no encontrado")
    receiver = data.get("receivedBy")
    if receiver is not None and not isinstance(receiver, str):
        return error_response(400, "El nombre de quien recibe debe ser texto.")
    if not isinstance(receiver, str) or not receiver.strip():
        return error_response(400, "Escribe el nombre de quien recibe el paquete.")
    delivery_media_url = data.get("deliveryMediaUrl")
    if delivery_media_url is not None and not isinstance(delivery_media_url, str):
        return error_response(400, "La foto de entrega no es válida.")
    if package.status != "entregado":
        package.status = "entregado"
        package.delivered_at = now_colombia()
        package.delivered_to = receiver.strip()
        package.delivery_media_url = delivery_media_url
        package.delivered_by_id = g.current_user.id
        notify_user(
            package.resident_id,
            "Paquete entregado",
            f"Tu paquete ({package.description or 'sin descripción'}) fue entregado "
            f"a {package.delivered_to}.",
            "package",
        )
        db.session.commit()
    return jsonify({"message": "Paquete marcado como entregado", "packageItem": package.to_dict()})


@bp.get("/visits")
@token_required
def get_visits():
    user = g.current_user
    query = Visit.query
    if user.role == "RESIDENT":
        query = query.filter_by(resident_id=user.id)
    elif user.role in ("ADMIN", "GUARD"):
        pass
    else:
        return error_response(403, "No tienes permiso para ver los ingresos")
    status = request.args.get("status")
    if status:
        if status not in ("pendiente", "aprobada", "rechazada"):
            return error_response(400, "Estado de visita inválido.")
        query = query.filter(Visit.approval_status == status)
    search = (request.args.get("search") or "").strip()
    if search:
        pattern = f"%{search}%"
        query = query.join(User, Visit.resident_id == User.id).filter(db.or_(
            Visit.visitor_name.ilike(pattern),
            User.name.ilike(pattern),
            User.last_name.ilike(pattern),
            User.apartment.ilike(pattern),
        ))
    items = query.order_by(Visit.created_at.desc()).limit(500).all()
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

    try:
        document_refused = parse_bool(data.get("documentRefused"), default=False)
    except ValueError:
        return error_response(400, "documentRefused debe ser verdadero o falso.")
    document = data.get("visitorDocument")
    if document is not None and not isinstance(document, str):
        return error_response(400, "El documento del visitante debe ser texto")
    if document_refused:
        visitor_document = "NO SUMINISTRADO"
    else:
        visitor_document = document.strip() if document else ""
        if not visitor_document:
            return error_response(
                400,
                "El documento de identidad del visitante es obligatorio, o debes marcar que se negó a suministrarlo.",
            )
    consent = data.get("mediaConsent", False)
    if not isinstance(consent, bool):
        return error_response(400, "El consentimiento debe ser verdadero o falso.")
    if ((visitor_document and not document_refused) or data.get("mediaUrl")) and not consent:
        return error_response(400, "Se necesita consentimiento para guardar documento o foto.")
    if data.get("mediaUrl"):
        if error := validate_media_fields(data):
            return error_response(400, error)
    if data.get("mediaType") and data["mediaType"] != "image":
        return error_response(400, "La foto del visitante debe ser una imagen.")
    description = data.get("description")
    if description is not None and not isinstance(description, str):
        return error_response(400, "Los detalles del pedido deben ser texto.")
    visit = Visit(
        resident_id=resident.id,
        registered_by=g.current_user.id,
        visitor_name=data["visitorName"].strip(),
        visitor_document=visitor_document,
        document_refused=document_refused,
        visitor_photo_url=data.get("mediaUrl"),
        visitor_photo_type=data.get("mediaType"),
        media_consent=consent,
        type=visit_type,
        description=description.strip()[:250] if description else None,
    )
    db.session.add(visit)
    visit.events.append(VisitEvent(
        event_type="solicitud",
        method="app",
        actor_id=g.current_user.id,
    ))
    notify_user(
        resident.id,
        "Visitante esperando autorización",
        f"{visit.visitor_name} está en portería para ingresar. "
        "Si se quedará varios días, puedes crear un QR de acceso.",
        "visit",
    )
    db.session.commit()
    return jsonify({"message": "Ingreso registrado", "visit": visit.to_dict()}), 201


@bp.put("/visits/<int:visit_id>/decision")
@token_required
@role_required("RESIDENT")
def decide_visit(visit_id):
    if g.current_user.role != "RESIDENT":
        return error_response(403, "Solo un residente puede autorizar esta visita.")
    data, failure = _json_body()
    if failure:
        return failure
    decision = data.get("decision")
    if decision not in ("aprobada", "rechazada"):
        return error_response(400, "La decisión debe ser aprobar o rechazar.")
    visit = db.session.get(Visit, visit_id)
    if visit is None:
        return error_response(404, "Visita no encontrada.")
    if visit.resident_id != g.current_user.id:
        return error_response(403, "Solo puedes decidir sobre visitas dirigidas a tu cuenta.")
    if visit.approval_status != "pendiente":
        return error_response(400, "Esta visita ya tiene una decisión.")
    visit.approval_status = decision
    visit.authorization_method = "app"
    visit.events.append(VisitEvent(
        event_type=decision,
        method="app",
        actor_id=g.current_user.id,
    ))
    db.session.commit()
    return jsonify({"message": "Decisión registrada.", "visit": visit.to_dict()})


@bp.put("/visits/<int:visit_id>/authorize-call")
@token_required
@role_required("GUARD")
def authorize_visit_by_call(visit_id):
    visit = db.session.get(Visit, visit_id)
    if visit is None:
        return error_response(404, "Visita no encontrada.")
    if visit.approval_status != "pendiente":
        return error_response(400, "Esta visita ya tiene una decisión.")
    visit.approval_status = "aprobada"
    visit.authorization_method = "llamada"
    visit.events.append(VisitEvent(
        event_type="aprobada",
        method="llamada",
        actor_id=g.current_user.id,
    ))
    db.session.commit()
    return jsonify({"message": "Autorización telefónica registrada.", "visit": visit.to_dict()})


@bp.post("/visits/<int:visit_id>/entry")
@token_required
@role_required("GUARD")
def register_visit_entry(visit_id):
    visit = db.session.get(Visit, visit_id)
    if visit is None:
        return error_response(404, "Visita no encontrada.")
    if visit.approval_status != "aprobada":
        return error_response(400, "El residente debe autorizar el ingreso antes de registrar la entrada.")
    if visit.qr_pass_id is not None:
        return error_response(400, "Este visitante debe ingresar usando el QR asociado.")
    if visit.entered_at and not visit.exited_at:
        return error_response(409, "Este visitante ya aparece dentro de la unidad.")
    if visit.exited_at and (
        not visit.exit_returning or visit.exited_at.date() < now_colombia().date()
    ):
        return error_response(400, "El registro indica salida definitiva; crea una nueva solicitud de ingreso.")
    visit.entered_at = now_colombia()
    visit.exited_at = None
    visit.exit_returning = False
    method = visit.authorization_method or "app"
    visit.events.append(VisitEvent(
        event_type="entrada",
        method=method,
        actor_id=g.current_user.id,
    ))
    if method != "qr":
        notify_user(
            visit.resident_id,
            "Visitante ingresó",
            f"{visit.visitor_name} ingresó a la unidad.",
            "visit",
        )
    db.session.commit()
    return jsonify({"message": "Entrada registrada.", "visit": visit.to_dict()})


@bp.post("/visits/<int:visit_id>/exit")
@token_required
@role_required("GUARD")
def register_visit_exit(visit_id):
    data, failure = _json_body()
    if failure:
        return failure
    returning = data.get("returningToday", False)
    if not isinstance(returning, bool):
        return error_response(400, "returningToday debe ser verdadero o falso.")
    visit = db.session.get(Visit, visit_id)
    if visit is None:
        return error_response(404, "Visita no encontrada.")
    if visit.entered_at is None or visit.exited_at is not None:
        return error_response(400, "El visitante no figura actualmente dentro.")
    visit.exited_at = now_colombia()
    visit.exit_returning = returning
    method = visit.authorization_method or "app"
    visit.events.append(VisitEvent(
        event_type="salida",
        method=method,
        actor_id=g.current_user.id,
        returning_today=returning,
    ))
    if method != "qr":
        notify_user(
            visit.resident_id,
            "Visitante salió",
            f"{visit.visitor_name} salió de la unidad.",
            "visit",
        )
    db.session.commit()
    return jsonify({"message": "Salida registrada.", "visit": visit.to_dict()})


@bp.post("/visits/qr")
@bp.post("/visits/qr-passes")
@token_required
@role_required("RESIDENT")
def create_visit_qr_pass():
    data, failure = _json_body()
    if failure:
        return failure
    resident = g.current_user
    if g.current_user.role == "ADMIN":
        resident_id = data.get("residentId")
        if not isinstance(resident_id, int) or isinstance(resident_id, bool):
            return error_response(400, "Selecciona un residente válido.")
        resident = User.query.filter_by(id=resident_id, role="RESIDENT").first()
        if resident is None:
            return error_response(400, "Selecciona un residente válido.")
    elif g.current_user.role != "RESIDENT":
        return error_response(403, "Solo un residente o administrador puede crear códigos QR.")
    required_fields = [("validFrom", "fecha de inicio")]
    has_guests = "guests" in data
    if not has_guests:
        required_fields.extend((
            ("visitorName", "nombre del visitante"),
            ("visitorDocument", "documento del visitante"),
        ))
    validation_error = require_non_empty_fields(data, required_fields)
    if validation_error:
        return error_response(400, validation_error)

    max_guests = data.get("maxGuests", data.get("maxPeople", 1))
    if (
        not isinstance(max_guests, int)
        or isinstance(max_guests, bool)
        or not 1 <= max_guests <= 5
    ):
        return error_response(400, "maxGuests debe ser un entero entre 1 y 5.")
    guests = data.get("guests")
    if has_guests:
        if not isinstance(guests, list) or not 1 <= len(guests) <= max_guests:
            return error_response(
                400,
                "guests debe contener entre 1 y maxGuests invitados.",
            )
        normalized_guests = []
        for guest in guests:
            if not isinstance(guest, dict):
                return error_response(400, "Cada invitado debe incluir nombre y documento.")
            full_name = guest.get("fullName")
            document = guest.get("document")
            if (
                not isinstance(full_name, str)
                or not full_name.strip()
                or len(full_name.strip()) > 120
                or not isinstance(document, str)
                or not document.strip()
                or len(document.strip()) > 40
            ):
                return error_response(400, "El nombre o documento de un invitado no es válido.")
            normalized_guests.append({
                "fullName": full_name.strip(),
                "document": document.strip(),
            })
        visitor_name = normalized_guests[0]["fullName"]
        visitor_document = normalized_guests[0]["document"]
    else:
        visitor_name = data["visitorName"]
        visitor_document = data["visitorDocument"]
        if not isinstance(visitor_name, str) or len(visitor_name.strip()) > 120:
            return error_response(400, "El nombre del visitante no puede superar 120 caracteres.")
        if not isinstance(visitor_document, str) or len(visitor_document.strip()) > 40:
            return error_response(400, "El documento del visitante no puede superar 40 caracteres.")
        normalized_guests = None
    if error := validate_iso_date(data["validFrom"]):
        return error_response(400, "Indica una fecha de inicio válida para el QR.")
    try:
        valid_from = date.fromisoformat(data["validFrom"])
    except (TypeError, ValueError):
        return error_response(400, "Indica una fecha de inicio válida para el QR.")

    today = now_colombia().date()
    if valid_from < today:
        return error_response(400, "La fecha de inicio del QR no puede ser anterior a hoy.")
    valid_until_value = data.get("validUntil")
    if valid_until_value is None:
        valid_until = valid_from + timedelta(hours=24)
    else:
        if error := validate_iso_date(valid_until_value):
            return error_response(400, "Indica una fecha de vencimiento válida para el QR.")
        try:
            valid_until = date.fromisoformat(valid_until_value)
        except (TypeError, ValueError):
            return error_response(400, "Indica una fecha de vencimiento válida para el QR.")
    if valid_until < valid_from:
        return error_response(400, "La fecha de vencimiento no puede ser anterior al inicio.")
    if (valid_until - valid_from).total_seconds() > timedelta(hours=72).total_seconds():
        return error_response(400, "La vigencia del QR no puede superar las 72 horas desde el inicio.")

    qr_pass = VisitQrPass(
        resident_id=resident.id,
        token=secrets.token_urlsafe(32),
        valid_from=valid_from.isoformat(),
        valid_until=valid_until.isoformat(),
        max_people=max_guests,
        visitor_name=visitor_name.strip(),
        visitor_document=visitor_document.strip(),
        guests_json=(
            json.dumps(normalized_guests, ensure_ascii=False)
            if normalized_guests is not None else None
        ),
        max_guests=max_guests,
    )
    db.session.add(qr_pass)
    notify_role(
        "GUARD",
        "Nuevo pase QR de visita",
        f"{resident.full_name} generó un pase QR para visitantes.",
        "visit",
    )
    db.session.commit()
    result = qr_pass.to_dict(include_token=True)
    result["qrData"] = f"DOMUX:{qr_pass.token}"
    return jsonify({"qrPass": result}), 201


@bp.get("/visits/qr-passes")
@token_required
@role_required("RESIDENT")
def get_visit_qr_passes():
    if g.current_user.role != "RESIDENT":
        return error_response(403, "Solo un residente puede consultar sus códigos QR.")
    passes = VisitQrPass.query.filter_by(resident_id=g.current_user.id).order_by(
        VisitQrPass.created_at.desc()
    ).all()
    results = []
    for qr_pass in passes:
        result = qr_pass.to_dict(include_token=True)
        result["qrData"] = f"DOMUX:{qr_pass.token}"
        results.append(result)
    return jsonify({"qrPasses": results})


@bp.put("/visits/qr-passes/<int:pass_id>/revoke")
@token_required
@role_required("RESIDENT")
def revoke_visit_qr_pass(pass_id):
    if g.current_user.role != "RESIDENT":
        return error_response(403, "Solo un residente puede revocar sus códigos QR.")
    qr_pass = db.session.get(VisitQrPass, pass_id)
    if qr_pass is None:
        return error_response(404, "Código QR no encontrado.")
    if qr_pass.resident_id != g.current_user.id:
        return error_response(403, "Solo puedes revocar tus propios códigos QR.")
    qr_pass.revoked = True
    qr_pass.revoked_at = now_colombia()
    db.session.commit()
    return jsonify({"message": "Código QR revocado."})


def _qr_pass_for_guard(token):
    qr_pass = VisitQrPass.query.filter_by(token=token).first()
    if qr_pass is None or qr_pass.revoked:
        return None, error_response(404, "Código QR inválido o revocado.")
    today = now_colombia().date().isoformat()
    if not qr_pass.valid_from <= today <= qr_pass.valid_until:
        return None, error_response(400, "El código QR está fuera de su período de vigencia.")
    if qr_pass.used_entries >= qr_pass.max_guests:
        return None, error_response(409, "El QR alcanzó el límite de entradas disponibles.")
    return qr_pass, None


@bp.get("/visits/qr/<string:token>")
@token_required
@role_required("GUARD")
def inspect_visit_qr(token):
    qr_pass = VisitQrPass.query.filter_by(token=token).first()
    if qr_pass is None:
        return error_response(404, "Código QR no encontrado.")
    today = now_colombia().date().isoformat()
    return jsonify({
        "qrPass": qr_pass.to_dict(),
        "residentName": qr_pass.resident.full_name,
        "apartment": qr_pass.resident.apartment,
        "canRegister": (
            not qr_pass.revoked
            and qr_pass.valid_from <= today <= qr_pass.valid_until
            and qr_pass.used_entries < qr_pass.max_guests
        ),
        "inside": [visit.to_dict() for visit in qr_pass.visits if visit.entered_at and not visit.exited_at],
        "registeredVisits": [visit.to_dict() for visit in qr_pass.visits],
        "linkableVisits": [
            visit.to_dict()
            for visit in Visit.query.filter_by(resident_id=qr_pass.resident_id)
            .filter(
                Visit.qr_pass_id.is_(None),
                Visit.approval_status != "rechazada",
            ).all()
            if visit.entered_at is None or visit.exited_at is not None
        ],
    })


@bp.post("/visits/qr/<string:token>/entry")
@token_required
@role_required("GUARD")
def enter_visit_qr(token):
    data, failure = _json_body()
    if failure:
        return failure
    qr_pass, failure = _qr_pass_for_guard(token)
    if failure:
        return failure
    visit_id = data.get("visitId")
    if visit_id is not None and (not isinstance(visit_id, int) or isinstance(visit_id, bool)):
        return error_response(400, "El visitante seleccionado no es válido.")
    visit = db.session.get(Visit, visit_id) if visit_id is not None else None
    if visit_id is not None and (
        visit is None
        or visit.resident_id != qr_pass.resident_id
        or visit.qr_pass_id not in (None, qr_pass.id)
        or visit.approval_status == "rechazada"
    ):
        return error_response(400, "El registro no puede vincularse a este código QR.")
    visitor_name = data.get("visitorName")
    visitor_document = qr_pass.visitor_document
    if visit is None:
        pre_registered_guests = (
            json.loads(qr_pass.guests_json) if qr_pass.guests_json else None
        )
        if pre_registered_guests:
            guest_index = len(qr_pass.visits)
            if guest_index < len(pre_registered_guests):
                visitor_name = pre_registered_guests[guest_index]["fullName"]
                visitor_document = pre_registered_guests[guest_index]["document"]
        else:
            visitor_name = qr_pass.visitor_name
        if not visitor_name:
            visitor_name = data.get("visitorName")
            if not isinstance(visitor_name, str) or not visitor_name.strip():
                return error_response(400, "Escribe el nombre del visitante.")
            visitor_name = visitor_name.strip()
        if visitor_document is None and "visitorDocument" in data:
            visitor_document = data["visitorDocument"]
            if (
                not isinstance(visitor_document, str)
                or len(visitor_document.strip()) > 40
            ):
                return error_response(400, "El documento del visitante no es válido.")
            visitor_document = visitor_document.strip()
    elif visitor_name is not None and (
        not isinstance(visitor_name, str)
        or visitor_name.strip().casefold() != visit.visitor_name.casefold()
    ):
        return error_response(400, "El nombre no coincide con el visitante seleccionado.")
    if visit and visit.entered_at and not visit.exited_at:
        return error_response(409, "Este visitante ya aparece dentro.")
    if visit is None:
        visit = Visit(
            resident_id=qr_pass.resident_id,
            registered_by=g.current_user.id,
            visitor_name=visitor_name,
            visitor_document=visitor_document,
            type="visitante",
            approval_status="aprobada",
            authorization_method="qr",
            qr_pass=qr_pass,
        )
        db.session.add(visit)
        db.session.flush()
    elif visit.qr_pass_id is None:
        visit.qr_pass = qr_pass
        if visit.approval_status == "pendiente":
            visit.approval_status = "aprobada"
            visit.events.append(VisitEvent(
                event_type="aprobada",
                method="qr",
                actor_id=g.current_user.id,
            ))
    visit.authorization_method = "qr"
    visit.entered_at = now_colombia()
    visit.exited_at = None
    visit.exit_returning = False
    visit.events.append(VisitEvent(
        event_type="entrada",
        method="qr",
        actor_id=g.current_user.id,
    ))
    qr_pass.used_entries += 1
    notify_user(
        visit.resident_id,
        "Visitante ingresó por QR",
        f"{visit.visitor_name} ingresó a la unidad con el código QR.",
        "visit",
    )
    db.session.commit()
    return jsonify({"message": "Entrada por QR registrada.", "visit": visit.to_dict()}), 201


@bp.post("/visits/qr/<string:token>/exit")
@token_required
@role_required("GUARD")
def exit_visit_qr(token):
    data, failure = _json_body()
    if failure:
        return failure
    visit_id = data.get("visitId")
    returning = data.get("returningToday", False)
    if not isinstance(visit_id, int) or isinstance(visit_id, bool):
        return error_response(400, "Selecciona un visitante.")
    if not isinstance(returning, bool):
        return error_response(400, "returningToday debe ser verdadero o falso.")
    qr_pass = VisitQrPass.query.filter_by(token=token).first()
    if qr_pass is None:
        return error_response(404, "Código QR no encontrado.")
    visit = db.session.get(Visit, visit_id)
    if visit is None or visit.qr_pass_id != qr_pass.id:
        return error_response(404, "El visitante no pertenece a este código QR.")
    if visit.entered_at is None or visit.exited_at is not None:
        return error_response(400, "El visitante no figura actualmente dentro.")
    visit.exited_at = now_colombia()
    visit.exit_returning = returning
    visit.events.append(VisitEvent(
        event_type="salida",
        method="qr",
        actor_id=g.current_user.id,
        returning_today=returning,
    ))
    db.session.commit()
    return jsonify({"message": "Salida por QR registrada.", "visit": visit.to_dict()})


@bp.get("/notifications")
@token_required
def get_notifications():
    finalize_expired_reservations()
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


@bp.delete("/notifications/read")
@token_required
def delete_read_notifications():
    deleted_count = Notification.query.filter_by(
        user_id=g.current_user.id,
        is_read=True,
    ).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({
        "message": "Notificaciones leídas eliminadas.",
        "deletedCount": deleted_count,
    })
