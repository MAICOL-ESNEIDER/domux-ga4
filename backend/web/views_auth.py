"""Inicio y cierre de sesión de la web de administración (HU-074).

El inicio de sesión no repite ninguna regla: llama a ``POST /api/auth/login``, la misma ruta que usa la
app. Así valen el bloqueo de 15 minutos tras 5 intentos (HU-006), el mensaje único para correo o
contraseña incorrectos (RN-002) y el aviso de cuenta inhabilitada. Lo único que añade la web es que
solo entra la administración (RN-006).
"""

from flask import flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from extensions import db
from models import User
from services.audit_service import add_audit_log
from web import bp
from web.api import Api
from services.login_attempt_service import LOGIN, register_failure, register_success, seconds_locked
from web.security import (
    current_admin,
    end_session,
    login_required,
    mark_account_to_remember,
    mark_password_confirmed,
    safe_next,
    start_session,
)

#: Lo que ve un residente o un guardia que escribe bien su contraseña (CA-HU-074-01).
NOT_ADMIN_MESSAGE = (
    "Esta página es solo para la administración. Si eres residente o guardia, usa la app DOMUX."
)


def _login_page(email, next_url, error=None, status=200):
    """La página de inicio de sesión; nunca devuelve la contraseña escrita."""
    return render_template("web/login.html", email=email, next_url=next_url, error=error), status


@bp.get("/login")
def login():
    user, reason = current_admin()
    if user is not None:
        return redirect(url_for("web.panel"))
    if reason:
        flash(reason, "error")
    return _login_page("", safe_next(request.args.get("next")))


@bp.post("/login")
def login_submit():
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    next_url = safe_next(request.form.get("next"))
    if not email or not password:
        return _login_page(email, next_url, "Escribe tu correo y tu contraseña.", 400)

    result = Api().post("/api/auth/login", {"email": email, "password": password})
    if not result.ok:
        return _login_page(email, next_url, result.error, result.status)

    account = result.get("user") or {}
    user = db.session.get(User, account.get("id"))
    if user is None:
        return _login_page(email, next_url, "No se pudo iniciar la sesión. Inténtalo de nuevo.", 500)
    if user.role != "ADMIN":
        add_audit_log("user", user.id, "web_login_denied", {"role": user.role}, actor=user)
        db.session.commit()
        return _login_page(email, next_url, NOT_ADMIN_MESSAGE, 403)

    start_session(user)
    # «Recordar mi correo en este equipo»: solo después de entrar bien y siendo administración.
    if request.form.get("recordar") == "1":
        mark_account_to_remember()
    add_audit_log("user", user.id, "web_login", None, actor=user)
    db.session.commit()
    return redirect(next_url or url_for("web.panel"))


@bp.post("/logout")
@login_required
def logout():
    end_session()
    flash("Cerraste la sesión.", "success")
    return redirect(url_for("web.login"))


# --- Confirmar la contraseña antes de descargar ------------------------------------------------

@bp.get("/confirmar-contrasena")
@login_required
def password_confirm():
    return render_template("web/password_confirm.html", next_url=safe_next(request.args.get("next")))


@bp.post("/confirmar-contrasena")
@login_required
def password_confirm_submit():
    """Comprueba la contraseña del administrador; los fallos cuentan para el bloqueo de 15 minutos."""
    next_url = safe_next(request.form.get("next"))
    user = g.web_user
    attempts_key = user.email.strip().lower()[:160]
    if seconds_locked(LOGIN, attempts_key):
        end_session()
        flash("Demasiados intentos fallidos. Espera 15 minutos e inicia sesión de nuevo.", "error")
        return redirect(url_for("web.login"))
    if not check_password_hash(user.password_hash, request.form.get("password", "")):
        register_failure(LOGIN, attempts_key)
        add_audit_log("user", user.id, "web_password_confirm_failed", None, actor=user)
        db.session.commit()
        flash("La contraseña no es correcta.", "error")
        return redirect(url_for("web.password_confirm", next=next_url))
    register_success(LOGIN, attempts_key)
    db.session.commit()
    mark_password_confirmed()
    flash("Listo: ya puedes descargar durante los próximos 10 minutos.", "success")
    return redirect(next_url or url_for("web.panel"))


# --- Cambiar la contraseña propia ----------------------------------------------------------------

@bp.get("/cambiar-contrasena")
@login_required
def password_change():
    return render_template("web/password_change.html", forced=g.web_user.must_change_password)


@bp.post("/cambiar-contrasena")
@login_required
def password_change_submit():
    """Cambia la contraseña con la misma ruta de la app (``PUT /api/auth/password``)."""
    new_password = request.form.get("newPassword", "")
    if new_password != request.form.get("newPassword2", ""):
        flash("Las dos contraseñas nuevas no coinciden. Escríbelas de nuevo.", "error")
        return redirect(url_for("web.password_change"))
    result = Api(g.web_user).put("/api/auth/password", {
        "currentPassword": request.form.get("currentPassword", ""), "newPassword": new_password,
    })
    if not result.ok:
        flash(result.error, "error")
        return redirect(url_for("web.password_change"))
    # Cambiar la contraseña cierra las demás sesiones; esta sigue con la versión nueva.
    db.session.refresh(g.web_user)
    session["ver"] = g.web_user.token_version or 0
    flash("Contraseña cambiada. Las demás sesiones abiertas con tu cuenta se cerraron.", "success")
    return redirect(url_for("web.panel"))
