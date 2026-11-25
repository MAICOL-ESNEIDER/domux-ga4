"""Documentos de la unidad en la web (DEC-032).

La administración sube aquí el manual de convivencia, las reglas, los presupuestos aprobados, los históricos de
gastos y las actas, y marca quién puede verlos en la app: propietarios, arrendatarios, otros residentes o
portería. Sin ninguna marca el documento es solo de la administración. Nada se borra: un documento retirado deja
de verse para los demás, pero queda guardado y se puede volver a publicar.

La web solo reúne lo que escribió la administración y lo manda a la API (que revisa el archivo por sus primeros
bytes, el título y los públicos, y anota todo en la auditoría). Manda solo lo que cambió.
"""

from flask import abort, flash, g, redirect, render_template, request, url_for

from errors import ApiError
from models import DOCUMENT_AUDIENCES, DOCUMENT_CATEGORIES
from services import document_service
from services.document_service import DESCRIPTION_MAX, TITLE_MAX
from web import bp, texts
from web.api import Api
from web.forms import checked, compact, text
from web.security import login_required
from web.support import flash_result
from web.uploads import (
    MAX_MEDIA_BYTES,
    UNIT_DOCUMENT_ACCEPT,
    UNIT_DOCUMENT_FORMATS_TEXT,
    UploadError,
    read_unit_document,
)

#: Cada público con el nombre de su casilla en el formulario.
AUDIENCE_FIELDS = {key: f"publico_{key}" for key in DOCUMENT_AUDIENCES}

#: Lo que se explica bajo cada casilla.
AUDIENCE_HELP = {
    "propietario": "Los residentes que son dueños de su apartamento.",
    "arrendatario": "Los residentes que lo tienen en arriendo.",
    "residente": "Los demás residentes, por ejemplo familiares que viven allí.",
    "guardia": "La portería, en la tablet de la entrada.",
}


def _documents(api, category=None):
    """Los documentos (también los retirados) que entrega la API; si falla, un aviso y una lista vacía."""
    result = api.get("/api/documents", includeRetired="true", category=category)
    if not result.ok:
        flash(result.error, "error")
    return result.get("documents", [])


def _document(api, document_id):
    """El documento con ese id (vigente o retirado); si no existe, la página «no encontrada»."""
    result = api.get(f"/api/documents/{document_id}")
    if not result.ok:
        abort(404)
    return result.get("document")


def _summary(document):
    """Un documento con los textos que muestra la lista."""
    audiences = document["visibleTo"]
    return {
        **document,
        "audienceNames": [DOCUMENT_AUDIENCES[key] for key in audiences],
        "size": texts.size_text(document["sizeBytes"]),
        "created": texts.date_es(document["createdAt"]),
        "retiredOn": texts.date_es(document["retiredAt"]),
    }


def _page(document, values, status=200):
    """El formulario de un documento; sin ``document`` es el de uno nuevo."""
    return render_template(
        "web/document_form.html", document=document, values=values,
        category_options=list(DOCUMENT_CATEGORIES.items()),
        audiences=[(key, label, AUDIENCE_FIELDS[key], AUDIENCE_HELP[key]) for key, label in DOCUMENT_AUDIENCES.items()],
        max_title=TITLE_MAX, max_description=DESCRIPTION_MAX,
        accept=UNIT_DOCUMENT_ACCEPT, formats=UNIT_DOCUMENT_FORMATS_TEXT, max_mb=MAX_MEDIA_BYTES // (1024 * 1024),
    ), status


def _values_of(document):
    """Lo que muestra el formulario de un documento que ya existe."""
    return {
        "title": document["title"], "description": document["description"] or "", "category": document["category"],
        "audiences": list(document["visibleTo"]), "notify": False,
    }


def _posted_values():
    """Lo que llegó en el formulario: textos, los públicos marcados y si se avisa."""
    return {
        "title": text("title"), "description": text("description"), "category": text("category"),
        "audiences": [key for key, field in AUDIENCE_FIELDS.items() if checked(field)],
        "notify": checked("notify"),
    }


@bp.get("/documentos")
@login_required
def documents_list():
    category = request.args.get("tipo") or ""
    if category not in DOCUMENT_CATEGORIES:
        category = ""
    found = [_summary(item) for item in _documents(Api(g.web_user), category or None)]
    return render_template(
        "web/documents.html",
        documents=[item for item in found if not item["isRetired"]],
        retired=[item for item in found if item["isRetired"]],
        category=category, category_options=list(DOCUMENT_CATEGORIES.items()),
    )


@bp.route("/documentos/nuevo", methods=("GET", "POST"))
@login_required
def document_new():
    if request.method == "GET":
        return _page(None, {
            "title": "", "description": "", "category": "convivencia", "audiences": ["propietario", "arrendatario"],
            "notify": True,
        })

    values = _posted_values()
    try:
        file, file_name = read_unit_document(request.files.get("file"))
    except UploadError as problem:
        flash(str(problem), "error")
        return _page(None, values, 400)
    body = compact({
        "title": values["title"], "description": values["description"], "category": values["category"],
        "file": file, "fileName": file_name,
    })
    body["visibleTo"] = values["audiences"]
    body["notify"] = values["notify"]
    result = Api(g.web_user).post("/api/documents", body)
    if result.ok:
        notified = result.get("notified", 0)
        message = "Documento publicado."
        if values["audiences"]:
            message += " Las personas que marcaste ya lo ven en la app."
        else:
            message += " Solo la administración lo ve."
        if notified:
            message += f" Se avisó a {texts.plural(notified, 'persona', 'personas')}."
        flash(message, "success")
        return redirect(url_for("web.documents_list"))
    flash(result.error, "error")
    flash("Vuelve a elegir el archivo: el navegador no lo conserva cuando se rechaza el formulario.", "error")
    return _page(None, values, result.status)


@bp.route("/documentos/<int:document_id>/editar", methods=("GET", "POST"))
@login_required
def document_edit(document_id):
    api = Api(g.web_user)
    document = _document(api, document_id)
    if document["isRetired"]:
        flash("Ese documento está retirado. Vuelve a publicarlo para poder editarlo.", "error")
        return redirect(url_for("web.documents_list"))
    if request.method == "GET":
        return _page(document, _values_of(document))

    values = _posted_values()
    changes = {}
    if values["title"] != document["title"]:
        changes["title"] = values["title"]
    if values["description"] != (document["description"] or ""):
        changes["description"] = values["description"] or None
    if values["category"] != document["category"]:
        changes["category"] = values["category"]
    if sorted(values["audiences"]) != sorted(document["visibleTo"]):
        changes["visibleTo"] = values["audiences"]
    if not changes:
        flash("No cambiaste nada.", "info")
        return _page(document, values)
    result = api.put(f"/api/documents/{document_id}", changes)
    if result.ok:
        flash("Documento actualizado.", "success")
        return redirect(url_for("web.documents_list"))
    flash(result.error, "error")
    return _page(document, values, result.status)


@bp.post("/documentos/<int:document_id>/retirar")
@login_required
def document_retire(document_id):
    flash_result(Api(g.web_user).delete(f"/api/documents/{document_id}"), "Documento retirado.")
    return redirect(url_for("web.documents_list"))


@bp.post("/documentos/<int:document_id>/publicar")
@login_required
def document_restore(document_id):
    flash_result(Api(g.web_user).post(f"/api/documents/{document_id}/restore"), "Documento publicado de nuevo.")
    return redirect(url_for("web.documents_list"))


@bp.get("/documentos/<int:document_id>/archivo")
@login_required
def document_file(document_id):
    """El archivo del documento, vigente o retirado. Un PDF baja al equipo; una imagen se ve en la página."""
    try:
        document = document_service.find_any(document_id)
    except ApiError:  # no existe: aquí es la página «no encontrada»
        abort(404)
    return document_service.file_response(document, "attachment" if document.kind == "pdf" else "inline")
