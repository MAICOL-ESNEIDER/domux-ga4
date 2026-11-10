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


def register_error_handlers(app):
    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        logger.warning("HTTP %s %s: %s", error.code, request.method, safe_path(request.path))
        return error_response(error.code, DEFAULT_MESSAGES.get(error.code))

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        logger.exception("Error no controlado en %s %s", request.method, safe_path(request.path))
        return error_response(500)
