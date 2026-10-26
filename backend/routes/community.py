from datetime import datetime

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from auth import role_required, token_required
from errors import error_response
from extensions import db
from models import (
    Announcement,
    CommonArea,
    Pqrs,
    PqrsMessage,
    PqrsSatisfaction,
    Reservation,
    User,
)
from services.notification_service import notify_residents, notify_user
from services.reservation_service import (
    ACTIVE_RESERVATION_STATUSES,
    reservation_availability,
    reservation_conflicts,
)
from validators import (
    VALID_PQRS_STATUSES,
    require_non_empty_fields,
    validate_future_or_today_date,
    validate_iso_date,
    validate_media_fields,
    validate_no_empty_strings,
    validate_time,
    validate_time_slot,
)

bp = Blueprint("community", __name__, url_prefix="/api")
RESERVATION_STATUSES = ("pendiente", "activa", "aprobada", "rechazada", "cancelada")


def _json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, error_response(400, "El cuerpo de la solicitud debe ser un objeto JSON válido.")
    message = validate_no_empty_strings(data)
    if message:
        return None, error_response(400, message)
    return data, None


def _media_and_event_error(data, date_key, time_key):
    error = validate_media_fields(data)
    if error:
        return error
    event_date = data.get(date_key)
    if event_date is not None and (error := validate_iso_date(event_date)):
        return error
    event_time = data.get(time_key)
    if event_time is not None and (error := validate_time(event_time)):
        return error
    return None


def _resident_for_write(data):
    if g.current_user.role == "RESIDENT":
        return g.current_user
    resident_id = data.get("residentId")
    if not isinstance(resident_id, int) or isinstance(resident_id, bool):
        return None
    return User.query.filter_by(id=resident_id, role="RESIDENT").first()


@bp.get("/announcements")
@token_required
def get_announcements():
    items = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return jsonify({"announcements": [item.to_dict() for item in items]})


@bp.post("/announcements")
@token_required
@role_required("ADMIN")
def create_announcement():
    data, failure = _json_body()
    if failure:
        return failure
    validation_error = require_non_empty_fields(
        data,
        (("title", "título"), ("message", "mensaje")),
    )
    if validation_error:
        return error_response(400, validation_error)
    if error := _media_and_event_error(data, "eventDate", "eventTime"):
        return error_response(400, error)

    announcement = Announcement(
        title=data["title"].strip(),
        message=data["message"].strip(),
        event_date=data.get("eventDate"),
        event_time=data.get("eventTime"),
        media_url=data.get("mediaUrl"),
        media_type=data.get("mediaType"),
        author_id=g.current_user.id,
    )
    db.session.add(announcement)
    notify_residents(
        "Nuevo anuncio",
        announcement.title,
        "announcement",
    )
    db.session.commit()
    return jsonify({"message": "Anuncio publicado", "announcement": announcement.to_dict()}), 201


@bp.delete("/announcements/<int:announcement_id>")
@token_required
@role_required("ADMIN")
def delete_announcement(announcement_id):
    announcement = db.session.get(Announcement, announcement_id)
    if announcement is None:
        return error_response(404, "Anuncio no encontrado")
    db.session.delete(announcement)
    db.session.commit()
    return jsonify({"message": "Anuncio eliminado"})


@bp.get("/pqrs")
@token_required
def get_pqrs():
    user = g.current_user
    query = Pqrs.query.join(User, Pqrs.resident_id == User.id)
    if user.role == "RESIDENT":
        query = query.filter(Pqrs.resident_id == user.id)
    elif user.role != "ADMIN":
        return error_response(403, "No tienes permiso para ver las PQRS")

    status = request.args.get("status")
    category = request.args.get("category")
    search = (request.args.get("search") or request.args.get("q") or "").strip()
    if status:
        if status not in VALID_PQRS_STATUSES:
            return error_response(400, "Estado de PQRS inválido")
        query = query.filter(Pqrs.status == status)
    if category:
        query = query.filter(Pqrs.category == category.strip())
    if search:
        pattern = f"%{search}%"
        query = query.filter(db.or_(
            Pqrs.subject.ilike(pattern),
            Pqrs.message.ilike(pattern),
            Pqrs.category.ilike(pattern),
            User.name.ilike(pattern),
            User.last_name.ilike(pattern),
            User.apartment.ilike(pattern),
        ))
    items = query.order_by(Pqrs.created_at.desc()).all()
    return jsonify({"pqrs": [item.to_dict() for item in items]})


@bp.post("/pqrs")
@token_required
def create_pqrs():
    data, failure = _json_body()
    if failure:
        return failure
    validation_error = require_non_empty_fields(
        data,
        (("subject", "asunto"), ("message", "mensaje")),
    )
    if validation_error:
        return error_response(400, validation_error)
    if error := _media_and_event_error(data, "incidentDate", "incidentTime"):
        return error_response(400, error)
    if g.current_user.role not in ("RESIDENT", "ADMIN"):
        return error_response(403, "No tienes permiso para crear PQRS")
    resident = _resident_for_write(data)
    if resident is None:
        return error_response(400, "Selecciona un residente válido")
    category = data.get("category", "Petición")
    if not isinstance(category, str):
        return error_response(400, "La categoría debe ser texto")

    pqrs = Pqrs(
        resident_id=resident.id,
        category=category.strip(),
        subject=data["subject"].strip(),
        message=data["message"].strip(),
        incident_date=data.get("incidentDate"),
        incident_time=data.get("incidentTime"),
        media_url=data.get("mediaUrl"),
        media_type=data.get("mediaType"),
    )
    db.session.add(pqrs)
    db.session.flush()
    pqrs.conversation.append(PqrsMessage(
        author_id=g.current_user.id,
        author_role=g.current_user.role,
        message=data["message"].strip(),
        media_url=data.get("mediaUrl"),
        media_type=data.get("mediaType"),
    ))
    if g.current_user.role == "ADMIN":
        notify_user(
            resident.id,
            "Nueva PQRS registrada",
            f"Administración registró una PQRS a tu nombre: {pqrs.subject}.",
            "pqrs",
        )
    db.session.commit()
    return jsonify({"message": "PQRS enviada", "pqrs": pqrs.to_dict()}), 201


@bp.put("/pqrs/<int:pqrs_id>/respond")
@token_required
@role_required("ADMIN")
def respond_pqrs(pqrs_id):
    data, failure = _json_body()
    if failure:
        return failure
    if "status" not in data or data["status"] not in VALID_PQRS_STATUSES:
        return error_response(400, "Estado de PQRS inválido")
    response_text = data.get("adminResponse")
    if not isinstance(response_text, str) or not response_text.strip():
        return error_response(400, "Escribe una respuesta antes de actualizar la PQRS.")
    if error := validate_media_fields(data):
        return error_response(400, error)

    pqrs = db.session.get(Pqrs, pqrs_id)
    if pqrs is None:
        return error_response(404, "PQRS no encontrada")
    if data["status"] == "resuelta" and not response_text.strip():
        return error_response(400, "No puedes resolver una PQRS sin escribir una respuesta.")
    previous_status = pqrs.status
    pqrs.status = data["status"]
    pqrs.admin_response = response_text.strip()
    if previous_status != pqrs.status:
        pqrs.updated_at = datetime.utcnow()
    pqrs.conversation.append(PqrsMessage(
        author_id=g.current_user.id,
        author_role="ADMIN",
        message=response_text.strip(),
        media_url=data.get("mediaUrl"),
        media_type=data.get("mediaType"),
    ))
    notify_user(
        pqrs.resident_id,
        "Actualización de PQRS",
        f"Tu solicitud '{pqrs.subject}' ahora está {pqrs.status}.",
        "pqrs",
    )
    db.session.commit()
    return jsonify({"message": "PQRS actualizada", "pqrs": pqrs.to_dict()})


@bp.post("/pqrs/<int:pqrs_id>/messages")
@token_required
@role_required("RESIDENT")
def add_pqrs_message(pqrs_id):
    data, failure = _json_body()
    if failure:
        return failure
    if error := validate_media_fields(data):
        return error_response(400, error)
    message = data.get("message")
    if message is not None and not isinstance(message, str):
        return error_response(400, "El mensaje debe ser texto.")
    if not (message and message.strip()) and not data.get("mediaUrl"):
        return error_response(400, "Escribe un mensaje o adjunta un archivo.")

    pqrs = db.session.get(Pqrs, pqrs_id)
    if pqrs is None:
        return error_response(404, "PQRS no encontrada")
    if pqrs.resident_id != g.current_user.id:
        return error_response(403, "Solo puedes responder tus propias PQRS.")

    was_resolved = pqrs.status == "resuelta"
    if was_resolved:
        pqrs.status = "abierta"
        pqrs.updated_at = datetime.utcnow()
    pqrs.conversation.append(PqrsMessage(
        author_id=g.current_user.id,
        author_role="RESIDENT",
        message=message.strip() if message and message.strip() else None,
        media_url=data.get("mediaUrl"),
        media_type=data.get("mediaType"),
    ))
    if was_resolved:
        admins = User.query.filter_by(role="ADMIN", is_active=True).all()
        for admin in admins:
            notify_user(
                admin.id,
                "PQRS reabierta",
                f"El residente respondió la PQRS '{pqrs.subject}', que volvió a estado abierta.",
                "pqrs",
            )
    db.session.commit()
    return jsonify({"message": "Mensaje agregado", "pqrs": pqrs.to_dict()}), 201


@bp.put("/pqrs/<int:pqrs_id>/satisfaction")
@token_required
@role_required("RESIDENT")
def rate_pqrs(pqrs_id):
    data, failure = _json_body()
    if failure:
        return failure
    rating = data.get("rating")
    if not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 5:
        return error_response(400, "La calificación debe ser un número entre 1 y 5.")
    comment = data.get("comment")
    if comment is not None and not isinstance(comment, str):
        return error_response(400, "El comentario debe ser texto.")

    pqrs = db.session.get(Pqrs, pqrs_id)
    if pqrs is None:
        return error_response(404, "PQRS no encontrada")
    if pqrs.resident_id != g.current_user.id:
        return error_response(403, "Solo puedes calificar tus propias PQRS.")
    if pqrs.status != "resuelta":
        return error_response(400, "Solo puedes calificar una PQRS resuelta.")

    rated_this_cycle = None
    if pqrs.updated_at:
        rated_this_cycle = PqrsSatisfaction.query.filter(
            PqrsSatisfaction.pqrs_id == pqrs.id,
            PqrsSatisfaction.created_at >= pqrs.updated_at,
        ).order_by(PqrsSatisfaction.created_at.desc(), PqrsSatisfaction.id.desc()).first()
    if rated_this_cycle is None:
        rated_this_cycle = PqrsSatisfaction(pqrs_id=pqrs.id)
        db.session.add(rated_this_cycle)
    rated_this_cycle.rating = rating
    rated_this_cycle.comment = comment.strip() if comment and comment.strip() else None
    rated_this_cycle.created_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Calificación guardada", "pqrs": pqrs.to_dict()})


@bp.post("/pqrs/batch/respond")
@token_required
@role_required("ADMIN")
def respond_pqrs_batch():
    data, failure = _json_body()
    if failure:
        return failure
    ids = data.get("pqrsIds")
    status = data.get("status")
    message = data.get("message")
    if (
        not isinstance(ids, list)
        or not ids
        or any(not isinstance(pqrs_id, int) or isinstance(pqrs_id, bool) or pqrs_id <= 0 for pqrs_id in ids)
    ):
        return error_response(400, "Selecciona una o más PQRS válidas.")
    if len(set(ids)) != len(ids):
        return error_response(400, "La selección contiene PQRS repetidas.")
    if status not in ("en_proceso", "resuelta"):
        return error_response(400, "El estado debe ser 'en_proceso' o 'resuelta'.")
    if not isinstance(message, str) or not message.strip():
        return error_response(400, "Escribe una respuesta para todas las PQRS seleccionadas.")
    if error := validate_media_fields(data):
        return error_response(400, error)

    pqrs_items = Pqrs.query.filter(Pqrs.id.in_(ids)).all()
    if len(pqrs_items) != len(ids):
        found_ids = {item.id for item in pqrs_items}
        missing_ids = [pqrs_id for pqrs_id in ids if pqrs_id not in found_ids]
        return jsonify({
            "error": "Algunas PQRS ya no existen; no se actualizó ninguna.",
            "status": 404,
            "failedPqrsIds": missing_ids,
            "updatedCount": 0,
        }), 404
    categories = {item.category or "Petición" for item in pqrs_items}
    if len(categories) != 1:
        return error_response(400, "La respuesta por lotes solo permite PQRS de la misma categoría.")

    resident_ids = {item.resident_id for item in pqrs_items}
    for pqrs in pqrs_items:
        previous_status = pqrs.status
        pqrs.status = status
        pqrs.admin_response = message.strip()
        if previous_status != status:
            pqrs.updated_at = datetime.utcnow()
        pqrs.conversation.append(PqrsMessage(
            author_id=g.current_user.id,
            author_role="ADMIN",
            message=message.strip(),
            media_url=data.get("mediaUrl"),
            media_type=data.get("mediaType"),
        ))
    for resident_id in resident_ids:
        notify_user(
            resident_id,
            "Actualización de PQRS",
            f"Administración respondió {sum(item.resident_id == resident_id for item in pqrs_items)} "
            "de tus solicitudes.",
            "pqrs",
        )
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({
            "error": "No se pudo guardar la respuesta; ninguna PQRS fue modificada.",
            "status": 500,
            "failedPqrsIds": ids,
            "updatedCount": 0,
        }), 500
    return jsonify({
        "message": "Las PQRS seleccionadas fueron actualizadas.",
        "updatedCount": len(pqrs_items),
        "pqrsIds": ids,
    })


@bp.get("/common-areas")
@token_required
def get_common_areas():
    areas = CommonArea.query.order_by(CommonArea.name).all()
    return jsonify({"areas": [area.to_dict() for area in areas]})


@bp.get("/reservations")
@token_required
def get_reservations():
    user = g.current_user
    if user.role == "ADMIN":
        items = Reservation.query.order_by(Reservation.created_at.desc()).all()
    elif user.role == "RESIDENT":
        items = Reservation.query.filter_by(
            resident_id=user.id
        ).order_by(Reservation.created_at.desc()).all()
    else:
        return error_response(403, "No tienes permiso para ver las reservas")
    return jsonify({"reservations": [item.to_dict() for item in items]})


@bp.get("/reservations/availability")
@token_required
def get_reservation_availability():
    common_area_id = request.args.get("commonAreaId", type=int)
    date = request.args.get("date")
    if common_area_id is None or not date:
        return error_response(400, "commonAreaId y date son obligatorios")
    if error := validate_future_or_today_date(date):
        return error_response(400, error)
    if db.session.get(CommonArea, common_area_id) is None:
        return error_response(404, "Zona común no encontrada")

    slots = reservation_availability(common_area_id, date)
    return jsonify({
        "commonAreaId": common_area_id,
        "date": date,
        **slots,
    })


@bp.post("/reservations")
@token_required
@role_required("RESIDENT")
def create_reservation():
    data, failure = _json_body()
    if failure:
        return failure
    validation_error = require_non_empty_fields(
        data,
        (("date", "fecha"), ("timeSlot", "horario")),
    )
    if validation_error:
        return error_response(400, validation_error)
    area_id = data.get("commonAreaId")
    if not isinstance(area_id, int) or isinstance(area_id, bool):
        return error_response(400, "Selecciona una zona común válida")
    area = db.session.get(CommonArea, area_id)
    if area is None:
        return error_response(400, "Selecciona una zona común válida")
    if error := validate_future_or_today_date(data["date"]):
        return error_response(400, error)
    if error := validate_time_slot(data["timeSlot"]):
        return error_response(400, error)
    resident = _resident_for_write(data)
    if resident is None:
        return error_response(400, "Selecciona un residente válido")
    if reservation_conflicts(area.id, data["date"], data["timeSlot"]):
        return error_response(409, "Ese horario ya no está disponible")

    reservation = Reservation(
        resident_id=resident.id,
        common_area_id=area.id,
        date=data["date"],
        time_slot=data["timeSlot"],
    )
    db.session.add(reservation)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if reservation_conflicts(area.id, data["date"], data["timeSlot"]):
            return error_response(409, "Ese horario ya no está disponible")
        raise
    return jsonify({"message": "Reserva creada", "reservation": reservation.to_dict()}), 201


@bp.put("/reservations/<int:res_id>/status")
@token_required
@role_required("ADMIN")
def update_reservation_status(res_id):
    data, failure = _json_body()
    if failure:
        return failure
    status = data.get("status")
    if status not in RESERVATION_STATUSES:
        return error_response(400, "Estado de reserva inválido")
    reservation = db.session.get(Reservation, res_id)
    if reservation is None:
        return error_response(404, "Reserva no encontrada")
    if status in ACTIVE_RESERVATION_STATUSES and reservation_conflicts(
        reservation.common_area_id,
        reservation.date,
        reservation.time_slot,
        exclude_id=reservation.id,
    ):
        return error_response(409, "Ese horario ya no está disponible")

    previous_status = reservation.status
    reservation.status = status
    if status in ("aprobada", "rechazada") and status != previous_status:
        notify_user(
            reservation.resident_id,
            "Reserva actualizada",
            f"Tu reserva de {reservation.common_area.name if reservation.common_area else 'la zona'} "
            f"fue {status}.",
            "reservation",
        )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if status in ACTIVE_RESERVATION_STATUSES and reservation_conflicts(
            reservation.common_area_id,
            reservation.date,
            reservation.time_slot,
        ):
            return error_response(409, "Ese horario ya no está disponible")
        raise
    return jsonify({"message": "Reserva actualizada", "reservation": reservation.to_dict()})


@bp.put("/reservations/<int:res_id>/cancel")
@token_required
@role_required("RESIDENT", "ADMIN")
def cancel_reservation(res_id):
    reservation = db.session.get(Reservation, res_id)
    if reservation is None:
        return error_response(404, "Reserva no encontrada")
    if g.current_user.role == "RESIDENT" and reservation.resident_id != g.current_user.id:
        return error_response(403, "Esa reserva no es tuya")
    reservation.status = "cancelada"
    db.session.commit()
    return jsonify({"message": "Reserva cancelada", "reservation": reservation.to_dict()})
