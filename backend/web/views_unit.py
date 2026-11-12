"""Datos de la unidad en la web (HU-077): nombre, NIT, dirección, teléfono de portería y logo.

La web solo reúne lo que escribió la administración y lo manda a la API (que revisa el NIT, el
teléfono y la imagen del logo). El nombre y el logo se ven en el encabezado de toda la web y en la
pantalla de inicio de sesión; el resto de los datos los ven los residentes en la app.
"""

import base64

from flask import abort, flash, g, redirect, render_template, request, url_for

from services import unit_service
from web import bp
from web.api import Api
from web.forms import checked, text
from web.security import login_required

#: Los campos de texto del formulario, con el nombre con que los recibe la API.
TEXT_FIELDS = ("name", "nit", "address", "portalPhone")


def _logo_upload():
    """El archivo del logo que se eligió en el formulario, o None si no se eligió ninguno."""
    upload = request.files.get("logo")
    return upload if upload is not None and upload.filename else None


def _body(upload):
    """Lo que escribió la administración, listo para la API.

    Un campo vacío se manda como null: así se borra el dato. El logo viaja como imagen en texto
    («data:image/png;base64,…»), igual que los adjuntos de la app.
    """
    body = {key: text(key) or None for key in TEXT_FIELDS}
    if upload is not None:
        # Se lee un byte más que el máximo: alcanza para que la API diga que pesa demasiado.
        raw = upload.read(unit_service.MAX_LOGO_BYTES + 1)
        kind = unit_service.sniff_logo_type(raw) or "application/octet-stream"
        body["logo"] = f"data:{kind};base64,{base64.b64encode(raw).decode()}"
    elif checked("removeLogo"):
        body["logo"] = None
    return body


def _page(unit, values, status=200):
    return render_template("web/unit_form.html", unit=unit, values=values), status


@bp.route("/unidad", methods=("GET", "POST"))
@login_required
def unit_data():
    api = Api(g.web_user)
    if request.method == "POST":
        upload = _logo_upload()
        result = api.put("/api/admin/unit-info", _body(upload))
        if result.ok:
            flash("Datos de la unidad guardados.", "success")
            return redirect(url_for("web.unit_data"))
        flash(result.error, "error")
        if upload is not None:
            flash("Vuelve a elegir el logo: el navegador no conserva el archivo cuando se rechaza el formulario.", "error")
        current = api.get("/api/unit-info")
        unit = current.get("unit") if current.ok else unit_service.BLANK_UNIT
        return _page(unit, {key: text(key) for key in TEXT_FIELDS}, result.status)

    current = api.get("/api/unit-info")
    if not current.ok:
        flash(current.error, "error")
    unit = current.get("unit") if current.ok else unit_service.BLANK_UNIT
    return _page(unit, {
        "name": unit["name"] or "",
        "nit": unit["nit"] or "",
        "address": unit["address"] or "",
        "portalPhone": unit["portalPhone"] or "",
    })


@bp.get("/unidad/logo")
def unit_logo():
    """El logo de la unidad. Lo ve cualquiera, también quien aún no inició sesión: sale en esa pantalla.

    El resto de los datos (NIT, dirección, teléfono) no se muestran sin sesión.
    """
    response = unit_service.logo_response()
    if response is None:
        abort(404)
    return response
