# seed.py — crea datos de prueba la primera vez que arranca el backend (si la
# base de datos está vacía). Así siempre hay usuarios y zonas comunes con los
# que probar la app sin tener que crearlos a mano.

from werkzeug.security import generate_password_hash

from extensions import db
from models import User, CommonArea, Announcement


def seed_if_empty():
    if User.query.first() is not None:
        return  # ya hay datos, no volver a sembrar

    admin = User(
        name="Administración Domux",
        email="admin@domux.com",
        password_hash=generate_password_hash("admin123"),
        role="ADMIN",
        apartment=None,
    )
    guardia = User(
        name="Guardia Principal",
        email="guardia@domux.com",
        password_hash=generate_password_hash("guardia123"),
        role="GUARD",
        apartment=None,
    )
    residente1 = User(
        name="María Gómez",
        email="maria@domux.com",
        password_hash=generate_password_hash("residente123"),
        role="RESIDENT",
        apartment="Torre 1 · Apto 101",
    )
    residente2 = User(
        name="Carlos Pérez",
        email="carlos@domux.com",
        password_hash=generate_password_hash("residente123"),
        role="RESIDENT",
        apartment="Torre 2 · Apto 202",
    )
    db.session.add_all([admin, guardia, residente1, residente2])
    db.session.commit()

    zonas = [
        CommonArea(name="Salón social"),
        CommonArea(name="Gimnasio"),
        CommonArea(name="Cancha múltiple"),
        CommonArea(name="Zona BBQ"),
    ]
    db.session.add_all(zonas)

    bienvenida = Announcement(
        title="¡Bienvenido a Domux!",
        message="Esta es la app de gestión de la unidad residencial. Aquí verás "
                "los anuncios de administración, tus PQRS, tus reservas y las "
                "notificaciones de paquetes y visitantes.",
        author_id=admin.id,
    )
    db.session.add(bienvenida)
    db.session.commit()

    print("Datos de prueba creados:")
    print("  Admin    -> admin@domux.com / admin123")
    print("  Guardia  -> guardia@domux.com / guardia123")
    print("  Residente-> maria@domux.com / residente123 (Torre 1 · Apto 101)")
    print("  Residente-> carlos@domux.com / residente123 (Torre 2 · Apto 202)")
