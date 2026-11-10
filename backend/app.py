import logging
import os

from dotenv import load_dotenv
from flask import Flask, request
from flask_cors import CORS
from flask_migrate import stamp, upgrade
from sqlalchemy import inspect

from config import cors_origins
from errors import error_response, register_error_handlers
from extensions import db, migrations
from logging_config import configure_logging
from models import Apartment, Pqrs, PqrsMessage, ResidentialUnit, User
from routes.admin import bp as admin_bp
from routes.auth import bp as auth_bp
from routes.community import bp as community_bp
from routes.security import bp as security_bp
from routes.structure import bp as structure_bp
from routes.vehicles import bp as vehicles_bp
from seed import seed_if_empty, sync_demo_passwords
from validators import OCCUPANCY_TYPES, validate_no_empty_strings

load_dotenv()

#: Carpeta de las migraciones de Alembic y versión que tienen las bases antiguas.
MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")
BASE_REVISION = "0001_base"

SQLITE_ADDITIONS = {
    "users": {
        "last_name": "VARCHAR(120)",
        "phone": "VARCHAR(30)",
        "document_id": "VARCHAR(40)",
        "occupancy_type": "VARCHAR(30)",
        "apartment_number": "INTEGER",
        "social_networks": "VARCHAR(500)",
        "birth_date": "VARCHAR(20)",
        "parental_consent": "BOOLEAN NOT NULL DEFAULT 0",
        "data_processing_consent": "BOOLEAN NOT NULL DEFAULT 0",
        "data_processing_consent_at": "DATETIME",
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
        "created_by_admin_id": "INTEGER REFERENCES users(id)",
        "is_archived": "BOOLEAN NOT NULL DEFAULT 0",
        "archived_at": "DATETIME",
    },
    "reservations": {
        "created_by_admin_id": "INTEGER REFERENCES users(id)",
        "is_archived": "BOOLEAN NOT NULL DEFAULT 0",
        "archived_at": "DATETIME",
    },
    "packages": {
        "media_url": "TEXT",
        "media_type": "VARCHAR(20)",
        "event_date": "VARCHAR(20)",
        "event_time": "VARCHAR(20)",
        "delivered_to": "VARCHAR(120)",
        "delivered_by_id": "INTEGER REFERENCES users(id)",
        "is_deleted": "BOOLEAN NOT NULL DEFAULT 0",
        "deleted_at": "DATETIME",
        "deleted_by_id": "INTEGER REFERENCES users(id)",
    },
    "visits": {
        "visitor_document": "VARCHAR(40)",
        "visitor_photo_url": "TEXT",
        "visitor_photo_type": "VARCHAR(20)",
        "media_consent": "BOOLEAN NOT NULL DEFAULT FALSE",
        "description": "VARCHAR(250)",
        "approval_status": "VARCHAR(20) NOT NULL DEFAULT 'pendiente'",
        "authorization_method": "VARCHAR(20)",
        "entered_at": "DATETIME",
        "exited_at": "DATETIME",
        "exit_returning": "BOOLEAN NOT NULL DEFAULT FALSE",
        "qr_pass_id": "INTEGER REFERENCES visit_qr_passes(id)",
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


def migrate_profile_columns():
    """Add profile columns on existing SQLite or PostgreSQL databases."""
    inspector = inspect(db.engine)
    if "users" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    dialect = db.engine.dialect.name
    column_types = {
        "apartment_number": "INTEGER",
        "social_networks": "VARCHAR(500)",
        "birth_date": "VARCHAR(20)",
        "parental_consent": (
            "BOOLEAN NOT NULL DEFAULT FALSE" if dialect == "postgresql"
            else "BOOLEAN NOT NULL DEFAULT 0"
        ),
        "data_processing_consent": (
            "BOOLEAN NOT NULL DEFAULT FALSE" if dialect == "postgresql"
            else "BOOLEAN NOT NULL DEFAULT 0"
        ),
        "data_processing_consent_at": (
            "TIMESTAMP" if dialect == "postgresql" else "DATETIME"
        ),
    }
    with db.engine.begin() as connection:
        for name, column_type in column_types.items():
            if name not in existing_columns:
                connection.exec_driver_sql(
                    f'ALTER TABLE "users" ADD COLUMN "{name}" {column_type}'
                )


def migrate_admin_action_columns():
    """Add nullable audit references for admin-created resident requests."""
    inspector = inspect(db.engine)
    for table_name in ("pqrs", "reservations"):
        if table_name not in inspector.get_table_names():
            continue
        existing_columns = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        if "created_by_admin_id" in existing_columns:
            continue
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                f'ALTER TABLE "{table_name}" ADD COLUMN "created_by_admin_id" '
                'INTEGER REFERENCES users(id)'
            )


def migrate_security_columns():
    """Add portería workflow fields to existing SQLite and PostgreSQL databases."""
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    dialect = db.engine.dialect.name
    additions = {
        "packages": {
            "delivered_to": "VARCHAR(120)",
            "delivered_by_id": "INTEGER REFERENCES users(id)",
            "is_deleted": (
                "BOOLEAN NOT NULL DEFAULT FALSE" if dialect == "postgresql"
                else "BOOLEAN NOT NULL DEFAULT 0"
            ),
            "deleted_at": "TIMESTAMP" if dialect == "postgresql" else "DATETIME",
            "deleted_by_id": "INTEGER REFERENCES users(id)",
        },
        "visits": {
            "visitor_photo_url": "TEXT",
            "visitor_photo_type": "VARCHAR(20)",
            "media_consent": (
                "BOOLEAN NOT NULL DEFAULT FALSE" if dialect == "postgresql"
                else "BOOLEAN NOT NULL DEFAULT 0"
            ),
            "description": "VARCHAR(250)",
            "approval_status": "VARCHAR(20) NOT NULL DEFAULT 'pendiente'",
            "authorization_method": "VARCHAR(20)",
            "entered_at": "TIMESTAMP" if dialect == "postgresql" else "DATETIME",
            "exited_at": "TIMESTAMP" if dialect == "postgresql" else "DATETIME",
            "exit_returning": (
                "BOOLEAN NOT NULL DEFAULT FALSE" if dialect == "postgresql"
                else "BOOLEAN NOT NULL DEFAULT 0"
            ),
            "qr_pass_id": "INTEGER REFERENCES visit_qr_passes(id)",
        },
        "visit_qr_passes": {
            "revoked_at": "TIMESTAMP" if dialect == "postgresql" else "DATETIME",
        },
        "pqrs": {
            "is_archived": (
                "BOOLEAN NOT NULL DEFAULT FALSE" if dialect == "postgresql"
                else "BOOLEAN NOT NULL DEFAULT 0"
            ),
            "archived_at": "TIMESTAMP" if dialect == "postgresql" else "DATETIME",
        },
        "reservations": {
            "is_archived": (
                "BOOLEAN NOT NULL DEFAULT FALSE" if dialect == "postgresql"
                else "BOOLEAN NOT NULL DEFAULT 0"
            ),
            "archived_at": "TIMESTAMP" if dialect == "postgresql" else "DATETIME",
        },
    }
    with db.engine.begin() as connection:
        for table_name, columns in additions.items():
            if table_name not in tables:
                continue
            existing_columns = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            for column_name, column_type in columns.items():
                if column_name not in existing_columns:
                    connection.exec_driver_sql(
                        f'ALTER TABLE "{table_name}" ADD COLUMN '
                        f'"{column_name}" {column_type}'
                    )


def migrate_resident_profiles():
    """Deja al día los datos de los residentes sin borrar nada.

    Todo residente con apartamento debe tener su tipo de ocupación (RN-007) y
    todo apartamento vigente su ficha del hogar. El texto del apartamento de las
    bases viejas ya lo pasó a la estructura la migración 0006.
    """
    residents = User.query.filter(
        User.role == "RESIDENT",
        User.apartment_id.isnot(None),
    ).all()
    for resident in residents:
        if resident.occupancy_type not in OCCUPANCY_TYPES:
            resident.occupancy_type = "residente"
    for apartment in Apartment.query.filter(Apartment.retired_at.is_(None)).all():
        if apartment.unit is None:
            apartment.unit = ResidentialUnit()
    db.session.commit()


def migrate_pqrs_conversations():
    """Preserve the legacy PQRS description and response as conversation messages."""
    admin_id = db.session.query(User.id).filter_by(role="ADMIN").first()
    for pqrs in Pqrs.query.all():
        if pqrs.conversation:
            continue
        pqrs.conversation.append(PqrsMessage(
            author_id=pqrs.resident_id,
            author_role="RESIDENT",
            message=pqrs.message,
            media_url=pqrs.media_url,
            media_type=pqrs.media_type,
            created_at=pqrs.created_at,
        ))
        if pqrs.admin_response and pqrs.admin_response.strip():
            pqrs.conversation.append(PqrsMessage(
                author_id=admin_id[0] if admin_id else None,
                author_role="ADMIN",
                message=pqrs.admin_response,
                created_at=pqrs.updated_at or pqrs.created_at,
            ))
    db.session.commit()


def prepare_database():
    """Deja la estructura de la base al día al arrancar el servidor (TT-008).

    Una base nueva se crea con las migraciones de Alembic. Una base creada antes
    de usar migraciones (con db.create_all) se completa con las tablas y columnas
    que le falten, se marca con la versión inicial y desde ahí sigue con
    migraciones, sin perder datos.
    """
    tables = set(inspect(db.engine).get_table_names())
    if tables and "alembic_version" not in tables:
        db.create_all()
        migrate_sqlite_schema()
        migrate_profile_columns()
        migrate_admin_action_columns()
        migrate_security_columns()
        stamp(directory=MIGRATIONS_DIR, revision=BASE_REVISION)
    upgrade(directory=MIGRATIONS_DIR)


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
    configure_logging(app)
    # Solo las páginas de CORS_ORIGINS pueden llamar a la API desde un navegador.
    # La app Android no lo necesita y la web la sirve este mismo servidor.
    allowed_origins = cors_origins()
    if allowed_origins:
        CORS(app, origins=allowed_origins)

    database_url = os.environ.get("DATABASE_URL", "sqlite:///domux.db")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    migrations.init_app(app, db, directory=MIGRATIONS_DIR, render_as_batch=True)

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(community_bp)
    app.register_blueprint(security_bp)
    app.register_blueprint(structure_bp)
    app.register_blueprint(vehicles_bp)
    register_error_handlers(app)

    @app.before_request
    def reject_empty_write_fields():
        if request.method not in ("POST", "PUT", "PATCH"):
            return None
        if request.path == "/api/profile" and request.method == "PUT":
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

    # Para crear una migración nueva (flask db migrate) la base debe quedar como
    # está: con DOMUX_SKIP_STARTUP=1 el servidor no la toca al cargarse.
    if os.environ.get("DOMUX_SKIP_STARTUP") == "1":
        return app

    with app.app_context():
        prepare_database()
        seed_if_empty()
        sync_demo_passwords()
        # Completan datos de registros viejos; no hacen nada si ya están al día.
        migrate_resident_profiles()
        migrate_pqrs_conversations()

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # El modo de depuración solo se activa a propósito (FLASK_DEBUG=1): con él
    # encendido, cualquiera en la misma red podría ejecutar código en el equipo.
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
