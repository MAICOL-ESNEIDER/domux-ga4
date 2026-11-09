import logging
import os

from flask import request


def configure_logging(app):
    """Log request audit events to the server console only."""
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    app.logger.setLevel(level)
    app.logger.handlers.clear()
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    app.logger.addHandler(console_handler)

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
