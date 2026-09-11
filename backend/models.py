# models.py — tablas reales de la base de datos (SQLite en local, PostgreSQL en
# Render). Cada modelo tiene un to_dict() que arma el JSON EXACTO que espera la
# app Android (mismos nombres de campo que las data class de Models.kt).

from datetime import datetime
from extensions import db

ROLES = ("ADMIN", "RESIDENT", "GUARD")


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M") if dt else None


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)          # ADMIN | RESIDENT | GUARD
    apartment = db.Column(db.String(60), nullable=True)       # solo para RESIDENT
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "apartment": self.apartment,
        }

    def to_resident_summary(self):
        return {"id": self.id, "name": self.name, "apartment": self.apartment}


class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    author = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "createdAt": _fmt(self.created_at),
            "authorName": self.author.name if self.author else None,
        }


class Pqrs(db.Model):
    __tablename__ = "pqrs"

    id = db.Column(db.Integer, primary_key=True)
    resident_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    subject = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="abierta")   # abierta | en_proceso | resuelta
    admin_response = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    resident = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "subject": self.subject,
            "message": self.message,
            "status": self.status,
            "adminResponse": self.admin_response,
            "createdAt": _fmt(self.created_at),
            "residentName": self.resident.name if self.resident else None,
        }


class CommonArea(db.Model):
    __tablename__ = "common_areas"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    def to_dict(self):
        return {"id": self.id, "name": self.name}


class Reservation(db.Model):
    __tablename__ = "reservations"

    id = db.Column(db.Integer, primary_key=True)
    resident_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    common_area_id = db.Column(db.Integer, db.ForeignKey("common_areas.id"), nullable=False)
    date = db.Column(db.String(20), nullable=False)         # "AAAA-MM-DD"
    time_slot = db.Column(db.String(40), nullable=False)     # ej. "18:00-20:00"
    status = db.Column(db.String(20), default="activa")      # activa | cancelada
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    resident = db.relationship("User")
    common_area = db.relationship("CommonArea")

    def to_dict(self):
        return {
            "id": self.id,
            "commonAreaId": self.common_area_id,
            "commonAreaName": self.common_area.name if self.common_area else None,
            "date": self.date,
            "timeSlot": self.time_slot,
            "status": self.status,
            "residentName": self.resident.name if self.resident else None,
        }


class PackageItem(db.Model):
    __tablename__ = "packages"

    id = db.Column(db.Integer, primary_key=True)
    resident_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    registered_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    description = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), default="pendiente")   # pendiente | entregado
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivered_at = db.Column(db.DateTime, nullable=True)

    resident = db.relationship("User", foreign_keys=[resident_id])
    guard = db.relationship("User", foreign_keys=[registered_by])

    def to_dict(self):
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status,
            "createdAt": _fmt(self.created_at),
            "deliveredAt": _fmt(self.delivered_at),
            "residentName": self.resident.name if self.resident else None,
            "registeredByName": self.guard.name if self.guard else None,
        }


class Visit(db.Model):
    __tablename__ = "visits"

    id = db.Column(db.Integer, primary_key=True)
    resident_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    registered_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    visitor_name = db.Column(db.String(120), nullable=False)
    type = db.Column(db.String(20), nullable=False)          # visitante | domiciliario
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    resident = db.relationship("User", foreign_keys=[resident_id])
    guard = db.relationship("User", foreign_keys=[registered_by])

    def to_dict(self):
        return {
            "id": self.id,
            "visitorName": self.visitor_name,
            "type": self.type,
            "createdAt": _fmt(self.created_at),
            "residentName": self.resident.name if self.resident else None,
            "registeredByName": self.guard.name if self.guard else None,
        }
