import secrets
from datetime import date, timedelta

from flask import Blueprint, g, jsonify, request

from sqlalchemy.orm import contains_eager, selectinload

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
from routes.common import bool_arg, int_arg, json_body, paginated
from services import package_service, visit_service
from services.alert_service import run_alerts
from services.notification_service import notify_user
from validators import (
    VALID_PACKAGE_STATUSES,
    require_non_empty_fields,
    validate_iso_date,
    validate_media_fields,
    validate_time,
)
from time_utils import colombia_today, to_colombia, utc_now

bp = Blueprint("security", __name__, url_prefix="/api")
VISIT_TYPES = ("visitante", "domiciliario", "contratista")


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


def _cleanup_expired_packages():
    """Pasa a la papelera los paquetes entregados hace más de 7 días.

    Solo los oculta de la lista diaria del guardia: siguen en la base y se pueden
    restaurar. Ningún paquete se borra (DEC-090), para responder si alguien
    reclama un pedido perdido; los más viejos los guarda el archivo histórico.
    """
    now = utc_now()
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


@bp.post("/push-tokens")
@token_required
@role_required("ADMIN", "GUARD", "RESIDENT")
def register_push_token():
    data, failure = json_body()
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
@role_required("ADMIN", "GUARD", "RESIDENT")
def delete_push_token():
    data, failure = json_body()
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
@role_required("ADMIN", "GUARD", "RESIDENT")
def get_packages():
    _cleanup_expired_packages()
    user = g.current_user
    # Con el residente en la misma consulta y lo demás por lotes, la lista no hace
    # una consulta por paquete al armar cada respuesta.
    query = (
        PackageItem.query.join(User, PackageItem.resident_id == User.id)
        .options(
            contains_eager(PackageItem.resident),
            selectinload(PackageItem.guard),
            selectinload(PackageItem.delivered_by),
            selectinload(PackageItem.pickup_codes),
        )
    )
    if user.role == "RESIDENT":
        query = query.filter(PackageItem.resident_id == user.id)
        requested_resident_id = request.args.get("residentId", type=int)
        if requested_resident_id is not None and requested_resident_id != user.id:
            return error_response(403, "No puedes consultar paquetes de otro residente")
    elif user.role not in ("ADMIN", "GUARD"):
        return error_response(403, "No tienes permiso para ver los paquetes")

    status = request.args.get("status")
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
            PackageItem.carrier.ilike(pattern),
            PackageItem.tracking_number.ilike(pattern),
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
    data, failure = json_body()
    if failure:
        return failure
    status = data.get("status", "pendiente")
    if status not in ("pendiente", "por_llegar"):
        return error_response(400, "Estado de paquete inválido")
    validation_error = require_non_empty_fields(
        data,
        (("description", "descripción"),),
    )
    if validation_error:
        return error_response(400, validation_error)
    if error := _package_metadata_error(data):
        return error_response(400, error)
    carrier, tracking_number = package_service.clean_shipping(data)
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
        carrier=carrier,
        tracking_number=tracking_number,
        status=status,
        # Las horas sin reclamar se cuentan desde que llega a la portería (RN-018).
        arrived_at=utc_now() if status == "pendiente" else None,
        media_url=data.get("mediaUrl"),
        media_type=data.get("mediaType"),
        event_date=data.get("eventDate"),
        event_time=data.get("eventTime"),
    )
    db.session.add(package)
    from_carrier = f" de {carrier}" if carrier else ""
    notify_user(
        resident.id,
        "Paquete registrado",
        f"Se registró un paquete{from_carrier} para {resident.apartment or 'tu cuenta'}.",
        "package",
    )
    db.session.commit()
    return jsonify({"message": "Paquete registrado", "packageItem": package.to_dict()}), 201


@bp.put("/packages/<int:pkg_id>/status")
@token_required
@role_required("GUARD", "ADMIN")
def update_package_status(pkg_id):
    data, failure = json_body()
    if failure:
        return failure
    status = data.get("status")
    if status not in ("por_llegar", "pendiente"):
        return error_response(400, "Estado de paquete inválido")
    package = db.session.get(PackageItem, pkg_id)
    if package is None:
        return error_response(404, "Paquete no encontrado")
    if package.status == "entregado":
        return error_response(409, "Este paquete ya fue entregado: su estado no se puede cambiar.")
    if package.status != status:
        package.status = status
        # Al llegar a la portería empieza a contar el tiempo sin reclamar (RN-018).
        package.arrived_at = utc_now() if status == "pendiente" else None
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
    """Envía un paquete a la papelera (retiro lógico).

    El paquete no se borra de la base (DEC-090): queda en la papelera, se puede
    restaurar y lo guarda el archivo histórico. Por eso no existe borrar para
    siempre, ni siquiera desde la papelera.
    """
    package = db.session.get(PackageItem, pkg_id)
    if package is None:
        return error_response(404, "Paquete no encontrado")
    if package.is_deleted:
        return error_response(
            409,
            "El paquete ya está en la papelera. Los paquetes no se eliminan para "
            "siempre: se pueden restaurar.",
        )
    package.is_deleted = True
    package.deleted_at = utc_now()
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
@role_required("GUARD", "ADMIN")
def deliver_package(pkg_id):
    data, failure = json_body()
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
    pickup_code = data.get("pickupCode")
    if package.status != "entregado":
        # Con código (QR o PIN) se valida antes de entregar; sin él, el guardia entrega
        # como siempre y el código que hubiera queda anulado (RN-016, HU-048).
        if pickup_code is not None:
            package_service.check_pickup_code(package, pickup_code, g.current_user)
        else:
            package_service.close_active_code(package)
        package.status = "entregado"
        package.delivered_at = utc_now()
        package.delivered_to = receiver.strip()
        package.delivered_by_id = g.current_user.id
        with_code = " con tu código de entrega" if pickup_code is not None else ""
        notify_user(
            package.resident_id,
            "Paquete entregado",
            f"Tu paquete ({package.description or 'sin descripción'}) fue entregado "
            f"a {package.delivered_to}{with_code}.",
            "package",
        )
        db.session.commit()
    return jsonify({"message": "Paquete marcado como entregado", "packageItem": package.to_dict()})


@bp.post("/packages/<int:pkg_id>/pickup-code")
@token_required
@role_required("RESIDENT")
def create_package_pickup_code(pkg_id):
    """El residente genera el código para que otra persona recoja su paquete (HU-048).

    La respuesta trae el QR y el PIN de 6 dígitos; el PIN no se vuelve a mostrar:
    si se pierde, se genera un código nuevo y el anterior queda anulado.
    """
    package = db.session.get(PackageItem, pkg_id)
    if package is None:
        return error_response(404, "Paquete no encontrado")
    code, pin = package_service.create_pickup_code(package, g.current_user)
    db.session.commit()
    return jsonify({
        "message": "Código de entrega generado. Compártelo solo con quien va a recoger el paquete.",
        "pickupCode": {"qrData": f"{package_service.QR_PREFIX}{code.token}", "pin": pin},
        "packageItem": package.to_dict(),
    }), 201


@bp.post("/packages/pickup-lookup")
@token_required
@role_required("GUARD", "ADMIN")
def lookup_package_pickup_code():
    """El guardia escanea el QR de un código de entrega y ve de qué paquete es (HU-048).

    El código viaja en el cuerpo y no en la dirección, para que no quede en los
    registros del servidor.
    """
    data, failure = json_body()
    if failure:
        return failure
    package = package_service.package_for_pickup_token(data.get("code"))
    return jsonify({"packageItem": package.to_dict()})


@bp.get("/visits")
@token_required
@role_required("ADMIN", "GUARD", "RESIDENT")
def get_visits():
    """Historial de visitas (HU-030).

    El administrador y el guardia ven todas; el residente, solo las de su
    apartamento. Se filtra por status, search, apartmentId, from y to (días de
    Colombia) y, con inside=true, solo las que entraron y no tienen salida (HU-032).
    """
    query = visit_service.visits_query(
        g.current_user,
        status=request.args.get("status"),
        search=(request.args.get("search") or "").strip(),
        apartment_id=int_arg("apartmentId"),
        date_from=request.args.get("from"),
        date_to=request.args.get("to"),
        inside=bool_arg("inside"),
    )
    return paginated(query, "visits", default_size=50, max_size=200)


@bp.post("/visits")
@token_required
@role_required("GUARD")
def register_visit():
    data, failure = json_body()
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
    consent = data.get("mediaConsent", False)
    if not isinstance(consent, bool):
        return error_response(400, "El consentimiento debe ser verdadero o falso.")
    if (document or data.get("mediaUrl")) and not consent:
        return error_response(400, "Se necesita consentimiento para guardar documento o foto.")
    if data.get("mediaUrl"):
        if error := validate_media_fields(data):
            return error_response(400, error)
    if data.get("mediaType") and data["mediaType"] != "image":
        return error_response(400, "La foto del visitante debe ser una imagen.")
    description = data.get("description")
    if description is not None and not isinstance(description, str):
        return error_response(400, "Los detalles del pedido deben ser texto.")
    stay = visit_service.expected_stay(data.get("expectedStayMinutes"))
    visit = Visit(
        resident_id=resident.id,
        registered_by=g.current_user.id,
        expected_stay_minutes=stay,
        visitor_name=data["visitorName"].strip(),
        visitor_document=document.strip() if document else None,
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
    data, failure = json_body()
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


def _start_stay(visit, stay):
    """Empieza una estadía: la alerta de estadía larga vuelve a quedar pendiente (HU-031).

    Si el guardia anotó una estadía prevista nueva, reemplaza la anterior.
    """
    visit.overstay_alerted_at = None
    if stay is not None:
        visit.expected_stay_minutes = stay


@bp.post("/visits/<int:visit_id>/entry")
@token_required
@role_required("GUARD")
def register_visit_entry(visit_id):
    # El cuerpo es opcional: solo trae la estadía prevista, si el guardia la anota ahora.
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    elif not isinstance(data, dict):
        return error_response(400, "El cuerpo de la solicitud debe ser un objeto JSON válido.")
    stay = visit_service.expected_stay(data.get("expectedStayMinutes"))
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
        # «Vuelve hoy» se mide con el día de Colombia, no con el de UTC (TT-031).
        not visit.exit_returning or to_colombia(visit.exited_at).date() < colombia_today()
    ):
        return error_response(400, "El registro indica salida definitiva; crea una nueva solicitud de ingreso.")
    visit.entered_at = utc_now()
    visit.exited_at = None
    visit.exit_returning = False
    _start_stay(visit, stay)
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
    data, failure = json_body()
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
    visit.exited_at = utc_now()
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


@bp.post("/visits/qr-passes")
@token_required
@role_required("RESIDENT")
def create_visit_qr_pass():
    if g.current_user.role != "RESIDENT":
        return error_response(403, "Solo un residente puede crear códigos QR.")
    data, failure = json_body()
    if failure:
        return failure
    try:
        valid_from = date.fromisoformat(data.get("validFrom", ""))
        valid_until = date.fromisoformat(data.get("validUntil", ""))
    except (TypeError, ValueError):
        return error_response(400, "Indica fechas válidas para el QR.")
    today = colombia_today()
    if valid_from < today or valid_until < valid_from:
        return error_response(400, "El período del QR debe ser actual o futuro.")
    if (valid_until - valid_from).days >= 30:
        return error_response(400, "El QR puede tener una duración máxima de 30 días.")
    max_people = data.get("maxPeople")
    if (
        not isinstance(max_people, int)
        or isinstance(max_people, bool)
        or not 1 <= max_people <= 2_147_483_647
    ):
        return error_response(400, "El límite de personas debe ser un entero positivo válido.")
    names = visit_service.clean_visitor_names(data.get("visitorNames"), max_people)
    qr_pass = VisitQrPass(
        resident_id=g.current_user.id,
        token=secrets.token_urlsafe(32),
        valid_from=valid_from.isoformat(),
        valid_until=valid_until.isoformat(),
        max_people=max_people,
    )
    qr_pass.names = names
    db.session.add(qr_pass)
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
    qr_pass.revoked_at = utc_now()
    db.session.commit()
    return jsonify({"message": "Código QR revocado."})


def _qr_pass_for_guard(token):
    qr_pass = VisitQrPass.query.filter_by(token=token).first()
    # El QR de un residente desactivado tampoco sirve, aunque no esté anulado (TT-027).
    if qr_pass is None or qr_pass.revoked or not qr_pass.resident.is_active:
        return None, error_response(404, "Código QR inválido o revocado.")
    today = colombia_today().isoformat()
    if not qr_pass.valid_from <= today <= qr_pass.valid_until:
        return None, error_response(400, "El código QR está fuera de su período de vigencia.")
    return qr_pass, None


@bp.get("/visits/qr/<string:token>")
@token_required
@role_required("GUARD")
def inspect_visit_qr(token):
    qr_pass = VisitQrPass.query.filter_by(token=token).first()
    if qr_pass is None:
        return error_response(404, "Código QR no encontrado.")
    today = colombia_today().isoformat()
    return jsonify({
        "qrPass": qr_pass.to_dict(),
        "pendingVisitorNames": visit_service.pending_visitor_names(qr_pass),
        "residentName": qr_pass.resident.full_name,
        "apartment": qr_pass.resident.apartment,
        "canRegister": (
            not qr_pass.revoked
            and qr_pass.resident.is_active
            and qr_pass.valid_from <= today <= qr_pass.valid_until
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
    data, failure = json_body()
    if failure:
        return failure
    stay = visit_service.expected_stay(data.get("expectedStayMinutes"))
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
    if visit is None:
        if not isinstance(visitor_name, str) or not visitor_name.strip():
            return error_response(400, "Escribe el nombre del visitante.")
        visitor_name = visitor_name.strip()
    elif visitor_name is not None and (
        not isinstance(visitor_name, str)
        or visitor_name.strip().casefold() != visit.visitor_name.casefold()
    ):
        return error_response(400, "El nombre no coincide con el visitante seleccionado.")
    if visit and visit.entered_at and not visit.exited_at:
        return error_response(409, "Este visitante ya aparece dentro.")
    if visit is not None and visit.qr_pass_id == qr_pass.id:
        if len(qr_pass.visits) > qr_pass.max_people:
            return error_response(409, "El QR alcanzó el límite de personas. Debe generarse otro código.")
    else:
        if len(qr_pass.visits) >= qr_pass.max_people:
            return error_response(409, "El QR alcanzó el límite de personas. Debe generarse otro código.")
    if visit is None:
        visit = Visit(
            resident_id=qr_pass.resident_id,
            registered_by=g.current_user.id,
            visitor_name=visitor_name,
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
    visit.entered_at = utc_now()
    visit.exited_at = None
    visit.exit_returning = False
    _start_stay(visit, stay)
    visit.events.append(VisitEvent(
        event_type="entrada",
        method="qr",
        actor_id=g.current_user.id,
    ))
    db.session.commit()
    return jsonify({"message": "Entrada por QR registrada.", "visit": visit.to_dict()}), 201


@bp.post("/visits/qr/<string:token>/exit")
@token_required
@role_required("GUARD")
def exit_visit_qr(token):
    data, failure = json_body()
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
    visit.exited_at = utc_now()
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
@role_required("ADMIN", "GUARD", "RESIDENT")
def get_notifications():
    # Las alertas pendientes (tiempo máximo de parqueo, visitas largas) se generan
    # al consultar: no hay un reloj que las dispare (ver services/alert_service.py).
    run_alerts()
    notifications = Notification.query.filter_by(
        user_id=g.current_user.id
    ).order_by(Notification.created_at.desc()).all()
    return jsonify({"notifications": [item.to_dict() for item in notifications]})


@bp.put("/notifications/<int:notification_id>/read")
@token_required
@role_required("ADMIN", "GUARD", "RESIDENT")
def mark_notification_read(notification_id):
    notification = db.session.get(Notification, notification_id)
    if notification is None:
        return error_response(404, "Notificación no encontrada")
    if notification.user_id != g.current_user.id:
        return error_response(403, "No puedes modificar una notificación ajena")
    notification.is_read = True
    db.session.commit()
    return jsonify({"message": "Notificación marcada como leída", "notification": notification.to_dict()})
