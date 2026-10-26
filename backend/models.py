"""SQLAlchemy models and Android-compatible JSON serializers."""

from datetime import datetime

from sqlalchemy import Index, text

from extensions import db

ROLES = ("ADMIN", "RESIDENT", "GUARD")


def _fmt(value):
    return value.strftime("%Y-%m-%d %H:%M") if value else None


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    last_name = db.Column(db.String(120), nullable=True, default="")
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(30), nullable=True, default="")
    document_id = db.Column(db.String(40), nullable=True, default="")
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    apartment = db.Column(db.String(60), nullable=True)
    occupancy_type = db.Column(db.String(30), nullable=True, default="propietario")
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def full_name(self):
        name = (self.name or "").strip()
        last_name = (self.last_name or "").strip()
        return f"{name} {last_name}".strip()

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.full_name,
            "lastName": self.last_name or "",
            "fullName": self.full_name,
            "email": self.email or "",
            "phone": self.phone or "",
            "documentId": self.document_id or "",
            "role": self.role or "",
            "apartment": self.apartment,
            "occupancyType": self.occupancy_type or "propietario",
            "isActive": self.is_active if self.is_active is not None else True,
            "createdAt": _fmt(self.created_at),
        }

    def to_resident_summary(self):
        return {
            "id": self.id,
            "name": self.full_name,
            "email": self.email or "",
            "phone": self.phone or "",
            "apartment": self.apartment,
            "occupancyType": self.occupancy_type or "propietario",
        }


class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    event_date = db.Column(db.String(20), nullable=True)
    event_time = db.Column(db.String(20), nullable=True)
    media_url = db.Column(db.Text, nullable=True)
    media_type = db.Column(db.String(20), nullable=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    author = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title or "",
            "message": self.message or "",
            "eventDate": self.event_date,
            "eventTime": self.event_time,
            "mediaUrl": self.media_url,
            "mediaType": self.media_type,
            "createdAt": _fmt(self.created_at),
            "authorName": self.author.full_name if self.author else None,
        }


class Pqrs(db.Model):
    __tablename__ = "pqrs"

    id = db.Column(db.Integer, primary_key=True)
    resident_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category = db.Column(db.String(40), default="Petición")
    subject = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="abierta")
    admin_response = db.Column(db.Text, nullable=True)
    incident_date = db.Column(db.String(20), nullable=True)
    incident_time = db.Column(db.String(20), nullable=True)
    media_url = db.Column(db.Text, nullable=True)
    media_type = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    resident = db.relationship("User")
    conversation = db.relationship(
        "PqrsMessage",
        back_populates="pqrs",
        cascade="all, delete-orphan",
        order_by="PqrsMessage.created_at, PqrsMessage.id",
    )
    satisfaction_ratings = db.relationship(
        "PqrsSatisfaction",
        back_populates="pqrs",
        cascade="all, delete-orphan",
        order_by="PqrsSatisfaction.created_at, PqrsSatisfaction.id",
    )

    def to_dict(self):
        latest_rating = self.satisfaction_ratings[-1] if self.satisfaction_ratings else None
        return {
            "id": self.id,
            "residentId": self.resident_id,
            "category": self.category or "Petición",
            "subject": self.subject or "",
            "message": self.message or "",
            "status": self.status or "abierta",
            "adminResponse": self.admin_response,
            "incidentDate": self.incident_date,
            "incidentTime": self.incident_time,
            "mediaUrl": self.media_url,
            "mediaType": self.media_type,
            "messages": [message.to_dict() for message in self.conversation],
            "satisfactionRating": latest_rating.rating if latest_rating else None,
            "satisfactionComment": latest_rating.comment if latest_rating else None,
            "satisfactionHistory": [rating.to_dict() for rating in self.satisfaction_ratings],
            "createdAt": _fmt(self.created_at),
            "updatedAt": _fmt(self.updated_at),
            "residentName": self.resident.full_name if self.resident else None,
            "apartment": self.resident.apartment if self.resident else None,
        }


class PqrsMessage(db.Model):
    __tablename__ = "pqrs_messages"

    id = db.Column(db.Integer, primary_key=True)
    pqrs_id = db.Column(db.Integer, db.ForeignKey("pqrs.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    author_role = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=True)
    media_url = db.Column(db.Text, nullable=True)
    media_type = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    pqrs = db.relationship("Pqrs", back_populates="conversation")
    author = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "pqrsId": self.pqrs_id,
            "authorId": self.author_id,
            "authorName": self.author.full_name if self.author else None,
            "authorRole": self.author_role,
            "message": self.message,
            "mediaUrl": self.media_url,
            "mediaType": self.media_type,
            "createdAt": _fmt(self.created_at),
        }


class PqrsSatisfaction(db.Model):
    __tablename__ = "pqrs_satisfaction"

    id = db.Column(db.Integer, primary_key=True)
    pqrs_id = db.Column(db.Integer, db.ForeignKey("pqrs.id"), nullable=False, index=True)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    pqrs = db.relationship("Pqrs", back_populates="satisfaction_ratings")

    def to_dict(self):
        return {
            "id": self.id,
            "pqrsId": self.pqrs_id,
            "rating": self.rating,
            "comment": self.comment,
            "createdAt": _fmt(self.created_at),
        }


class CommonArea(db.Model):
    __tablename__ = "common_areas"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    def to_dict(self):
        return {"id": self.id, "name": self.name or ""}


class Reservation(db.Model):
    __tablename__ = "reservations"
    __table_args__ = (
        Index(
            "uq_reservation_active_slot",
            "common_area_id",
            "date",
            "time_slot",
            unique=True,
            sqlite_where=text("status IN ('activa', 'aprobada')"),
            postgresql_where=text("status IN ('activa', 'aprobada')"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    resident_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    common_area_id = db.Column(db.Integer, db.ForeignKey("common_areas.id"), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    time_slot = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(20), default="activa")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    resident = db.relationship("User")
    common_area = db.relationship("CommonArea")

    def to_dict(self):
        return {
            "id": self.id,
            "residentId": self.resident_id,
            "commonAreaId": self.common_area_id,
            "commonAreaName": self.common_area.name if self.common_area else None,
            "date": self.date,
            "timeSlot": self.time_slot,
            "status": self.status or "activa",
            "createdAt": _fmt(self.created_at),
            "residentName": self.resident.full_name if self.resident else None,
            "apartment": self.resident.apartment if self.resident else None,
        }


class PackageItem(db.Model):
    __tablename__ = "packages"

    id = db.Column(db.Integer, primary_key=True)
    resident_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    registered_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    description = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), default="pendiente")
    media_url = db.Column(db.Text, nullable=True)
    media_type = db.Column(db.String(20), nullable=True)
    event_date = db.Column(db.String(20), nullable=True)
    event_time = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivered_at = db.Column(db.DateTime, nullable=True)

    resident = db.relationship("User", foreign_keys=[resident_id])
    guard = db.relationship("User", foreign_keys=[registered_by])

    def to_dict(self):
        return {
            "id": self.id,
            "residentId": self.resident_id,
            "description": self.description or "",
            "status": self.status or "pendiente",
            "mediaUrl": self.media_url,
            "mediaType": self.media_type,
            "eventDate": self.event_date,
            "eventTime": self.event_time,
            "createdAt": _fmt(self.created_at),
            "deliveredAt": _fmt(self.delivered_at),
            "residentName": self.resident.full_name if self.resident else None,
            "apartment": self.resident.apartment if self.resident else None,
            "registeredByName": self.guard.full_name if self.guard else None,
        }


class Visit(db.Model):
    __tablename__ = "visits"

    id = db.Column(db.Integer, primary_key=True)
    resident_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    registered_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    visitor_name = db.Column(db.String(120), nullable=False)
    visitor_document = db.Column(db.String(40), nullable=True)
    type = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    resident = db.relationship("User", foreign_keys=[resident_id])
    guard = db.relationship("User", foreign_keys=[registered_by])

    def to_dict(self):
        return {
            "id": self.id,
            "residentId": self.resident_id,
            "visitorName": self.visitor_name or "",
            "visitorDocument": self.visitor_document or "",
            "type": self.type or "",
            "createdAt": _fmt(self.created_at),
            "residentName": self.resident.full_name if self.resident else None,
            "apartment": self.resident.apartment if self.resident else None,
            "registeredByName": self.guard.full_name if self.guard else None,
        }


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(30), default="general")
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "userId": self.user_id,
            "title": self.title or "",
            "message": self.message or "",
            "type": self.type or "general",
            "isRead": self.is_read if self.is_read is not None else False,
            "createdAt": _fmt(self.created_at),
        }
