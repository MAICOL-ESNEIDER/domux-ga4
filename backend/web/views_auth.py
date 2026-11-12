"""Inicio y cierre de sesión de la web de administración (HU-074).

El inicio de sesión no repite ninguna regla: llama a ``POST /api/auth/login``, la misma ruta que usa la
app. Así valen el bloqueo de 15 minutos tras 5 intentos (HU-006), el mensaje único para correo o
contraseña incorrectos (RN-002) y el aviso de cuenta inhabilitada. Lo único que añade la web es que
solo entra la administración (RN-006).
"""

from flask import flash, redirect, render_template, request, url_for

from extensions import db
from models import User
from services.audit_service import add_audit_log
from web import bp
from web.api import Api
from web.security import current_admin, end_session, login_required, safe_next, start_session

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
    add_audit_log("user", user.id, "web_login", None, actor=user)
    db.session.commit()
    return redirect(next_url or url_for("web.panel"))


@bp.post("/logout")
@login_required
def logout():
    end_session()
    flash("Cerraste la sesión.", "success")
    return redirect(url_for("web.login"))
