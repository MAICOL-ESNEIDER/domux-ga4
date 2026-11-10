import base64
from datetime import date, timedelta

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
    ReservationMessage,
    User,
)
from services.audit_service import add_audit_log
from services.notification_service import notify_residents, notify_user
from services.excel_service import (
    MIME_XLSX,
    generate_legal_report_xlsx,
)
from services.reservation_service import (
    ACTIVE_RESERVATION_STATUSES,
    reservation_availability,
    reservation_conflicts,
)
from validators import (
    VALID_PQRS_STATUSES,
    VALID_TIME_SLOTS,
    parse_optional_bool,
    require_non_empty_fields,
    validate_future_or_today_date,
    validate_iso_date,
    validate_media_fields,
    validate_no_empty_strings,
    validate_time,
    validate_time_slot,
)
from time_utils import colombia_today, utc_now

bp = Blueprint("community", __name__, url_prefix="/api")


@bp.post("/admin/archive-history")
@token_required
@role_required("ADMIN")
def archive_history():
    today = colombia_today().isoformat()
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
    archived_at = utc_now()
    for pqrs in pqrs_items:
        pqrs.is_archived = True
        pqrs.archived_at = archived_at
    for reservation in reservations:
        reservation.is_archived = True
        reservation.archived_at = archived_at

    archived_pqrs = len(pqrs_items)
    archived_reservations = len(reservations)
    add_audit_log(
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
        "fileName": f"Archivo_Historico_DOMUX_{colombia_today().isoformat()}.xlsx",
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
@role_required("ADMIN", "GUARD", "RESIDENT")
def get_announcements():
    """Lista los comunicados publicados, del más nuevo al más antiguo.

    Los retirados no salen en la lista, pero siguen guardados en la base.
    """
    items = (
        Announcement.query.filter(Announcement.retired_at.is_(None))
        .order_by(Announcement.created_at.desc())
        .all()
    )
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


def _retire_announcement(announcement_id):
    """Retira un comunicado sin borrarlo (TT-029, DEC-090 y ADR-013).

    Guarda cuándo y quién lo retiró y lo anota en el registro de auditoría.
    Deja de verse en la app, pero la fila queda en la base para el historial.
    """
    announcement = db.session.get(Announcement, announcement_id)
    if announcement is None:
        return error_response(404, "Anuncio no encontrado")
    if announcement.is_retired:
        return error_response(409, "El anuncio ya estaba retirado.")
    announcement.retire(g.current_user)
    add_audit_log("announcement", announcement.id, "retired", {"title": announcement.title})
    db.session.commit()
    return jsonify({
        "message": "Anuncio retirado. Ya no se ve en la app, pero queda guardado.",
        "announcement": announcement.to_dict(),
    })


@bp.put("/announcements/<int:announcement_id>/retire")
@token_required
@role_required("ADMIN")
def retire_announcement(announcement_id):
    """Retira un comunicado (API-COM-04). Solo la administración."""
    return _retire_announcement(announcement_id)


@bp.delete("/announcements/<int:announcement_id>")
@token_required
@role_required("ADMIN")
def delete_announcement(announcement_id):
    """Ruta anterior para quitar un comunicado: ahora también lo retira.

    Se deja para que las versiones viejas de la app sigan funcionando; ya no
    borra nada. La ruta nueva es PUT /api/announcements/<id>/retire.
    """
    return _retire_announcement(announcement_id)


@bp.get("/pqrs")
@token_required
@role_required("ADMIN", "RESIDENT")
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
@role_required("RESIDENT", "ADMIN")
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
    add_audit_log("PQRS", pqrs.id, "created")
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
        pqrs.updated_at = utc_now()
    pqrs.conversation.append(PqrsMessage(
        author_id=g.current_user.id,
        author_role="ADMIN",
        message=response_text.strip(),
        media_url=data.get("mediaUrl"),
        media_type=data.get("mediaType"),
    ))
    add_audit_log(
        "PQRS",
        pqrs.id,
        "responded",
        {"status": pqrs.status},
    )
    if previous_status != pqrs.status:
        add_audit_log(
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
        pqrs.updated_at = utc_now()
    pqrs.conversation.append(PqrsMessage(
        author_id=g.current_user.id,
        author_role="RESIDENT",
        message=message.strip() if message and message.strip() else None,
        media_url=data.get("mediaUrl"),
        media_type=data.get("mediaType"),
    ))
    add_audit_log("PQRS", pqrs.id, "responded")
    if was_resolved:
        add_audit_log(
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
    rated_this_cycle.created_at = utc_now()
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
            pqrs.updated_at = utc_now()
        pqrs.conversation.append(PqrsMessage(
            author_id=g.current_user.id,
            author_role="ADMIN",
            message=message.strip(),
            media_url=data.get("mediaUrl"),
            media_type=data.get("mediaType"),
        ))
        add_audit_log("PQRS", pqrs.id, "responded", {"status": status})
        if previous_status != status:
            add_audit_log(
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
@role_required("ADMIN", "GUARD", "RESIDENT")
def get_common_areas():
    areas = CommonArea.query.order_by(CommonArea.name).all()
    return jsonify({"areas": [area.to_dict() for area in areas]})


@bp.get("/reservations")
@token_required
@role_required("ADMIN", "RESIDENT")
def get_reservations():
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
@role_required("ADMIN", "GUARD", "RESIDENT")
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


@bp.get("/reservations/calendar")
@token_required
@role_required("ADMIN", "GUARD", "RESIDENT")
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
    prefix = f"{year:04d}-{month:02d}-"
    rows = db.session.query(
        Reservation.date,
        db.func.count(db.func.distinct(Reservation.time_slot)),
    ).filter(
        Reservation.common_area_id == common_area_id,
        Reservation.date.like(f"{prefix}%"),
        Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
    ).group_by(Reservation.date).having(
        db.func.count(db.func.distinct(Reservation.time_slot)) >= len(VALID_TIME_SLOTS)
    ).all()
    return jsonify({
        "commonAreaId": common_area_id,
        "year": year,
        "month": month,
        "blockedDates": [reservation_date for reservation_date, _ in rows],
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
    if error := validate_time_slot(data["timeSlot"]):
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
    if g.current_user.role == "RESIDENT":
        active_statuses = ("pendiente", "activa", "aprobada")
        daily_reservation = Reservation.query.filter(
            Reservation.resident_id == resident.id,
            Reservation.date == data["date"],
            Reservation.status.in_(active_statuses),
            Reservation.is_archived.is_(False),
        ).first()
        if daily_reservation is not None:
            return error_response(
                409,
                "Límite diario alcanzado: solo puedes tener 1 reserva activa o pendiente por día.",
            )
        requested_date = date.fromisoformat(data["date"])
        week_start = requested_date - timedelta(days=requested_date.weekday())
        week_end = week_start + timedelta(days=6)
        weekly_reservation_count = Reservation.query.filter(
            Reservation.resident_id == resident.id,
            Reservation.date.between(week_start.isoformat(), week_end.isoformat()),
            Reservation.status.in_(active_statuses),
            Reservation.is_archived.is_(False),
        ).count()
        if weekly_reservation_count >= 2:
            return error_response(
                409,
                "Límite semanal alcanzado: máximo 2 reservas por semana para permitir el uso equitativo de las zonas comunes.",
            )
    if reservation_conflicts(area.id, data["date"], data["timeSlot"]):
        return error_response(409, "Ese horario ya no está disponible")

    reservation = Reservation(
        resident_id=resident.id,
        created_by_admin_id=g.current_user.id if g.current_user.role == "ADMIN" else None,
        common_area_id=area.id,
        date=data["date"],
        time_slot=data["timeSlot"],
        status="pendiente",
    )
    db.session.add(reservation)
    if (message and message.strip()) or data.get("mediaUrl"):
        reservation.messages.append(ReservationMessage(
            author_id=g.current_user.id,
            author_role=g.current_user.role,
            message=message.strip() if message and message.strip() else None,
            media_url=data.get("mediaUrl"),
            media_type=data.get("mediaType"),
        ))
    if g.current_user.role == "ADMIN":
        notify_user(
            resident.id,
            "Reserva registrada por administración",
            f"Administración creó una reserva para {area.name} el {reservation.date} "
            f"de {reservation.time_slot}.",
            "reservation",
        )
    else:
        for admin in User.query.filter_by(role="ADMIN", is_active=True).all():
            notify_user(
                admin.id,
                "Nueva solicitud de reserva",
                f"{resident.full_name} solicitó {area.name} el {reservation.date} "
                f"de {reservation.time_slot}.",
                "reservation",
            )
    add_audit_log("RESERVATION", reservation.id, "created")
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
    if status not in ("aprobada", "rechazada"):
        return error_response(400, "El estado debe ser 'aprobada' o 'rechazada'.")
    reservation = db.session.get(Reservation, res_id)
    if reservation is None:
        return error_response(404, "Reserva no encontrada")
    if reservation.status not in ("pendiente", "activa"):
        return error_response(400, "Solo puedes aprobar o rechazar reservas pendientes.")
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
        add_audit_log(
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
@role_required("RESIDENT", "ADMIN")
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
    add_audit_log("RESERVATION", reservation.id, "responded")
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
    reservation = db.session.get(Reservation, res_id)
    if reservation is None:
        return error_response(404, "Reserva no encontrada")
    if g.current_user.role == "RESIDENT" and reservation.resident_id != g.current_user.id:
        return error_response(403, "Esa reserva no es tuya")
    if reservation.status not in ("pendiente", "activa", "aprobada"):
        return error_response(400, "Solo se pueden cancelar reservas pendientes o aprobadas.")
    if g.current_user.role == "RESIDENT" and reservation.date <= colombia_today().isoformat():
        return error_response(400, "Solo puedes cancelar la reserva antes del día reservado.")
    previous_status = reservation.status
    reservation.status = "cancelada"
    add_audit_log(
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
