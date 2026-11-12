"""Comunicados en la web (HU-080): publicar, ver cuántos apartamentos los leyeron y retirarlos.

Son las mismas reglas de la app (categoría obligatoria, toda la unidad o una torre, fecha de vencimiento,
foto, video o audio adjunto): la web reúne lo que escribió o eligió la administración y lo manda a la API.
Un comunicado nunca se borra: al retirarlo deja de verse en la app, pero queda guardado con quién y cuándo
lo retiró (ADR-013). En la pantalla ancha la lista y el comunicado se ven juntos; en la angosta (celular o
ventana pequeña) son dos pantallas, con un enlace para volver.

El adjunto no viaja dentro de la página: se pide aparte a una ruta que solo entrega imágenes, videos y
audios (ver ``file_response``).
"""

from flask import abort, flash, g, redirect, render_template, request, url_for

from models import ANNOUNCEMENT_CATEGORIES
from services import announcement_view
from time_utils import colombia_today
from web import bp
from web.api import Api
from web.forms import compact, number, text
from web.security import login_required, safe_next
from web.support import file_response
from web.uploads import MAX_MEDIA_BYTES, MEDIA_ACCEPT, MEDIA_FORMATS_TEXT, UploadError, read_media

#: Filas de la lista por página.
PAGE_SIZE = 15

#: Las pestañas: clave en la URL, texto y clave del número en ``counts``. La primera se abre sola.
TABS = (
    ("vigentes", "Vigentes", "current"),
    ("archivados", "Archivados", "archived"),
)
DEFAULT_TAB = TABS[0][0]
_TAB_KEYS = tuple(key for key, _label, _count in TABS)

#: Lo que se lee cuando una pestaña no tiene comunicados.
EMPTY_TEXTS = {
    "vigentes": "No hay comunicados vigentes.",
    "archivados": "No hay comunicados archivados: son los que ya pasaron su fecha de vencimiento.",
}

#: Los campos de texto del formulario de un comunicado nuevo.
FORM_FIELDS = ("title", "message", "category", "towerId", "expiresAt", "eventDate", "eventTime")


# --- Lo que se pide en la URL -------------------------------------------------------------------

def _tower_filter(value):
    """La torre de la URL («unit» para toda la unidad, o el número de una torre); lo demás se ignora."""
    if value == announcement_view.WHOLE_UNIT or (value.isascii() and value.isdigit() and int(value) > 0):
        return value
    return ""


def _filters():
    """Los filtros de la lista; un valor desconocido se ignora."""
    tab = request.args.get("estado", "")
    category = request.args.get("categoria", "")
    return {
        "q": (request.args.get("q") or "").strip(),
        "estado": tab if tab in _TAB_KEYS else DEFAULT_TAB,
        "categoria": category if category in ANNOUNCEMENT_CATEGORIES else "",
        "torre": _tower_filter(request.args.get("torre", "")),
    }


def _args(filters, page=None):
    """Los filtros que cambian la lista, listos para un enlace (la pestaña que se abre sola no se escribe)."""
    args = {key: value for key, value in filters.items() if value}
    if args.get("estado") == DEFAULT_TAB:
        del args["estado"]
    if page and page > 1:
        args["page"] = page
    return args


def _list_args():
    """Lo que hay que conservar en los enlaces y formularios para volver a la misma lista."""
    return _args(_filters(), request.args.get("page", type=int))


def _tabs(filters, counts):
    """Las pestañas con su número y su enlace; cada una conserva los demás filtros."""
    others = {key: value for key, value in filters.items() if key != "estado"}
    return [
        {
            "key": key,
            "label": label,
            "count": counts.get(count_key, 0),
            "url": url_for("web.announcements_list", **_args({**others, "estado": key})),
            "current": key == filters["estado"],
        }
        for key, label, count_key in TABS
    ]


def _towers(api):
    """Las torres de la unidad como opciones de una lista desplegable: ``[(id, nombre)]``."""
    result = api.get("/api/admin/towers")
    if not result.ok:
        flash(result.error, "error")
    return [(str(tower["id"]), tower["name"]) for tower in result.get("towers", [])]


# --- La lista y el comunicado ---------------------------------------------------------------------

def _page(selected_id=None):
    """La lista con los filtros de la URL y, si se pide, el comunicado abierto al lado."""
    api = Api(g.web_user)
    filters = _filters()
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    result = api.get(
        "/api/announcements", view="summary", archived="true" if filters["estado"] == "archivados" else "",
        category=filters["categoria"], towerId=filters["torre"], search=filters["q"],
        page=page, pageSize=PAGE_SIZE,
    )
    if not result.ok:
        flash(result.error, "error")
    total_pages = result.get("totalPages", 1) or 1
    if request.method == "GET" and result.ok and not result.get("announcements") and page > 1:
        # Un enlace viejo a una página que ya no existe lleva a la última.
        return redirect(url_for(request.endpoint, **{**(request.view_args or {}), **_args(filters, total_pages)}))

    selected = None
    if selected_id is not None:
        found = api.get(f"/api/announcements/{selected_id}", view="summary")
        if found.status == 404:
            abort(404)
        if found.ok:
            selected = found.get("announcement")
        else:
            flash(found.error, "error")

    return render_template(
        "web/announcements.html",
        items=result.get("announcements", []), total=result.get("total", 0), page=page, pages=total_pages,
        filters=filters, list_args=_list_args(), tabs=_tabs(filters, result.get("counts", {})),
        empty_text=EMPTY_TEXTS[filters["estado"]], selected=selected,
        category_options=list(ANNOUNCEMENT_CATEGORIES.items()),
        tower_options=[(announcement_view.WHOLE_UNIT, "Toda la unidad"), *_towers(api)],
    )


@bp.get("/comunicados")
@login_required
def announcements_list():
    return _page()


@bp.get("/comunicados/<int:announcement_id>")
@login_required
def announcement_detail(announcement_id):
    return _page(announcement_id)


# --- Publicar -----------------------------------------------------------------------------------------

def _new_page(towers, values, status=200):
    """El formulario de un comunicado nuevo, con lo que ya se escribió."""
    return render_template(
        "web/announcement_new.html", values=values, towers=towers,
        category_options=list(ANNOUNCEMENT_CATEGORIES.items()), today=colombia_today().isoformat(),
        media_accept=MEDIA_ACCEPT, media_formats=MEDIA_FORMATS_TEXT, media_mb=MAX_MEDIA_BYTES // (1024 * 1024),
    ), status


@bp.route("/comunicados/nuevo", methods=("GET", "POST"))
@login_required
def announcement_new():
    api = Api(g.web_user)
    towers = _towers(api)
    if request.method == "GET":
        return _new_page(towers, {key: "" for key in FORM_FIELDS})

    values = {key: text(key) for key in FORM_FIELDS}
    try:
        media = read_media(request.files.get("media"))
    except UploadError as problem:
        flash(str(problem), "error")
        return _new_page(towers, values, 400)
    body = compact({
        "title": values["title"], "message": values["message"], "category": values["category"],
        "towerId": number("towerId"), "expiresAt": values["expiresAt"], "eventDate": values["eventDate"],
        "eventTime": values["eventTime"],
    })
    if media is not None:
        body["mediaUrl"], body["mediaType"] = media
    result = api.post("/api/announcements", body)
    if result.ok:
        flash("Comunicado publicado. Los residentes lo ven en la app.", "success")
        published = result.get("announcement") or {}
        if "id" in published:
            return redirect(url_for("web.announcement_detail", announcement_id=published["id"]))
        return redirect(url_for("web.announcements_list"))
    flash(result.error, "error")
    if media is not None:
        flash("Vuelve a elegir el archivo: el navegador no lo conserva cuando se rechaza el formulario.", "error")
    return _new_page(towers, values, result.status)


# --- Retirar y adjunto --------------------------------------------------------------------------------

@bp.post("/comunicados/<int:announcement_id>/retirar")
@login_required
def announcement_retire(announcement_id):
    """Retira el comunicado: deja de verse en la app, pero queda guardado (nunca se borra)."""
    result = Api(g.web_user).put(f"/api/announcements/{announcement_id}/retire")
    if result.ok:
        flash(result.message or "Comunicado retirado.", "success")
    else:
        flash(result.error, "error")
    return redirect(safe_next(request.form.get("next")) or url_for("web.announcements_list"))


@bp.get("/comunicados/<int:announcement_id>/adjunto")
@login_required
def announcement_attachment(announcement_id):
    """El adjunto del comunicado (foto, video o audio)."""
    return file_response(announcement_view.attachment(announcement_id))
