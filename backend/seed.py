"""Create demo accounts and community data for an empty database."""

from werkzeug.security import generate_password_hash

from extensions import db
from models import Announcement, CommonArea, User


def seed_if_empty():
    if User.query.first() is not None:
        return

    admin = User(
        name="Administración",
        last_name="Domux",
        email="admin@domux.com",
        password_hash=generate_password_hash("Admin123*"),
        role="ADMIN",
        occupancy_type="propietario",
    )
    guardia = User(
        name="Guardia",
        last_name="Principal",
        email="guardia@domux.com",
        password_hash=generate_password_hash("Guardia123*"),
        role="GUARD",
        occupancy_type="propietario",
    )
    residente1 = User(
        name="María",
        last_name="Gómez",
        email="maria@domux.com",
        password_hash=generate_password_hash("Residente123*"),
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
        password_hash=generate_password_hash("Residente123*"),
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
        CommonArea(name="Gimnasio"),
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
    db.session.commit()

    print("Datos de prueba creados:")
    print("  Admin     -> admin@domux.com / Admin123*")
    print("  Guardia   -> guardia@domux.com / Guardia123*")
    print("  Residente -> maria@domux.com / Residente123* (Torre 1 · Apto 101)")
    print("  Residente -> carlos@domux.com / Residente123* (Torre 2 · Apto 202)")
