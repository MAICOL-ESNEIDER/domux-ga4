"""Variables de entorno comunes de las pruebas automáticas.

Cada archivo de prueba lo importa antes de crear la app, para que todas usen la
misma base de pruebas y solo valores de prueba, nunca los reales. La base es
SQLite en memoria, salvo que TEST_DATABASE_URL indique otra (el pipeline la usa
para correr las mismas pruebas en PostgreSQL).
"""

import os
import secrets

os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or "sqlite://"
os.environ["JWT_SECRET"] = "unit-test-only-secret-with-enough-bytes"

# Contraseñas al azar para las cuentas de prueba: así la semilla no crea archivos.
for _name in ("SEED_ADMIN_PASSWORD", "SEED_GUARD_PASSWORD", "SEED_RESIDENT_PASSWORD"):
    os.environ.setdefault(_name, secrets.token_urlsafe(9) + "Aa1*")


def release_app(app):
    """Cierra las conexiones que dejó abiertas la app de un grupo de pruebas.

    Cada grupo crea su propia app y, con ella, su propia reserva de conexiones. En PostgreSQL, si nadie las
    cierra, se acumulan hasta el límite del servidor (100) y los últimos grupos ya no pueden conectarse
    («too many clients»). Los grupos la piden con ``cls.addClassCleanup(env_setup.release_app, cls.app)``.
    """
    from extensions import db  # se importa aquí para que las variables de arriba ya estén puestas

    with app.app_context():
        db.session.remove()
        db.engine.dispose()
