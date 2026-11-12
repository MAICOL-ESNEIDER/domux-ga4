"""Estructura de la unidad en la web (HU-076): torres, apartamentos, parqueaderos y cuartos útiles.

Son las mismas validaciones de la app (RN-008): la web reúne lo que escribió la administración y lo
manda a la API, que responde con su mensaje en español. Quitar algo no lo borra: queda retirado y su
historial se conserva (ADR-013).
"""

from flask import abort, flash, g, redirect, render_template, request, url_for

from web import bp
from web.api import Api
from web.forms import compact, number, text
from web.security import login_required
from web.support import fetch_all, flash_result

PAGE_SIZE = 25

PARKING_KINDS = (("residente", "De residente"), ("visitante", "De visitantes"))
ASSIGNED_OPTIONS = (("si", "Asignados"), ("no", "Libres"))


# --- Piezas comunes -----------------------------------------------------------------------------

def _field(id, label, value="", kind="text", **options):
    """La descripción de un campo del formulario genérico de la estructura."""
    return {"id": id, "label": label, "value": "" if value is None else value, "kind": kind, **options}


def _form_page(*, title, intro, fields, action, submit, back, retire=None, status=200):
    return render_template(
        "web/structure_form.html",
        title=title, intro=intro, fields=fields, action=action, submit=submit, back=back, retire=retire,
    ), status


def _load(api, path):
    """La respuesta de la API con un elemento vigente; si no existe, la página «no encontrada»."""
    found = api.get(path)
    if found.status == 404:
        abort(404)
    if not found.ok:
        flash(found.error, "error")
        return None
    return found


def _towers(api):
    result = api.get("/api/admin/towers")
    if not result.ok:
        flash(result.error, "error")
    return result.get("towers", [])


def _tower_options(towers):
    return [(tower["id"], tower["name"]) for tower in towers]


def _apartment_options(api):
    apartments, failure = fetch_all(api, "/api/admin/apartments", "apartments")
    if failure is not None:
        flash(failure.error, "error")
    return [(item["id"], item["label"]) for item in apartments]


def _paginated_args():
    return max(request.args.get("page", 1, type=int) or 1, 1)


def _retire_card(action, label, explanation, confirm):
    return {"action": action, "label": label, "explanation": explanation, "confirm": confirm}


def _retire(path, back):
    """Retira un elemento: queda fuera de las listas pero su historial se conserva (ADR-013)."""
    flash_result(Api(g.web_user).delete(path))
    return redirect(back)


def _after_save(result, success, back):
    """Si la API aceptó el cambio, avisa y vuelve a la lista; si no, devuelve ``None`` para mostrar el error."""
    if result.ok:
        flash(success, "success")
        return redirect(back)
    flash(result.error, "error")
    return None


# --- Torres (HU-013) ----------------------------------------------------------------------------

@bp.get("/estructura")
@login_required
def structure_towers():
    return render_template("web/structure_towers.html", towers=_towers(Api(g.web_user)))


def _tower_form(tower, values, status=200):
    fields = [
        _field("name", "Nombre de la torre", values.get("name", ""), required=True, maxlength=60,
               help="Por ejemplo: Torre 1."),
        _field("floors", "Número de pisos", values.get("floors", ""), kind="number", required=True,
               extra={"min": 1, "max": 100, "inputmode": "numeric"}),
    ]
    retire = _retire_card(
        url_for("web.tower_retire", tower_id=tower["id"]), "Retirar torre",
        "La torre sale de las listas, pero su historial se conserva. Solo se puede retirar si ya no tiene apartamentos.",
        f"¿Retirar la torre {tower['name']}? Su historial se conserva.",
    ) if tower else None
    return _form_page(
        title=f"Editar {tower['name']}" if tower else "Crear torre",
        intro="Cambia el nombre o el número de pisos." if tower else "Escribe el nombre y cuántos pisos tiene.",
        fields=fields, submit="Guardar cambios" if tower else "Crear torre",
        action=url_for("web.tower_edit", tower_id=tower["id"]) if tower else url_for("web.tower_new"),
        back=url_for("web.structure_towers"), retire=retire, status=status,
    )


@bp.route("/estructura/torres/nueva", methods=("GET", "POST"))
@login_required
def tower_new():
    if request.method == "POST":
        result = Api(g.web_user).post("/api/admin/towers", compact({"name": text("name"), "floors": number("floors")}))
        done = _after_save(result, "Torre creada.", url_for("web.structure_towers"))
        return done or _tower_form(None, request.form, result.status)
    return _tower_form(None, {})


@bp.route("/estructura/torres/<int:tower_id>", methods=("GET", "POST"))
@login_required
def tower_edit(tower_id):
    api = Api(g.web_user)
    found = _load(api, f"/api/admin/towers/{tower_id}")
    if found is None:
        return redirect(url_for("web.structure_towers"))
    tower = found.get("tower")
    if request.method == "POST":
        result = api.put(f"/api/admin/towers/{tower_id}", compact({"name": text("name"), "floors": number("floors")}))
        done = _after_save(result, "Torre actualizada.", url_for("web.structure_towers"))
        return done or _tower_form(tower, request.form, result.status)
    return _tower_form(tower, {"name": tower["name"], "floors": tower["floors"]})


@bp.post("/estructura/torres/<int:tower_id>/retirar")
@login_required
def tower_retire(tower_id):
    return _retire(f"/api/admin/towers/{tower_id}", url_for("web.structure_towers"))


# --- Apartamentos (HU-014 y HU-023) ---------------------------------------------------------------

@bp.get("/estructura/apartamentos")
@login_required
def structure_apartments():
    api = Api(g.web_user)
    tower_id = request.args.get("torre", type=int)
    search = (request.args.get("q") or "").strip()
    page = _paginated_args()
    result = api.get("/api/admin/apartments", towerId=tower_id, search=search, page=page, pageSize=PAGE_SIZE)
    if not result.ok:
        flash(result.error, "error")
    total_pages = result.get("totalPages", 1) or 1
    if result.ok and not result.get("apartments") and page > 1:
        return redirect(url_for("web.structure_apartments", **{**request.args.to_dict(), "page": total_pages}))
    return render_template(
        "web/structure_apartments.html",
        apartments=result.get("apartments", []), total=result.get("total", 0), page=page, pages=total_pages,
        towers=_towers(api), filters={"torre": tower_id, "q": search},
    )


def _apartment_new_form(towers, values, status=200):
    fields = [
        _field("towerId", "Torre", values.get("towerId", ""), kind="select", required=True,
               options=_tower_options(towers), blank="Elige la torre"),
        _field("code", "Código del apartamento", values.get("code", ""), required=True, maxlength=20,
               help="Por ejemplo: 101. Es el número con el que se conoce el apartamento."),
        _field("floor", "Piso", values.get("floor", ""), kind="number",
               extra={"min": 1, "max": 100, "inputmode": "numeric"},
               help="Si lo dejas vacío, se toma del código (101 queda en el piso 1)."),
    ]
    return _form_page(
        title="Crear apartamento", intro="Registra un apartamento de una torre. Para varios de un mismo piso, usa «Crear un piso completo».",
        fields=fields, submit="Crear apartamento", action=url_for("web.apartment_new"),
        back=url_for("web.structure_apartments"), status=status,
    )


@bp.route("/estructura/apartamentos/nuevo", methods=("GET", "POST"))
@login_required
def apartment_new():
    api = Api(g.web_user)
    towers = _towers(api)
    if request.method == "POST":
        body = compact({"towerId": number("towerId"), "code": text("code"), "floor": number("floor")})
        if "towerId" not in body:
            flash("Elige la torre del apartamento.", "error")
            return _apartment_new_form(towers, request.form, 400)
        result = api.post("/api/admin/apartments", body)
        done = _after_save(
            result, "Apartamento creado.", url_for("web.structure_apartments", torre=body["towerId"])
        )
        return done or _apartment_new_form(towers, request.form, result.status)
    return _apartment_new_form(towers, {"towerId": request.args.get("torre", "")})


def _floor_form(towers, values, status=200):
    fields = [
        _field("towerId", "Torre", values.get("towerId", ""), kind="select", required=True,
               options=_tower_options(towers), blank="Elige la torre"),
        _field("floor", "Piso", values.get("floor", ""), kind="number", required=True,
               extra={"min": 1, "max": 100, "inputmode": "numeric"}),
        _field("count", "Cantidad de apartamentos", values.get("count", ""), kind="number", required=True,
               extra={"min": 1, "max": 99, "inputmode": "numeric"}),
        _field("first", "Número del primer apartamento", values.get("first", "1"), kind="number",
               extra={"min": 1, "max": 99, "inputmode": "numeric"},
               help="Casi siempre es 1. El código es el piso seguido del número con dos cifras: "
                    "el piso 3 con 4 apartamentos crea el 301, 302, 303 y 304."),
    ]
    return _form_page(
        title="Crear un piso completo",
        intro="Crea de una vez los apartamentos de un piso. Si alguno ya existe, no se crea ninguno.",
        fields=fields, submit="Crear apartamentos", action=url_for("web.apartment_floor"),
        back=url_for("web.structure_apartments"), status=status,
    )


@bp.route("/estructura/apartamentos/piso", methods=("GET", "POST"))
@login_required
def apartment_floor():
    api = Api(g.web_user)
    towers = _towers(api)
    if request.method == "POST":
        body = compact({
            "towerId": number("towerId"), "floor": number("floor"), "count": number("count"), "from": number("first"),
        })
        if "towerId" not in body:
            flash("Elige la torre de los apartamentos.", "error")
            return _floor_form(towers, request.form, 400)
        result = api.post("/api/admin/apartments/batch", body)
        if result.ok:
            flash_result(result)
            return redirect(url_for("web.structure_apartments", torre=body["towerId"]))
        flash(result.error, "error")
        return _floor_form(towers, request.form, result.status)
    return _floor_form(towers, {"towerId": request.args.get("torre", "")})


def _apartment_edit_form(apartment, values, status=200):
    fields = [
        _field("code", "Código del apartamento", values.get("code", ""), required=True, maxlength=20),
        _field("floor", "Piso", values.get("floor", ""), kind="number", required=True,
               extra={"min": 1, "max": 100, "inputmode": "numeric"}),
    ]
    retire = _retire_card(
        url_for("web.apartment_retire", apartment_id=apartment["id"]), "Retirar apartamento",
        "El apartamento sale de las listas y su historial se conserva. Solo se puede retirar si ya no tiene "
        "residentes activos; sus parqueaderos y cuartos útiles quedan libres.",
        f"¿Retirar el apartamento {apartment['label']}? Sus parqueaderos y cuartos útiles quedan libres y lo "
        "vigente de su ficha (integrantes, mascotas y vehículos) se retira con él. El historial se conserva.",
    )
    return _form_page(
        title=f"Editar {apartment['label']}",
        intro="Un apartamento no cambia de torre: para moverlo, retíralo y créalo en la otra.",
        fields=fields, submit="Guardar cambios", action=url_for("web.apartment_edit", apartment_id=apartment["id"]),
        back=url_for("web.structure_apartments", torre=apartment["towerId"]), retire=retire, status=status,
    )


@bp.route("/estructura/apartamentos/<int:apartment_id>", methods=("GET", "POST"))
@login_required
def apartment_edit(apartment_id):
    api = Api(g.web_user)
    found = _load(api, f"/api/admin/apartments/{apartment_id}")
    if found is None:
        return redirect(url_for("web.structure_apartments"))
    apartment = found.get("apartment")
    if request.method == "POST":
        result = api.put(
            f"/api/admin/apartments/{apartment_id}", compact({"code": text("code"), "floor": number("floor")})
        )
        done = _after_save(
            result, "Apartamento actualizado.", url_for("web.structure_apartments", torre=apartment["towerId"])
        )
        return done or _apartment_edit_form(apartment, request.form, result.status)
    return _apartment_edit_form(apartment, {"code": apartment["code"], "floor": apartment["floor"]})


@bp.post("/estructura/apartamentos/<int:apartment_id>/retirar")
@login_required
def apartment_retire(apartment_id):
    return _retire(f"/api/admin/apartments/{apartment_id}", url_for("web.structure_apartments"))


# --- Parqueaderos (HU-015) ------------------------------------------------------------------------

@bp.get("/estructura/parqueaderos")
@login_required
def structure_parking():
    kind = request.args.get("tipo", "")
    assigned = request.args.get("asignado", "")
    search = (request.args.get("q") or "").strip()
    page = _paginated_args()
    result = Api(g.web_user).get(
        "/api/admin/parking-spots",
        type=kind if kind in dict(PARKING_KINDS) else "",
        assigned={"si": "true", "no": "false"}.get(assigned, ""),
        search=search, page=page, pageSize=PAGE_SIZE,
    )
    if not result.ok:
        flash(result.error, "error")
    total_pages = result.get("totalPages", 1) or 1
    if result.ok and not result.get("parkingSpots") and page > 1:
        return redirect(url_for("web.structure_parking", **{**request.args.to_dict(), "page": total_pages}))
    return render_template(
        "web/structure_parking.html",
        spots=result.get("parkingSpots", []), total=result.get("total", 0), page=page, pages=total_pages,
        filters={"tipo": kind if kind in dict(PARKING_KINDS) else "", "asignado": assigned if assigned in dict(ASSIGNED_OPTIONS) else "", "q": search},
        kind_options=PARKING_KINDS, assigned_options=ASSIGNED_OPTIONS,
    )


def _parking_form(api, spot, values, status=200):
    fields = [
        _field("code", "Código del parqueadero", values.get("code", ""), required=True, maxlength=20,
               help="Por ejemplo: P-101."),
        _field("type", "Tipo", values.get("type", "residente"), kind="select", required=True, options=PARKING_KINDS),
        _field("location", "Ubicación", values.get("location", ""), required=True, maxlength=120,
               help="Por ejemplo: Sótano 1, frente al ascensor."),
        _field("apartmentId", "Apartamento asignado", values.get("apartmentId", ""), kind="select",
               options=_apartment_options(api), blank="Sin asignar",
               help="Solo los parqueaderos de residente se asignan a un apartamento."),
    ]
    retire = _retire_card(
        url_for("web.parking_retire", spot_id=spot["id"]), "Retirar parqueadero",
        "El parqueadero sale de las listas y su historial se conserva. No se puede retirar mientras esté ocupado.",
        f"¿Retirar el parqueadero {spot['code']}? Su historial se conserva.",
    ) if spot else None
    return _form_page(
        title=f"Editar el parqueadero {spot['code']}" if spot else "Crear parqueadero",
        intro="Cambia sus datos o a quién está asignado." if spot else "Registra un parqueadero de residente o de visitantes.",
        fields=fields, submit="Guardar cambios" if spot else "Crear parqueadero",
        action=url_for("web.parking_edit", spot_id=spot["id"]) if spot else url_for("web.parking_new"),
        back=url_for("web.structure_parking"), retire=retire, status=status,
    )


def _parking_body(editing):
    body = compact({"code": text("code"), "type": text("type"), "location": text("location")})
    apartment = number("apartmentId")
    if apartment is not None or editing:
        # Al editar, «Sin asignar» se manda como nulo para liberar el parqueadero.
        body["apartmentId"] = apartment
    return body


@bp.route("/estructura/parqueaderos/nuevo", methods=("GET", "POST"))
@login_required
def parking_new():
    api = Api(g.web_user)
    if request.method == "POST":
        result = api.post("/api/admin/parking-spots", _parking_body(editing=False))
        done = _after_save(result, "Parqueadero creado.", url_for("web.structure_parking"))
        return done or _parking_form(api, None, request.form, result.status)
    return _parking_form(api, None, {})


@bp.route("/estructura/parqueaderos/<int:spot_id>", methods=("GET", "POST"))
@login_required
def parking_edit(spot_id):
    api = Api(g.web_user)
    found = _load(api, f"/api/admin/parking-spots/{spot_id}")
    if found is None:
        return redirect(url_for("web.structure_parking"))
    spot = found.get("parkingSpot")
    if request.method == "POST":
        result = api.put(f"/api/admin/parking-spots/{spot_id}", _parking_body(editing=True))
        done = _after_save(result, "Parqueadero actualizado.", url_for("web.structure_parking"))
        return done or _parking_form(api, spot, request.form, result.status)
    return _parking_form(api, spot, {
        "code": spot["code"], "type": spot["type"], "location": spot["location"], "apartmentId": spot["apartmentId"],
    })


@bp.post("/estructura/parqueaderos/<int:spot_id>/retirar")
@login_required
def parking_retire(spot_id):
    return _retire(f"/api/admin/parking-spots/{spot_id}", url_for("web.structure_parking"))


# --- Cuartos útiles (HU-016) ------------------------------------------------------------------------

@bp.get("/estructura/cuartos")
@login_required
def structure_storage():
    assigned = request.args.get("asignado", "")
    search = (request.args.get("q") or "").strip()
    page = _paginated_args()
    result = Api(g.web_user).get(
        "/api/admin/storage-rooms",
        assigned={"si": "true", "no": "false"}.get(assigned, ""), search=search, page=page, pageSize=PAGE_SIZE,
    )
    if not result.ok:
        flash(result.error, "error")
    total_pages = result.get("totalPages", 1) or 1
    if result.ok and not result.get("storageRooms") and page > 1:
        return redirect(url_for("web.structure_storage", **{**request.args.to_dict(), "page": total_pages}))
    return render_template(
        "web/structure_storage.html",
        rooms=result.get("storageRooms", []), total=result.get("total", 0), page=page, pages=total_pages,
        filters={"asignado": assigned if assigned in dict(ASSIGNED_OPTIONS) else "", "q": search},
        assigned_options=ASSIGNED_OPTIONS,
    )


def _storage_form(api, room, values, status=200):
    fields = [
        _field("code", "Código del cuarto útil", values.get("code", ""), required=True, maxlength=20,
               help="Por ejemplo: CU-12."),
        _field("apartmentId", "Apartamento asignado", values.get("apartmentId", ""), kind="select",
               options=_apartment_options(api), blank="Sin asignar"),
    ]
    retire = _retire_card(
        url_for("web.storage_retire", room_id=room["id"]), "Retirar cuarto útil",
        "El cuarto útil sale de las listas y su historial se conserva.",
        f"¿Retirar el cuarto útil {room['code']}? Su historial se conserva.",
    ) if room else None
    return _form_page(
        title=f"Editar el cuarto útil {room['code']}" if room else "Crear cuarto útil",
        intro="Cambia su código o a quién está asignado." if room else "Registra un cuarto útil y, si ya se sabe, a quién pertenece.",
        fields=fields, submit="Guardar cambios" if room else "Crear cuarto útil",
        action=url_for("web.storage_edit", room_id=room["id"]) if room else url_for("web.storage_new"),
        back=url_for("web.structure_storage"), retire=retire, status=status,
    )


def _storage_body(editing):
    body = compact({"code": text("code")})
    apartment = number("apartmentId")
    if apartment is not None or editing:
        body["apartmentId"] = apartment
    return body


@bp.route("/estructura/cuartos/nuevo", methods=("GET", "POST"))
@login_required
def storage_new():
    api = Api(g.web_user)
    if request.method == "POST":
        result = api.post("/api/admin/storage-rooms", _storage_body(editing=False))
        done = _after_save(result, "Cuarto útil creado.", url_for("web.structure_storage"))
        return done or _storage_form(api, None, request.form, result.status)
    return _storage_form(api, None, {})


@bp.route("/estructura/cuartos/<int:room_id>", methods=("GET", "POST"))
@login_required
def storage_edit(room_id):
    api = Api(g.web_user)
    found = _load(api, f"/api/admin/storage-rooms/{room_id}")
    if found is None:
        return redirect(url_for("web.structure_storage"))
    room = found.get("storageRoom")
    if request.method == "POST":
        result = api.put(f"/api/admin/storage-rooms/{room_id}", _storage_body(editing=True))
        done = _after_save(result, "Cuarto útil actualizado.", url_for("web.structure_storage"))
        return done or _storage_form(api, room, request.form, result.status)
    return _storage_form(api, room, {"code": room["code"], "apartmentId": room["apartmentId"]})


@bp.post("/estructura/cuartos/<int:room_id>/retirar")
@login_required
def storage_retire(room_id):
    return _retire(f"/api/admin/storage-rooms/{room_id}", url_for("web.structure_storage"))
