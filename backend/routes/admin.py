from flask import Blueprint, jsonify, request
from werkzeug.security import generate_password_hash

from auth import role_required, token_required
from errors import error_response
from extensions import db
from models import User

bp = Blueprint("admin", __name__, url_prefix="/api")


@bp.get("/users")
@token_required
@role_required("ADMIN")
def get_users():
    users = User.query.order_by(User.id).all()
    return jsonify({"users": [user.to_dict() for user in users]})


@bp.post("/users")
@token_required
@role_required("ADMIN")
def create_user():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = data.get("role")
    apartment = data.get("apartment")

    if not name or not email or not password or role not in ("ADMIN", "RESIDENT", "GUARD"):
        return error_response(400, "Datos incompletos o rol inválido")
    if role == "RESIDENT" and not apartment:
        return error_response(400, "El residente necesita un apartamento")
    if User.query.filter(db.func.lower(User.email) == email).first():
        return error_response(409, "Ese correo ya está registrado")

    user = User(
        name=name,
        email=email,
        password_hash=generate_password_hash(password),
        role=role,
        apartment=apartment if role == "RESIDENT" else None,
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "Usuario creado", "user": user.to_dict()}), 201


@bp.get("/residents")
@token_required
@role_required("ADMIN", "GUARD")
def get_residents():
    residents = User.query.filter_by(role="RESIDENT").order_by(User.name).all()
    return jsonify({"residents": [resident.to_resident_summary() for resident in residents]})