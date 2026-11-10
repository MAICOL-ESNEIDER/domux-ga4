"""Cuentas y datos de prueba para una base vacía.

Las contraseñas de las cuentas de prueba nunca se escriben en el código ni se
muestran en la consola (SEC-004 y SEC-013): se leen de variables de entorno.
"""

import logging
import os
import secrets
import string
from datetime import datetime
from pathlib import Path

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from config import is_production
from extensions import db
from models import Announcement, CommonArea, PackageItem, User
from validators import validate_strong_password

logger = logging.getLogger(__name__)

#: Cada cuenta de prueba y la variable de entorno que guarda su contraseña.
DEMO_PASSWORD_VARS = {
    "admin@domux.com": "SEED_ADMIN_PASSWORD",
    "guardia@domux.com": "SEED_GUARD_PASSWORD",
    "maria@domux.com": "SEED_RESIDENT_PASSWORD",
    "carlos@domux.com": "SEED_RESIDENT_PASSWORD",
}


def _env_password(var):
    """Devuelve la contraseña de una variable si existe y cumple la política."""
    value = os.environ.get(var, "")
    if value and validate_strong_password(value):
        logger.warning("%s no cumple la política de contraseñas y no se usó.", var)
        return ""
    return value


def _random_password():
    """Crea una contraseña al azar que cumple la política de DOMUX."""
    alphabet = string.ascii_letters + string.digits
    body = "".join(secrets.choice(alphabet) for _ in range(12))
    # El final garantiza mayúscula, minúscula, número y símbolo.
    return f"{body}Aa1*"


def _save_generated_credentials(credentials):
    """Guarda en instance/ las contraseñas creadas al azar en desarrollo.

    La carpeta instance/ está fuera de Git, así que el archivo nunca se sube. Se
    usa en lugar de la consola para que las contraseñas no queden en los registros.
    """
    folder = Path(current_app.instance_path)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "demo_credentials.txt"
    lines = [f"{email}: {password}" for email, password in credentials.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)
    logger.warning(
        "Se crearon contraseñas al azar para las cuentas de prueba; están en %s.",
        path,
    )


def _demo_passwords():
    """Reúne las contraseñas de las cuentas de prueba, una por variable.

    En producción, si falta alguna variable, devuelve None y no se crean cuentas
    de prueba. En desarrollo crea al azar las que falten.
    """
    passwords = {var: _env_password(var) for var in set(DEMO_PASSWORD_VARS.values())}
    missing = sorted(var for var, value in passwords.items() if not value)
    if missing and is_production():
        logger.warning(
            "No se crearon las cuentas de prueba: faltan %s.", ", ".join(missing)
        )
        return None
    for var in missing:
        passwords[var] = _random_password()
    if missing:
        _save_generated_credentials({
            email: passwords[var]
            for email, var in DEMO_PASSWORD_VARS.items()
            if var in missing
        })
    return passwords


def sync_demo_passwords():
    """Pone a las cuentas de prueba la contraseña que diga el entorno.

    Para cambiar una contraseña de prueba basta con cambiar su variable y reiniciar
    el servidor; no hace falta borrar la base. Solo toca las cuentas de prueba que
    existan y nunca muestra la contraseña.
    """
    changed = False
    for email, var in DEMO_PASSWORD_VARS.items():
        password = _env_password(var)
        if not password:
            # En el servidor de pruebas se avisa: la cuenta sigue con su clave vieja.
            if is_production() and not os.environ.get(var):
                logger.warning("%s no está configurada: %s conserva su contraseña anterior.", var, email)
            continue
        user = User.query.filter_by(email=email).first()
        if user is not None and not check_password_hash(user.password_hash, password):
            user.password_hash = generate_password_hash(password)
            changed = True
            logger.info("Contraseña de prueba de %s actualizada desde %s.", email, var)
    if changed:
        db.session.commit()


def seed_if_empty():
    """Crea las cuentas y los datos de prueba si la base no tiene usuarios."""
    if User.query.first() is not None:
        return
    passwords = _demo_passwords()
    if passwords is None:
        return

    admin = User(
        name="Administración",
        last_name="Domux",
        email="admin@domux.com",
        password_hash=generate_password_hash(passwords["SEED_ADMIN_PASSWORD"]),
        role="ADMIN",
        occupancy_type="propietario",
    )
    guardia = User(
        name="Guardia",
        last_name="Principal",
        email="guardia@domux.com",
        password_hash=generate_password_hash(passwords["SEED_GUARD_PASSWORD"]),
        role="GUARD",
        occupancy_type="propietario",
    )
    residente1 = User(
        name="María",
        last_name="Gómez",
        email="maria@domux.com",
        password_hash=generate_password_hash(passwords["SEED_RESIDENT_PASSWORD"]),
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
        password_hash=generate_password_hash(passwords["SEED_RESIDENT_PASSWORD"]),
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
            delivered_at=datetime.utcnow(),
            delivered_to=residente1.full_name,
            delivered_by_id=guardia.id,
        ),
    ])
    db.session.commit()

    logger.info("Datos de prueba creados: administración, portería y dos residentes.")
