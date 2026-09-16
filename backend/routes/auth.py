from flask import Blueprint, jsonify, request
from werkzeug.security import check_password_hash

from auth import generate_token
from errors import error_response
from extensions import db
from models import User

bp = Blueprint("auth", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@bp.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    user = User.query.filter(db.func.lower(User.email) == email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return error_response(401, "Credenciales inválidas")

    return jsonify({
        "message": "Login exitoso",
        "token": generate_token(user),
        "user": user.to_dict(),
    })
