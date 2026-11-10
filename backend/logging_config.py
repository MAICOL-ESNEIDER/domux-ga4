import logging
import os

from flask import request


#: Marca de la salida de consola que agrega DOMUX, para no duplicarla.
_HANDLER_NAME = "domux-consola"


def configure_logging(app):
    """Configura los registros del servidor: una sola salida por consola, con fecha.

    Todos los registros (los de la app, los de cada módulo y los de Alembic) pasan
    por la misma salida, así ninguna línea sale repetida. El nivel se toma de
    LOG_LEVEL (INFO si no se define).
    """
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    root = logging.getLogger()
    if not any(handler.get_name() == _HANDLER_NAME for handler in root.handlers):
        console_handler = logging.StreamHandler()
        console_handler.set_name(_HANDLER_NAME)
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        root.addHandler(console_handler)
    root.setLevel(level)
    # La app usa la salida común; las migraciones solo informan si algo falla.
    app.logger.handlers.clear()
    app.logger.setLevel(level)
    logging.getLogger("alembic").setLevel(logging.WARNING)

    @app.before_request
    def log_request_start():
        app.logger.info("request_start method=%s path=%s", request.method, request.path)

    @app.after_request
    def log_request_end(response):
        app.logger.info(
            "request_end method=%s path=%s status=%s",
            request.method,
            request.path,
            response.status_code,
        )
        return response
