import re

from flask import Blueprint, current_app, g, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
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
RECOVERY_EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
LOGIN_RATE_LIMIT_ERROR = (
    "Demasiados intentos de inicio de sesión. Intenta nuevamente en un minuto."
)
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
)


def _login_rate_limit_key():
    data = request.get_json(silent=True)
    email = data.get("email", "") if isinstance(data, dict) else ""
    normalized_email = email.strip().lower() if isinstance(email, str) else ""
    return f"{get_remote_address()}:{normalized_email}"


@bp.errorhandler(429)
def handle_rate_limit_exceeded(_error):
    current_app.logger.warning("Login rate limit exceeded: %s", _error)
    data = request.get_json(silent=True)
    email = data.get("email", "") if isinstance(data, dict) else ""
    normalized_email = email.strip().lower() if isinstance(email, str) else ""
    user = User.query.filter(db.func.lower(User.email) == normalized_email).first()
    db.session.add(AuditLog(
        entity_type="AUTH",
        entity_id=user.id if user else None,
        action="login_rate_limited",
        actor_id=user.id if user else None,
        actor_role=user.role if user else None,
        details=f"Intento de inicio de sesión limitado desde {get_remote_address()}.",
    ))
    db.session.commit()
    return jsonify({"error": LOGIN_RATE_LIMIT_ERROR}), 429


@bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@bp.post("/auth/login")
@limiter.limit("5 per minute", key_func=_login_rate_limit_key)
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
    if user is not None and user.is_active is not True:
        return error_response(
            403,
            "Tu cuenta se encuentra desactivada. Contacta a administración.",
        )
    if not user or not check_password_hash(user.password_hash, password):
        return error_response(401, "Credenciales inválidas")

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
    recovery_email = data.get("recoveryEmail")
    if isinstance(recovery_email, str):
        recovery_email = recovery_email.strip()
    if recovery_email == "":
        data = {key: value for key, value in data.items() if key != "recoveryEmail"}
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

    if recovery_email is not None and recovery_email != "":
        if not isinstance(recovery_email, str):
            return error_response(400, "El correo de recuperación no es válido.")
        recovery_email = recovery_email.strip().lower()
        if (
            len(recovery_email) > 120
            or not RECOVERY_EMAIL_PATTERN.fullmatch(recovery_email)
        ):
            return error_response(400, "El correo de recuperación no es válido.")
        if recovery_email == user.email.strip().lower():
            return error_response(
                400,
                "El correo de recuperación debe ser distinto al correo principal.",
            )
        user.recovery_email = recovery_email

    user.password_hash = generate_password_hash(data["newPassword"])
    user.token_version = (user.token_version or 1) + 1
    user.must_change_password = False
    db.session.add(AuditLog(
        entity_type="USER",
        entity_id=user.id,
        action="password_changed",
        actor_id=user.id,
        actor_role=user.role,
        details="El usuario actualizó su contraseña.",
    ))
    db.session.commit()
    return jsonify({
        "message": "Contraseña actualizada exitosamente.",
        "user": user.to_dict(),
    })
