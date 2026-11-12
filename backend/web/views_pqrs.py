"""PQRS en la web (HU-078): la bandeja con la solicitud abierta al lado (DEC-097 y UI-103).

Son las mismas reglas de la app (RN-024: no se cambia el estado sin escribir una respuesta; la
respuesta por lotes solo sirve para PQRS del mismo tipo): la web reúne lo que escribió la
administración y lo manda a la API. En la pantalla ancha la bandeja y la solicitud se ven juntas; en
la angosta (celular o ventana pequeña) son dos pantallas, con un enlace para volver.

Las fotos, videos y audios de las PQRS no viajan dentro de la página: cada uno se pide aparte a una
ruta que solo entrega imágenes, videos y audios, con una política de seguridad que no deja ejecutar
nada (ver ``_file``).
"""

import hashlib

from flask import Response, abort, flash, g, redirect, render_template, request, url_for

from services import pqrs_service
from web import bp
from web.api import Api
from web.forms import compact, number, text
from web.security import login_required
from web.support import fetch_all
from web.texts import PQRS_STATUSES, plural

#: Filas de la bandeja por página.
PAGE_SIZE = 15

#: Los tipos de PQRS que ofrece la app (PqrsScreen.kt).
CATEGORIES = ("Petición", "Queja", "Reclamo", "Sugerencia", "Daño")

STATUS_OPTIONS = tuple((key, label) for key, (label, _tone) in PQRS_STATUSES.items())

#: Del color más urgente al menos urgente, con las palabras del semáforo de la app.
DEADLINE_OPTIONS = (("rojo", "Vencida"), ("amarillo", "Por vencer"), ("verde", "En plazo"))

#: La API solo deja responder por lotes con estos dos estados.
BATCH_STATUS_OPTIONS = tuple(option for option in STATUS_OPTIONS if option[0] != "abierta")

#: Política de seguridad de un archivo adjunto: no puede cargar ni ejecutar nada, aunque alguien
#: haya guardado como «imagen» otra cosa. (GitHub entrega así el contenido de los usuarios.)
FILE_POLICY = "default-src 'none'; style-src 'unsafe-inline'; sandbox"


# --- Lo que se pide en la URL -------------------------------------------------------------------

def _filters():
    """Los filtros de la bandeja; un valor desconocido se ignora."""
    state = request.args.get("estado", "")
    category = request.args.get("tipo", "")
    deadline = request.args.get("plazo", "")
    return {
        "q": (request.args.get("q") or "").strip(),
        "estado": state if state in dict(STATUS_OPTIONS) else "",
        "tipo": category if category in CATEGORIES else "",
        "plazo": deadline if deadline in dict(DEADLINE_OPTIONS) else "",
        "archivadas": "1" if request.args.get("archivadas") == "1" else "",
    }


def _list_args():
    """Lo que hay que conservar en los enlaces y formularios para volver a la misma bandeja."""
    args = {key: value for key, value in _filters().items() if value}
    page = request.args.get("page", type=int)
    if page and page > 1:
        args["page"] = page
    return args


# --- La bandeja y la solicitud -------------------------------------------------------------------

def _thread(pqrs):
    """La conversación sin su primer mensaje cuando este solo repite la solicitud (que ya se muestra arriba)."""
    messages = list(pqrs.get("messages") or [])
    if messages:
        first = messages[0]
        same_text = (first.get("message") or "") == (pqrs.get("message") or "")
        if same_text and (pqrs.get("hasMedia") or not first.get("hasMedia")):
            messages = messages[1:]
    return messages


def _default_reply(pqrs):
    """Una PQRS abierta se contesta, casi siempre, pasándola a «en proceso»; las demás conservan su estado."""
    status = pqrs.get("status") if pqrs else "en_proceso"
    return {"status": "en_proceso" if status == "abierta" else status, "adminResponse": ""}


def _inbox(selected_id=None, reply=None, batch=None, status=200):
    """La bandeja con los filtros de la URL y, si se pide, la solicitud abierta al lado."""
    api = Api(g.web_user)
    filters = _filters()
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    result = api.get(
        "/api/pqrs", view="summary", status=filters["estado"], category=filters["tipo"],
        semaphore=filters["plazo"], search=filters["q"],
        includeArchived="true" if filters["archivadas"] else "", page=page, pageSize=PAGE_SIZE,
    )
    if not result.ok:
        flash(result.error, "error")
    total_pages = result.get("totalPages", 1) or 1
    if request.method == "GET" and result.ok and not result.get("pqrs") and page > 1:
        # Un enlace viejo a una página que ya no existe lleva a la última.
        return redirect(url_for(request.endpoint, **{**(request.view_args or {}), **_list_args(), "page": total_pages}))

    selected = None
    if selected_id is not None:
        found = api.get(f"/api/pqrs/{selected_id}", view="summary")
        if found.status == 404:
            abort(404)
        if found.ok:
            selected = found.get("pqrs")
        else:
            flash(found.error, "error")

    return render_template(
        "web/pqrs.html",
        items=result.get("pqrs", []), total=result.get("total", 0), page=page, pages=total_pages,
        filters=filters, list_args=_list_args(),
        selected=selected, thread=_thread(selected) if selected else [],
        reply=reply or _default_reply(selected),
        batch=batch or {"ids": [], "status": "en_proceso", "message": "", "open": False},
        status_options=STATUS_OPTIONS, deadline_options=DEADLINE_OPTIONS, category_options=CATEGORIES,
        status_reply_options=STATUS_OPTIONS, status_batch_options=BATCH_STATUS_OPTIONS,
    ), status


@bp.get("/pqrs")
@login_required
def pqrs_list():
    return _inbox()


@bp.get("/pqrs/<int:pqrs_id>")
@login_required
def pqrs_detail(pqrs_id):
    return _inbox(pqrs_id)


# --- Responder -------------------------------------------------------------------------------------

@bp.route("/pqrs/<int:pqrs_id>/responder", methods=("GET", "POST"))
@login_required
def pqrs_respond(pqrs_id):
    """Cambia el estado y manda la respuesta al residente, con las reglas de la app (RN-024)."""
    if request.method == "GET":
        # Un enlace a esta dirección (por ejemplo, el de otra página de la bandeja tras un error) vuelve a la solicitud.
        return redirect(url_for("web.pqrs_detail", pqrs_id=pqrs_id, **_list_args()))
    reply = {"status": text("status"), "adminResponse": text("adminResponse")}
    result = Api(g.web_user).put(f"/api/pqrs/{pqrs_id}/respond", compact(reply))
    if result.ok:
        flash("PQRS actualizada.", "success")
        return redirect(url_for("web.pqrs_detail", pqrs_id=pqrs_id, **_list_args()))
    flash(result.error, "error")
    return _inbox(pqrs_id, reply=reply, status=result.status)


@bp.route("/pqrs/lote", methods=("GET", "POST"))
@login_required
def pqrs_batch():
    """Una misma respuesta para varias PQRS marcadas en la bandeja (deben ser del mismo tipo)."""
    if request.method == "GET":
        return redirect(url_for("web.pqrs_list", **_list_args()))
    # Lo que no es un número se manda tal cual: la API lo rechaza con su mensaje.
    ids = [int(value) if value.isascii() and value.isdigit() else value for value in request.form.getlist("ids")]
    chosen = {"ids": ids, "status": text("batchStatus") or "en_proceso", "message": text("batchMessage"), "open": True}
    body = compact({"pqrsIds": ids, "status": text("batchStatus"), "message": chosen["message"]})
    result = Api(g.web_user).post("/api/pqrs/batch/respond", body)
    if result.ok:
        flash(f"{plural(result.get('updatedCount', len(ids)), 'PQRS actualizada', 'PQRS actualizadas')}.", "success")
        return redirect(url_for("web.pqrs_list", **_list_args()))
    flash(result.error, "error")
    return _inbox(batch=chosen, status=result.status)


# --- Registrar a nombre de un residente --------------------------------------------------------------

def _new_page(api, values, status=200):
    residents, failure = fetch_all(api, "/api/admin/users", "users", role="RESIDENT", isActive="true")
    if failure is not None:
        flash(failure.error, "error")
    options = [
        (item["id"], f"{item['fullName']} · {item['apartment']}" if item.get("apartment") else item["fullName"])
        for item in residents
    ]
    return render_template(
        "web/pqrs_new.html", values=values, resident_options=options,
        category_pairs=[(name, name) for name in CATEGORIES],
    ), status


@bp.route("/pqrs/nueva", methods=("GET", "POST"))
@login_required
def pqrs_new():
    """Registra una PQRS a nombre de un residente; la app le avisa y queda anotado que la registró la administración."""
    api = Api(g.web_user)
    if request.method == "POST":
        values = {key: text(key) for key in ("residentId", "category", "subject", "message")}
        body = compact({
            "residentId": number("residentId"), "category": values["category"],
            "subject": values["subject"], "message": values["message"],
        })
        result = api.post("/api/pqrs", body)
        if result.ok:
            flash("PQRS registrada a nombre del residente. Se le avisó en la app.", "success")
            created = result.get("pqrs", {}).get("id")
            return redirect(url_for("web.pqrs_detail", pqrs_id=created) if created else url_for("web.pqrs_list"))
        flash(result.error, "error")
        return _new_page(api, values, result.status)
    return _new_page(api, {"residentId": "", "category": CATEGORIES[0], "subject": "", "message": ""})


# --- Adjuntos ------------------------------------------------------------------------------------------

def _file(found):
    """La respuesta con un adjunto, o un 404 si no existe o no es una imagen, un video o un audio.

    Lleva una política de seguridad propia (sin scripts, sin cargar nada y en una caja aislada) y se
    puede pedir por partes, para que un video avance y retroceda.
    """
    if found is None:
        abort(404)
    raw, mime = found
    response = Response(raw, mimetype=mime)
    response.set_etag(hashlib.sha256(raw).hexdigest())
    response.headers["Content-Security-Policy"] = FILE_POLICY
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    return response.make_conditional(request, accept_ranges=True, complete_length=len(raw))


@bp.get("/pqrs/<int:pqrs_id>/adjunto")
@login_required
def pqrs_attachment(pqrs_id):
    """El adjunto con el que el residente radicó la PQRS."""
    return _file(pqrs_service.attachment(pqrs_id))


@bp.get("/pqrs/<int:pqrs_id>/mensajes/<int:message_id>/adjunto")
@login_required
def pqrs_message_attachment(pqrs_id, message_id):
    """El adjunto de un mensaje de la conversación."""
    return _file(pqrs_service.attachment(pqrs_id, message_id))
