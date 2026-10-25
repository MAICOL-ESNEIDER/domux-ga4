from flask import Blueprint, jsonify, request
from werkzeug.security import check_password_hash

from auth import generate_token
from errors import error_response
from extensions import db
from models import User
from validators import require_non_empty_fields, validate_no_empty_strings

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
