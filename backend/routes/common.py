"""Piezas que comparten las rutas de la API."""

from flask import request

from errors import error_response
from validators import validate_no_empty_strings


def json_body():
    """Lee el cuerpo JSON de la solicitud y revisa que no traiga textos vacíos.

    Devuelve ``(datos, None)`` si todo está bien, o ``(None, respuesta_de_error)``
    para que la ruta responda con el error tal cual.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, error_response(400, "El cuerpo de la solicitud debe ser un objeto JSON válido.")
    message = validate_no_empty_strings(data)
    if message:
        return None, error_response(400, message)
    return data, None
