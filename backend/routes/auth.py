from flask import Blueprint, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from auth import generate_token, token_required
from errors import error_response
from extensions import db
from models import User
from services.login_attempt_service import (
    LOCK_MINUTES,
    LOGIN,
    register_failure,
    register_success,
    seconds_locked,
)
from validators import require_non_empty_fields, validate_no_empty_strings

bp = Blueprint("auth", __name__, url_prefix="/api")

#: Hash de una contraseña que nadie conoce. Cuando el correo no existe, la
#: contraseña se compara contra este hash para que la respuesta tarde casi lo
#: mismo que con un correo real y no se pueda saber qué cuentas existen (SEC-011).
FAKE_PASSWORD_HASH = generate_password_hash("contraseña-que-ninguna-cuenta-tiene")

#: Mensaje del bloqueo (MSG-011). No dice si el correo existe (RN-002).
LOCKED_MESSAGE = (
    f"Por seguridad, la cuenta quedó bloqueada {LOCK_MINUTES} minutos. "
    "Intenta de nuevo más tarde."
)


def locked_response(seconds):
    """Respuesta 429 del bloqueo; Retry-After dice cuántos segundos faltan."""
    response, status = error_response(429, LOCKED_MESSAGE)
    response.headers["Retry-After"] = str(max(1, seconds))
    return response, status


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
    # Los intentos se cuentan por correo, exista o no la cuenta (RN-002 y HU-006).
    attempts_key = email[:160]

    wait = seconds_locked(LOGIN, attempts_key)
    if wait:
        return locked_response(wait)

    user = User.query.filter(db.func.lower(User.email) == email).first()
    # Se compara siempre contra un hash, exista o no el correo (SEC-011).
    password_ok = check_password_hash(
        user.password_hash if user else FAKE_PASSWORD_HASH, password
    )
    if user is None or not password_ok:
        locked = register_failure(LOGIN, attempts_key)
        db.session.commit()
        if locked:
            return locked_response(LOCK_MINUTES * 60)
        return error_response(401, "Credenciales inválidas")

    register_success(LOGIN, attempts_key)
    db.session.commit()
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
