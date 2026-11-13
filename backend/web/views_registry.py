"""Paquetería y visitas en la web (HU-088): consulta del historial de paquetes, visitas y vehículos de visitantes.

Es solo de consulta (DEC-098): la administración busca y revisa lo que registró la portería —por ejemplo,
para responder el reclamo de un paquete que no llegó— pero no registra ni cambia nada desde aquí; el
registro sigue en la app de portería. Por eso esta web no tiene formularios que cambien datos: solo
filtros que viajan en la dirección (GET). Cada lista se puede descargar en Excel con sus filtros
(``exports.py``): solo con los datos necesarios y anotado en la auditoría.

Los paquetes y las visitas se ven con la lista a la izquierda y el elegido al lado (en la pantalla angosta
son dos pantallas, con un enlace para volver); los vehículos, en una tabla. Las fotos no viajan dentro de
la página: cada una se pide aparte a una ruta que solo entrega imágenes (ver ``file_response``). La foto
del visitante solo existe si él dio su consentimiento cuando se guardó.
"""

from datetime import date

from flask import abort, flash, g, redirect, render_template, request, url_for

from services import package_view, visit_view
from web import bp
from web.api import Api
from web.exports import PACKAGE_COLUMNS, VEHICLE_COLUMNS, VISIT_COLUMNS, excel_download, filters_text
from web.security import login_required
from web.support import file_response

#: Filas de cada lista por página.
PAGE_SIZE = 15

#: Las pestañas de cada sección: clave en la URL, texto, clave del número en ``counts`` y lo que se le
#: pide a la API. La primera es la que se abre sola: todo el historial, del más reciente al más antiguo.
PACKAGE_TABS = (
    ("todos", "Todos", "all", {"status": "todos"}),
    ("pendiente", "En portería", "waiting", {"status": "pendiente"}),
    ("por_llegar", "Por llegar", "incoming", {"status": "por_llegar"}),
    ("entregado", "Entregados", "delivered", {"status": "entregado"}),
    ("archivados", "Archivados", "trash", {"status": package_view.TRASH_FILTER}),
)
VISIT_TABS = (
    ("todas", "Todas", "all", {}),
    ("dentro", "Dentro ahora", "inside", {"inside": "true"}),
    ("pendiente", "Esperando autorización", "pending", {"status": "pendiente"}),
    ("aprobada", "Aprobadas", "approved", {"status": "aprobada"}),
    ("rechazada", "Rechazadas", "rejected", {"status": "rechazada"}),
)
VEHICLE_TABS = (
    ("todos", "Todos", "all", {}),
    ("adentro", "Adentro", "inside", {"inside": "true"}),
    ("vencidos", "Vencidos", "overdue", {"overdue": "true"}),
    ("salieron", "Ya salieron", "exited", {"inside": "false"}),
)

#: Lo que se lee cuando una pestaña no tiene filas.
PACKAGE_EMPTY = {
    "todos": "Todavía no hay paquetes registrados.",
    "pendiente": "No hay paquetes esperando en la portería.",
    "por_llegar": "No hay paquetes anunciados que estén por llegar.",
    "entregado": "No hay paquetes entregados en los últimos 7 días.",
    "archivados": "No hay paquetes archivados.",
}
VISIT_EMPTY = {
    "todas": "Todavía no hay visitas registradas.",
    "dentro": "No hay visitantes dentro de la unidad en este momento.",
    "pendiente": "No hay visitas esperando autorización.",
    "aprobada": "No hay visitas aprobadas.",
    "rechazada": "No hay visitas rechazadas.",
}
VEHICLE_EMPTY = {
    "todos": "Todavía no hay entradas de vehículos de visitantes.",
    "adentro": "No hay vehículos de visitantes adentro en este momento.",
    "vencidos": "Ningún vehículo de visitante ha pasado el tiempo máximo.",
    "salieron": "Todavía no hay vehículos de visitantes que hayan salido.",
}

#: Una frase bajo las pestañas que ayuda a leer la lista (solo las pestañas que la necesitan).
PACKAGE_HINTS = {
    "todos": "Del más reciente al más antiguo, también los archivados.",
    "pendiente": "Los que llevan más tiempo esperando van primero.",
    "por_llegar": "Anunciados que todavía no han llegado a la portería.",
    "entregado": "Los entregados hace más de 7 días pasan a «Archivados»: búscalos allí o en «Todos».",
    "archivados": (
        "Son los paquetes que la portería ya no ve en su lista: los entregados hace más de 7 días y los que "
        "se quitaron a mano. Siguen guardados para poder responder un reclamo."
    ),
}
VISIT_HINTS = {
    "dentro": "Los que llevan más tiempo dentro van primero.",
}
VEHICLE_HINTS = {
    "vencidos": "Siguen adentro y ya pasaron el tiempo máximo de parqueo de visitantes.",
}


# --- Lo que se pide en la URL -------------------------------------------------------------------

def _day(name):
    """Una fecha de la URL como AAAA-MM-DD; lo que no se entiende como fecha se ignora."""
    value = (request.args.get(name) or "").strip()
    try:
        return date.fromisoformat(value).isoformat() if value else ""
    except ValueError:
        return ""


def _page_number():
    return max(request.args.get("page", 1, type=int) or 1, 1)


def _tab(tabs):
    """La pestaña pedida en la URL; una desconocida abre la primera."""
    name = request.args.get("estado", "")
    return name if name in {tab[0] for tab in tabs} else tabs[0][0]


def _tab_params(tabs, name):
    """Lo que hay que pedirle a la API para la pestaña elegida."""
    return next(params for key, _label, _count, params in tabs if key == name)


def _args(filters, tabs, page=None):
    """Los filtros que cambian la lista, listos para un enlace (la pestaña que se abre sola no se escribe)."""
    args = {key: value for key, value in filters.items() if value}
    if args.get("estado") == tabs[0][0]:
        del args["estado"]
    if page and page > 1:
        args["page"] = page
    return args


def _tab_links(endpoint, tabs, filters, counts):
    """Las pestañas con su número y su enlace; cada una conserva los demás filtros."""
    others = {key: value for key, value in filters.items() if key != "estado"}
    return [
        {
            "key": key,
            "label": label,
            "count": counts.get(count_key, 0),
            "url": url_for(endpoint, **_args({**others, "estado": key}, tabs)),
            "current": key == filters["estado"],
        }
        for key, label, count_key, _params in tabs
    ]


def _out_of_range(result, rows_key, page, filters, tabs):
    """Un enlace viejo a una página que ya no existe lleva a la última; si no es el caso, None."""
    if request.method == "GET" and result.ok and not result.get(rows_key) and page > 1:
        last = result.get("totalPages", 1) or 1
        return redirect(url_for(request.endpoint, **{**(request.view_args or {}), **_args(filters, tabs, last)}))
    return None


def _tab_label(tabs, name):
    return next(label for key, label, _count, _params in tabs if key == name)


def _selected(api, path, key):
    """El elemento abierto al lado, con la API como fuente; si no existe, la página de «no encontrado»."""
    found = api.get(path, view="summary")
    if found.status == 404:
        abort(404)
    if found.ok:
        return found.get(key)
    flash(found.error, "error")
    return None


# --- Paquetes -----------------------------------------------------------------------------------

def _package_filters():
    return {"q": (request.args.get("q") or "").strip(), "estado": _tab(PACKAGE_TABS)}


def _package_api_filters(filters):
    return {"view": "summary", "search": filters["q"], **_tab_params(PACKAGE_TABS, filters["estado"])}


def _packages_page(selected_id=None):
    """La lista de paquetes con los filtros de la URL y, si se pide, el paquete abierto al lado."""
    api = Api(g.web_user)
    filters = _package_filters()
    page = _page_number()
    result = api.get("/api/packages", **_package_api_filters(filters), page=page, pageSize=PAGE_SIZE)
    if not result.ok:
        flash(result.error, "error")
    if (moved := _out_of_range(result, "packages", page, filters, PACKAGE_TABS)) is not None:
        return moved

    selected = _selected(api, f"/api/packages/{selected_id}", "packageItem") if selected_id is not None else None
    list_args = _args(filters, PACKAGE_TABS, request.args.get("page", type=int))
    return render_template(
        "web/registry_packages.html",
        items=result.get("packages", []), total=result.get("total", 0), page=page,
        pages=result.get("totalPages", 1) or 1, filters=filters, list_args=list_args,
        tabs=_tab_links("web.registry_packages", PACKAGE_TABS, filters, result.get("counts", {})),
        empty_text=PACKAGE_EMPTY[filters["estado"]], hint=PACKAGE_HINTS.get(filters["estado"]),
        selected=selected, excel_url=url_for("web.registry_packages_excel", **_args(filters, PACKAGE_TABS)),
    )


@bp.get("/paqueteria")
@login_required
def registry_packages():
    return _packages_page()


@bp.get("/paqueteria/<int:package_id>")
@login_required
def registry_package_detail(package_id):
    return _packages_page(package_id)


@bp.get("/paqueteria/excel")
@login_required
def registry_packages_excel():
    """Los paquetes de la pestaña y la búsqueda que tenga la lista, en Excel (sin fotos ni guías)."""
    filters = _package_filters()
    words = filters_text((("Estado", _tab_label(PACKAGE_TABS, filters["estado"])), ("Búsqueda", filters["q"])))
    return excel_download(
        "paquetes", "Paquetes", Api(g.web_user), "/api/packages", "packages", _package_api_filters(filters),
        words, PACKAGE_COLUMNS, url_for("web.registry_packages", **_args(filters, PACKAGE_TABS)),
    )


@bp.get("/paqueteria/<int:package_id>/foto")
@login_required
def registry_package_photo(package_id):
    """La foto del paquete (imagen); la ruta no entrega nada que no sea una imagen, un video o un audio."""
    return file_response(package_view.attachment(package_id))


# --- Visitas ------------------------------------------------------------------------------------

def _visit_filters():
    return {
        "q": (request.args.get("q") or "").strip(),
        "estado": _tab(VISIT_TABS),
        "desde": _day("desde"),
        "hasta": _day("hasta"),
    }


def _visit_api_filters(filters):
    return {
        "view": "summary", "search": filters["q"], "from": filters["desde"], "to": filters["hasta"],
        **_tab_params(VISIT_TABS, filters["estado"]),
    }


def _visits_page(selected_id=None):
    """La lista de visitas con los filtros de la URL y, si se pide, la visita abierta al lado."""
    api = Api(g.web_user)
    filters = _visit_filters()
    page = _page_number()
    result = api.get("/api/visits", **_visit_api_filters(filters), page=page, pageSize=PAGE_SIZE)
    if not result.ok:
        flash(result.error, "error")
    if (moved := _out_of_range(result, "visits", page, filters, VISIT_TABS)) is not None:
        return moved

    selected = _selected(api, f"/api/visits/{selected_id}", "visit") if selected_id is not None else None
    list_args = _args(filters, VISIT_TABS, request.args.get("page", type=int))
    return render_template(
        "web/registry_visits.html",
        items=result.get("visits", []), total=result.get("total", 0), page=page,
        pages=result.get("totalPages", 1) or 1, filters=filters, list_args=list_args,
        tabs=_tab_links("web.registry_visits", VISIT_TABS, filters, result.get("counts", {})),
        empty_text=VISIT_EMPTY[filters["estado"]], hint=VISIT_HINTS.get(filters["estado"]),
        selected=selected, excel_url=url_for("web.registry_visits_excel", **_args(filters, VISIT_TABS)),
    )


@bp.get("/visitas")
@login_required
def registry_visits():
    return _visits_page()


@bp.get("/visitas/<int:visit_id>")
@login_required
def registry_visit_detail(visit_id):
    return _visits_page(visit_id)


@bp.get("/visitas/excel")
@login_required
def registry_visits_excel():
    """Las visitas de la pestaña, la búsqueda y las fechas que tenga la lista, en Excel.

    Sin fotos ni números de documento: solo si la persona dio el documento o no lo quiso dar.
    """
    filters = _visit_filters()
    words = filters_text((
        ("Estado", _tab_label(VISIT_TABS, filters["estado"])), ("Búsqueda", filters["q"]),
        ("Desde", filters["desde"]), ("Hasta", filters["hasta"]),
    ))
    return excel_download(
        "visitas", "Visitas", Api(g.web_user), "/api/visits", "visits", _visit_api_filters(filters),
        words, VISIT_COLUMNS, url_for("web.registry_visits", **_args(filters, VISIT_TABS)),
    )


@bp.get("/visitas/<int:visit_id>/foto")
@login_required
def registry_visit_photo(visit_id):
    """La foto del visitante; solo existe si él dio su consentimiento al guardarla."""
    return file_response(visit_view.photo(visit_id))


# --- Vehículos de visitantes --------------------------------------------------------------------

@bp.get("/vehiculos")
@login_required
def registry_vehicles():
    """Las entradas de vehículos de visitantes, de la más reciente a la más antigua, en una tabla."""
    api = Api(g.web_user)
    filters = _vehicle_filters()
    page = _page_number()
    result = api.get(
        "/api/vehicle-entries", counts="true", page=page, pageSize=PAGE_SIZE, **_vehicle_api_filters(filters)
    )
    if not result.ok:
        flash(result.error, "error")
    if (moved := _out_of_range(result, "vehicleEntries", page, filters, VEHICLE_TABS)) is not None:
        return moved
    return render_template(
        "web/registry_vehicles.html",
        entries=result.get("vehicleEntries", []), total=result.get("total", 0), page=page,
        pages=result.get("totalPages", 1) or 1, filters=filters,
        tabs=_tab_links("web.registry_vehicles", VEHICLE_TABS, filters, result.get("counts", {})),
        empty_text=VEHICLE_EMPTY[filters["estado"]], hint=VEHICLE_HINTS.get(filters["estado"]),
        excel_url=url_for("web.registry_vehicles_excel", **_args(filters, VEHICLE_TABS)),
    )


def _vehicle_filters():
    return {"placa": (request.args.get("placa") or "").strip(), "estado": _tab(VEHICLE_TABS)}


def _vehicle_api_filters(filters):
    return {"plate": filters["placa"], **_tab_params(VEHICLE_TABS, filters["estado"])}


@bp.get("/vehiculos/excel")
@login_required
def registry_vehicles_excel():
    """Las entradas de vehículos de la pestaña y la placa que tenga la lista, en Excel."""
    filters = _vehicle_filters()
    words = filters_text((("Situación", _tab_label(VEHICLE_TABS, filters["estado"])), ("Placa", filters["placa"])))
    return excel_download(
        "vehiculos", "Vehículos de visitantes", Api(g.web_user), "/api/vehicle-entries", "vehicleEntries",
        _vehicle_api_filters(filters), words, VEHICLE_COLUMNS,
        url_for("web.registry_vehicles", **_args(filters, VEHICLE_TABS)),
    )
