from flask import Blueprint, jsonify, request
from werkzeug.security import generate_password_hash

from auth import role_required, token_required
from errors import error_response
from extensions import db
from models import ROLES, User
from validators import (
    OCCUPANCY_TYPES,
    require_non_empty_fields,
    validate_no_empty_strings,
    validate_occupancy_type,
    validate_strong_password,
)

bp = Blueprint("admin", __name__, url_prefix="/api")


def _json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, error_response(400, "El cuerpo de la solicitud debe ser un objeto JSON válido.")
    message = validate_no_empty_strings(data)
    if message:
        return None, error_response(400, message)
    return data, None


def _normalize_role(value):
    return value.strip().upper() if isinstance(value, str) else None


@bp.get("/users")
@bp.get("/admin/users")
@token_required
@role_required("ADMIN")
def get_users():
    users = User.query.order_by(User.id).all()
    return jsonify({"users": [user.to_dict() for user in users]})


@bp.post("/users")
@bp.post("/admin/users")
@token_required
@role_required("ADMIN")
def create_user():
    data, failure = _json_body()
    if failure:
        return failure
    validation_error = require_non_empty_fields(
        data,
        (("name", "nombre"), ("email", "correo"), ("password", "contraseña")),
    )
    if validation_error:
        return error_response(400, validation_error)

    email = data["email"].strip().lower()
    role = _normalize_role(data.get("role"))
    apartment = data.get("apartment")
    occupancy_type = data.get("occupancyType", "propietario")
    if "@" not in email or role not in ROLES:
        return error_response(400, "Correo o rol inválido")
    password_error = validate_strong_password(data["password"])
    if password_error:
        return error_response(400, password_error)
    if role == "RESIDENT" and (
        not isinstance(apartment, str) or not apartment.strip()
    ):
        return error_response(400, "El residente necesita un apartamento")
    if not isinstance(occupancy_type, str) or occupancy_type not in OCCUPANCY_TYPES:
        return error_response(400, validate_occupancy_type(occupancy_type))
    for field in ("lastName", "phone", "documentId"):
        if field in data and not isinstance(data[field], str):
            return error_response(400, f"El campo '{field}' debe ser texto")
    if User.query.filter(db.func.lower(User.email) == email).first():
        return error_response(409, "Ese correo ya está registrado")

    user = User(
        name=data["name"].strip(),
        last_name=data.get("lastName", "").strip(),
        email=email,
        phone=data.get("phone", "").strip(),
        document_id=data.get("documentId", "").strip(),
        password_hash=generate_password_hash(data["password"]),
        role=role,
        apartment=apartment.strip() if role == "RESIDENT" else None,
        occupancy_type=occupancy_type,
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "Usuario creado", "user": user.to_dict()}), 201


@bp.put("/users/<int:user_id>")
@bp.put("/admin/users/<int:user_id>")
@token_required
@role_required("ADMIN")
def update_user(user_id):
    data, failure = _json_body()
    if failure:
        return failure
    if not data:
        return error_response(400, "Debes proporcionar al menos un dato para actualizar")
    if "password" in data or "passwordHash" in data or "password_hash" in data:
        return error_response(400, "Usa PUT /users/<id>/password para cambiar la contraseña")

    user = db.session.get(User, user_id)
    if user is None:
        return error_response(404, "Usuario no encontrado")

    if "name" in data:
        if not isinstance(data["name"], str):
            return error_response(400, "El nombre debe ser texto")
        user.name = data["name"].strip()
    if "lastName" in data:
        if not isinstance(data["lastName"], str):
            return error_response(400, "El apellido debe ser texto")
        user.last_name = data["lastName"].strip()
    if "email" in data:
        if not isinstance(data["email"], str) or "@" not in data["email"]:
            return error_response(400, "Correo inválido")
        email = data["email"].strip().lower()
        duplicate = User.query.filter(
            db.func.lower(User.email) == email,
            User.id != user.id,
        ).first()
        if duplicate:
            return error_response(409, "Ese correo ya está registrado")
        user.email = email
    for field, attribute, label in (
        ("phone", "phone", "teléfono"),
        ("documentId", "document_id", "documento"),
    ):
        if field in data:
            if not isinstance(data[field], str):
                return error_response(400, f"El {label} debe ser texto")
            setattr(user, attribute, data[field].strip())

    if "role" in data:
        role = _normalize_role(data["role"])
        if role not in ROLES:
            return error_response(400, "Rol inválido")
        user.role = role
    if "occupancyType" in data:
        error = validate_occupancy_type(data["occupancyType"])
        if error:
            return error_response(400, error)
        user.occupancy_type = data["occupancyType"]
    if "apartment" in data:
        apartment = data["apartment"]
        if apartment is not None and not isinstance(apartment, str):
            return error_response(400, "El apartamento debe ser texto")
        user.apartment = apartment.strip() if apartment else None
    if user.role == "RESIDENT" and not user.apartment:
        return error_response(400, "El residente necesita un apartamento")
    if user.role != "RESIDENT":
        user.apartment = None
    if "isActive" in data:
        if not isinstance(data["isActive"], bool):
            return error_response(400, "isActive debe ser verdadero o falso")
        user.is_active = data["isActive"]

    db.session.commit()
    return jsonify({"message": "Usuario actualizado", "user": user.to_dict()})


@bp.put("/users/<int:user_id>/password")
@bp.put("/admin/users/<int:user_id>/password")
@token_required
@role_required("ADMIN")
def reset_user_password(user_id):
    data, failure = _json_body()
    if failure:
        return failure
    validation_error = require_non_empty_fields(data, (("password", "contraseña"),))
    if validation_error:
        return error_response(400, validation_error)
    password_error = validate_strong_password(data["password"])
    if password_error:
        return error_response(400, password_error)

    user = db.session.get(User, user_id)
    if user is None:
        return error_response(404, "Usuario no encontrado")
    user.password_hash = generate_password_hash(data["password"])
    db.session.commit()
    return jsonify({"message": "Contraseña restablecida"})


@bp.get("/residents")
@token_required
@role_required("ADMIN", "GUARD")
def get_residents():
    residents = User.query.filter_by(role="RESIDENT").order_by(User.name).all()
    return jsonify({"residents": [resident.to_resident_summary() for resident in residents]})
