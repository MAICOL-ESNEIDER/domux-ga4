# auth.py — todo lo relacionado con el token: generarlo, leerlo del encabezado
# Authorization, y dos decoradores para proteger las rutas:
#   @token_required            -> exige un token válido (401 si falta o es inválido)
#   @role_required("ADMIN")    -> exige además un rol concreto (403 si no cumple)
# Esta es la "segunda capa de seguridad" de la que habla la GA3: aunque la app
# oculte botones, el backend vuelve a comprobar todo.

import os
from datetime import datetime, timedelta
from functools import wraps

import jwt
from flask import request, jsonify, g

from models import User

JWT_SECRET = os.environ.get("JWT_SECRET", "clave-de-desarrollo-domux-cambiar-en-produccion")
JWT_ALGORITHM = "HS256"
JWT_EXP_HOURS = 24 * 7  # el token dura 7 días


def generate_token(user: User) -> str:
    payload = {
        "user_id": user.id,
        "role": user.role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXP_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _extraer_token():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    return header.split(" ", 1)[1].strip()


def token_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = _extraer_token()
        if not token:
            return jsonify({"error": "Falta el token de autenticación"}), 401
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Tu sesión venció, inicia sesión de nuevo"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Token inválido"}), 401

        user = User.query.get(payload.get("user_id"))
        if user is None:
            return jsonify({"error": "El usuario del token ya no existe"}), 401

        g.current_user = user
        return f(*args, **kwargs)

    return wrapper


def role_required(*roles_permitidos):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = getattr(g, "current_user", None)
            if user is None or user.role not in roles_permitidos:
                return jsonify({"error": "No tienes permiso para hacer esta acción"}), 403
            return f(*args, **kwargs)

        return wrapper

    return decorator
