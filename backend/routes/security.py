from datetime import datetime

from flask import Blueprint, g, jsonify, request

from auth import role_required, token_required
from extensions import db
from models import PackageItem, User, Visit

bp = Blueprint("security", __name__, url_prefix="/api")


@bp.get("/packages")
@token_required
def get_packages():
    user = g.current_user
    if user.role == "RESIDENT":
        items = PackageItem.query.filter_by(resident_id=user.id).order_by(PackageItem.created_at.desc()).all()
    else:
        items = PackageItem.query.order_by(PackageItem.created_at.desc()).all()
    return jsonify({"packages": [item.to_dict() for item in items]})


@bp.post("/packages")
@token_required
@role_required("GUARD")
def register_package():
    data = request.get_json(silent=True) or {}
    resident = User.query.filter_by(id=data.get("residentId"), role="RESIDENT").first()
    if not resident:
        return jsonify({"error": "Selecciona un residente válido"}), 400

    package = PackageItem(
        resident_id=resident.id,
        registered_by=g.current_user.id,
        description=data.get("description"),
    )
    db.session.add(package)
    db.session.commit()
    return jsonify({"message": "Paquete registrado", "packageItem": package.to_dict()}), 201


@bp.put("/packages/<int:pkg_id>/deliver")
@token_required
@role_required("GUARD")
def deliver_package(pkg_id):
    package = PackageItem.query.get(pkg_id)
    if not package:
        return jsonify({"error": "Paquete no encontrado"}), 404

    package.status = "entregado"
    package.delivered_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Paquete marcado como entregado", "packageItem": package.to_dict()})


@bp.get("/visits")
@token_required
def get_visits():
    user = g.current_user
    if user.role == "RESIDENT":
        items = Visit.query.filter_by(resident_id=user.id).order_by(Visit.created_at.desc()).all()
    else:
        items = Visit.query.order_by(Visit.created_at.desc()).all()
    return jsonify({"visits": [item.to_dict() for item in items]})


@bp.post("/visits")
@token_required
@role_required("GUARD")
def register_visit():
    data = request.get_json(silent=True) or {}
    resident = User.query.filter_by(id=data.get("residentId"), role="RESIDENT").first()
    visitor_name = (data.get("visitorName") or "").strip()
    visit_type = data.get("type")
    if not resident or not visitor_name or visit_type not in ("visitante", "domiciliario"):
        return jsonify({"error": "Datos incompletos para registrar el ingreso"}), 400

    visit = Visit(
        resident_id=resident.id,
        registered_by=g.current_user.id,
        visitor_name=visitor_name,
        type=visit_type,
    )
    db.session.add(visit)
    db.session.commit()
    return jsonify({"message": "Ingreso registrado", "visit": visit.to_dict()}), 201
