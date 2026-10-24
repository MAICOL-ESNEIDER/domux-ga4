import logging
import os

from dotenv import load_dotenv
from flask import Flask, request
from flask_cors import CORS
from sqlalchemy import inspect

from errors import error_response, register_error_handlers
from extensions import db
from logging_config import configure_logging
from routes.admin import bp as admin_bp
from routes.auth import bp as auth_bp
from routes.community import bp as community_bp
from routes.security import bp as security_bp
from seed import seed_if_empty
from validators import validate_no_empty_strings

load_dotenv()

SQLITE_ADDITIONS = {
    "users": {
        "last_name": "VARCHAR(120)",
        "phone": "VARCHAR(30)",
        "document_id": "VARCHAR(40)",
        "occupancy_type": "VARCHAR(30)",
        "is_active": "BOOLEAN NOT NULL DEFAULT 1",
    },
    "announcements": {
        "event_date": "VARCHAR(20)",
        "event_time": "VARCHAR(20)",
        "media_url": "TEXT",
        "media_type": "VARCHAR(20)",
    },
    "pqrs": {
        "category": "VARCHAR(40)",
        "incident_date": "VARCHAR(20)",
        "incident_time": "VARCHAR(20)",
        "media_url": "TEXT",
        "media_type": "VARCHAR(20)",
        "updated_at": "DATETIME",
    },
    "packages": {
        "media_url": "TEXT",
        "media_type": "VARCHAR(20)",
        "event_date": "VARCHAR(20)",
        "event_time": "VARCHAR(20)",
    },
    "visits": {
        "visitor_document": "VARCHAR(40)",
    },
}


def migrate_sqlite_schema():
    """Add model columns to existing SQLite tables without replacing user data."""
    if db.engine.dialect.name != "sqlite":
        return

    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())
    with db.engine.begin() as connection:
        for table_name, additions in SQLITE_ADDITIONS.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            for column_name, column_type in additions.items():
                if column_name not in existing_columns:
                    connection.exec_driver_sql(
                        f'ALTER TABLE "{table_name}" ADD COLUMN '
                        f'"{column_name}" {column_type}'
                    )
        if "reservations" in existing_tables:
            duplicate_active_slots = connection.exec_driver_sql(
                "SELECT 1 FROM reservations "
                "WHERE status IN ('activa', 'aprobada') "
                "GROUP BY common_area_id, date, time_slot "
                "HAVING COUNT(*) > 1 LIMIT 1"
            ).first()
            if duplicate_active_slots:
                logging.getLogger(__name__).warning(
                    "Reservation uniqueness index was skipped because legacy "
                    "active reservations already contain duplicate time slots."
                )
                return
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_reservation_active_slot "
                "ON reservations (common_area_id, date, time_slot) "
                "WHERE status IN ('activa', 'aprobada')"
            )


def create_app():
    app = Flask(__name__)
    configure_logging(app)
    CORS(app)

    database_url = os.environ.get("DATABASE_URL", "sqlite:///domux.db")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(community_bp)
    app.register_blueprint(security_bp)
    register_error_handlers(app)

    @app.before_request
    def reject_empty_write_fields():
        if request.method not in ("POST", "PUT", "PATCH"):
            return None
        body = request.get_data(cache=True)
        if not body:
            return None
        if not request.is_json:
            return error_response(400, "El cuerpo de la solicitud debe usar JSON.")
        data = request.get_json(silent=True)
        validation_error = validate_no_empty_strings(data)
        if validation_error:
            return error_response(400, validation_error)
        return None

    with app.app_context():
        db.create_all()
        migrate_sqlite_schema()
        seed_if_empty()

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
