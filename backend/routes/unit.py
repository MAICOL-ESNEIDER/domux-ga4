"""Rutas de los datos de la unidad (HU-077).

Cualquier persona con sesión (residente, portería o administración) lee el nombre, el NIT, la
dirección, el teléfono de portería y el logo de la unidad; solo la administración los cambia
(ADR-015). Las reglas están en services/unit_service.py.
"""

from flask import Blueprint, g, jsonify

from auth import role_required, token_required
from errors import ApiError
from routes.common import json_object, save_changes
from services import unit_service as unit

bp = Blueprint("unit", __name__, url_prefix="/api")


@bp.get("/unit-info")
@token_required
def get_unit_info():
    """Los datos de la unidad; mientras no se hayan guardado, todos vienen vacíos."""
    return jsonify({"unit": unit.unit_dict()})


@bp.get("/unit-info/logo")
@token_required
def get_unit_logo():
    """La imagen del logo (solo si la unidad tiene una); responde 304 si no cambió desde la última vez."""
    response = unit.logo_response()
    if response is None:
        raise ApiError("La unidad todavía no tiene un logo.", 404)
    return response


@bp.put("/admin/unit-info")
@token_required
@role_required("ADMIN")
def update_unit_info():
    profile = unit.update_unit(json_object(required=True), g.current_user)
    save_changes("Otra persona estaba guardando los datos de la unidad al mismo tiempo. Inténtalo de nuevo.")
    return jsonify({"message": "Datos de la unidad guardados", "unit": profile.to_dict()})
