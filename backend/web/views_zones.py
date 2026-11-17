"""Zonas comunes en la web: sus reglas de reserva (HU-055) y su manejo completo (DEC-032).

Cada zona guarda su horario, la duración de sus franjas, cuántas franjas seguidas se reservan de una vez y si
se puede reservar el día completo, su aforo, con cuánta anticipación se puede reservar, hasta cuándo se puede
cancelar, cuántas reservas por semana tiene cada residente y su día de mantenimiento (RN-020 a RN-022). La administración los ajusta aquí, sin tocar el código. Las reservas nuevas usan las
reglas desde que se guardan; las que ya existen no se tocan.

La administración también agrega las zonas que tiene su unidad, las renombra, las cierra cuando fallan (con el
motivo que verán los residentes), las vuelve a abrir y retira las que ya no existen. Nada se borra: una zona
retirada deja de ofrecerse, pero sus reservas viejas conservan su nombre.

La web solo reúne lo que escribió la administración y lo manda a la API (que revisa cada dato y que todos
tengan sentido juntos). Manda solo lo que cambió, para que el registro de auditoría diga exactamente qué se cambió.
"""

from flask import abort, flash, g, redirect, render_template, request, url_for

from services.zone_rules import (
    ALLOWED_SLOT_MINUTES,
    MAX_CLOSED_REASON,
    MAX_ZONE_NAME,
    WEEKDAY_NAMES,
    days_text,
    default_zone_values,
)
from web import bp, texts
from web.api import Api
from web.forms import number, text
from web.security import login_required
from web.support import flash_result

#: Los datos del formulario con el nombre con que los recibe la API, en el orden en que se ven.
#: Los de hora se escriben como HH:MM; los demás son números enteros.
TIME_FIELDS = ("openTime", "closeTime")
NUMBER_FIELDS = (
    "slotMinutes", "maxConsecutiveSlots", "capacity", "minAdvanceDays", "maxAdvanceDays", "cancelDeadlineDays",
    "weeklyLimit", "maintenanceWeekday",
)
#: Las casillas de sí o no: marcada es sí.
FLAG_FIELDS = ("allowFullDay",)
#: Los que se pueden dejar vacíos: el aforo y el día de mantenimiento quedan «sin definir» y el plazo de
#: cancelación y el límite semanal vuelven al valor por defecto (la API entiende ``null`` así).
CLEARABLE_FIELDS = ("capacity", "maintenanceWeekday", "cancelDeadlineDays", "weeklyLimit")


def _plural_day(name):
    """«lunes» pasa a «los lunes» y «sábado», a «los sábados»."""
    return f"los {name if name.endswith('s') else name + 's'}"


def _summary(area):
    """Las reglas de una zona escritas con palabras, para la lista."""
    slots = area["slots"]
    minimum, maximum = area["minAdvanceDays"], area["maxAdvanceDays"]
    weekday = area["maintenanceWeekday"]
    upcoming = area.get("upcomingReservations", 0)
    return {
        "id": area["id"],
        "name": area["name"],
        "isOpen": area["isOpen"],
        "closedReason": area["closedReason"],
        "closedSince": texts.date_es(area["closedAt"]),
        "upcoming": texts.plural(upcoming, "reserva próxima", "reservas próximas") if upcoming else "",
        "schedule": f"De {area['openTime']} a {area['closeTime']}",
        "slots": f"{texts.slot_length_text(area['slotMinutes'])} cada una · {texts.plural(len(slots), 'franja', 'franjas')} al día",
        "consecutive": (
            "Una franja a la vez" if area["maxConsecutiveSlots"] == 1
            else f"Hasta {area['maxConsecutiveSlots']} franjas seguidas"
        ),
        "fullDay": (
            f"Se puede reservar el día completo ({area['fullDaySlot']})" if area["allowFullDay"] and area["fullDaySlot"]
            else "No se reserva el día completo"
        ),
        "capacity": (
            texts.plural(area["capacity"], "persona", "personas") if area["capacity"] else "Sin límite definido"
        ),
        "advance": (
            ("Desde el mismo día" if minimum == 0 else f"Desde {days_text(minimum)} antes")
            + f" y hasta {days_text(maximum)} antes"
        ),
        "cancel": f"El residente cancela hasta {days_text(area['cancelDeadlineDays'])} antes",
        "weekly": f"{texts.plural(area['weeklyLimit'], 'reserva', 'reservas')} por semana por residente",
        "maintenance": (
            f"Cierra {_plural_day(WEEKDAY_NAMES[weekday])} (si ese día es festivo, pasa al día siguiente)"
            if weekday is not None else "Sin día de mantenimiento"
        ),
    }


def _areas(api, include_retired=False):
    """Las zonas que entrega la API (también las retiradas, si se piden); si falla, un aviso y una lista vacía."""
    result = api.get("/api/common-areas", includeRetired="true" if include_retired else None)
    if not result.ok:
        flash(result.error, "error")
    return result.get("areas", [])


def _area(api, area_id):
    """La zona vigente con ese id; si no existe o está retirada, la página «no encontrada»."""
    area = next((item for item in _areas(api) if item["id"] == area_id), None)
    if area is None:
        abort(404)
    return area


def _form_values(area):
    """El nombre y las reglas de la zona como los muestra el formulario (texto, lo vacío en blanco; las casillas, sí o no)."""
    values = {
        key: "" if area[key] is None else str(area[key])
        for key in ("name", *TIME_FIELDS, *NUMBER_FIELDS)
    }
    for key in FLAG_FIELDS:
        values[key] = bool(area.get(key))
    return values


def _new_zone_values():
    """Lo que muestra el formulario de una zona nueva: las reglas por defecto y el nombre vacío."""
    defaults = default_zone_values()
    return {
        "name": "",
        "openTime": defaults["open_time"],
        "closeTime": defaults["close_time"],
        "slotMinutes": str(defaults["slot_minutes"]),
        "maxConsecutiveSlots": str(defaults["max_consecutive_slots"]),
        "capacity": "",
        "minAdvanceDays": str(defaults["min_advance_days"]),
        "maxAdvanceDays": str(defaults["max_advance_days"]),
        "cancelDeadlineDays": str(defaults["cancel_deadline_days"]),
        "weeklyLimit": str(defaults["weekly_limit"]),
        "maintenanceWeekday": "",
        "allowFullDay": defaults["allow_full_day"],
    }


def _posted_values():
    """Lo que llegó en el formulario: texto en los campos y sí o no en las casillas."""
    values = {key: text(key) for key in ("name", *TIME_FIELDS, *NUMBER_FIELDS)}
    for key in FLAG_FIELDS:
        values[key] = request.form.get(key) == "1"
    return values


def _typed(values):
    """Lo escrito en el formulario como lo entiende la API: horas en texto, números enteros.

    Un campo que se puede dejar vacío viaja como ``None``; los demás, si quedan vacíos, no viajan (sin cambio).
    Lo que no se entiende como número se manda tal cual para que la API lo rechace con su mensaje.
    """
    typed = {}
    if values["name"]:
        typed["name"] = values["name"]
    for key in TIME_FIELDS:
        if values[key]:
            typed[key] = values[key]
    for key in NUMBER_FIELDS:
        raw = values[key]
        if raw:
            typed[key] = number(key)
        elif key in CLEARABLE_FIELDS:
            typed[key] = None
    for key in FLAG_FIELDS:
        typed[key] = bool(values[key])
    return typed


def _changes(area, typed):
    """Solo las reglas que cambiaron frente a lo que tiene la zona ahora."""
    return {key: value for key, value in typed.items() if area.get(key) != value}


def _page(area, values, status=200):
    """El formulario de una zona; sin ``area`` es el de una zona nueva."""
    return render_template(
        "web/zone_form.html", area=area, values=values, max_name=MAX_ZONE_NAME,
        upcoming=area.get("upcomingReservations", 0) if area else 0,
        slot_options=[(str(minutes), texts.slot_length_text(minutes)) for minutes in ALLOWED_SLOT_MINUTES],
        weekday_options=[(str(index), name.capitalize()) for index, name in enumerate(WEEKDAY_NAMES)],
    ), status


@bp.get("/zonas")
@login_required
def zones_list():
    areas = _areas(Api(g.web_user), include_retired=True)
    return render_template(
        "web/zones.html",
        zones=[_summary(area) for area in areas if not area["retiredAt"]],
        retired=[
            {"name": area["name"], "since": texts.date_es(area["retiredAt"])} for area in areas if area["retiredAt"]
        ],
    )


@bp.route("/zonas/nueva", methods=("GET", "POST"))
@login_required
def zone_new():
    if request.method == "GET":
        return _page(None, _new_zone_values())

    values = _posted_values()
    result = Api(g.web_user).post("/api/common-areas", _typed(values))
    if result.ok:
        flash(f"Zona {values['name']} creada. Ya se puede reservar; ajusta sus reglas cuando quieras.", "success")
        return redirect(url_for("web.zones_list"))
    flash(result.error, "error")
    return _page(None, values, result.status)


@bp.route("/zonas/<int:area_id>", methods=("GET", "POST"))
@login_required
def zone_edit(area_id):
    api = Api(g.web_user)
    area = _area(api, area_id)
    if request.method == "GET":
        return _page(area, _form_values(area))

    values = _posted_values()
    changes = _changes(area, _typed(values))
    if not changes:
        flash("No cambiaste ninguna regla.", "info")
        return _page(area, values)
    result = api.put(f"/api/common-areas/{area_id}/rules", changes)
    if result.ok:
        name = changes.get("name", area["name"])
        flash(f"Reglas de {name} guardadas. Las reservas nuevas ya las usan; las que existían no cambian.", "success")
        return redirect(url_for("web.zones_list"))
    flash(result.error, "error")
    return _page(area, values, result.status)


@bp.route("/zonas/<int:area_id>/cerrar", methods=("GET", "POST"))
@login_required
def zone_close(area_id):
    """Cierra la zona con el motivo que verán los residentes; si ya estaba cerrada, cambia el motivo."""
    api = Api(g.web_user)
    area = _area(api, area_id)
    reason = text("reason") if request.method == "POST" else (area["closedReason"] or "")
    status = 200
    if request.method == "POST":
        result = api.post(f"/api/common-areas/{area_id}/close", {"reason": reason} if reason else {})
        if result.ok:
            pending = result.get("upcomingReservations", 0)
            message = f"{area['name']} quedó cerrada. Los residentes verán el motivo."
            if pending and area["isOpen"]:
                message += (
                    f" Tiene {texts.plural(pending, 'reserva próxima', 'reservas próximas')} que se "
                    f"{'mantiene' if pending == 1 else 'mantienen'}: revísalas en Reservas."
                )
            flash(message, "success")
            return redirect(url_for("web.zones_list"))
        flash(result.error, "error")
        status = result.status
    return render_template(
        "web/zone_close.html", area=area, reason=reason, max_reason=MAX_CLOSED_REASON,
        upcoming=area.get("upcomingReservations", 0),
    ), status


@bp.post("/zonas/<int:area_id>/abrir")
@login_required
def zone_open(area_id):
    flash_result(Api(g.web_user).post(f"/api/common-areas/{area_id}/open"), "Zona abierta.")
    return redirect(url_for("web.zones_list"))


@bp.post("/zonas/<int:area_id>/retirar")
@login_required
def zone_retire(area_id):
    flash_result(Api(g.web_user).delete(f"/api/common-areas/{area_id}"), "Zona retirada.")
    return redirect(url_for("web.zones_list"))
