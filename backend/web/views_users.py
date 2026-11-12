"""Usuarios en la web (HU-075): crear, editar, desactivar y restablecer contraseñas desde una tabla con filtros.

Son las mismas reglas de la app (RN-001, RN-004 y RN-008): la web solo reúne lo que escribió la
administración y lo manda a la API. Nada se borra: desactivar a alguien cierra su acceso y deja su
historial (ADR-013).
"""

from flask import abort, flash, g, redirect, render_template, request, url_for

from web import bp
from web.api import Api
from web.forms import checked, compact, number, text
from web.security import login_required
from web.support import fetch_all, flash_result

PAGE_SIZE = 25

#: Los mismos nombres de rol y de tipo de residente que muestra la app.
ROLE_OPTIONS = (("RESIDENT", "Residente"), ("GUARD", "Portería"), ("ADMIN", "Administración"))
OCCUPANCY_OPTIONS = (
    ("propietario", "Propietario"),
    ("arrendatario", "Arrendatario"),
    ("residente", "Residente"),
)
STATE_OPTIONS = (("activos", "Activos"), ("inactivos", "Inactivos"))


# --- Lista con filtros --------------------------------------------------------------------------

@bp.get("/usuarios")
@login_required
def users_list():
    search = (request.args.get("q") or "").strip()
    role = request.args.get("rol", "")
    state = request.args.get("estado", "")
    page = request.args.get("page", 1, type=int)
    params = {
        "search": search,
        "role": role if role in dict(ROLE_OPTIONS) else "",
        "page": max(page or 1, 1),
        "pageSize": PAGE_SIZE,
    }
    if state in dict(STATE_OPTIONS):
        params["isActive"] = "true" if state == "activos" else "false"
    result = Api(g.web_user).get("/api/admin/users", **params)
    if not result.ok:
        flash(result.error, "error")
    total_pages = result.get("totalPages", 1) or 1
    if result.ok and not result.get("users") and params["page"] > 1:
        # Un enlace viejo a una página que ya no existe lleva a la última.
        return redirect(url_for("web.users_list", **{**request.args.to_dict(), "page": total_pages}))
    return render_template(
        "web/users.html",
        users=result.get("users", []), total=result.get("total", 0), page=params["page"], pages=total_pages,
        filters={"q": search, "rol": params["role"], "estado": state if state in dict(STATE_OPTIONS) else ""},
        role_options=ROLE_OPTIONS, state_options=STATE_OPTIONS,
    )


# --- Crear y editar -----------------------------------------------------------------------------

def _user_body(creating, current=None):
    """Lo que la persona escribió, listo para la API (los campos vacíos no viajan)."""
    role = text("role")
    body = {
        "role": role,
        "name": text("name"),
        "lastName": text("lastName"),
        "email": text("email"),
        "phone": text("phone"),
        "documentId": text("documentId"),
        "birthDate": text("birthDate"),
    }
    if creating:
        # La contraseña va tal cual, sin recortar: la API revisa que sea fuerte.
        body["password"] = request.form.get("password", "")
    if role == "RESIDENT":
        body["apartmentId"] = number("apartmentId")
        body["occupancyType"] = text("occupancyType")
        body["parentalConsent"] = checked("parentalConsent")
        if creating or (current is not None and current["role"] != "RESIDENT"):
            body["dataProcessingConsent"] = checked("dataProcessingConsent")
    return compact(body)


def _values_of(user):
    """Los datos de un usuario con los nombres de los campos del formulario."""
    return {
        "role": user["role"],
        "name": user["firstName"],
        "lastName": user["lastName"],
        "email": user["email"],
        "phone": user["phone"],
        "documentId": user["documentId"],
        "birthDate": user["birthDate"] or "",
        "apartmentId": user["apartmentId"],
        "occupancyType": user["occupancyType"],
        "parentalConsent": user["parentalConsent"],
    }


def _values_of_form():
    """Lo que había escrito el formulario, para no perderlo cuando la API lo rechaza."""
    form = request.form
    values = {key: form.get(key, "") for key in (
        "role", "name", "lastName", "email", "phone", "documentId", "birthDate", "apartmentId", "occupancyType",
    )}
    values["parentalConsent"] = "parentalConsent" in form
    values["dataProcessingConsent"] = "dataProcessingConsent" in form
    return values


def _render_form(api, user, values, status=200):
    apartments, failure = fetch_all(api, "/api/admin/apartments", "apartments")
    if failure is not None:
        flash(failure.error, "error")
    return render_template(
        "web/user_form.html",
        user=user, values=values, role_options=ROLE_OPTIONS, occupancy_options=OCCUPANCY_OPTIONS,
        apartment_options=[(item["id"], item["label"]) for item in apartments],
    ), status


@bp.route("/usuarios/nuevo", methods=("GET", "POST"))
@login_required
def user_new():
    api = Api(g.web_user)
    if request.method == "POST":
        result = api.post("/api/admin/users", _user_body(creating=True))
        if result.ok:
            flash("Usuario creado.", "success")
            return redirect(url_for("web.user_edit", user_id=result.get("user", {}).get("id")))
        flash(result.error, "error")
        return _render_form(api, None, _values_of_form(), result.status)
    return _render_form(api, None, {"role": "RESIDENT", "occupancyType": "propietario"})


def _load_user(api, user_id):
    found = api.get(f"/api/admin/users/{user_id}")
    if found.status == 404:
        abort(404)
    if not found.ok:
        flash(found.error, "error")
        return None
    return found.get("user")


@bp.route("/usuarios/<int:user_id>", methods=("GET", "POST"))
@login_required
def user_edit(user_id):
    api = Api(g.web_user)
    user = _load_user(api, user_id)
    if user is None:
        return redirect(url_for("web.users_list"))
    if request.method == "POST":
        result = api.put(f"/api/admin/users/{user_id}", _user_body(creating=False, current=user))
        if result.ok:
            flash("Cambios guardados.", "success")
            return redirect(url_for("web.user_edit", user_id=user_id))
        flash(result.error, "error")
        return _render_form(api, user, {**_values_of(user), **_values_of_form()}, result.status)
    return _render_form(api, user, _values_of(user))


# --- Estado, contraseña y PIN -------------------------------------------------------------------

@bp.post("/usuarios/<int:user_id>/estado")
@login_required
def user_state(user_id):
    """Desactiva o reactiva una cuenta; desactivar la cierra pero deja todo su historial."""
    active = request.form.get("activo") == "1"
    result = Api(g.web_user).put(f"/api/admin/users/{user_id}", {"isActive": active})
    if result.ok:
        flash(
            "Usuario reactivado: ya puede entrar de nuevo." if active
            else "Usuario desactivado: ya no puede entrar y su historial se conserva.",
            "success",
        )
    else:
        flash_result(result)
    return redirect(url_for("web.user_edit", user_id=user_id))


@bp.post("/usuarios/<int:user_id>/clave")
@login_required
def user_password(user_id):
    """Restablece la contraseña; la nueva viaja directo a la API y nunca se vuelve a mostrar."""
    password = request.form.get("password", "")
    if password != request.form.get("password2", ""):
        flash("Las dos contraseñas no coinciden. Escríbelas de nuevo.", "error")
    else:
        result = Api(g.web_user).put(f"/api/admin/users/{user_id}/password", {"password": password})
        if result.ok:
            flash("Contraseña restablecida. Dásela a la persona por un medio seguro.", "success")
        else:
            flash_result(result)
    return redirect(url_for("web.user_edit", user_id=user_id))


@bp.post("/usuarios/<int:user_id>/pin")
@login_required
def user_pin(user_id):
    """Asigna o cambia el PIN de 4 dígitos con el que un guardia toma el turno (HU-010)."""
    result = Api(g.web_user).put(f"/api/admin/users/{user_id}/pin", compact({"pin": text("pin")}))
    if result.ok:
        flash("PIN asignado. El guardia lo usa para tomar el turno.", "success")
    else:
        flash_result(result)
    return redirect(url_for("web.user_edit", user_id=user_id))
