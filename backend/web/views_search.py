"""El buscador general de la web (HU-089): una caja arriba de cada página y la página de resultados.

La caja tiene el filtro «Buscar en» (todo, personas, apartamentos, vehículos, PQRS, paquetes o
visitas). La búsqueda no tiene reglas propias: la hace ``GET /api/search``, la misma de la app, y
aquí solo se dibujan los grupos de resultados y a qué página lleva cada uno.
"""

from flask import flash, g, render_template, request, url_for

from services.global_search import MIN_CHARS, places_for
from web import bp
from web.api import Api
from web.security import login_required


def _target(item):
    """La página de la web donde se ve ese resultado, o None si la web no tiene una para él."""
    kind = item["type"]
    if kind == "personas":
        return url_for("web.users_list", q=item["title"])
    if kind == "apartamentos":
        return url_for("web.structure_apartments", q=item["title"])
    if kind == "pqrs":
        return url_for("web.pqrs_detail", pqrs_id=item["id"])
    if kind == "paquetes":
        return url_for("web.registry_package_detail", package_id=item["id"])
    if kind == "visitas":
        return url_for("web.registry_visit_detail", visit_id=item["id"])
    if kind == "vehiculos":
        if item.get("kind") == "visitante":
            return url_for("web.registry_vehicles", placa=item["title"])
        # El vehículo de un residente se ve en su apartamento.
        if item.get("apartmentLabel"):
            return url_for("web.structure_apartments", q=item["apartmentLabel"])
    return None


def search_form():
    """Lo que la caja de búsqueda de la barra de arriba necesita: el texto, el lugar y las opciones.

    Si la persona está en la página de resultados, la caja conserva lo que buscó.
    """
    on_results = request.endpoint == "web.search_page"
    user = g.get("web_user")
    return {
        "text": (request.args.get("q") or "").strip()[:100] if on_results else "",
        "place": (request.args.get("en") or "todo").strip().lower() if on_results else "todo",
        "places": places_for(user.role if user is not None else "ADMIN"),
        "min_chars": MIN_CHARS,
    }


bp.add_app_template_global(search_form, "search_form")


@bp.get("/buscar")
@login_required
def search_page():
    text = (request.args.get("q") or "").strip()
    place = (request.args.get("en") or "todo").strip().lower()
    result = Api(g.web_user).get("/api/search", q=text, **{"in": place})
    groups = []
    if not result.ok:
        # Un lugar desconocido en la dirección no deja la página rota: se avisa y se muestra la caja.
        flash(result.error, "error")
    else:
        for group in result.get("groups", []):
            items = [{**item, "url": _target(item)} for item in group["items"]]
            groups.append({
                **group,
                "items": items,
                "all_url": url_for("web.search_page", q=text, en=group["type"]) if place == "todo" and group["more"] else None,
            })
    return render_template(
        "web/search.html",
        text=text, place=place if result.ok else "todo", groups=groups, too_short=result.get("tooShort", True),
        min_chars=MIN_CHARS, total=sum(len(group["items"]) for group in groups),
        place_label=next((p["label"] for p in places_for("ADMIN") if p["value"] == place), "Todo"),
    )
