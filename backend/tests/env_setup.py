"""Variables de entorno comunes de las pruebas automáticas.

Cada archivo de prueba lo importa antes de crear la app, para que todas usen la
misma base de pruebas y solo valores de prueba, nunca los reales. La base es
SQLite en memoria, salvo que TEST_DATABASE_URL indique otra (el pipeline la usa
para correr las mismas pruebas en PostgreSQL).
"""

import os
import secrets

os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "sqlite://")
os.environ["JWT_SECRET"] = "unit-test-only-secret-with-enough-bytes"

# Contraseñas al azar para las cuentas de prueba: así la semilla no crea archivos.
for _name in ("SEED_ADMIN_PASSWORD", "SEED_GUARD_PASSWORD", "SEED_RESIDENT_PASSWORD"):
    os.environ.setdefault(_name, secrets.token_urlsafe(9) + "Aa1*")
