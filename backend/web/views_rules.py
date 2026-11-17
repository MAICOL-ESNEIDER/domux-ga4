"""Reglas de la unidad en la web (DEC-032): plazos de PQRS, alertas de paquetes y parqueadero de visitantes.

Lo que la asamblea decide cada año (cuántos días tiene la administración para responder una PQRS, a qué hora
un paquete sin reclamar se pone naranja o roja, cuántos días puede quedarse el carro de un visitante) se cambia
aquí, sin tocar el código. Los cambios rigen desde que se guardan, también para lo que ya existe.

La web solo reúne lo que escribió la administración y lo manda a la API (que revisa cada valor y que todos tengan
sentido juntos). Manda solo lo que cambió, para que una regla que nadie tocó siga rigiendo con el valor de DOMUX
y para que la auditoría diga exactamente qué se cambió.
"""

from flask import flash, g, redirect, render_template, request, url_for

from services.unit_rules import (
    PACKAGE_ORANGE_LIMITS,
    PACKAGE_RED_LIMITS,
    PARKING_DAYS_LIMITS,
    PQRS_CATEGORIES,
    PQRS_TERM_LIMITS,
    PQRS_WARNING_LIMITS,
    default_rules,
)
from web import bp
from web.api import Api
from web.forms import number, text
from web.security import login_required

#: Las reglas de un solo número, con el nombre con que las recibe la API.
SIMPLE_FIELDS = (
    "pqrsTermDays", "pqrsWarningDays", "packageOrangeHours", "packageRedHours", "visitorParkingMaxDays",
)
#: Un campo por cada tipo de PQRS, en el orden de la app: («term_0», «Petición»), («term_1», «Queja»)…
CATEGORY_FIELDS = tuple((f"term_{index}", name) for index, name in enumerate(PQRS_CATEGORIES))

LIMITS = {
    "pqrsTermDays": PQRS_TERM_LIMITS,
    "pqrsWarningDays": PQRS_WARNING_LIMITS,
    "packageOrangeHours": PACKAGE_ORANGE_LIMITS,
    "packageRedHours": PACKAGE_RED_LIMITS,
    "visitorParkingMaxDays": PARKING_DAYS_LIMITS,
}
#: Para el plazo de un solo tipo de PQRS rige el mismo límite que para el plazo general.
CATEGORY_LIMITS = PQRS_TERM_LIMITS


def _fallback_view():
    """Si la API no responde, la página se dibuja con los valores de DOMUX para no quedar en blanco."""
    defaults = default_rules().to_dict()
    return {
        "rules": defaults, "defaults": defaults, "updatedAt": None, "updatedByName": None,
        "customized": {key: False for key in (*SIMPLE_FIELDS, "pqrsTermsByCategory")},
    }


def _current(api):
    """Lo que dice la API de las reglas; si falla, un aviso y la página con los valores de DOMUX."""
    result = api.get("/api/admin/unit-rules")
    if result.ok:
        return result.data
    flash(result.error, "error")
    return _fallback_view()


def _values(view):
    """Las reglas vigentes como las muestra el formulario: texto, y en blanco los tipos sin plazo propio."""
    rules = view["rules"]
    values = {key: str(rules[key]) for key in SIMPLE_FIELDS}
    terms = rules["pqrsTermsByCategory"]
    for field_id, name in CATEGORY_FIELDS:
        values[field_id] = str(terms[name]) if name in terms else ""
    return values


def _posted_values():
    """Lo que llegó en el formulario, como texto."""
    return {key: text(key) for key in (*SIMPLE_FIELDS, *(field_id for field_id, _name in CATEGORY_FIELDS))}


def _changes(view):
    """Solo las reglas que cambiaron frente a las vigentes; un campo vacío devuelve esa regla al valor de DOMUX."""
    rules, customized = view["rules"], view["customized"]
    changes = {}
    for key in SIMPLE_FIELDS:
        typed = number(key)  # vacío es None; lo que no es un número viaja tal cual y la API lo rechaza
        if typed is None:
            if customized[key]:
                changes[key] = None
        elif typed != rules[key]:
            changes[key] = typed
    terms = {name: number(field_id) for field_id, name in CATEGORY_FIELDS if number(field_id) is not None}
    if terms != rules["pqrsTermsByCategory"]:
        changes["pqrsTermsByCategory"] = terms or None
    return changes


def _page(view, values, status=200):
    return render_template(
        "web/rules.html", view=view, rules=view["rules"], defaults=view["defaults"], customized=view["customized"],
        values=values, limits=LIMITS, category_limits=CATEGORY_LIMITS, categories=CATEGORY_FIELDS,
    ), status


@bp.route("/reglas", methods=("GET", "POST"))
@login_required
def rules_page():
    api = Api(g.web_user)
    view = _current(api)
    if request.method == "GET":
        return _page(view, _values(view))

    values = _posted_values()
    changes = _changes(view)
    if not changes:
        flash("No cambiaste ninguna regla.", "info")
        return _page(view, values)
    result = api.put("/api/admin/unit-rules", changes)
    if result.ok:
        flash("Reglas de la unidad guardadas. Ya rigen para todo, también para lo que estaba abierto.", "success")
        return redirect(url_for("web.rules_page"))
    flash(result.error, "error")
    return _page(view, values, result.status)


@bp.post("/reglas/restablecer")
@login_required
def rules_reset():
    """Devuelve todas las reglas al valor de DOMUX (el botón pide confirmación antes)."""
    body = {key: None for key in (*SIMPLE_FIELDS, "pqrsTermsByCategory")}
    result = Api(g.web_user).put("/api/admin/unit-rules", body)
    if result.ok:
        flash("Las reglas volvieron a los valores de DOMUX.", "success")
    else:
        flash(result.error, "error")
    return redirect(url_for("web.rules_page"))
