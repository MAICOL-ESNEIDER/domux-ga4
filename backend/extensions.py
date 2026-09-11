# extensions.py — instancia única de SQLAlchemy, compartida por models.py y app.py
# para evitar imports circulares.

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
