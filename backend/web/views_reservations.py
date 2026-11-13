"""Reservas en la web (HU-079): la lista por estado con la reserva abierta al lado (DEC-097 y UI-103).

Son las mismas reglas de la app (RN-019: una franja que ya ocupa una reserva aprobada no se vuelve a
aprobar; solo se aprueban o rechazan las reservas que esperan decisión; una conversación terminada ya
no recibe mensajes): la web reúne lo que eligió o escribió la administración y lo manda a la API. En
la pantalla ancha la lista y la reserva se ven juntas; en la angosta (celular o ventana pequeña) son
dos pantallas, con un enlace para volver.

Los adjuntos de la conversación (fotos, videos y audios) no viajan dentro de la página: cada uno se
pide aparte a una ruta que solo entrega imágenes, videos y audios (ver ``file_response``).
"""

from datetime import date

from flask import abort, flash, g, redirect, render_template, request, url_for

from services import reservation_view
from services.reservation_service import CLOSED_RESERVATION_STATUSES, PENDING_RESERVATION_STATUSES
from web import bp
from web.api import Api
from web.exports import RESERVATION_COLUMNS, excel_download, filters_text
from web.forms import compact, text
from web.security import login_required, safe_next
from web.support import file_response, flash_result

#: Filas de la lista por página.
PAGE_SIZE = 15

#: Lo que la administración puede decidir sobre una reserva pendiente.
DECISIONS = {"aprobada": "aprobada", "rechazada": "rechazada"}

#: Las pestañas por estado: clave en la URL, texto, estado que se le pide a la API y clave del
#: número en ``counts``. La primera es la que se abre sola: lo que espera la decisión.
TABS = (
    ("por_aprobar", "Por aprobar", "por_aprobar", "pending"),
    ("aprobada", "Aprobadas", "aprobada", "approved"),
    ("rechazada", "Rechazadas", "rechazada", "rejected"),
    ("cancelada", "Canceladas", "cancelada", "cancelled"),
    ("todas", "Todas", "", "all"),
)
DEFAULT_TAB = TABS[0][0]
_TAB_STATUS = {key: status for key, _label, status, _count in TABS}

#: Lo que se lee cuando una pestaña no tiene reservas.
EMPTY_TEXTS = {
    "por_aprobar": "No hay reservas esperando decisión.",
    "aprobada": "No hay reservas aprobadas.",
    "rechazada": "No hay reservas rechazadas.",
    "cancelada": "No hay reservas canceladas.",
    "todas": "Todavía no hay reservas.",
}


# --- Lo que se pide en la URL -------------------------------------------------------------------

def _day(name):
    """Una fecha de la URL como AAAA-MM-DD; lo que no se entiende como fecha se ignora."""
    value = (request.args.get(name) or "").strip()
    try:
        return date.fromisoformat(value).isoformat() if value else ""
    except ValueError:
        return ""


def _filters():
    """Los filtros de la lista; un valor desconocido se ignora."""
    tab = request.args.get("estado", "")
    zone = request.args.get("zona", type=int)
    return {
        "q": (request.args.get("q") or "").strip(),
        "estado": tab if tab in _TAB_STATUS else DEFAULT_TAB,
        "zona": str(zone) if zone and zone > 0 else "",
        "desde": _day("desde"),
        "hasta": _day("hasta"),
        "archivadas": "1" if request.args.get("archivadas") == "1" else "",
    }


def _args(filters, page=None):
    """Los filtros que cambian la lista, listos para un enlace (la pestaña que se abre sola no se escribe)."""
    args = {key: value for key, value in filters.items() if value}
    if args.get("estado") == DEFAULT_TAB:
        del args["estado"]
    if page and page > 1:
        args["page"] = page
    return args


def _api_filters(filters):
    """Los filtros de la lista como se los pide la API (sin la página)."""
    return {
        "view": "summary", "status": _TAB_STATUS[filters["estado"]], "commonAreaId": filters["zona"],
        "dateFrom": filters["desde"], "dateTo": filters["hasta"], "search": filters["q"],
        "includeArchived": "true" if filters["archivadas"] else "",
    }


def _list_args():
    """Lo que hay que conservar en los enlaces y formularios para volver a la misma lista."""
    return _args(_filters(), request.args.get("page", type=int))


# --- La lista y la reserva -------------------------------------------------------------------------

def _tabs(filters, counts):
    """Las pestañas con su número y su enlace; cada una conserva los demás filtros."""
    others = {key: value for key, value in filters.items() if key != "estado"}
    return [
        {
            "key": key,
            "label": label,
            "count": counts.get(count_key, 0),
            "url": url_for("web.reservations_list", **_args({**others, "estado": key})),
            "current": key == filters["estado"],
        }
        for key, label, _status, count_key in TABS
    ]


def _page(selected_id=None, reply=None, status=200):
    """La lista con los filtros de la URL y, si se pide, la reserva abierta al lado."""
    api = Api(g.web_user)
    filters = _filters()
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    result = api.get("/api/reservations", **_api_filters(filters), page=page, pageSize=PAGE_SIZE)
    if not result.ok:
        flash(result.error, "error")
    total_pages = result.get("totalPages", 1) or 1
    if request.method == "GET" and result.ok and not result.get("reservations") and page > 1:
        # Un enlace viejo a una página que ya no existe lleva a la última.
        return redirect(url_for(request.endpoint, **{**(request.view_args or {}), **_args(filters, total_pages)}))

    areas = api.get("/api/common-areas")
    if not areas.ok:
        flash(areas.error, "error")

    selected = None
    if selected_id is not None:
        found = api.get(f"/api/reservations/{selected_id}", view="summary")
        if found.status == 404:
            abort(404)
        if found.ok:
            selected = found.get("reservation")
        else:
            flash(found.error, "error")

    current = selected["status"] if selected else None
    return render_template(
        "web/reservations.html",
        items=result.get("reservations", []), total=result.get("total", 0), page=page, pages=total_pages,
        filters=filters, list_args=_list_args(), tabs=_tabs(filters, result.get("counts", {})),
        excel_url=url_for("web.reservations_excel", **_args(filters)),
        empty_text=EMPTY_TEXTS[filters["estado"]],
        zone_options=[(str(area["id"]), area["name"]) for area in areas.get("areas", [])],
        selected=selected, reply=reply or {"message": ""},
        can_decide=current in PENDING_RESERVATION_STATUSES,
        can_cancel=current == "aprobada",  # una reserva pendiente se rechaza, no se cancela
        is_closed=current in CLOSED_RESERVATION_STATUSES,
    ), status


@bp.get("/reservas")
@login_required
def reservations_list():
    return _page()


@bp.get("/reservas/<int:res_id>")
@login_required
def reservation_detail(res_id):
    return _page(res_id)


@bp.get("/reservas/excel")
@login_required
def reservations_excel():
    """La lista, con la pestaña y los filtros que tenga, en Excel (sin conversaciones ni adjuntos)."""
    filters = _filters()
    api = Api(g.web_user)
    zone_name = ""
    if filters["zona"]:
        areas = api.get("/api/common-areas").get("areas", []) or []
        zone_name = next((area["name"] for area in areas if str(area["id"]) == filters["zona"]), filters["zona"])
    words = filters_text((
        ("Estado", next(label for key, label, _status, _count in TABS if key == filters["estado"])),
        ("Zona", zone_name),
        ("Desde", filters["desde"]),
        ("Hasta", filters["hasta"]),
        ("Búsqueda", filters["q"]),
        ("Incluye archivadas", "Sí" if filters["archivadas"] else ""),
    ))
    back = url_for("web.reservations_list", **_args(filters))
    return excel_download(
        "reservas", "Reservas", api, "/api/reservations", "reservations", _api_filters(filters), words,
        RESERVATION_COLUMNS, back,
    )


# --- Decidir, cancelar y escribirle al residente ---------------------------------------------------

@bp.post("/reservas/<int:res_id>/decision")
@login_required
def reservation_decide(res_id):
    """Aprueba o rechaza una reserva con las mismas reglas de la app (RN-019: sin cruces)."""
    decision = DECISIONS.get(request.form.get("decision", ""))
    if decision is None:
        flash("Elige si quieres aprobar o rechazar la reserva.", "error")
    else:
        result = Api(g.web_user).put(f"/api/reservations/{res_id}/status", {"status": decision})
        if result.ok:
            flash(f"Reserva {decision}. Se le avisó al residente.", "success")
        else:
            flash_result(result)
    return redirect(safe_next(request.form.get("next")) or url_for("web.panel"))


@bp.post("/reservas/<int:res_id>/cancelar")
@login_required
def reservation_cancel(res_id):
    """Cancela una reserva pendiente o aprobada; la franja queda libre y el residente recibe un aviso."""
    result = Api(g.web_user).put(f"/api/reservations/{res_id}/cancel")
    if result.ok:
        flash("Reserva cancelada. Se le avisó al residente.", "success")
    else:
        flash_result(result)
    return redirect(safe_next(request.form.get("next")) or url_for("web.reservation_detail", res_id=res_id))


@bp.route("/reservas/<int:res_id>/mensaje", methods=("GET", "POST"))
@login_required
def reservation_message(res_id):
    """Le escribe al residente en la conversación de la reserva; él recibe un aviso en la app."""
    if request.method == "GET":
        # Un enlace a esta dirección (por ejemplo, el de otra página de la lista tras un error) vuelve a la reserva.
        return redirect(url_for("web.reservation_detail", res_id=res_id, **_list_args()))
    reply = {"message": text("message")}
    result = Api(g.web_user).post(f"/api/reservations/{res_id}/messages", compact(reply))
    if result.ok:
        flash("Mensaje enviado. El residente recibió un aviso en la app.", "success")
        return redirect(url_for("web.reservation_detail", res_id=res_id, **_list_args()))
    flash(result.error, "error")
    return _page(res_id, reply=reply, status=result.status)


# --- Adjuntos ------------------------------------------------------------------------------------------

@bp.get("/reservas/<int:res_id>/mensajes/<int:message_id>/adjunto")
@login_required
def reservation_attachment(res_id, message_id):
    """El adjunto de un mensaje de la conversación."""
    return file_response(reservation_view.attachment(res_id, message_id))
