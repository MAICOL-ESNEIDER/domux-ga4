import base64
from datetime import date

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from auth import role_required, token_required
from errors import ApiError, error_response
from extensions import db
from models import (
    ANNOUNCEMENT_CATEGORIES,
    Announcement,
    CommonArea,
    Pqrs,
    PqrsMessage,
    PqrsSatisfaction,
    Reservation,
    ReservationMessage,
    User,
)
from routes.common import bool_arg, json_body, json_object, page_args, save_changes
from services.announcement_service import (
    announcement_payloads,
    archived_only,
    current_only,
    mark_as_read,
    parse_category,
    parse_expiry,
    parse_tower_id,
    unread_count,
    unread_only,
    visible_announcements,
)
from services.audit_service import add_audit_log
from services import pqrs_service
from services.notification_service import notify_residents, notify_user
from services.excel_service import (
    MIME_XLSX,
    generate_legal_report_xlsx,
)
from services.reservation_service import (
    ACTIVE_RESERVATION_STATUSES,
    LIMIT_RESERVATION_STATUSES,
    month_calendar,
    reservation_availability,
    reservation_conflicts,
    weekly_reservation_count,
)
from services.zone_rules import (
    days_text,
    human_date,
    is_maintenance_day,
    parse_zone_rules,
    WEEKDAY_NAMES,
)
from validators import (
    VALID_PQRS_STATUSES,
    parse_optional_bool,
    require_non_empty_fields,
    validate_future_or_today_date,
    validate_iso_date,
    validate_media_fields,
    validate_time,
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
    """Lista los comunicados, del más nuevo al más antiguo, de a 50 por página.

    Por defecto salen los vigentes; con ``archived=true``, los que ya pasaron su
    fecha de vencimiento (HU-060). Un residente solo ve los de toda la unidad y los
    de su torre (HU-061), y puede pedir solo los que no ha leído con ``unread=true``
    (HU-059). Se puede filtrar por ``category``. Los retirados no salen, pero siguen
    guardados en la base. ``unreadCount`` dice cuántos vigentes le faltan por leer.
    """
    user = g.current_user
    archived = bool_arg("archived")
    query = visible_announcements(user)
    query = archived_only(query) if archived else current_only(query)
    if request.args.get("category"):
        query = query.filter(Announcement.category == parse_category(request.args["category"]))
    if user.role == "RESIDENT" and bool_arg("unread"):
        query = unread_only(query, user)
    page, size = page_args(default_size=50, max_size=200)
    total = query.count()
    items = (
        query.order_by(Announcement.created_at.desc(), Announcement.id.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return jsonify({
        "announcements": announcement_payloads(items, user),
        "page": page,
        "pageSize": size,
        "total": total,
        "totalPages": (total + size - 1) // size,
        "unreadCount": unread_count(user),
    })


@bp.post("/announcements")
@token_required
@role_required("ADMIN")
def create_announcement():
    data, failure = json_body()
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
    category = parse_category(data.get("category"))
    tower_id = parse_tower_id(data.get("towerId"))
    expires_at = parse_expiry(data.get("expiresAt"))

    announcement = Announcement(
        title=data["title"].strip(),
        message=data["message"].strip(),
        category=category,
        tower_id=tower_id,
        expires_at=expires_at,
        event_date=data.get("eventDate"),
        event_time=data.get("eventTime"),
        media_url=data.get("mediaUrl"),
        media_type=data.get("mediaType"),
        author_id=g.current_user.id,
    )
    db.session.add(announcement)
    notify_residents(
        "Anuncio urgente" if category == "urgente" else "Nuevo anuncio",
        f"{ANNOUNCEMENT_CATEGORIES[category]}: {announcement.title}",
        "announcement",
        tower_id=tower_id,
    )
    db.session.commit()
    return jsonify({
        "message": "Anuncio publicado",
        "announcement": announcement_payloads([announcement], g.current_user)[0],
    }), 201


@bp.post("/announcements/<int:announcement_id>/read")
@token_required
@role_required("RESIDENT")
def read_announcement(announcement_id):
    """Marca el comunicado como leído por el residente que lo abrió (HU-059).

    Se puede llamar más de una vez: la lectura se anota una sola vez. Un comunicado
    que el residente no puede ver (de otra torre o retirado) responde 404.
    """
    announcement = visible_announcements(g.current_user).filter(
        Announcement.id == announcement_id
    ).first()
    if announcement is None:
        raise ApiError("Anuncio no encontrado", 404)
    mark_as_read(g.current_user, announcement)
    try:
        db.session.commit()
    except IntegrityError:
        # Otra solicitud lo marcó al mismo tiempo: ya quedó leído.
        db.session.rollback()
    return jsonify({
        "message": "Anuncio marcado como leído",
        "announcement": announcement_payloads([announcement], g.current_user)[0],
        "unreadCount": unread_count(g.current_user),
    })


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
        "announcement": announcement_payloads([announcement], g.current_user)[0],
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
    """Las PQRS del residente, o todas las de la unidad si quien consulta es la administración.

    Sin parámetros entrega la lista completa de siempre (con conversación y adjuntos), que es la que
    usa la app. Con ``view=summary`` entrega la lista liviana de la bandeja de la web: sin
    conversación ni adjuntos, paginada (``page`` y ``pageSize``) y con las más urgentes primero.
    Con ``semaphore=verde|amarillo|rojo`` deja solo las que están en curso con ese color de plazo.
    """
    user = g.current_user
    view = pqrs_service.parse_view(request.args.get("view"))
    semaphore = pqrs_service.parse_semaphore(request.args.get("semaphore"))
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
            Pqrs.radicado.ilike(pattern),
            Pqrs.subject.ilike(pattern),
            Pqrs.message.ilike(pattern),
            Pqrs.category.ilike(pattern),
            User.name.ilike(pattern),
            User.last_name.ilike(pattern),
            (User.name + " " + User.last_name).ilike(pattern),
            User.apartment.ilike(pattern),
        ))
    if semaphore is not None:
        query = pqrs_service.filter_by_semaphore(query, semaphore)
    if view is not None:
        page, size = page_args(default_size=25, max_size=100)
        return jsonify(pqrs_service.summary_page(query, page, size))
    items = query.order_by(Pqrs.created_at.desc()).all()
    return jsonify({"pqrs": [item.to_dict() for item in items]})


@bp.get("/pqrs/<int:pqrs_id>")
@token_required
@role_required("ADMIN", "RESIDENT")
def get_pqrs_item(pqrs_id):
    """Una PQRS con su conversación. Un residente solo ve las suyas.

    Con ``view=summary`` va sin el contenido de los adjuntos (solo dice cuáles mensajes los tienen),
    para que la web no cargue fotos que no va a mostrar en esa página.
    """
    view = pqrs_service.parse_view(request.args.get("view"))
    pqrs = db.session.get(Pqrs, pqrs_id)
    if pqrs is None or (g.current_user.role == "RESIDENT" and pqrs.resident_id != g.current_user.id):
        raise ApiError("PQRS no encontrada", 404)
    data = pqrs_service.detail_dict(pqrs) if view is not None else pqrs.to_dict()
    return jsonify({"pqrs": data})


@bp.post("/pqrs")
@token_required
@role_required("RESIDENT", "ADMIN")
def create_pqrs():
    data, failure = json_body()
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
    data, failure = json_body()
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
    data, failure = json_body()
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
    data, failure = json_body()
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
    data, failure = json_body()
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
    """Las zonas comunes con sus reglas de reserva (horario, franjas, aforo, plazos...)."""
    areas = CommonArea.query.order_by(CommonArea.name).all()
    return jsonify({"areas": [area.to_dict() for area in areas]})


@bp.put("/common-areas/<int:area_id>/rules")
@token_required
@role_required("ADMIN")
def update_common_area_rules(area_id):
    """Cambia las reglas de una zona común (HU-055, RN-022). Solo la administración.

    Solo se cambian los datos que vienen en la solicitud. Las reservas nuevas usan
    las reglas desde ese momento; las que ya existen no se tocan.
    """
    data = json_object(required=True)
    area = db.session.get(CommonArea, area_id)
    if area is None:
        raise ApiError("Zona común no encontrada", 404)
    changes = parse_zone_rules(data, area)
    before = {column: getattr(area, column) for column in changes}
    for column, value in changes.items():
        setattr(area, column, value)
    add_audit_log(
        "common_area", area.id, "rules_changed", {"before": before, "after": changes}
    )
    save_changes()
    return jsonify({"message": "Reglas de la zona actualizadas", "area": area.to_dict()})


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
    """Franjas libres y ocupadas de una zona en un día, según el horario de la zona."""
    common_area_id = request.args.get("commonAreaId", type=int)
    day = request.args.get("date")
    if common_area_id is None or not day:
        return error_response(400, "commonAreaId y date son obligatorios")
    if error := validate_future_or_today_date(day):
        return error_response(400, error)
    area = db.session.get(CommonArea, common_area_id)
    if area is None:
        return error_response(404, "Zona común no encontrada")

    return jsonify({
        "commonAreaId": common_area_id,
        "date": day,
        **reservation_availability(area, day),
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
    area = db.session.get(CommonArea, common_area_id)
    if area is None:
        return error_response(404, "Zona común no encontrada.")
    full_days, closed_days = month_calendar(area, year, month)
    return jsonify({
        "commonAreaId": common_area_id,
        "year": year,
        "month": month,
        "blockedDates": full_days,
        "closedDates": closed_days,
    })


def _zone_request_error(area, data):
    """Revisa que la franja, el día y el número de personas encajen con las reglas de la zona.

    Aplica a todos, también cuando la administración reserva por un residente:
    una franja fuera del horario, un día de mantenimiento o más personas que el
    aforo no son reservas posibles (HU-055 y RN-021).
    """
    if data["timeSlot"] not in area.slots:
        return error_response(
            400,
            f"Esa franja no existe en {area.name}: abre de {area.open_time} a {area.close_time}, "
            f"en franjas de {area.slot_minutes} minutos.",
        )
    requested_day = date.fromisoformat(data["date"])
    if is_maintenance_day(area.maintenance_weekday, requested_day):
        return error_response(
            400,
            f"{area.name} está cerrada por mantenimiento el {human_date(requested_day)}: "
            f"su mantenimiento es cada {WEEKDAY_NAMES[area.maintenance_weekday]} "
            "(si ese día es festivo, pasa al día siguiente).",
        )
    attendees = data.get("attendees")
    if attendees is not None:
        if isinstance(attendees, bool) or not isinstance(attendees, int) or attendees < 1:
            return error_response(400, "El número de personas debe ser un entero mayor que 0.")
        if area.capacity is not None and attendees > area.capacity:
            return error_response(
                400,
                f"El aforo de {area.name} es de {area.capacity} personas y escribiste {attendees}.",
            )
    return None


def _resident_limit_error(area, resident, data):
    """Revisa la anticipación y los límites diario y semanal del residente en esa zona.

    La administración no pasa por estos límites cuando reserva a nombre de un
    residente. El límite semanal es de cada zona (HU-055); el diario es uno por día.
    """
    requested_day = date.fromisoformat(data["date"])
    days_ahead = (requested_day - colombia_today()).days
    if days_ahead < area.min_advance_days:
        return error_response(
            400,
            f"{area.name} se reserva con al menos {days_text(area.min_advance_days)} de anticipación.",
        )
    if days_ahead > area.max_advance_days:
        return error_response(
            400,
            f"{area.name} se puede reservar con máximo {days_text(area.max_advance_days)} de anticipación.",
        )
    same_day = Reservation.query.filter(
        Reservation.resident_id == resident.id,
        Reservation.date == data["date"],
        Reservation.status.in_(LIMIT_RESERVATION_STATUSES),
        Reservation.is_archived.is_(False),
    ).first()
    if same_day is not None:
        return error_response(
            409,
            "Límite diario alcanzado: solo puedes tener 1 reserva activa o pendiente por día.",
        )
    if weekly_reservation_count(resident.id, area.id, requested_day) >= area.weekly_limit:
        noun = "reserva" if area.weekly_limit == 1 else "reservas"
        return error_response(
            409,
            f"Límite semanal alcanzado: máximo {area.weekly_limit} {noun} por semana en "
            f"{area.name} para permitir el uso equitativo de las zonas comunes.",
        )
    return None


@bp.post("/reservations")
@token_required
@role_required("RESIDENT", "ADMIN")
def create_reservation():
    data, failure = json_body()
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
    if error := _zone_request_error(area, data):
        return error
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
    if g.current_user.role == "RESIDENT" and (error := _resident_limit_error(area, resident, data)):
        return error
    if reservation_conflicts(area.id, data["date"], data["timeSlot"]):
        return error_response(409, "Ese horario ya no está disponible")

    reservation = Reservation(
        resident_id=resident.id,
        created_by_admin_id=g.current_user.id if g.current_user.role == "ADMIN" else None,
        common_area_id=area.id,
        date=data["date"],
        time_slot=data["timeSlot"],
        attendees=data.get("attendees"),
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
    data, failure = json_body()
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
    data, failure = json_body()
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
    if g.current_user.role == "RESIDENT" and not reservation.resident_can_cancel:
        area = reservation.common_area
        return error_response(
            400,
            f"El plazo para cancelar ya venció: {area.name} se cancela hasta "
            f"{days_text(area.cancel_deadline_days)} antes de la fecha reservada, es decir, hasta el "
            f"{human_date(reservation.cancel_until)}. Escríbele a administración en la "
            "conversación de la reserva si necesitas cambiarla.",
        )
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
