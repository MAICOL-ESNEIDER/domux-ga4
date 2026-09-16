from flask import Blueprint, g, jsonify, request

from auth import role_required, token_required
from extensions import db
from models import Announcement, CommonArea, Pqrs, Reservation

bp = Blueprint("community", __name__, url_prefix="/api")


@bp.get("/announcements")
@token_required
def get_announcements():
    items = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return jsonify({"announcements": [item.to_dict() for item in items]})


@bp.post("/announcements")
@token_required
@role_required("ADMIN")
def create_announcement():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    message = (data.get("message") or "").strip()
    if not title or not message:
        return jsonify({"error": "Título y mensaje son obligatorios"}), 400

    announcement = Announcement(title=title, message=message, author_id=g.current_user.id)
    db.session.add(announcement)
    db.session.commit()
    return jsonify({"message": "Anuncio publicado", "announcement": announcement.to_dict()}), 201


@bp.get("/pqrs")
@token_required
def get_pqrs():
    user = g.current_user
    if user.role == "ADMIN":
        items = Pqrs.query.order_by(Pqrs.created_at.desc()).all()
    elif user.role == "RESIDENT":
        items = Pqrs.query.filter_by(resident_id=user.id).order_by(Pqrs.created_at.desc()).all()
    else:
        return jsonify({"error": "No tienes permiso para ver las PQRS"}), 403
    return jsonify({"pqrs": [item.to_dict() for item in items]})


@bp.post("/pqrs")
@token_required
@role_required("RESIDENT")
def create_pqrs():
    data = request.get_json(silent=True) or {}
    subject = (data.get("subject") or "").strip()
    message = (data.get("message") or "").strip()
    if not subject or not message:
        return jsonify({"error": "Asunto y mensaje son obligatorios"}), 400

    pqrs = Pqrs(resident_id=g.current_user.id, subject=subject, message=message)
    db.session.add(pqrs)
    db.session.commit()
    return jsonify({"message": "PQRS enviada", "pqrs": pqrs.to_dict()}), 201


@bp.put("/pqrs/<int:pqrs_id>/respond")
@token_required
@role_required("ADMIN")
def respond_pqrs(pqrs_id):
    pqrs = Pqrs.query.get(pqrs_id)
    if not pqrs:
        return jsonify({"error": "PQRS no encontrada"}), 404

    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ("abierta", "en_proceso", "resuelta"):
        return jsonify({"error": "Estado inválido"}), 400
    pqrs.status = status
    pqrs.admin_response = data.get("adminResponse")
    db.session.commit()
    return jsonify({"message": "PQRS actualizada", "pqrs": pqrs.to_dict()})


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
        items = Reservation.query.filter_by(resident_id=user.id).order_by(Reservation.created_at.desc()).all()
    else:
        return jsonify({"error": "No tienes permiso para ver las reservas"}), 403
    return jsonify({"reservations": [item.to_dict() for item in items]})


@bp.post("/reservations")
@token_required
@role_required("RESIDENT")
def create_reservation():
    data = request.get_json(silent=True) or {}
    area = CommonArea.query.get(data.get("commonAreaId")) if data.get("commonAreaId") else None
    date = (data.get("date") or "").strip()
    time_slot = (data.get("timeSlot") or "").strip()
    if not area or not date or not time_slot:
        return jsonify({"error": "Zona, fecha y horario son obligatorios"}), 400

    reservation = Reservation(
        resident_id=g.current_user.id,
        common_area_id=area.id,
        date=date,
        time_slot=time_slot,
    )
    db.session.add(reservation)
    db.session.commit()
    return jsonify({"message": "Reserva creada", "reservation": reservation.to_dict()}), 201


@bp.put("/reservations/<int:res_id>/cancel")
@token_required
@role_required("RESIDENT", "ADMIN")
def cancel_reservation(res_id):
    reservation = Reservation.query.get(res_id)
    if not reservation:
        return jsonify({"error": "Reserva no encontrada"}), 404
    if g.current_user.role == "RESIDENT" and reservation.resident_id != g.current_user.id:
        return jsonify({"error": "Esa reserva no es tuya"}), 403

    reservation.status = "cancelada"
    db.session.commit()
    return jsonify({"message": "Reserva cancelada", "reservation": reservation.to_dict()})
