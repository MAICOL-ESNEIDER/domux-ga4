"""Seguridad de la web de administración (HU-074, RN-006 y RNF-005).

- La sesión es una cookie firmada con una clave derivada de JWT_SECRET: el navegador la manda sola,
  pero JavaScript no puede leerla (HttpOnly), en producción solo viaja por HTTPS (Secure) y solo
  hacia las páginas de la web (Path).
- Cada formulario que cambia algo lleva un código contra CSRF; sin él la página responde 400.
- La sesión vence a los 30 minutos sin actividad y, pase lo que pase, a las 8 horas.
- En cada página se vuelve a comprobar en la base que la cuenta existe, está activa y es de la
  administración: desactivar a alguien le cierra la web de inmediato.
- Las páginas salen con cabeceras que impiden meterlas dentro de otro sitio, adivinar tipos de
  archivo, cargar scripts de otro origen y guardarlas en la memoria del navegador.
"""

import hashlib
import hmac
import secrets
import time
from datetime import timedelta
from functools import wraps
from urllib.parse import urlsplit

from flask import abort, flash, g, redirect, request, session, url_for

from auth import JWT_SECRET
from config import is_production
from errors import is_web_path
from extensions import db
from models import User
from web import bp

#: Segundos sin actividad después de los cuales la sesión se cierra sola.
IDLE_SECONDS = 30 * 60

#: Horas que dura una sesión como máximo, aunque la persona no deje de usarla.
SESSION_HOURS = 8

#: Qué puede cargar una página: todo sale de este mismo servidor, salvo las imágenes de las
#: PQRS y los comunicados, que se guardan como data URL (RNF-005).
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "img-src 'self' data:",
    "media-src 'self'",
    "style-src 'self'",
    "script-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


def configure(app):
    """Cookie de sesión, clave y cabeceras de seguridad de la web."""
    # Otra clave distinta de la de los tokens, derivada de la misma variable secreta.
    app.secret_key = hmac.new(JWT_SECRET.encode(), b"domux-web-sesion", hashlib.sha256).hexdigest()
    app.config.update(
        SESSION_COOKIE_NAME="domux_web",
        SESSION_COOKIE_PATH="/web",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=is_production(),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=SESSION_HOURS),
    )

    @app.after_request
    def add_security_headers(response):
        if not is_web_path(request.path):
            return response
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if is_production():
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # Las páginas llevan datos de residentes: el navegador no debe guardarlas. Los archivos de
        # diseño (CSS, JS, logo) los guarda y los revalida en cada visita (si no cambiaron, el
        # servidor responde 304 sin volver a enviarlos), así un cambio de diseño llega al instante.
        if request.endpoint != "web.static":
            response.headers["Cache-Control"] = "no-store"
        return response


# --- Código contra CSRF ---------------------------------------------------------------------------

def csrf_token():
    """El código de este navegador; se crea la primera vez que se pide."""
    token = session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf"] = token
    return token


@bp.before_request
def check_csrf():
    """Todo lo que cambia algo (POST) debe traer el código de la sesión."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
    expected = session.get("csrf") or ""
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, description="csrf")
    return None


# --- Sesión de la administración ------------------------------------------------------------------

def safe_next(target):
    """Una dirección de la web a la que volver después de iniciar sesión, o None.

    Solo se aceptan rutas de la propia web: nunca otro sitio (redirección abierta).
    """
    if not target:
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not parts.path.startswith("/web/"):
        return None
    if parts.path.startswith("/web/login") or parts.path.startswith("/web/static"):
        return None
    return parts.path + (f"?{parts.query}" if parts.query else "")


def start_session(user):
    """Abre la sesión de un administrador. Se parte de una sesión limpia (fijación de sesión)."""
    session.clear()
    session.permanent = True
    session["uid"] = user.id
    session["seen"] = int(time.time())
    session["csrf"] = secrets.token_urlsafe(32)


def end_session():
    session.clear()


def current_admin():
    """El administrador de la sesión, o ``(None, motivo)`` si no hay uno válido.

    Devuelve siempre una pareja ``(usuario, motivo)``. El motivo, cuando hay uno, es el texto que
    se le muestra a la persona.
    """
    user_id = session.get("uid")
    if not user_id:
        return None, None
    now = int(time.time())
    if now - int(session.get("seen", 0)) > IDLE_SECONDS:
        end_session()
        return None, "Tu sesión se cerró por inactividad. Inicia sesión de nuevo."
    user = db.session.get(User, user_id)
    if user is None or not user.is_active or user.role != "ADMIN":
        end_session()
        return None, "Tu sesión ya no es válida. Inicia sesión de nuevo."
    session["seen"] = now
    return user, None


def login_required(view):
    """Deja pasar solo a un administrador con la sesión abierta; los demás van al inicio de sesión."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        user, reason = current_admin()
        if user is None:
            if reason:
                flash(reason, "error")
            target = safe_next(request.full_path.rstrip("?")) if request.method == "GET" else None
            # Al inicio no hace falta recordarlo: es adonde se va de todas formas.
            if target is None or target == url_for("web.panel"):
                return redirect(url_for("web.login"))
            return redirect(url_for("web.login", next=target))
        g.web_user = user
        return view(*args, **kwargs)

    return wrapper
