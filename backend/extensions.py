# extensions.py — instancia única de SQLAlchemy, compartida por models.py y app.py
# para evitar imports circulares.

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Migraciones de la base con Alembic (TT-008): cada cambio de estructura queda
# en backend/migrations/versions y se aplica solo al arrancar el servidor.
migrations = Migrate()
