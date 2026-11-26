"""Reglas de la unidad: la administración cambia plazos y alertas sin tocar el código (DEC-032, RN-022).

Aquí están los límites de lo que se puede guardar; las rutas solo leen la solicitud, llaman a estas funciones
y responden. Ninguna guarda en la base (commit): lo hace la ruta, para que el cambio y su anotación en la
auditoría se guarden juntos.

Los valores viven en una sola fila (UnitSettings). Una regla que la administración nunca tocó, o que devolvió
a «el valor de DOMUX» enviando null, queda vacía en la fila y rige el valor por defecto (unit_rules.py). Un
cambio rige desde ese momento para todo, también para lo que ya existe: por ejemplo, el semáforo de una PQRS
abierta se recalcula con el plazo nuevo.
"""

from types import SimpleNamespace

from errors import ApiError
from extensions import db
from models import UnitSettings, User
from services.audit_service import add_audit_log
from services.unit_rules import (
    ARCHIVE_DAYS_LIMITS,
    AUTO_QR_LIMITS,
    MOTOS_PER_SPOT_LIMITS,
    PACKAGE_ORANGE_LIMITS,
    PACKAGE_RED_LIMITS,
    PARKING_DAYS_LIMITS,
    QR_PEOPLE_LIMITS,
    QR_VALID_LIMITS,
    VISIT_STAY_LIMITS,
    PQRS_CATEGORIES,
    PQRS_TERM_LIMITS,
    PQRS_WARNING_LIMITS,
    default_rules,
    read_category_terms,
    rules_from_row,
    write_category_terms,
)
from time_utils import format_colombia, utc_now

#: (dato de la API, columna, mínimo y máximo, cómo se llama en los mensajes). La API habla en camelCase.
SIMPLE_RULES = (
    ("pqrsTermDays", "pqrs_term_days", PQRS_TERM_LIMITS,
     "El plazo para responder una PQRS", "días hábiles"),
    ("pqrsWarningDays", "pqrs_warning_days", PQRS_WARNING_LIMITS,
     "El aviso amarillo de una PQRS (días hábiles por vencer)", "días hábiles"),
    ("packageOrangeHours", "package_orange_hours", PACKAGE_ORANGE_LIMITS,
     "El aviso naranja de un paquete sin reclamar", "horas"),
    ("packageRedHours", "package_red_hours", PACKAGE_RED_LIMITS,
     "El aviso rojo de un paquete sin reclamar", "horas"),
    ("visitorParkingMaxDays", "visitor_parking_max_days", PARKING_DAYS_LIMITS,
     "El tiempo máximo de un vehículo visitante en el parqueadero", "días"),
    ("visitMaxStayDays", "visit_max_stay_days", VISIT_STAY_LIMITS,
     "La estadía máxima que se puede anotar en una visita", "días"),
    ("qrMaxPeople", "qr_max_people", QR_PEOPLE_LIMITS,
     "Las personas que caben en un solo QR de visita", "personas"),
    ("qrMaxValidDays", "qr_max_valid_days", QR_VALID_LIMITS,
     "La vigencia máxima de un QR de visita", "días"),
    ("autoQrMinStayDays", "auto_qr_min_stay_days", AUTO_QR_LIMITS,
     "Los días de estadía desde los que el QR de la visita se crea solo", "días"),
    ("deliveredArchiveDays", "delivered_archive_days", ARCHIVE_DAYS_LIMITS,
     "Los días que un paquete entregado tarda en archivarse solo", "días"),
    ("motosPerCarSpot", "motos_per_car_spot", MOTOS_PER_SPOT_LIMITS,
     "Las motos que caben en un parqueadero de carro de visitantes", "motos"),
)

CATEGORY_KEY = "pqrsTermsByCategory"
CATEGORY_COLUMN = "pqrs_terms_by_category"


def get_settings():
    """La fila de reglas, o None mientras la administración no haya guardado ninguna."""
    return db.session.get(UnitSettings, UnitSettings.SINGLE_ID)


def _whole_number(value, label, limits, unit):
    """Un número entero dentro de los límites; cualquier otra cosa (texto, decimales, verdadero/falso) se rechaza."""
    low, high = limits
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(f"{label} debe ser un número entero de {unit}, entre {low} y {high}.")
    if not low <= value <= high:
        raise ApiError(f"{label} debe estar entre {low} y {high} {unit}.")
    return value


def parse_category_terms(value):
    """Los plazos por tipo de PQRS como ``{tipo: días hábiles}``; vacío o null los quita todos."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ApiError(
            "Los plazos por tipo deben ser un objeto con cada tipo y sus días hábiles, por ejemplo {\"Daño\": 5}."
        )
    terms = {}
    for category, days in value.items():
        if category not in PQRS_CATEGORIES:
            known = ", ".join(PQRS_CATEGORIES[:-1]) + f" y {PQRS_CATEGORIES[-1]}"
            raise ApiError(f"«{category}» no es un tipo de PQRS. Los tipos son: {known}.")
        terms[category] = _whole_number(days, f"El plazo de «{category}»", PQRS_TERM_LIMITS, "días hábiles")
    return terms


def _check_together(rules):
    """Que las reglas tengan sentido juntas (se revisa con los valores que quedarían, no con los enviados)."""
    if rules.pqrs_warning_days > rules.pqrs_term_days:
        raise ApiError(
            f"El semáforo no puede pasar a amarillo con {rules.pqrs_warning_days} días hábiles por vencer "
            f"si el plazo general es de {rules.pqrs_term_days}. "
            f"Baja los días del aviso amarillo (máximo {rules.pqrs_term_days}) o sube el plazo."
        )
    if rules.auto_qr_min_stay_days > rules.visit_max_stay_days:
        raise ApiError(
            f"El QR automático desde {rules.auto_qr_min_stay_days} días de estadía no puede ser mayor que la "
            f"estadía máxima ({rules.visit_max_stay_days} días)."
        )
    if rules.package_red_hours <= rules.package_orange_hours:
        raise ApiError(
            f"El aviso rojo ({rules.package_red_hours} horas) debe llegar después del naranja "
            f"({rules.package_orange_hours} horas)."
        )


def _stored(row):
    """Lo que dice la fila, tal cual (con None donde rige el valor de DOMUX)."""
    if row is None:
        return {key: None for key, *_rest in SIMPLE_RULES} | {CATEGORY_KEY: None}
    values = {key: getattr(row, column) for key, column, *_rest in SIMPLE_RULES}
    values[CATEGORY_KEY] = write_category_terms(read_category_terms(row.pqrs_terms_by_category))
    return values


def customized_flags(row):
    """Qué reglas cambió la administración (las demás rigen con el valor de DOMUX)."""
    return {key: value is not None for key, value in _stored(row).items()}


def update_rules(data, actor):
    """Guarda las reglas que trae la solicitud; las que no trae quedan como estaban.

    Una regla enviada como null vuelve al valor de DOMUX. Primero se revisa todo (cada valor y que las
    reglas tengan sentido juntas) y recién después se toca la fila: un dato inválido no deja nada a medias.
    Si nada cambió no se anota nada en la auditoría. Devuelve la fila.
    """
    row = get_settings()
    before_rules = rules_from_row(row)
    before_stored = _stored(row)

    changes = {}
    for key, column, limits, label, unit in SIMPLE_RULES:
        if key in data:
            changes[column] = None if data[key] is None else _whole_number(data[key], label, limits, unit)
    if CATEGORY_KEY in data:
        changes[CATEGORY_COLUMN] = write_category_terms(parse_category_terms(data[CATEGORY_KEY]))
    if not changes:
        raise ApiError("Debes proporcionar al menos una regla para actualizar.")

    # Cómo quedarían las reglas, para revisarlas juntas antes de guardar nada.
    creating = row is None
    if creating and all(value is None for value in changes.values()):
        return None  # primera vez y solo «volver al valor de DOMUX»: no hay nada que guardar
    merged = {column: getattr(row, column, None) for _key, column, *_rest in SIMPLE_RULES}
    merged[CATEGORY_COLUMN] = getattr(row, CATEGORY_COLUMN, None)
    merged.update(changes)
    after_rules = rules_from_row(SimpleNamespace(**merged))
    _check_together(after_rules)

    if creating:
        row = UnitSettings(id=UnitSettings.SINGLE_ID)
        db.session.add(row)
    for column, value in changes.items():
        setattr(row, column, value)
    after_stored = _stored(row)
    if creating or before_stored != after_stored:
        row.updated_at = utc_now()
        row.updated_by_id = actor.id
        db.session.flush()
        add_audit_log(
            "unit_settings", row.id, "created" if creating else "updated",
            {"before": before_rules.to_dict(), "after": after_rules.to_dict()},
            actor=actor,
        )
    return row


def rules_view(row=None):
    """Lo que ve la administración: las reglas vigentes, las de DOMUX, cuáles cambió y quién fue."""
    row = row if row is not None else get_settings()
    editor = db.session.get(User, row.updated_by_id) if row is not None and row.updated_by_id else None
    return {
        "rules": rules_from_row(row).to_dict(),
        "defaults": default_rules().to_dict(),
        "customized": customized_flags(row),
        "updatedAt": format_colombia(row.updated_at) if row is not None else None,
        "updatedByName": editor.full_name if editor is not None else None,
    }
