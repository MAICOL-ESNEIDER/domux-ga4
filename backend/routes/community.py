import base64
import json
import unicodedata
from datetime import date, timedelta

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from auth import role_required, token_required
from errors import error_response
from extensions import db
from models import (
    Announcement,
    AuditLog,
    CommonArea,
    Pqrs,
    PqrsMessage,
    PqrsSatisfaction,
    Reservation,
    ReservationMessage,
    User,
)
from time_utils import COLOMBIA_TIMEZONE, now_colombia
from services.notification_service import (
    notify_admins,
    notify_residents,
    notify_role,
    notify_user,
)
from services.excel_service import (
    MIME_XLSX,
    generate_legal_report_xlsx,
)
from services.reservation_service import (
    ACTIVE_RESERVATION_STATUSES,
    finalize_expired_reservations,
    reservation_availability,
    reservation_conflicts,
    time_slots_overlap,
)
from validators import (
    EXTENDED_TIME_SLOTS,
    VALID_PQRS_STATUSES,
    STANDARD_TIME_SLOTS,
    parse_optional_bool,
    parse_bool,
    require_non_empty_fields,
    validate_future_or_today_date,
    validate_iso_date,
    validate_media_fields,
    validate_no_empty_strings,
    validate_media_url,
    validate_time,
    validate_time_slot,
)

bp = Blueprint("community", __name__, url_prefix="/api")


def _add_audit_log(entity_type, entity_id, action, details=None):
    db.session.add(AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=g.current_user.id,
        actor_role=g.current_user.role,
        details=json.dumps(details, ensure_ascii=False) if details is not None else None,
    ))


@bp.post("/admin/archive-history")
@token_required
@role_required("ADMIN")
def archive_history():
    finalize_expired_reservations()
    today = now_colombia().date().isoformat()
    pqrs_items = Pqrs.query.filter(
        Pqrs.status == "resuelta",
        Pqrs.is_archived.is_(False),
    ).all()
    reservations = Reservation.query.filter(
        Reservation.is_archived.is_(False),
        db.or_(
            Reservation.status.in_(("rechazada", "cancelada")),
            Reservation.date < today,
        ),
    ).all()
    archived_at = now_colombia()
    for pqrs in pqrs_items:
        pqrs.is_archived = True
        pqrs.archived_at = archived_at
    for reservation in reservations:
        reservation.is_archived = True
        reservation.archived_at = archived_at

    archived_pqrs = len(pqrs_items)
    archived_reservations = len(reservations)
    _add_audit_log(
        "history_archive",
        None,
        "archived",
        {
            "archivedPqrsCount": archived_pqrs,
            "archivedReservationsCount": archived_reservations,
        },
    )
    db.session.commit()
    workbook_bytes, _ = generate_legal_report_xlsx()
    return jsonify({
        "message": (
            f"Se archivaron {archived_pqrs} PQRS y {archived_reservations} "
            "reservas en el expediente Excel."
        ),
        "archivedPqrsCount": archived_pqrs,
        "archivedReservationsCount": archived_reservations,
        "fileName": f"Archivo_Historico_DOMUX_{now_colombia().date().isoformat()}.xlsx",
        "mimeType": MIME_XLSX,
        "base64": base64.b64encode(workbook_bytes).decode("ascii"),
    })


def _json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, error_response(400, "El cuerpo de la solicitud debe ser un objeto JSON válido.")
    message = validate_no_empty_strings(data)
    if message:
        return None, error_response(400, message)
    if "mediaUrl" in data and (
        media_error := validate_media_url(data["mediaUrl"])
    ):
        return None, error_response(400, media_error)
    return data, None


def _media_and_event_error(data, date_key, time_key):
    error = validate_media_fields(data)
    if error:
        return error
    event_date = data.get(date_key)
    if event_date is not None and (error := validate_iso_date(event_date)):
        return error
    if event_date is not None and event_date < now_colombia().date().isoformat():
        return "La fecha del evento no puede ser anterior a hoy."
    event_time = data.get(time_key)
    if event_time is not None and (error := validate_time(event_time)):
        return error
    return None


def _is_social_hall(area_name):
    normalized_name = unicodedata.normalize("NFD", area_name or "")
    normalized_name = "".join(
        character for character in normalized_name
        if not unicodedata.combining(character)
    ).casefold()
    return "salon" in normalized_name


def _special_reservation_slot_error(area, time_slot):
    if time_slot in EXTENDED_TIME_SLOTS and (
        area is None or not _is_social_hall(area.name)
    ):
        return "El día completo o media jornada es exclusivo del Salón Social."
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
    notify_role(
        "GUARD",
        "Nuevo anuncio publicado",
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
    include_archived, error = parse_optional_bool(
        request.args.get("includeArchived"), "includeArchived"
    )
    if error:
        return error_response(400, error)
    if include_archived is not True:
        query = query.filter(Pqrs.is_archived.is_(False))
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
    resident_id = request.args.get("residentId", type=int)
    if resident_id is not None:
        if user.role != "ADMIN":
            return error_response(403, "Solo administración puede consultar PQRS por residente.")
        resident = db.session.get(User, resident_id)
        if resident_id <= 0 or resident is None or resident.role != "RESIDENT":
            return error_response(404, "Residente no encontrado.")
        query = query.filter(Pqrs.resident_id == resident_id)
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
    if error := validate_media_fields(data):
        return error_response(400, error)
    incident_date = data.get("incidentDate")
    if incident_date is not None:
        if error := validate_iso_date(incident_date):
            return error_response(400, error)
        if incident_date > now_colombia().date().isoformat():
            return error_response(400, "La fecha del incidente no puede ser futura.")
    incident_time = data.get("incidentTime")
    if incident_time is not None and (error := validate_time(incident_time)):
        return error_response(400, error)
    if g.current_user.role not in ("RESIDENT", "ADMIN"):
        return error_response(403, "No tienes permiso para crear PQRS")
    resident = _resident_for_write(data)
    if resident is None:
        return error_response(400, "Selecciona un residente válido")
    if (
        g.current_user.role == "RESIDENT"
        and g.current_user.is_minor
        and not g.current_user.parental_consent
    ):
        return error_response(
            403,
            "Las cuentas de menores de edad sin autorización parental están en modo consulta y no pueden radicar PQRS.",
        )
    if g.current_user.role == "RESIDENT":
        active_pqrs_count = Pqrs.query.filter(
            Pqrs.resident_id == resident.id,
            Pqrs.status.in_(("abierta", "en_proceso")),
            Pqrs.is_archived.is_(False),
        ).count()
        if active_pqrs_count >= 3:
            return error_response(
                409,
                "Límite alcanzado: ya tienes 3 PQRS activas en trámite. Espera a que sean resueltas.",
            )
    category = data.get("category", "Petición")
    if not isinstance(category, str):
        return error_response(400, "La categoría debe ser texto")

    pqrs = Pqrs(
        resident_id=resident.id,
        created_by_admin_id=g.current_user.id if g.current_user.role == "ADMIN" else None,
        category=category.strip(),
        subject=data["subject"].strip(),
        message=data["message"].strip(),
        incident_date=incident_date,
        incident_time=incident_time,
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
    notify_admins(
        "Nueva PQRS",
        f"{resident.full_name} registró la PQRS '{pqrs.subject}'.",
        "pqrs",
    )
    if g.current_user.role == "ADMIN":
        notify_user(
            resident.id,
            "Nueva PQRS registrada",
            f"Administración registró una PQRS a tu nombre: {pqrs.subject}.",
            "pqrs",
        )
    _add_audit_log("PQRS", pqrs.id, "created")
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
        pqrs.updated_at = now_colombia()
    pqrs.conversation.append(PqrsMessage(
        author_id=g.current_user.id,
        author_role="ADMIN",
        message=response_text.strip(),
        media_url=data.get("mediaUrl"),
        media_type=data.get("mediaType"),
    ))
    _add_audit_log(
        "PQRS",
        pqrs.id,
        "responded",
        {"status": pqrs.status},
    )
    if previous_status != pqrs.status:
        _add_audit_log(
            "PQRS",
            pqrs.id,
            "status_changed",
            {"previousStatus": previous_status, "status": pqrs.status},
        )
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
        pqrs.updated_at = now_colombia()
    pqrs.conversation.append(PqrsMessage(
        author_id=g.current_user.id,
        author_role="RESIDENT",
        message=message.strip() if message and message.strip() else None,
        media_url=data.get("mediaUrl"),
        media_type=data.get("mediaType"),
    ))
    _add_audit_log("PQRS", pqrs.id, "responded")
    if was_resolved:
        _add_audit_log(
            "PQRS",
            pqrs.id,
            "status_changed",
            {"previousStatus": "resuelta", "status": "abierta"},
        )
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
    rated_this_cycle.created_at = now_colombia()
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
            pqrs.updated_at = now_colombia()
        pqrs.conversation.append(PqrsMessage(
            author_id=g.current_user.id,
            author_role="ADMIN",
            message=message.strip(),
            media_url=data.get("mediaUrl"),
            media_type=data.get("mediaType"),
        ))
        _add_audit_log("PQRS", pqrs.id, "responded", {"status": status})
        if previous_status != status:
            _add_audit_log(
                "PQRS",
                pqrs.id,
                "status_changed",
                {"previousStatus": previous_status, "status": status},
            )
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
    finalize_expired_reservations()
    user = g.current_user
    if user.role == "ADMIN":
        query = Reservation.query
    elif user.role == "RESIDENT":
        query = Reservation.query.filter_by(resident_id=user.id)
    else:
        return error_response(403, "No tienes permiso para ver las reservas")
    include_archived, error = parse_optional_bool(
        request.args.get("includeArchived"), "includeArchived"
    )
    if error:
        return error_response(400, error)
    if include_archived is not True:
        query = query.filter(Reservation.is_archived.is_(False))
    items = query.order_by(Reservation.created_at.desc()).all()
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

    finalize_expired_reservations()
    slots = reservation_availability(common_area_id, date)
    return jsonify({
        "commonAreaId": common_area_id,
        "date": date,
        **slots,
    })


@bp.get("/reservations/calendar")
@token_required
def get_reservation_calendar():
    common_area_id = request.args.get("commonAreaId", type=int)
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    if common_area_id is None or year is None or month is None:
        return error_response(400, "commonAreaId, year y month son obligatorios.")
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        return error_response(400, "El mes o año del calendario no es válido.")
    if db.session.get(CommonArea, common_area_id) is None:
        return error_response(404, "Zona común no encontrada.")
    finalize_expired_reservations()
    prefix = f"{year:04d}-{month:02d}-"
    rows = db.session.query(Reservation.date, Reservation.time_slot).filter(
        Reservation.common_area_id == common_area_id,
        Reservation.date.like(f"{prefix}%"),
        Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
        Reservation.is_archived.is_(False),
    ).all()
    slots_by_date = {}
    for reservation_date, time_slot in rows:
        slots_by_date.setdefault(reservation_date, []).append(time_slot)
    blocked_dates = [
        reservation_date
        for reservation_date, occupied_slots in slots_by_date.items()
        if all(
            any(time_slots_overlap(slot, occupied) for occupied in occupied_slots)
            for slot in STANDARD_TIME_SLOTS
        )
    ]
    return jsonify({
        "commonAreaId": common_area_id,
        "year": year,
        "month": month,
        "blockedDates": blocked_dates,
    })


@bp.post("/reservations")
@token_required
@role_required("RESIDENT", "ADMIN")
def create_reservation():
    data, failure = _json_body()
    if failure:
        return failure
    if g.current_user.role not in ("RESIDENT", "ADMIN"):
        return error_response(403, "No tienes permiso para crear reservas")
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
    booking_date = date.fromisoformat(data["date"])
    max_advance_days = 60 if _is_social_hall(area.name) else 30
    if (
        g.current_user.role == "RESIDENT"
        and booking_date > now_colombia().date() + timedelta(days=max_advance_days)
    ):
        return error_response(
            400,
            f"Las reservas para esta zona solo pueden realizarse con máximo "
            f"{max_advance_days} días de anticipación.",
        )
    if error := validate_time_slot(data["timeSlot"]):
        return error_response(400, error)
    if error := _special_reservation_slot_error(area, data["timeSlot"]):
        return error_response(400, error)
    message = data.get("message")
    if message is not None and not isinstance(message, str):
        return error_response(400, "El mensaje debe ser texto.")
    if error := validate_media_fields(data):
        return error_response(400, error)
    resident = _resident_for_write(data)
    if resident is None:
        return error_response(400, "Selecciona un residente válido")
    if (
        g.current_user.role == "RESIDENT"
        and g.current_user.is_minor
        and not g.current_user.parental_consent
    ):
        return error_response(
            403,
            "Los menores de edad requieren autorización parental registrada por administración para solicitar reservas.",
        )
    finalize_expired_reservations()
    is_admin = g.current_user.role == "ADMIN"
    if not is_admin:
        pending_count = Reservation.query.filter(
            Reservation.resident_id == resident.id,
            Reservation.status == "pendiente_pago",
            Reservation.is_archived.is_(False),
        ).count()
        if pending_count >= 2:
            return error_response(
                409,
                "Ya tienes 2 reservas pendientes de pago. Confirma el pago antes de crear otra.",
            )
    if reservation_conflicts(area.id, data["date"], data["timeSlot"]):
        return error_response(409, "Ese horario ya no está disponible")

    try:
        payment_already_received = parse_bool(
            data.get("paymentAlreadyReceived"), default=False
        )
    except ValueError:
        return error_response(400, "paymentAlreadyReceived debe ser verdadero o falso.")
    approved_immediately = is_admin and payment_already_received
    reservation = Reservation(
        resident_id=resident.id,
        created_by_admin_id=g.current_user.id if is_admin else None,
        common_area_id=area.id,
        date=data["date"],
        time_slot=data["timeSlot"],
        status="aprobada" if approved_immediately else "pendiente_pago",
        payment_deadline=(
            None if approved_immediately else now_colombia() + timedelta(hours=4)
        ),
    )
    db.session.add(reservation)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        if reservation_conflicts(area.id, data["date"], data["timeSlot"]):
            return error_response(409, "Ese horario ya no está disponible")
        raise
    if (message and message.strip()) or data.get("mediaUrl"):
        reservation.messages.append(ReservationMessage(
            author_id=g.current_user.id,
            author_role=g.current_user.role,
            message=message.strip() if message and message.strip() else None,
            media_url=data.get("mediaUrl"),
            media_type=data.get("mediaType"),
        ))
    if is_admin:
        notify_user(
            resident.id,
            "Reserva registrada por administración",
            f"Administración creó una reserva para {area.name} el {reservation.date} "
            f"de {reservation.time_slot}.",
            "reservation",
        )
    notify_admins(
        "Nueva solicitud de reserva",
        (
            f"Administración registró {area.name} para {resident.full_name} "
            f"el {reservation.date} de {reservation.time_slot}."
            if is_admin else
            f"{resident.full_name} solicitó {area.name} el {reservation.date} "
            f"de {reservation.time_slot}."
        ),
        "reservation",
    )
    _add_audit_log("RESERVATION", reservation.id, "created")
    if approved_immediately:
        _add_audit_log(
            "RESERVATION",
            reservation.id,
            "payment_received",
            {"status": "aprobada"},
        )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if reservation_conflicts(area.id, data["date"], data["timeSlot"]):
            return error_response(409, "Ese horario ya no está disponible")
        raise
    return jsonify({"message": "Reserva creada", "reservation": reservation.to_dict()}), 201


@bp.post("/reservations/<int:res_id>/confirm-payment")
@token_required
@role_required("ADMIN")
def confirm_reservation_payment(res_id):
    finalize_expired_reservations()
    reservation = db.session.get(Reservation, res_id)
    if reservation is None:
        return error_response(404, "Reserva no encontrada.")
    if reservation.status != "pendiente_pago":
        return error_response(400, "Solo se puede confirmar el pago de una reserva pendiente.")
    if reservation_conflicts(
        reservation.common_area_id,
        reservation.date,
        reservation.time_slot,
        exclude_id=reservation.id,
    ):
        return error_response(409, "Ese horario ya no está disponible.")

    reservation.status = "aprobada"
    reservation.payment_deadline = None
    reservation.payment_reminder_sent = False
    _add_audit_log(
        "RESERVATION",
        reservation.id,
        "payment_confirmed",
        {"status": "aprobada"},
    )
    notify_user(
        reservation.resident_id,
        "Pago de reserva confirmado",
        "Administración confirmó el pago de tu reserva.",
        "reservation",
    )
    db.session.commit()
    return jsonify({
        "message": "Pago de reserva confirmado.",
        "reservation": reservation.to_dict(),
    })


@bp.post("/reservations/<int:res_id>/extend-payment")
@token_required
@role_required("ADMIN")
def extend_reservation_payment(res_id):
    finalize_expired_reservations()
    reservation = db.session.get(Reservation, res_id)
    if reservation is None:
        return error_response(404, "Reserva no encontrada.")
    if reservation.status != "pendiente_pago":
        return error_response(400, "Solo se puede extender el pago de una reserva pendiente.")

    now = now_colombia()
    deadline = reservation.payment_deadline or now
    if deadline.tzinfo:
        deadline = deadline.astimezone(COLOMBIA_TIMEZONE).replace(tzinfo=None)
    reservation.payment_deadline = max(now, deadline) + timedelta(hours=4)
    reservation.payment_reminder_sent = False
    notify_user(
        reservation.resident_id,
        "Plazo de pago extendido",
        "Administración extendió 4 horas el plazo de pago de tu reserva.",
        "reservation",
    )
    db.session.commit()
    return jsonify({
        "message": "Plazo de pago extendido 4 horas.",
        "reservation": reservation.to_dict(),
    })


@bp.post("/reservations/<int:res_id>/release")
@token_required
@role_required("ADMIN")
def release_reservation(res_id):
    finalize_expired_reservations()
    reservation = db.session.get(Reservation, res_id)
    if reservation is None:
        return error_response(404, "Reserva no encontrada.")
    if reservation.status != "pendiente_pago":
        return error_response(400, "Solo se puede liberar una reserva pendiente de pago.")

    reservation.status = "cancelada"
    reservation.payment_deadline = None
    reservation.payment_reminder_sent = False
    notify_user(
        reservation.resident_id,
        "Reserva liberada",
        "Administración liberó el horario de tu reserva.",
        "reservation",
    )
    db.session.commit()
    return jsonify({
        "message": "Reserva liberada.",
        "reservation": reservation.to_dict(),
    })


@bp.put("/reservations/<int:res_id>/status")
@token_required
@role_required("ADMIN")
def update_reservation_status(res_id):
    data, failure = _json_body()
    if failure:
        return failure
    status = data.get("status")
    if status not in ("aprobada", "rechazada"):
        return error_response(400, "El estado debe ser 'aprobada' o 'rechazada'.")
    finalize_expired_reservations()
    reservation = db.session.get(Reservation, res_id)
    if reservation is None:
        return error_response(404, "Reserva no encontrada")
    if reservation.status not in ("pendiente", "activa"):
        return error_response(400, "Solo puedes aprobar o rechazar reservas pendientes.")
    if status in ACTIVE_RESERVATION_STATUSES:
        if error := _special_reservation_slot_error(
            reservation.common_area, reservation.time_slot
        ):
            return error_response(400, error)
    if status in ACTIVE_RESERVATION_STATUSES and reservation_conflicts(
        reservation.common_area_id,
        reservation.date,
        reservation.time_slot,
        exclude_id=reservation.id,
    ):
        return error_response(409, "Ese horario ya no está disponible")

    previous_status = reservation.status
    reservation.status = status
    if previous_status != status:
        _add_audit_log(
            "RESERVATION",
            reservation.id,
            "status_changed",
            {"previousStatus": previous_status, "status": status},
        )
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


@bp.post("/reservations/<int:res_id>/messages")
@token_required
@role_required("RESIDENT")
def add_reservation_message(res_id):
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

    finalize_expired_reservations()
    reservation = db.session.get(Reservation, res_id)
    if reservation is None:
        return error_response(404, "Reserva no encontrada.")
    if g.current_user.role == "RESIDENT" and reservation.resident_id != g.current_user.id:
        return error_response(403, "Solo puedes escribir en tus propias reservas.")
    if reservation.status in ("rechazada", "cancelada"):
        return error_response(400, "No se puede continuar una conversación de una reserva finalizada.")

    reservation.messages.append(ReservationMessage(
        author_id=g.current_user.id,
        author_role=g.current_user.role,
        message=message.strip() if message and message.strip() else None,
        media_url=data.get("mediaUrl"),
        media_type=data.get("mediaType"),
    ))
    _add_audit_log("RESERVATION", reservation.id, "responded")
    if g.current_user.role == "ADMIN":
        notify_user(
            reservation.resident_id,
            "Respuesta sobre tu reserva",
            f"Administración respondió sobre la reserva de "
            f"{reservation.common_area.name if reservation.common_area else 'la zona común'}.",
            "reservation",
        )
    else:
        for admin in User.query.filter_by(role="ADMIN", is_active=True).all():
            notify_user(
                admin.id,
                "Nuevo mensaje de reserva",
                f"{g.current_user.full_name} envió un mensaje sobre una reserva "
                f"de {reservation.common_area.name if reservation.common_area else 'una zona común'}.",
                "reservation",
            )
    db.session.commit()
    return jsonify({
        "message": "Mensaje agregado a la reserva.",
        "reservation": reservation.to_dict(),
    }), 201


@bp.put("/reservations/<int:res_id>/cancel")
@token_required
@role_required("RESIDENT", "ADMIN")
def cancel_reservation(res_id):
    finalize_expired_reservations()
    reservation = db.session.get(Reservation, res_id)
    if reservation is None:
        return error_response(404, "Reserva no encontrada")
    if g.current_user.role == "RESIDENT" and reservation.resident_id != g.current_user.id:
        return error_response(403, "Esa reserva no es tuya")
    if reservation.status not in (
        "pendiente_pago", "pendiente", "activa", "aprobada"
    ):
        return error_response(400, "Solo se pueden cancelar reservas pendientes o aprobadas.")
    if g.current_user.role == "RESIDENT" and reservation.date <= now_colombia().date().isoformat():
        return error_response(400, "Solo puedes cancelar la reserva antes del día reservado.")
    previous_status = reservation.status
    reservation.status = "cancelada"
    if previous_status == "pendiente_pago":
        reservation.payment_deadline = None
        reservation.payment_reminder_sent = False
    _add_audit_log(
        "RESERVATION",
        reservation.id,
        "status_changed",
        {"previousStatus": previous_status, "status": reservation.status},
    )
    if g.current_user.role == "RESIDENT":
        for admin in User.query.filter_by(role="ADMIN", is_active=True).all():
            notify_user(
                admin.id,
                "Reserva cancelada por residente",
                f"{g.current_user.full_name} canceló la reserva de "
                f"{reservation.common_area.name if reservation.common_area else 'la zona común'} "
                f"del {reservation.date}.",
                "reservation",
            )
    else:
        notify_user(
            reservation.resident_id,
            "Reserva cancelada",
            "Administración canceló tu reserva.",
            "reservation",
        )
    db.session.commit()
    return jsonify({"message": "Reserva cancelada", "reservation": reservation.to_dict()})
