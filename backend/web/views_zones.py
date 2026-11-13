"""Zonas comunes y sus reglas de reserva en la web (HU-055).

Cada zona guarda su horario, la duración de sus franjas, cuántas franjas seguidas se reservan de una vez y si
se puede reservar el día completo, su aforo, con cuánta anticipación se puede reservar, hasta cuándo se puede
cancelar, cuántas reservas por semana tiene cada residente y su día de mantenimiento (RN-020 a RN-022). La administración los ajusta aquí, sin tocar el código. Las reservas nuevas usan las
reglas desde que se guardan; las que ya existen no se tocan.

La web solo reúne lo que escribió la administración y lo manda a la API (que revisa cada dato y que todos
tengan sentido juntos). Manda solo lo que cambió, para que el registro de auditoría diga exactamente qué se cambió.
"""

from flask import abort, flash, g, redirect, render_template, request, url_for

from services.zone_rules import ALLOWED_SLOT_MINUTES, WEEKDAY_NAMES, days_text
from web import bp, texts
from web.api import Api
from web.forms import number, text
from web.security import login_required

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
    return {
        "id": area["id"],
        "name": area["name"],
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


def _areas(api):
    """Las zonas que entrega la API; si falla, un aviso y una lista vacía."""
    result = api.get("/api/common-areas")
    if not result.ok:
        flash(result.error, "error")
    return result.get("areas", [])


def _form_values(area):
    """Las reglas de la zona como las muestra el formulario (texto, lo vacío en blanco; las casillas, sí o no)."""
    values = {
        key: "" if area[key] is None else str(area[key])
        for key in (*TIME_FIELDS, *NUMBER_FIELDS)
    }
    for key in FLAG_FIELDS:
        values[key] = bool(area.get(key))
    return values


def _posted_values():
    """Lo que llegó en el formulario: texto en los campos y sí o no en las casillas."""
    values = {key: text(key) for key in (*TIME_FIELDS, *NUMBER_FIELDS)}
    for key in FLAG_FIELDS:
        values[key] = request.form.get(key) == "1"
    return values


def _typed(values):
    """Lo escrito en el formulario como lo entiende la API: horas en texto, números enteros.

    Un campo que se puede dejar vacío viaja como ``None``; los demás, si quedan vacíos, no viajan (sin cambio).
    Lo que no se entiende como número se manda tal cual para que la API lo rechace con su mensaje.
    """
    typed = {}
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
    return render_template(
        "web/zone_form.html", area=area, values=values,
        slot_options=[(str(minutes), texts.slot_length_text(minutes)) for minutes in ALLOWED_SLOT_MINUTES],
        weekday_options=[(str(index), name.capitalize()) for index, name in enumerate(WEEKDAY_NAMES)],
    ), status


@bp.get("/zonas")
@login_required
def zones_list():
    return render_template("web/zones.html", zones=[_summary(area) for area in _areas(Api(g.web_user))])


@bp.route("/zonas/<int:area_id>", methods=("GET", "POST"))
@login_required
def zone_edit(area_id):
    api = Api(g.web_user)
    area = next((item for item in _areas(api) if item["id"] == area_id), None)
    if area is None:
        abort(404)
    if request.method == "GET":
        return _page(area, _form_values(area))

    values = _posted_values()
    changes = _changes(area, _typed(values))
    if not changes:
        flash("No cambiaste ninguna regla.", "info")
        return _page(area, values)
    result = api.put(f"/api/common-areas/{area_id}/rules", changes)
    if result.ok:
        flash(f"Reglas de {area['name']} guardadas. Las reservas nuevas ya las usan; las que existían no cambian.", "success")
        return redirect(url_for("web.zones_list"))
    flash(result.error, "error")
    return _page(area, values, result.status)
