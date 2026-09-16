import logging

from flask import jsonify, request
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


DEFAULT_MESSAGES = {
    400: "Solicitud inválida",
    401: "Autenticación requerida",
    403: "No tienes permiso para realizar esta acción",
    404: "Recurso no encontrado",
    405: "Método no permitido",
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
        logger.warning("HTTP %s %s: %s", error.code, request.method, request.path)
        return error_response(error.code, error.description)

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        logger.exception("Error no controlado en %s %s", request.method, request.path)
        return error_response(500)
