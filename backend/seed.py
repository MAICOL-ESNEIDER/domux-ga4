"""Create demo accounts and community data for an empty database."""

import os
import secrets

from flask import current_app
from werkzeug.security import generate_password_hash

from extensions import db
from models import Announcement, CommonArea, PackageItem, User
from time_utils import now_colombia


def seed_if_empty():
    if User.query.first() is not None:
        return

    if current_app.config.get("TESTING"):
        passwords = {
            "admin": secrets.token_urlsafe(24),
            "guard": secrets.token_urlsafe(24),
            "resident": secrets.token_urlsafe(24),
        }
    else:
        passwords = {
            "admin": os.environ.get("SEED_ADMIN_PASSWORD"),
            "guard": os.environ.get("SEED_GUARD_PASSWORD"),
            "resident": os.environ.get("SEED_RESIDENT_PASSWORD"),
        }
        if not all(passwords.values()):
            current_app.logger.info(
                "Seed inicial omitido: configura SEED_ADMIN_PASSWORD, "
                "SEED_GUARD_PASSWORD y SEED_RESIDENT_PASSWORD."
            )
            return

    admin = User(
        name="Administración",
        last_name="Domux",
        email="admin@domux.com",
        password_hash=generate_password_hash(passwords["admin"]),
        role="ADMIN",
        occupancy_type="propietario",
    )
    guardia = User(
        name="Guardia",
        last_name="Principal",
        email="guardia@domux.com",
        password_hash=generate_password_hash(passwords["guard"]),
        role="GUARD",
        occupancy_type="propietario",
    )
    residente1 = User(
        name="María",
        last_name="Gómez",
        email="maria@domux.com",
        password_hash=generate_password_hash(passwords["resident"]),
        role="RESIDENT",
        apartment="Torre 1 · Apto 101",
        phone="3000000001",
        document_id="1000000001",
        occupancy_type="propietario",
    )
    residente2 = User(
        name="Carlos",
        last_name="Pérez",
        email="carlos@domux.com",
        password_hash=generate_password_hash(passwords["resident"]),
        role="RESIDENT",
        apartment="Torre 2 · Apto 202",
        phone="3000000002",
        document_id="1000000002",
        occupancy_type="arrendatario",
    )
    db.session.add_all([admin, guardia, residente1, residente2])
    db.session.commit()

    db.session.add_all([
        CommonArea(name="Salón social"),
        CommonArea(name="Salón de Juegos"),
        CommonArea(name="Cancha múltiple"),
        CommonArea(name="Zona BBQ"),
    ])
    db.session.add(Announcement(
        title="¡Bienvenido a Domux!",
        message=(
            "Esta es la app de gestión de la unidad residencial. Aquí verás "
            "los anuncios de administración, tus PQRS, tus reservas y las "
            "notificaciones de paquetes y visitantes."
        ),
        author_id=admin.id,
    ))
    db.session.add_all([
        PackageItem(
            resident_id=residente1.id,
            registered_by=guardia.id,
            description="Paquete de prueba pendiente",
            status="pendiente",
        ),
        PackageItem(
            resident_id=residente2.id,
            registered_by=guardia.id,
            description="Paquete de prueba por llegar",
            status="por_llegar",
        ),
        PackageItem(
            resident_id=residente1.id,
            registered_by=guardia.id,
            description="Paquete de prueba entregado",
            status="entregado",
            delivered_at=now_colombia(),
            delivered_to=residente1.full_name,
            delivered_by_id=guardia.id,
        ),
    ])
    db.session.commit()

    current_app.logger.info("Cuentas iniciales y datos comunitarios creados.")
