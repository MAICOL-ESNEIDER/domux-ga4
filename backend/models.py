"""SQLAlchemy models and Android-compatible JSON serializers."""

from datetime import date, datetime

from sqlalchemy import Index, text
from sqlalchemy.orm import declared_attr

from extensions import db

ROLES = ("ADMIN", "RESIDENT", "GUARD")


def _fmt(value):
    return value.strftime("%Y-%m-%d %H:%M") if value else None


class RetirableMixin:
    """Retiro lógico (DEC-090 y ADR-013): la fila nunca se borra, se marca.

    retired_at guarda cuándo se retiró y retired_by_id quién lo hizo. Mientras
    los dos estén vacíos, el registro está vigente.
    """

    retired_at = db.Column(db.DateTime, nullable=True)

    @declared_attr
    def retired_by_id(cls):
        return db.Column(
            db.Integer,
            db.ForeignKey("users.id", name=f"fk_{cls.__tablename__}_retired_by_id_users"),
            nullable=True,
        )

    @property
    def is_retired(self):
        return self.retired_at is not None

    def retire(self, user):
        """Marca el registro como retirado por el usuario indicado."""
        self.retired_at = datetime.utcnow()
        self.retired_by_id = user.id


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
    apartment_number = db.Column(db.Integer, nullable=True, index=True)
    occupancy_type = db.Column(db.String(30), nullable=True, default="propietario")
    social_networks = db.Column(db.String(500), nullable=True, default="")
    birth_date = db.Column(db.String(20), nullable=True)
    parental_consent = db.Column(db.Boolean, default=False, nullable=False)
    data_processing_consent = db.Column(db.Boolean, nullable=False, default=False)
    data_processing_consent_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def full_name(self):
        name = (self.name or "").strip()
        last_name = (self.last_name or "").strip()
        return f"{name} {last_name}".strip()

    @property
    def age(self):
        if not self.birth_date:
            return None
        try:
            birth_date = date.fromisoformat(self.birth_date)
        except (TypeError, ValueError):
            return None
        if birth_date.isoformat() != self.birth_date:
            return None
        today = date.today()
        return today.year - birth_date.year - (
            (today.month, today.day) < (birth_date.month, birth_date.day)
        )

    @property
    def is_minor(self):
        return self.age is not None and self.age < 18

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.full_name,
            "firstName": (self.name or "").strip(),
            "lastName": self.last_name or "",
            "fullName": self.full_name,
            "email": self.email or "",
            "phone": self.phone or "",
            "documentId": self.document_id or "",
            "role": self.role or "",
            "apartment": self.apartment,
            "apartmentNumber": self.apartment_number,
            "occupancyType": self.occupancy_type or "propietario",
            "socialNetworks": self.social_networks or "",
            "birthDate": self.birth_date,
            "age": self.age,
            "isMinor": self.is_minor,
            "parentalConsent": bool(self.parental_consent),
            "dataProcessingConsent": bool(self.data_processing_consent),
            "dataProcessingConsentAt": _fmt(self.data_processing_consent_at),
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
            "apartmentNumber": self.apartment_number,
            "occupancyType": self.occupancy_type or "propietario",
            "birthDate": self.birth_date,
            "age": self.age,
            "isMinor": self.is_minor,
            "parentalConsent": bool(self.parental_consent),
        }


class ResidentialUnit(db.Model):
    __tablename__ = "residential_units"

    id = db.Column(db.Integer, primary_key=True)
    apartment = db.Column(db.String(60), nullable=False, unique=True, index=True)
    parking_identifier = db.Column(db.String(80), nullable=True)
    storage_identifier = db.Column(db.String(80), nullable=True)
    pet_insurance = db.Column(db.Boolean, nullable=False, default=False)
    pet_insurer = db.Column(db.String(120), nullable=True)
    funeral_plan = db.Column(db.Boolean, nullable=False, default=False)
    funeral_provider = db.Column(db.String(120), nullable=True)

    # Incluyen también lo retirado: es el historial de la ficha (TT-032). Sin
    # «delete-orphan», quitar algo de la lista nunca lo borra de la base.
    members = db.relationship(
        "HouseholdMember", back_populates="unit", order_by="HouseholdMember.id"
    )
    pets = db.relationship("Pet", back_populates="unit", order_by="Pet.id")
    vehicles = db.relationship("Vehicle", back_populates="unit", order_by="Vehicle.id")

    @property
    def active_members(self):
        return [member for member in self.members if not member.is_retired]

    @property
    def active_pets(self):
        return [pet for pet in self.pets if not pet.is_retired]

    @property
    def active_vehicles(self):
        return [vehicle for vehicle in self.vehicles if not vehicle.is_retired]

    def to_dict(self):
        residents = User.query.filter_by(apartment=self.apartment, role="RESIDENT").order_by(
            User.occupancy_type, User.name, User.id
        ).all()
        return {
            "id": self.id,
            "apartment": self.apartment,
            "residents": [
                {
                    "id": resident.id,
                    "name": resident.full_name,
                    "occupancyType": resident.occupancy_type,
                }
                for resident in residents
            ],
            "parkingIdentifier": self.parking_identifier,
            "storageIdentifier": self.storage_identifier,
            "petInsurance": self.pet_insurance,
            "petInsurer": self.pet_insurer,
            "funeralPlan": self.funeral_plan,
            "funeralProvider": self.funeral_provider,
            "members": [member.to_dict() for member in self.active_members],
            "pets": [pet.to_dict() for pet in self.active_pets],
            "vehicles": [vehicle.to_dict() for vehicle in self.active_vehicles],
        }


class HouseholdMember(RetirableMixin, db.Model):
    """Integrante del hogar; quitarlo de la ficha lo retira (TT-032)."""

    __tablename__ = "household_members"

    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey("residential_units.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    last_name = db.Column(db.String(120), nullable=False, default="")
    document_id = db.Column(db.String(40), nullable=False)
    birth_date = db.Column(db.String(10), nullable=False)
    phone = db.Column(db.String(30), nullable=True)
    relationship = db.Column(db.String(30), nullable=False)
    other_relationship = db.Column(db.String(80), nullable=True)

    unit = db.relationship("ResidentialUnit", back_populates="members")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            # Vacío sale como null: la app lo devuelve tal cual y el servidor
            # no acepta textos vacíos al guardar la ficha.
            "lastName": self.last_name or None,
            "documentId": self.document_id,
            "birthDate": self.birth_date,
            "phone": self.phone,
            "relationship": self.relationship,
            "otherRelationship": self.other_relationship,
        }


class Pet(RetirableMixin, db.Model):
    """Mascota del apartamento; quitarla de la ficha la retira (TT-032)."""

    __tablename__ = "pets"

    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey("residential_units.id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    species = db.Column(db.String(60), nullable=False)
    breed = db.Column(db.String(100), nullable=False)
    age_years = db.Column(db.Integer, nullable=False)

    unit = db.relationship("ResidentialUnit", back_populates="pets")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "species": self.species,
            "breed": self.breed,
            "ageYears": self.age_years,
        }


class Vehicle(RetirableMixin, db.Model):
    """Vehículo del apartamento; quitarlo de la ficha lo retira (TT-032).

    La placa solo es única entre los vehículos vigentes (IDX-013): una placa
    retirada puede volver a registrarse en este u otro apartamento.
    """

    __tablename__ = "vehicles"
    __table_args__ = (
        Index(
            "uq_vehicles_active_plate",
            "plate",
            unique=True,
            sqlite_where=text("retired_at IS NULL"),
            postgresql_where=text("retired_at IS NULL"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey("residential_units.id"), nullable=False, index=True)
    plate = db.Column(db.String(10), nullable=False, index=True)
    vehicle_type = db.Column(db.String(10), nullable=False)
    make_model = db.Column(db.String(120), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    registered_owner = db.Column(db.String(120), nullable=False)
    color = db.Column(db.String(60), nullable=True)

    unit = db.relationship("ResidentialUnit", back_populates="vehicles")

    def to_dict(self):
        return {
            "id": self.id,
            "plate": self.plate,
            "type": self.vehicle_type,
            "makeModel": self.make_model,
            "year": self.year,
            "registeredOwner": self.registered_owner,
            "color": self.color,
        }


class Announcement(RetirableMixin, db.Model):
    """Comunicado de la administración para los residentes.

    Un comunicado nunca se borra (TT-029): al retirarlo deja de verse en la
    app, pero sigue en la base con la fecha y quién lo retiró.
    """

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

    author = db.relationship("User", foreign_keys=[author_id])

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
            "isRetired": self.is_retired,
            "retiredAt": _fmt(self.retired_at),
        }


class Pqrs(db.Model):
    __tablename__ = "pqrs"

    id = db.Column(db.Integer, primary_key=True)
    resident_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_by_admin_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    category = db.Column(db.String(40), default="Petición")
    subject = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="abierta")
    admin_response = db.Column(db.Text, nullable=True)
    incident_date = db.Column(db.String(20), nullable=True)
    incident_time = db.Column(db.String(20), nullable=True)
    media_url = db.Column(db.Text, nullable=True)
    media_type = db.Column(db.String(20), nullable=True)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    archived_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    resident = db.relationship("User", foreign_keys=[resident_id])
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
            "createdByAdminId": self.created_by_admin_id,
            "createdByAdministration": self.created_by_admin_id is not None,
            "category": self.category or "Petición",
            "subject": self.subject or "",
            "message": self.message or "",
            "status": self.status or "abierta",
            "isArchived": bool(self.is_archived),
            "archivedAt": _fmt(self.archived_at),
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


class DevicePushToken(db.Model):
    __tablename__ = "device_push_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    token = db.Column(db.String(255), nullable=False, unique=True, index=True)
    device_id = db.Column(db.String(120), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User")


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
    created_by_admin_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    common_area_id = db.Column(db.Integer, db.ForeignKey("common_areas.id"), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    time_slot = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(20), default="pendiente")
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    archived_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    resident = db.relationship("User", foreign_keys=[resident_id])
    common_area = db.relationship("CommonArea")
    messages = db.relationship(
        "ReservationMessage",
        back_populates="reservation",
        cascade="all, delete-orphan",
        order_by="ReservationMessage.created_at, ReservationMessage.id",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "residentId": self.resident_id,
            "createdByAdminId": self.created_by_admin_id,
            "createdByAdministration": self.created_by_admin_id is not None,
            "commonAreaId": self.common_area_id,
            "commonAreaName": self.common_area.name if self.common_area else None,
            "date": self.date,
            "timeSlot": self.time_slot,
            "status": self.status or "activa",
            "isArchived": bool(self.is_archived),
            "archivedAt": _fmt(self.archived_at),
            "requestedByMinor": bool(self.resident and self.resident.is_minor),
            "createdAt": _fmt(self.created_at),
            "residentName": self.resident.full_name if self.resident else None,
            "apartment": self.resident.apartment if self.resident else None,
            "messages": [message.to_dict() for message in self.messages],
        }


class ReservationMessage(db.Model):
    __tablename__ = "reservation_messages"

    id = db.Column(db.Integer, primary_key=True)
    reservation_id = db.Column(
        db.Integer, db.ForeignKey("reservations.id"), nullable=False, index=True
    )
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    author_role = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=True)
    media_url = db.Column(db.Text, nullable=True)
    media_type = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    reservation = db.relationship("Reservation", back_populates="messages")
    author = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "reservationId": self.reservation_id,
            "authorId": self.author_id,
            "authorName": self.author.full_name if self.author else None,
            "authorRole": self.author_role,
            "message": self.message,
            "mediaUrl": self.media_url,
            "mediaType": self.media_type,
            "createdAt": _fmt(self.created_at),
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
    delivered_to = db.Column(db.String(120), nullable=True)
    delivered_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    resident = db.relationship("User", foreign_keys=[resident_id])
    guard = db.relationship("User", foreign_keys=[registered_by])
    delivered_by = db.relationship("User", foreign_keys=[delivered_by_id])

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
            "isDeleted": bool(self.is_deleted),
            "deletedAt": _fmt(self.deleted_at),
            "deliveredTo": self.delivered_to,
            "deliveredByName": self.delivered_by.full_name if self.delivered_by else None,
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
    visitor_photo_url = db.Column(db.Text, nullable=True)
    visitor_photo_type = db.Column(db.String(20), nullable=True)
    media_consent = db.Column(db.Boolean, default=False, nullable=False)
    type = db.Column(db.String(20), nullable=False)
    description = db.Column(db.String(250), nullable=True)
    approval_status = db.Column(db.String(20), default="pendiente", nullable=False)
    authorization_method = db.Column(db.String(20), nullable=True)
    entered_at = db.Column(db.DateTime, nullable=True)
    exited_at = db.Column(db.DateTime, nullable=True)
    exit_returning = db.Column(db.Boolean, default=False, nullable=False)
    qr_pass_id = db.Column(db.Integer, db.ForeignKey("visit_qr_passes.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    resident = db.relationship("User", foreign_keys=[resident_id])
    guard = db.relationship("User", foreign_keys=[registered_by])
    qr_pass = db.relationship("VisitQrPass", back_populates="visits")
    events = db.relationship(
        "VisitEvent",
        back_populates="visit",
        cascade="all, delete-orphan",
        order_by="VisitEvent.created_at, VisitEvent.id",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "residentId": self.resident_id,
            "visitorName": self.visitor_name or "",
            "visitorDocument": self.visitor_document or "",
            "visitorPhotoUrl": self.visitor_photo_url,
            "visitorPhotoType": self.visitor_photo_type,
            "mediaConsent": self.media_consent,
            "type": self.type or "",
            "description": self.description,
            "approvalStatus": self.approval_status,
            "authorizationMethod": self.authorization_method,
            "enteredAt": _fmt(self.entered_at),
            "exitedAt": _fmt(self.exited_at),
            "exitReturning": self.exit_returning,
            "qrPassId": self.qr_pass_id,
            "createdAt": _fmt(self.created_at),
            "events": [event.to_dict() for event in self.events],
            "residentName": self.resident.full_name if self.resident else None,
            "apartment": self.resident.apartment if self.resident else None,
            "registeredByName": self.guard.full_name if self.guard else None,
        }


class VisitQrPass(db.Model):
    __tablename__ = "visit_qr_passes"

    id = db.Column(db.Integer, primary_key=True)
    resident_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    token = db.Column(db.String(80), nullable=False, unique=True, index=True)
    valid_from = db.Column(db.String(10), nullable=False)
    valid_until = db.Column(db.String(10), nullable=False)
    max_people = db.Column(db.Integer, nullable=False)
    revoked = db.Column(db.Boolean, default=False, nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    resident = db.relationship("User")
    visits = db.relationship("Visit", back_populates="qr_pass")

    def to_dict(self, include_token=False):
        registered_people = len(self.visits)
        result = {
            "id": self.id,
            "residentId": self.resident_id,
            "validFrom": self.valid_from,
            "validUntil": self.valid_until,
            "maxPeople": self.max_people,
            "registeredPeople": registered_people,
            "remainingPeople": max(0, self.max_people - registered_people),
            "revoked": self.revoked,
            "revokedAt": _fmt(self.revoked_at),
        }
        if include_token:
            result["token"] = self.token
        return result


class VisitEvent(db.Model):
    __tablename__ = "visit_events"

    id = db.Column(db.Integer, primary_key=True)
    visit_id = db.Column(db.Integer, db.ForeignKey("visits.id"), nullable=False, index=True)
    event_type = db.Column(db.String(20), nullable=False)
    method = db.Column(db.String(20), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    returning_today = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    visit = db.relationship("Visit", back_populates="events")
    actor = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.event_type,
            "method": self.method,
            "actorName": self.actor.full_name if self.actor else None,
            "returningToday": self.returning_today,
            "createdAt": _fmt(self.created_at),
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


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(40), nullable=False, index=True)
    entity_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(60), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    actor_role = db.Column(db.String(20), nullable=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    actor = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "entityType": self.entity_type,
            "entityId": self.entity_id,
            "action": self.action,
            "actorId": self.actor_id,
            "actorRole": self.actor_role,
            "details": self.details,
            "createdAt": _fmt(self.created_at),
        }
