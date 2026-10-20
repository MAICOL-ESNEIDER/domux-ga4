# auth.py — todo lo relacionado con el token: generarlo, leerlo del encabezado
# Authorization, y dos decoradores para proteger las rutas:
#   @token_required            -> exige un token válido (401 si falta o es inválido)
#   @role_required("ADMIN")    -> exige además un rol concreto (403 si no cumple)
# Esta es la "segunda capa de seguridad" de la que habla la GA3: aunque la app
# oculte botones, el backend vuelve a comprobar todo.

import os
import secrets
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import request, g
from dotenv import load_dotenv

from errors import error_response
from models import User

logger = logging.getLogger(__name__)

load_dotenv()

JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    JWT_SECRET = secrets.token_urlsafe(32)
    logger.warning(
        "JWT_SECRET no está configurado; se usará una clave temporal. "
        "Configúralo antes de ejecutar el backend en producción."
    )

JWT_ALGORITHM = "HS256"
JWT_EXP_HOURS = 24 * 7  # el token dura 7 días


def generate_token(user: User) -> str:
    payload = {
        "user_id": user.id,
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXP_HOURS),
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
            return error_response(401, "Falta el token de autenticación")
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            return error_response(401, "Tu sesión venció, inicia sesión de nuevo")
        except jwt.PyJWTError:
            return error_response(401, "Token inválido")

        user = User.query.get(payload.get("user_id"))
        if user is None:
            return error_response(401, "El usuario del token ya no existe")
        if not getattr(user, "is_active", True):
            return error_response(401, "Tu cuenta se encuentra inhabilitada")

        g.current_user = user
        return f(*args, **kwargs)

    return wrapper


def role_required(*roles_permitidos):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = getattr(g, "current_user", None)
            if user is None or user.role not in roles_permitidos:
                return error_response(403, "No tienes permiso para hacer esta acción")
            return f(*args, **kwargs)

        return wrapper

    return decorator
