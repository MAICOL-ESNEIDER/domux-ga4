"""Reglas de la unidad que la administración puede ajustar: lo que antes estaba fijo en el código (DEC-032).

Los plazos y las alertas cambian de un conjunto a otro, y dentro de un mismo conjunto cambian cuando la
asamblea lo decide. Por eso viven en una sola fila de la base (UnitSettings) que la administración edita
desde la web, y no en el código:

* PQRS: los días hábiles para responder (el general y uno por tipo) y cuántos días antes de vencer el
  semáforo pasa a amarillo (RN-025).
* Paquetes: las horas sin reclamar para que se pongan naranja y rojo (RN-018).
* Parqueadero de visitantes: los días que un vehículo puede quedarse (RN-015).

Una regla que la administración nunca tocó usa el valor de DOMUX (el de ``DEFAULT_RULES``); así, mientras la
fila no exista todo se comporta como hasta ahora.

Este archivo solo lee: lo importan el modelo y las reglas puras de las PQRS, así que no importa ``models``
al cargarse (lo hace dentro de la función que consulta). Guardar los cambios, con sus límites, está en
``rules_service.py``.
"""

import json
from dataclasses import dataclass, field
from types import MappingProxyType

from flask import g, has_app_context

from config import visitor_parking_max_days
from extensions import db

#: Los tipos de PQRS que ofrece la app y la web. Un tipo que no esté aquí usa el plazo general.
PQRS_CATEGORIES = ("Petición", "Queja", "Reclamo", "Sugerencia", "Daño")

#: Valores de DOMUX: los que rigen mientras la administración no cambie nada.
DEFAULT_PQRS_TERM_DAYS = 15
DEFAULT_PQRS_WARNING_DAYS = 5
DEFAULT_PACKAGE_ORANGE_HOURS = 48
DEFAULT_PACKAGE_RED_HOURS = 72

#: (mínimo, máximo) que se acepta de cada regla: sirven para que nadie guarde un valor absurdo por error.
PQRS_TERM_LIMITS = (1, 90)
PQRS_WARNING_LIMITS = (1, 30)
PACKAGE_ORANGE_LIMITS = (1, 720)
PACKAGE_RED_LIMITS = (2, 1440)
PARKING_DAYS_LIMITS = (1, 30)

_CACHE_KEY = "_unit_rules"


@dataclass(frozen=True)
class UnitRules:
    """Las reglas vigentes de la unidad, ya con el valor de DOMUX donde la administración no cambió nada."""

    pqrs_term_days: int
    pqrs_warning_days: int
    pqrs_terms_by_category: dict = field(default_factory=dict)
    package_orange_hours: int = DEFAULT_PACKAGE_ORANGE_HOURS
    package_red_hours: int = DEFAULT_PACKAGE_RED_HOURS
    visitor_parking_max_days: int = 3

    def pqrs_term_for(self, category):
        """Días hábiles para responder una PQRS de ese tipo (el general si el tipo no tiene plazo propio)."""
        return self.pqrs_terms_by_category.get(category, self.pqrs_term_days)

    def to_dict(self):
        """Como lo recibe la app y la web (los nombres que usa la API)."""
        return {
            "pqrsTermDays": self.pqrs_term_days,
            "pqrsWarningDays": self.pqrs_warning_days,
            "pqrsTermsByCategory": dict(self.pqrs_terms_by_category),
            "packageOrangeHours": self.package_orange_hours,
            "packageRedHours": self.package_red_hours,
            "visitorParkingMaxDays": self.visitor_parking_max_days,
        }


def default_rules():
    """Las reglas de DOMUX. El parqueadero de visitantes puede traer otro valor de la variable de entorno."""
    return UnitRules(
        pqrs_term_days=DEFAULT_PQRS_TERM_DAYS,
        pqrs_warning_days=DEFAULT_PQRS_WARNING_DAYS,
        pqrs_terms_by_category=MappingProxyType({}),
        package_orange_hours=DEFAULT_PACKAGE_ORANGE_HOURS,
        package_red_hours=DEFAULT_PACKAGE_RED_HOURS,
        visitor_parking_max_days=visitor_parking_max_days(),
    )


def read_category_terms(raw):
    """Los plazos por tipo guardados como texto JSON, como ``{tipo: días}``; lo ilegible se ignora."""
    if not raw:
        return {}
    try:
        stored = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(stored, dict):
        return {}
    return {
        category: days
        for category, days in stored.items()
        if isinstance(category, str) and isinstance(days, int) and not isinstance(days, bool) and days > 0
    }


def write_category_terms(terms):
    """Los plazos por tipo como texto JSON para guardarlos, o None si no hay ninguno."""
    if not terms:
        return None
    ordered = {category: terms[category] for category in PQRS_CATEGORIES if category in terms}
    return json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))


def rules_from_row(row):
    """Las reglas que dice la fila guardada; donde falta un valor (o no hay fila) rige el de DOMUX."""
    base = default_rules()
    if row is None:
        return base
    return UnitRules(
        pqrs_term_days=row.pqrs_term_days or base.pqrs_term_days,
        pqrs_warning_days=row.pqrs_warning_days or base.pqrs_warning_days,
        pqrs_terms_by_category=read_category_terms(row.pqrs_terms_by_category),
        package_orange_hours=row.package_orange_hours or base.package_orange_hours,
        package_red_hours=row.package_red_hours or base.package_red_hours,
        visitor_parking_max_days=row.visitor_parking_max_days or base.visitor_parking_max_days,
    )


def current_rules():
    """Las reglas vigentes de la unidad.

    Se consultan una sola vez por solicitud (aunque una lista calcule el semáforo de cien PQRS) y se
    olvidan cuando se guarda un cambio en la fila (ver ``forget_rules``). Fuera de la aplicación (por
    ejemplo, en una prueba de una regla suelta) no hay base de datos y rigen los valores de DOMUX.
    """
    if not has_app_context():
        return default_rules()
    cached = g.get(_CACHE_KEY)
    if cached is not None:
        return cached
    from models import UnitSettings  # aquí y no arriba: el modelo importa este archivo

    rules = rules_from_row(db.session.get(UnitSettings, UnitSettings.SINGLE_ID))
    setattr(g, _CACHE_KEY, rules)
    return rules


def forget_rules():
    """Hace que la próxima consulta lea las reglas de nuevo (se llama cuando cambia la fila)."""
    if has_app_context() and _CACHE_KEY in g:
        delattr(g, _CACHE_KEY)
