from flask import Blueprint, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from auth import generate_token, token_required
from errors import error_response
from extensions import db
from models import AuditLog, User
from validators import (
    require_non_empty_fields,
    validate_no_empty_strings,
    validate_strong_password,
)

bp = Blueprint("auth", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@bp.post("/auth/login")
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response(400, "El cuerpo de la solicitud debe ser un objeto JSON válido.")
    validation_error = validate_no_empty_strings(data)
    if validation_error:
        return error_response(400, validation_error)
    validation_error = require_non_empty_fields(
        data,
        (("email", "correo"), ("password", "contraseña")),
    )
    if validation_error:
        return error_response(400, validation_error)

    email = data["email"].strip().lower()
    password = data["password"]
    user = User.query.filter(db.func.lower(User.email) == email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return error_response(401, "Credenciales inválidas")
    if not user.is_active:
        return error_response(401, "Tu cuenta se encuentra inhabilitada")

    return jsonify({
        "message": "Login exitoso",
        "token": generate_token(user),
        "user": user.to_dict(),
    })


@bp.get("/auth/session")
@token_required
def current_session():
    return jsonify({"user": g.current_user.to_dict()})


@bp.post("/auth/change-password")
@token_required
def change_password():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response(400, "El cuerpo de la solicitud debe ser un objeto JSON válido.")
    validation_error = validate_no_empty_strings(data)
    if validation_error:
        return error_response(400, validation_error)
    validation_error = require_non_empty_fields(
        data,
        (("currentPassword", "contraseña actual"), ("newPassword", "nueva contraseña")),
    )
    if validation_error:
        return error_response(400, validation_error)
    password_error = validate_strong_password(data["newPassword"])
    if password_error:
        return error_response(400, password_error)

    user = g.current_user
    if not check_password_hash(user.password_hash, data["currentPassword"]):
        return error_response(401, "La contraseña actual es incorrecta.")

    user.password_hash = generate_password_hash(data["newPassword"])
    db.session.add(AuditLog(
        entity_type="USER",
        entity_id=user.id,
        action="password_changed",
        actor_id=user.id,
        actor_role=user.role,
        details="El usuario actualizó su contraseña.",
    ))
    db.session.commit()
    return jsonify({"message": "Contraseña actualizada exitosamente."})
