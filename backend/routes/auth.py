from flask import Blueprint, g, jsonify
from werkzeug.security import check_password_hash, generate_password_hash

from auth import generate_token, role_required, token_required
from errors import error_response
from extensions import db
from models import User
from routes.common import json_body
from services.audit_service import add_audit_log
from services.login_attempt_service import (
    LOCK_MINUTES,
    LOGIN,
    PIN,
    register_failure,
    register_success,
    seconds_locked,
)
from validators import require_non_empty_fields, validate_pin

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


#: Lo mismo para el PIN de un guardia (HU-010): se bloquea solo el PIN de ese guardia.
PIN_LOCKED_MESSAGE = (
    f"Por seguridad, el PIN de este guardia quedó bloqueado {LOCK_MINUTES} minutos. "
    "Intenta de nuevo más tarde."
)


def locked_response(seconds, message=LOCKED_MESSAGE):
    """Respuesta 429 del bloqueo; Retry-After dice cuántos segundos faltan."""
    response, status = error_response(429, message)
    response.headers["Retry-After"] = str(max(1, seconds))
    return response, status


@bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@bp.post("/auth/login")
def login():
    data, failure = json_body()
    if failure:
        return failure
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


# --- Cambio de guardia con PIN en la tablet (HU-010, CU-008 y RN-029) ---------

@bp.get("/auth/guards")
@token_required
@role_required("GUARD")
def list_guards_for_shift():
    """Los guardias que pueden tomar el turno: activos y con PIN (paso 2 de CU-008).

    Solo se entrega el nombre: la tablet no necesita correos ni teléfonos de los
    compañeros (ADR-015).
    """
    guards = (
        User.query.filter_by(role="GUARD", is_active=True)
        .filter(User.pin_hash.isnot(None))
        .order_by(User.name, User.last_name)
        .all()
    )
    return jsonify({"guards": [{"id": guard.id, "name": guard.full_name} for guard in guards]})


@bp.post("/auth/guard-shift")
@token_required
@role_required("GUARD")
def guard_shift():
    """El guardia que entra toma el turno con su PIN, sin cerrar la sesión de la tablet.

    Si el PIN es correcto responde con la sesión del guardia nuevo: la app guarda
    ese token y, desde ese momento, cada registro queda a su nombre. Con un PIN
    incorrecto la sesión de la tablet no cambia. Cinco fallos seguidos bloquean
    el PIN de ese guardia 15 minutos (HU-006); su contraseña sigue funcionando.
    """
    data, failure = json_body()
    if failure:
        return failure
    guard_id = data.get("guardId")
    if isinstance(guard_id, bool) or not isinstance(guard_id, int) or guard_id < 1:
        return error_response(400, "Elige el guardia que toma el turno.")
    pin_error = validate_pin(data.get("pin"))
    if pin_error:
        return error_response(400, pin_error)

    guard = db.session.get(User, guard_id)
    # Quien no existe y quien no es guardia reciben lo mismo: no se revelan los roles.
    if guard is None or guard.role != "GUARD":
        return error_response(404, "No encontramos a ese guardia.")
    if not guard.is_active:
        return error_response(
            403, "La cuenta de este guardia está desactivada: no puede tomar el turno."
        )
    if not guard.pin_hash:
        return error_response(
            409, "Este guardia todavía no tiene PIN: pídele al administrador que se lo asigne."
        )

    subject = str(guard.id)
    wait = seconds_locked(PIN, subject)
    if wait:
        return locked_response(wait, PIN_LOCKED_MESSAGE)
    if not check_password_hash(guard.pin_hash, data["pin"]):
        locked = register_failure(PIN, subject)
        db.session.commit()
        if locked:
            return locked_response(LOCK_MINUTES * 60, PIN_LOCKED_MESSAGE)
        return error_response(401, "PIN incorrecto. El guardia activo no cambió.")

    register_success(PIN, subject)
    add_audit_log("user", guard.id, "guard_shift", {"previousGuardId": g.current_user.id}, actor=guard)
    db.session.commit()
    return jsonify({
        "message": f"Turno tomado por {guard.full_name}",
        "token": generate_token(guard),
        "user": guard.to_dict(),
    })
