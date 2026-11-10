import logging

from flask import jsonify, request
from werkzeug.exceptions import HTTPException

from logging_config import safe_path

logger = logging.getLogger(__name__)


#: Mensajes en español para los errores que responde Flask por su cuenta
#: (ruta inexistente, método no permitido, archivo muy grande...). El texto de
#: Werkzeug viene en inglés, por eso no se usa (DEF-012).
DEFAULT_MESSAGES = {
    400: "Solicitud inválida",
    401: "Autenticación requerida",
    403: "No tienes permiso para realizar esta acción",
    404: "Recurso no encontrado",
    405: "Método no permitido para esta ruta",
    413: "La solicitud supera el tamaño máximo permitido (12 MB)",
    415: "Tipo de contenido no admitido",
    429: "Demasiadas solicitudes: espera un momento e inténtalo de nuevo",
    500: "Error interno del servidor",
}


def error_response(status_code, message=None):
    return jsonify({
        "error": message or DEFAULT_MESSAGES.get(status_code, "Error en la solicitud"),
        "status": status_code,
    }), status_code


class ApiError(ValueError):
    """Un error que la API responde tal cual: un mensaje claro y su código HTTP.

    Los servicios lo lanzan cuando un dato no es válido o choca con otro (400,
    404, 409...) y no necesitan conocer Flask. Hereda de ValueError para que el
    importador del censo lo cuente como un error de esa fila.
    """

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(error):
        return error_response(error.status, error.message)

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        logger.warning("HTTP %s %s: %s", error.code, request.method, safe_path(request.path))
        return error_response(error.code, DEFAULT_MESSAGES.get(error.code))

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        logger.exception("Error no controlado en %s %s", request.method, safe_path(request.path))
        return error_response(500)
