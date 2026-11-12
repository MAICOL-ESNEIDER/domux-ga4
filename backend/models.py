"""SQLAlchemy models and Android-compatible JSON serializers."""

from datetime import date, timedelta

from sqlalchemy import Index, event, false, select, text
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import declared_attr, deferred
from sqlalchemy.orm.attributes import set_committed_value

from config import visitor_parking_max_days
from extensions import db
from services.pqrs_rules import RUNNING_STATUSES, make_radicado, pqrs_semaphore
from services.zone_rules import (
    DEFAULT_CANCEL_DEADLINE_DAYS,
    DEFAULT_CLOSE_TIME,
    DEFAULT_MAX_ADVANCE_DAYS,
    DEFAULT_MIN_ADVANCE_DAYS,
    DEFAULT_OPEN_TIME,
    DEFAULT_SLOT_MINUTES,
    DEFAULT_WEEKLY_LIMIT,
    zone_slots,
)
from time_utils import colombia_today, to_colombia, utc_now

ROLES = ("ADMIN", "RESIDENT", "GUARD")

#: Categorías de los comunicados (HU-058 y RN-026): lo que se guarda y lo que se muestra.
ANNOUNCEMENT_CATEGORIES = {
    "mantenimiento": "Mantenimiento",
    "urgente": "Urgente",
    "asamblea": "Asamblea",
    "seguridad": "Seguridad",
    "zonas_comunes": "Zonas comunes",
}

#: Tipos de parqueadero de la unidad (HU-015).
PARKING_KINDS = ("residente", "visitante")

#: Horas sin reclamar para resaltar un paquete en naranja y en rojo (RN-018, HU-049).
UNCLAIMED_ORANGE_HOURS = 48
UNCLAIMED_RED_HOURS = 72

#: Movimientos de un vehículo de residente por la portería (HU-040).
MOVEMENT_TYPES = ("entrada", "salida")

#: Lo que va entre la torre y el código en el texto de un apartamento: «Torre 1 · Apto 101».
APARTMENT_LABEL_SEPARATOR = " · Apto "


def _fmt(value):
    """Muestra una hora guardada en UTC en la hora de Colombia (ADR-011, TT-031)."""
    return to_colombia(value).strftime("%Y-%m-%d %H:%M") if value else None


def apartment_label(tower_name, code):
    """Arma el texto de un apartamento con su torre y su código: «Torre 1 · Apto 101»."""
    return f"{tower_name}{APARTMENT_LABEL_SEPARATOR}{code}"


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
        self.retired_at = utc_now()
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
    #: PIN de 4 dígitos del guardia para cambiar de turno en la tablet (RN-029, HU-010).
    #: Se guarda con hash, como la contraseña; solo los guardias lo tienen.
    pin_hash = db.Column(db.String(255), nullable=True)
    role = db.Column(db.String(20), nullable=False)
    #: El apartamento es una llave a la estructura de la unidad (HU-014 y HU-017).
    #: El texto «Torre 1 · Apto 101» ya no se guarda: se arma con la torre y el código.
    #: Los apartamentos apuntan de vuelta a users (quién los retiró): ese ciclo se
    #: declara con use_alter para que SQLAlchemy lo ordene al crear y borrar tablas.
    apartment_id = db.Column(
        db.Integer,
        db.ForeignKey("apartments.id", name="fk_users_apartment_id_apartments", use_alter=True),
        nullable=True,
        index=True,
    )
    occupancy_type = db.Column(db.String(30), nullable=True, default="propietario")
    social_networks = db.Column(db.String(500), nullable=True, default="")
    birth_date = db.Column(db.String(20), nullable=True)
    parental_consent = db.Column(db.Boolean, default=False, nullable=False)
    data_processing_consent = db.Column(db.Boolean, nullable=False, default=False)
    data_processing_consent_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now)

    # Entre usuarios y apartamentos hay dos llaves (apartment_id y el retiro lógico
    # retired_by_id del apartamento): se indica cuál es la del vínculo.
    apartment_ref = db.relationship(
        "Apartment", back_populates="residents", foreign_keys=[apartment_id], lazy="joined"
    )

    @hybrid_property
    def apartment(self):
        """Texto del apartamento, como «Torre 1 · Apto 101» (torre y código)."""
        return self.apartment_ref.label if self.apartment_ref else None

    @apartment.expression
    def apartment(cls):
        # En una consulta (filtro, búsqueda u orden) el texto se calcula con una
        # subconsulta; así User.apartment.ilike(...) sigue funcionando.
        return (
            select(Tower.name + APARTMENT_LABEL_SEPARATOR + Apartment.code)
            .select_from(Apartment)
            .join(Tower, Tower.id == Apartment.tower_id)
            .where(Apartment.id == cls.apartment_id)
            .correlate_except(Apartment, Tower)
            .scalar_subquery()
        )

    @hybrid_property
    def apartment_number(self):
        """Número del apartamento para filtrar y ordenar (sale de su código)."""
        return self.apartment_ref.number if self.apartment_ref else None

    @apartment_number.expression
    def apartment_number(cls):
        return (
            select(Apartment.number)
            .where(Apartment.id == cls.apartment_id)
            .correlate_except(Apartment)
            .scalar_subquery()
        )

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
        today = colombia_today()
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
            "hasPin": bool(self.pin_hash),
            "apartmentId": self.apartment_id,
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

    def to_guard_summary(self):
        """Lo que portería necesita para avisar o entregar (SEC-015 y ADR-015)."""
        return {
            "id": self.id,
            "name": self.full_name,
            "phone": self.phone or "",
            "apartment": self.apartment,
            "apartmentNumber": self.apartment_number,
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


class Tower(RetirableMixin, db.Model):
    """Torre de la unidad residencial (HU-013 y RF-013); retirarla no la borra.

    El nombre es único entre las torres vigentes (RN-008): una torre retirada
    libera su nombre.
    """

    __tablename__ = "towers"
    __table_args__ = (
        Index(
            "uq_towers_active_name",
            "name",
            unique=True,
            sqlite_where=text("retired_at IS NULL"),
            postgresql_where=text("retired_at IS NULL"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), nullable=False)
    floors = db.Column(db.Integer, nullable=False)

    apartments = db.relationship(
        "Apartment", back_populates="tower", order_by="Apartment.number, Apartment.code"
    )

    @property
    def active_apartments(self):
        return [apartment for apartment in self.apartments if not apartment.is_retired]

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "floors": self.floors,
            "apartmentCount": len(self.active_apartments),
        }


class Apartment(RetirableMixin, db.Model):
    """Apartamento de una torre (HU-014 y RF-014); retirarlo no lo borra.

    El código es único dentro de su torre entre los apartamentos vigentes
    (RN-008). number es el número del código y sirve para filtrar y ordenar.
    """

    __tablename__ = "apartments"
    __table_args__ = (
        Index(
            "uq_apartments_active_code",
            "tower_id",
            "code",
            unique=True,
            sqlite_where=text("retired_at IS NULL"),
            postgresql_where=text("retired_at IS NULL"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    tower_id = db.Column(
        db.Integer,
        db.ForeignKey("towers.id", name="fk_apartments_tower_id_towers"),
        nullable=False,
        index=True,
    )
    code = db.Column(db.String(20), nullable=False)
    floor = db.Column(db.Integer, nullable=False)
    number = db.Column(db.Integer, nullable=True, index=True)

    tower = db.relationship("Tower", back_populates="apartments", lazy="joined")
    unit = db.relationship("ResidentialUnit", back_populates="apartment_ref", uselist=False)
    residents = db.relationship(
        "User", back_populates="apartment_ref", foreign_keys="User.apartment_id"
    )
    parking_spots = db.relationship(
        "ParkingSpot", back_populates="apartment", order_by="ParkingSpot.code"
    )
    storage_rooms = db.relationship(
        "StorageRoom", back_populates="apartment", order_by="StorageRoom.code"
    )

    @property
    def label(self):
        """El apartamento con su torre, como «Torre 1 · Apto 101»."""
        return apartment_label(self.tower.name, self.code)

    @property
    def active_residents(self):
        """Residentes con la cuenta activa; los desactivados se quedan en el historial."""
        return [
            resident for resident in self.residents
            if resident.role == "RESIDENT" and resident.is_active
        ]

    @property
    def active_parking_spots(self):
        return [spot for spot in self.parking_spots if not spot.is_retired]

    @property
    def active_storage_rooms(self):
        return [room for room in self.storage_rooms if not room.is_retired]

    def to_dict(self):
        return {
            "id": self.id,
            "towerId": self.tower_id,
            "tower": self.tower.name,
            "code": self.code,
            "floor": self.floor,
            "number": self.number,
            "label": self.label,
            "residentCount": len(self.active_residents),
            "parkingSpots": [spot.code for spot in self.active_parking_spots],
            "storageRooms": [room.code for room in self.active_storage_rooms],
        }


class ParkingSpot(RetirableMixin, db.Model):
    """Parqueadero de residentes o de visitantes (HU-015 y RF-015).

    El de residente puede asignarse a un apartamento; el de visitantes no y
    empieza libre (occupied en falso). El código es único entre los vigentes
    (RN-008).
    """

    __tablename__ = "parking_spots"
    __table_args__ = (
        Index(
            "uq_parking_spots_active_code",
            "code",
            unique=True,
            sqlite_where=text("retired_at IS NULL"),
            postgresql_where=text("retired_at IS NULL"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False)
    kind = db.Column(db.String(12), nullable=False)
    location = db.Column(db.String(120), nullable=False)
    apartment_id = db.Column(
        db.Integer,
        db.ForeignKey("apartments.id", name="fk_parking_spots_apartment_id_apartments"),
        nullable=True,
        index=True,
    )
    occupied = db.Column(db.Boolean, nullable=False, default=False, server_default=false())

    apartment = db.relationship("Apartment", back_populates="parking_spots", lazy="joined")

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "type": self.kind,
            "location": self.location,
            "apartmentId": self.apartment_id,
            "apartment": self.apartment.label if self.apartment else None,
            "isOccupied": bool(self.occupied),
        }


class StorageRoom(RetirableMixin, db.Model):
    """Cuarto útil de la unidad, asignado a un apartamento (HU-016 y RF-016).

    El código es único entre los vigentes (RN-008).
    """

    __tablename__ = "storage_rooms"
    __table_args__ = (
        Index(
            "uq_storage_rooms_active_code",
            "code",
            unique=True,
            sqlite_where=text("retired_at IS NULL"),
            postgresql_where=text("retired_at IS NULL"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False)
    apartment_id = db.Column(
        db.Integer,
        db.ForeignKey("apartments.id", name="fk_storage_rooms_apartment_id_apartments"),
        nullable=True,
        index=True,
    )

    apartment = db.relationship("Apartment", back_populates="storage_rooms", lazy="joined")

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "apartmentId": self.apartment_id,
            "apartment": self.apartment.label if self.apartment else None,
        }


class ComplexProfile(db.Model):
    """Datos de la unidad residencial (el conjunto) que muestran la app y la web (HU-077).

    Hay una sola fila (id 1) y nace la primera vez que la administración guarda los datos:
    mientras no exista, la app y la web usan sus textos por defecto. No es la ficha del hogar
    de un apartamento (esa es ResidentialUnit).

    El logo se guarda como los bytes de una imagen PNG, JPG o WebP revisada al guardar.
    logo_sha256 es su huella: sirve de versión para que la app y el navegador sepan cuándo
    cambió y solo lo descarguen de nuevo en ese caso.
    """

    __tablename__ = "complex_profile"

    #: La única fila que existe.
    SINGLE_ID = 1

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    nit = db.Column(db.String(25), nullable=True)
    address = db.Column(db.String(200), nullable=True)
    portal_phone = db.Column(db.String(25), nullable=True)
    # «deferred»: los bytes del logo se leen solo cuando alguien los pide, no en cada consulta.
    logo = deferred(db.Column(db.LargeBinary, nullable=True))
    logo_type = db.Column(db.String(20), nullable=True)
    logo_sha256 = db.Column(db.String(64), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_complex_profile_updated_by_id_users"),
        nullable=True,
    )

    @property
    def has_logo(self):
        return self.logo_sha256 is not None

    @property
    def logo_version(self):
        """Un texto corto que cambia solo cuando cambia el logo (sirve para no descargarlo de nuevo)."""
        return self.logo_sha256[:12] if self.logo_sha256 else None

    def to_dict(self):
        return {
            "name": self.name,
            "nit": self.nit,
            "address": self.address,
            "portalPhone": self.portal_phone,
            "hasLogo": self.has_logo,
            "logoVersion": self.logo_version,
            "updatedAt": _fmt(self.updated_at),
        }


class ResidentialUnit(db.Model):
    """Ficha del hogar de un apartamento: integrantes, mascotas y vehículos.

    Hay una por apartamento y se crea junto con él. Los parqueaderos y cuartos
    útiles ya no se escriben aquí: se asignan al apartamento en la estructura de
    la unidad (HU-015 y HU-016).
    """

    __tablename__ = "residential_units"

    id = db.Column(db.Integer, primary_key=True)
    apartment_id = db.Column(
        db.Integer,
        db.ForeignKey("apartments.id", name="fk_residential_units_apartment_id_apartments"),
        nullable=False,
        unique=True,
        index=True,
    )
    pet_insurance = db.Column(db.Boolean, nullable=False, default=False)
    pet_insurer = db.Column(db.String(120), nullable=True)
    # El plan funerario ya no se registra (DEC-015, DEF-013): se quitó en la migración 0004.

    apartment_ref = db.relationship("Apartment", back_populates="unit", lazy="joined")

    # Incluyen también lo retirado: es el historial de la ficha (TT-032). Sin
    # «delete-orphan», quitar algo de la lista nunca lo borra de la base.
    members = db.relationship(
        "HouseholdMember", back_populates="unit", order_by="HouseholdMember.id"
    )
    pets = db.relationship("Pet", back_populates="unit", order_by="Pet.id")
    vehicles = db.relationship("Vehicle", back_populates="unit", order_by="Vehicle.id")

    @property
    def apartment(self):
        """Texto del apartamento de esta ficha, «Torre 1 · Apto 101»."""
        return self.apartment_ref.label

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
        residents = User.query.filter_by(
            apartment_id=self.apartment_id, role="RESIDENT"
        ).order_by(User.occupancy_type, User.name, User.id).all()
        parking_spots = [
            spot.code for spot in self.apartment_ref.active_parking_spots if spot.kind == "residente"
        ]
        storage_rooms = [room.code for room in self.apartment_ref.active_storage_rooms]
        return {
            "id": self.id,
            "apartmentId": self.apartment_id,
            "apartment": self.apartment,
            "residents": [
                {
                    "id": resident.id,
                    "name": resident.full_name,
                    "occupancyType": resident.occupancy_type,
                }
                for resident in residents
            ],
            # Salen de la estructura de la unidad; la ficha solo los muestra.
            "parkingIdentifier": ", ".join(parking_spots) or None,
            "storageIdentifier": ", ".join(storage_rooms) or None,
            "petInsurance": self.pet_insurance,
            "petInsurer": self.pet_insurer,
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
    """Mascota del apartamento; quitarla de la ficha la retira (TT-032).

    Guarda si tiene la vacunación y la desparasitación al día y la fecha de la
    última de cada una (RN-028, HU-021). Las fechas van como texto AAAA-MM-DD.
    """

    __tablename__ = "pets"

    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey("residential_units.id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    species = db.Column(db.String(60), nullable=False)
    breed = db.Column(db.String(100), nullable=False)
    age_years = db.Column(db.Integer, nullable=False)
    vaccines_up_to_date = db.Column(db.Boolean, nullable=False, default=False, server_default=false())
    last_vaccination_date = db.Column(db.String(10), nullable=True)
    deworming_up_to_date = db.Column(db.Boolean, nullable=False, default=False, server_default=false())
    last_deworming_date = db.Column(db.String(10), nullable=True)

    unit = db.relationship("ResidentialUnit", back_populates="pets")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "species": self.species,
            "breed": self.breed,
            "ageYears": self.age_years,
            "vaccinesUpToDate": bool(self.vaccines_up_to_date),
            "lastVaccinationDate": self.last_vaccination_date,
            "dewormingUpToDate": bool(self.deworming_up_to_date),
            "lastDewormingDate": self.last_deworming_date,
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

    Lleva una categoría (HU-058); solo los anteriores a esa historia no la
    tienen. Si tiene torre (HU-061), solo lo ven los residentes de esa torre; sin
    torre es para toda la unidad. Pasada su fecha de vencimiento (HU-060) sale
    de la lista principal y queda en «Archivados».
    """

    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(20), nullable=True)
    tower_id = db.Column(
        db.Integer,
        db.ForeignKey("towers.id", name="fk_announcements_tower_id_towers"),
        nullable=True,
        index=True,
    )
    expires_at = db.Column(db.Date, nullable=True)
    event_date = db.Column(db.String(20), nullable=True)
    event_time = db.Column(db.String(20), nullable=True)
    media_url = db.Column(db.Text, nullable=True)
    media_type = db.Column(db.String(20), nullable=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now)

    author = db.relationship("User", foreign_keys=[author_id])
    tower = db.relationship("Tower")

    @property
    def is_expired(self):
        """True si ya pasó su fecha de vencimiento: el último día vigente es el del vencimiento."""
        return self.expires_at is not None and self.expires_at < colombia_today()

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title or "",
            "message": self.message or "",
            "category": self.category,
            "categoryLabel": ANNOUNCEMENT_CATEGORIES.get(self.category),
            "towerId": self.tower_id,
            "towerName": self.tower.name if self.tower else None,
            "expiresAt": self.expires_at.isoformat() if self.expires_at else None,
            "isExpired": self.is_expired,
            "eventDate": self.event_date,
            "eventTime": self.event_time,
            "mediaUrl": self.media_url,
            "mediaType": self.media_type,
            "createdAt": _fmt(self.created_at),
            "authorName": self.author.full_name if self.author else None,
            "isRetired": self.is_retired,
            "retiredAt": _fmt(self.retired_at),
        }


class AnnouncementRead(db.Model):
    """Quién leyó un comunicado y cuándo (HU-059 y HU-062).

    Guarda el apartamento del residente al momento de leerlo: así el conteo de
    apartamentos que leyeron no cambia si después se muda. Cada residente deja
    una sola lectura por comunicado.
    """

    __tablename__ = "announcement_reads"
    __table_args__ = (
        db.UniqueConstraint("announcement_id", "user_id", name="uq_announcement_reads_user"),
    )

    id = db.Column(db.Integer, primary_key=True)
    announcement_id = db.Column(
        db.Integer,
        db.ForeignKey("announcements.id", name="fk_announcement_reads_announcement_id_announcements"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_announcement_reads_user_id_users"),
        nullable=False,
        index=True,
    )
    apartment_id = db.Column(
        db.Integer,
        db.ForeignKey("apartments.id", name="fk_announcement_reads_apartment_id_apartments"),
        nullable=True,
    )
    read_at = db.Column(db.DateTime, nullable=False, default=utc_now)


class Pqrs(db.Model):
    """Petición, queja, reclamo o sugerencia de un residente.

    Al guardarse recibe su número de radicado, único y visible en la lista y en el
    detalle (HU-072). Mientras no esté resuelta, su plazo corre en días hábiles y
    se muestra con un semáforo (HU-073).
    """

    __tablename__ = "pqrs"

    id = db.Column(db.Integer, primary_key=True)
    radicado = db.Column(db.String(30), unique=True, index=True, nullable=True)
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
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

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

    @property
    def semaphore(self):
        """El semáforo del plazo (HU-073); None si ya está resuelta, porque deja de correr."""
        if self.status not in RUNNING_STATUSES or self.created_at is None:
            return None
        return pqrs_semaphore(
            to_colombia(self.created_at).date(), colombia_today(), self.category
        )

    def to_dict(self):
        latest_rating = self.satisfaction_ratings[-1] if self.satisfaction_ratings else None
        semaphore = self.semaphore
        return {
            "id": self.id,
            "radicado": self.radicado,
            "semaphore": semaphore["color"] if semaphore else None,
            "daysRemaining": semaphore["daysRemaining"] if semaphore else None,
            "dueDate": semaphore["dueDate"] if semaphore else None,
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


@event.listens_for(Pqrs, "after_insert")
def _assign_radicado(mapper, connection, pqrs):
    """Le da su radicado a toda PQRS nueva, la cree la ruta que la cree (HU-072).

    El número lleva el id de la PQRS, que solo se conoce después de guardarla;
    por eso se escribe justo después del INSERT y dentro de la misma transacción.
    """
    if pqrs.radicado:
        return
    radicado = make_radicado(pqrs.id, pqrs.created_at)
    connection.execute(
        Pqrs.__table__.update().where(Pqrs.__table__.c.id == pqrs.id).values(radicado=radicado)
    )
    set_committed_value(pqrs, "radicado", radicado)


class PqrsMessage(db.Model):
    __tablename__ = "pqrs_messages"

    id = db.Column(db.Integer, primary_key=True)
    pqrs_id = db.Column(db.Integer, db.ForeignKey("pqrs.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    author_role = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=True)
    media_url = db.Column(db.Text, nullable=True)
    media_type = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

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
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

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
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    user = db.relationship("User")


class CommonArea(db.Model):
    """Zona común que los residentes pueden reservar, con sus propias reglas.

    El horario, el aforo, la anticipación y los plazos (HU-055, RN-020 a RN-022) se
    guardan en la zona y la administración los cambia desde la web, sin tocar el
    código. Las reservas nuevas siempre usan las reglas guardadas. Los valores por
    defecto vienen de services/zone_rules.py.

    * open_time, close_time y slot_minutes: el horario y la duración de cada franja.
    * capacity: aforo máximo de personas; sin valor, no se revisa.
    * min_advance_days y max_advance_days: con cuántos días de anticipación se
      puede reservar (como mínimo y como máximo).
    * cancel_deadline_days: el residente cancela hasta esos días antes de la fecha.
    * weekly_limit: reservas por semana de cada residente en esta zona.
    * maintenance_weekday: día de la semana (0 es lunes) en que la zona cierra por
      mantenimiento; si es festivo, pasa al día siguiente (RN-021).
    """

    __tablename__ = "common_areas"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    open_time = db.Column(
        db.String(5), nullable=False, default=DEFAULT_OPEN_TIME, server_default=DEFAULT_OPEN_TIME
    )
    close_time = db.Column(
        db.String(5), nullable=False, default=DEFAULT_CLOSE_TIME, server_default=DEFAULT_CLOSE_TIME
    )
    slot_minutes = db.Column(
        db.Integer, nullable=False, default=DEFAULT_SLOT_MINUTES,
        server_default=str(DEFAULT_SLOT_MINUTES),
    )
    capacity = db.Column(db.Integer, nullable=True)
    min_advance_days = db.Column(
        db.Integer, nullable=False, default=DEFAULT_MIN_ADVANCE_DAYS,
        server_default=str(DEFAULT_MIN_ADVANCE_DAYS),
    )
    max_advance_days = db.Column(
        db.Integer, nullable=False, default=DEFAULT_MAX_ADVANCE_DAYS,
        server_default=str(DEFAULT_MAX_ADVANCE_DAYS),
    )
    cancel_deadline_days = db.Column(
        db.Integer, nullable=False, default=DEFAULT_CANCEL_DEADLINE_DAYS,
        server_default=str(DEFAULT_CANCEL_DEADLINE_DAYS),
    )
    weekly_limit = db.Column(
        db.Integer, nullable=False, default=DEFAULT_WEEKLY_LIMIT,
        server_default=str(DEFAULT_WEEKLY_LIMIT),
    )
    maintenance_weekday = db.Column(db.Integer, nullable=True)

    @property
    def slots(self):
        """Las franjas que ofrece la zona cada día, según su horario."""
        return zone_slots(self.open_time, self.close_time, self.slot_minutes)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name or "",
            "openTime": self.open_time,
            "closeTime": self.close_time,
            "slotMinutes": self.slot_minutes,
            "slots": self.slots,
            "capacity": self.capacity,
            "minAdvanceDays": self.min_advance_days,
            "maxAdvanceDays": self.max_advance_days,
            "cancelDeadlineDays": self.cancel_deadline_days,
            "weeklyLimit": self.weekly_limit,
            "maintenanceWeekday": self.maintenance_weekday,
        }


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
    attendees = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), default="pendiente")
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    archived_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now)

    resident = db.relationship("User", foreign_keys=[resident_id])
    common_area = db.relationship("CommonArea")
    messages = db.relationship(
        "ReservationMessage",
        back_populates="reservation",
        cascade="all, delete-orphan",
        order_by="ReservationMessage.created_at, ReservationMessage.id",
    )

    @property
    def cancel_until(self):
        """Último día en que el residente puede cancelar (RN-020 y HU-053).

        Es el plazo de la zona contado hacia atrás desde la fecha reservada.
        """
        try:
            reserved_day = date.fromisoformat(self.date)
        except (TypeError, ValueError):
            return None
        days = self.common_area.cancel_deadline_days if self.common_area else DEFAULT_CANCEL_DEADLINE_DAYS
        return reserved_day - timedelta(days=days)

    @property
    def resident_can_cancel(self):
        """True si el residente todavía está a tiempo de cancelar esta reserva."""
        deadline = self.cancel_until
        return (
            self.status in ("pendiente", "activa", "aprobada")
            and deadline is not None
            and colombia_today() <= deadline
        )

    def to_dict(self):
        cancel_until = self.cancel_until
        return {
            "id": self.id,
            "residentId": self.resident_id,
            "createdByAdminId": self.created_by_admin_id,
            "createdByAdministration": self.created_by_admin_id is not None,
            "commonAreaId": self.common_area_id,
            "commonAreaName": self.common_area.name if self.common_area else None,
            "date": self.date,
            "timeSlot": self.time_slot,
            "attendees": self.attendees,
            "cancelUntil": cancel_until.isoformat() if cancel_until else None,
            "canCancel": self.resident_can_cancel,
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
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

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
    """Paquete que llega a la portería para un residente (HU-042 a HU-049).

    arrived_at es cuándo llegó a la portería (al registrarlo, o al pasarlo de
    «por llegar» a «en portería»): desde ahí se cuentan las horas sin reclamar
    que resaltan en naranja y en rojo (RN-018). carrier y tracking_number son la
    transportadora y el número de guía (HU-047).
    """

    __tablename__ = "packages"

    id = db.Column(db.Integer, primary_key=True)
    resident_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    registered_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    description = db.Column(db.String(200), nullable=True)
    carrier = db.Column(db.String(60), nullable=True)
    tracking_number = db.Column(db.String(60), nullable=True)
    status = db.Column(db.String(20), default="pendiente")
    media_url = db.Column(db.Text, nullable=True)
    media_type = db.Column(db.String(20), nullable=True)
    event_date = db.Column(db.String(20), nullable=True)
    event_time = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now)
    arrived_at = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    delivered_to = db.Column(db.String(120), nullable=True)
    delivered_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    resident = db.relationship("User", foreign_keys=[resident_id])
    guard = db.relationship("User", foreign_keys=[registered_by])
    delivered_by = db.relationship("User", foreign_keys=[delivered_by_id])
    pickup_codes = db.relationship(
        "PackagePickupCode", back_populates="package", order_by="PackagePickupCode.id"
    )

    @property
    def active_pickup_code(self):
        """El código de entrega vigente (no usado ni anulado), o None."""
        return next((code for code in self.pickup_codes if code.is_active), None)

    def waiting_minutes(self, now=None):
        """Minutos que lleva en portería sin reclamar; None si no está esperando a su dueño."""
        if self.status != "pendiente" or self.is_deleted or self.arrived_at is None:
            return None
        return max(0, int(((now or utc_now()) - self.arrived_at).total_seconds() // 60))

    def claim_alert(self, now=None):
        """«rojo» con más de 72 horas sin reclamar, «naranja» con más de 48, o None (RN-018)."""
        minutes = self.waiting_minutes(now)
        if minutes is None:
            return None
        if minutes > UNCLAIMED_RED_HOURS * 60:
            return "rojo"
        if minutes > UNCLAIMED_ORANGE_HOURS * 60:
            return "naranja"
        return None

    def to_dict(self):
        now = utc_now()
        waiting = self.waiting_minutes(now)
        return {
            "id": self.id,
            "residentId": self.resident_id,
            "description": self.description or "",
            "carrier": self.carrier,
            "trackingNumber": self.tracking_number,
            "arrivedAt": _fmt(self.arrived_at),
            "hoursWaiting": None if waiting is None else waiting // 60,
            "claimAlert": self.claim_alert(now),
            "hasPickupCode": self.active_pickup_code is not None,
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


class PackagePickupCode(db.Model):
    """Código para que otra persona recoja un paquete: un QR y un PIN de 6 dígitos (HU-048, RN-016).

    Lo genera el residente dueño del paquete. El QR (token) se guarda tal cual,
    como el de las visitas; el PIN se guarda con hash y solo se muestra al
    generarlo. Hay un solo código vigente por paquete: generar uno nuevo anula el
    anterior (revoked_at), y los que se usaron o se anularon quedan como historial,
    nunca se borran (ADR-013). Tras 5 intentos fallidos el código se anula.
    """

    __tablename__ = "package_pickup_codes"
    __table_args__ = (
        Index(
            "uq_package_pickup_codes_active",
            "package_id",
            unique=True,
            sqlite_where=text("revoked_at IS NULL AND used_at IS NULL"),
            postgresql_where=text("revoked_at IS NULL AND used_at IS NULL"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(
        db.Integer,
        db.ForeignKey("packages.id", name="fk_package_pickup_codes_package_id_packages"),
        nullable=False,
        index=True,
    )
    token = db.Column(db.String(80), nullable=False, unique=True, index=True)
    pin_hash = db.Column(db.String(255), nullable=False)
    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_package_pickup_codes_created_by_id_users"),
        nullable=False,
    )
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    used_at = db.Column(db.DateTime, nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True)
    failed_attempts = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    package = db.relationship("PackageItem", back_populates="pickup_codes")

    @property
    def is_active(self):
        return self.used_at is None and self.revoked_at is None


class Visit(db.Model):
    """Visita a un apartamento: quién llega, quién la autoriza y cuándo entra y sale.

    expected_stay_minutes es la estadía que el guardia anota al registrarla (HU-031):
    cuando pasa sin que la visita haya salido, el residente recibe «¿Tu visitante
    sigue en la unidad?» (RN-012). overstay_alerted_at guarda cuándo se le avisó,
    para no avisar dos veces; vuelve a quedar vacío cuando la visita reingresa.
    """

    __tablename__ = "visits"
    __table_args__ = (
        # Solo las visitas que están dentro con una estadía por vigilar: son las únicas
        # que busca la alerta, así que el índice es diminuto aunque haya miles de visitas.
        Index(
            "ix_visits_pending_overstay",
            "entered_at",
            sqlite_where=text(
                "exited_at IS NULL AND expected_stay_minutes IS NOT NULL AND overstay_alerted_at IS NULL"
            ),
            postgresql_where=text(
                "exited_at IS NULL AND expected_stay_minutes IS NOT NULL AND overstay_alerted_at IS NULL"
            ),
        ),
    )

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
    expected_stay_minutes = db.Column(db.Integer, nullable=True)
    overstay_alerted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now)

    resident = db.relationship("User", foreign_keys=[resident_id])
    guard = db.relationship("User", foreign_keys=[registered_by])
    qr_pass = db.relationship("VisitQrPass", back_populates="visits")
    events = db.relationship(
        "VisitEvent",
        back_populates="visit",
        cascade="all, delete-orphan",
        order_by="VisitEvent.created_at, VisitEvent.id",
    )

    @property
    def is_inside(self):
        """La visita entró y todavía no tiene salida."""
        return self.entered_at is not None and self.exited_at is None

    def inside_minutes(self, now=None):
        """Minutos que lleva dentro; None si no está dentro."""
        if not self.is_inside:
            return None
        return max(0, int(((now or utc_now()) - self.entered_at).total_seconds() // 60))

    def is_overstay(self, now=None):
        """Sigue dentro y ya pasó la estadía prevista (RN-012)."""
        if self.expected_stay_minutes is None or not self.is_inside:
            return False
        return self.inside_minutes(now) >= self.expected_stay_minutes

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
            "expectedStayMinutes": self.expected_stay_minutes,
            "insideMinutes": self.inside_minutes(),
            "isOverstay": self.is_overstay(),
            "createdAt": _fmt(self.created_at),
            "events": [event.to_dict() for event in self.events],
            "residentName": self.resident.full_name if self.resident else None,
            "apartment": self.resident.apartment if self.resident else None,
            "registeredByName": self.guard.full_name if self.guard else None,
        }


class VisitQrPass(db.Model):
    """QR que el residente crea para que sus visitas entren sin llamadas (HU-027, RN-011).

    visitor_names guarda, uno por línea, los nombres que el residente escribió al
    crearlo (HU-033); el guardia los ve al escanearlo.
    """

    __tablename__ = "visit_qr_passes"

    id = db.Column(db.Integer, primary_key=True)
    resident_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    token = db.Column(db.String(80), nullable=False, unique=True, index=True)
    valid_from = db.Column(db.String(10), nullable=False)
    valid_until = db.Column(db.String(10), nullable=False)
    max_people = db.Column(db.Integer, nullable=False)
    visitor_names = db.Column(db.Text, nullable=True)
    revoked = db.Column(db.Boolean, default=False, nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    resident = db.relationship("User")
    visits = db.relationship("Visit", back_populates="qr_pass")

    @property
    def names(self):
        """Los nombres de visitantes escritos al crear el QR, en una lista."""
        return [name for name in (self.visitor_names or "").split("\n") if name]

    @names.setter
    def names(self, values):
        self.visitor_names = "\n".join(values) or None

    def to_dict(self, include_token=False):
        registered_people = len(self.visits)
        result = {
            "id": self.id,
            "residentId": self.resident_id,
            "validFrom": self.valid_from,
            "validUntil": self.valid_until,
            "maxPeople": self.max_people,
            "visitorNames": self.names,
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
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

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


class VisitorVehicleEntry(db.Model):
    """Entrada de un vehículo visitante a la unidad, con su parqueadero (HU-035 a HU-041, DAT-07).

    Hay una fila por cada vez que un vehículo entra. Queda abierta (exited_at vacío)
    hasta que el guardia registra su salida y el parqueadero vuelve a quedar libre
    (RN-014). Nunca se borra (ADR-013): a los 5 años pasa al archivo histórico (DAT-07).

    Los dos índices únicos parciales son la última defensa contra el doble registro:
    una placa no puede tener dos entradas abiertas y un parqueadero no puede tener dos
    vehículos adentro (RN-013), aunque dos guardias lo intenten al mismo tiempo.
    """

    __tablename__ = "visitor_vehicle_entries"
    __table_args__ = (
        Index(
            "uq_visitor_vehicle_entries_open_plate",
            "plate",
            unique=True,
            sqlite_where=text("exited_at IS NULL"),
            postgresql_where=text("exited_at IS NULL"),
        ),
        Index(
            "uq_visitor_vehicle_entries_open_spot",
            "spot_id",
            unique=True,
            sqlite_where=text("exited_at IS NULL"),
            postgresql_where=text("exited_at IS NULL"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    plate = db.Column(db.String(10), nullable=False, index=True)
    visit_id = db.Column(
        db.Integer,
        db.ForeignKey("visits.id", name="fk_visitor_vehicle_entries_visit_id_visits"),
        nullable=False,
        index=True,
    )
    #: Apartamento al que visita, tomado de la visita; así el historial no depende de ella.
    apartment_id = db.Column(
        db.Integer,
        db.ForeignKey("apartments.id", name="fk_visitor_vehicle_entries_apartment_id_apartments"),
        nullable=True,
        index=True,
    )
    #: Vacío cuando no había parqueaderos libres y el guardia registró la entrada igual.
    spot_id = db.Column(
        db.Integer,
        db.ForeignKey("parking_spots.id", name="fk_visitor_vehicle_entries_spot_id_parking_spots"),
        nullable=True,
    )
    entered_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)
    exited_at = db.Column(db.DateTime, nullable=True)
    registered_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_visitor_vehicle_entries_registered_by_users"),
        nullable=False,
    )
    exited_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_visitor_vehicle_entries_exited_by_id_users"),
        nullable=True,
    )
    #: Cuándo se avisó a los guardias que pasó el tiempo máximo (RN-015); evita avisar dos veces.
    overdue_alerted_at = db.Column(db.DateTime, nullable=True)

    visit = db.relationship("Visit")
    apartment = db.relationship("Apartment", lazy="joined")
    spot = db.relationship("ParkingSpot", lazy="joined")
    guard = db.relationship("User", foreign_keys=[registered_by])
    exited_by = db.relationship("User", foreign_keys=[exited_by_id])

    @property
    def is_inside(self):
        return self.exited_at is None

    def parked_minutes(self, now=None):
        """Minutos que lleva (o llevó) el vehículo en la unidad."""
        end = self.exited_at or now or utc_now()
        return max(0, int((end - self.entered_at).total_seconds() // 60))

    def deadline(self):
        """Cuándo vence el tiempo máximo de parqueo (RN-015): 3 días o el plazo de la unidad."""
        return self.entered_at + timedelta(days=visitor_parking_max_days())

    def is_overdue(self, now=None):
        """Un vehículo que sigue adentro y ya pasó el tiempo máximo (RN-015)."""
        return self.is_inside and (now or utc_now()) >= self.deadline()

    def to_dict(self, now=None):
        now = now or utc_now()
        visit = self.visit
        return {
            "id": self.id,
            "plate": self.plate,
            "visitId": self.visit_id,
            "visitorName": visit.visitor_name if visit else None,
            "residentName": visit.resident.full_name if visit and visit.resident else None,
            "apartmentId": self.apartment_id,
            "apartment": self.apartment.label if self.apartment else None,
            "spotId": self.spot_id,
            "spotCode": self.spot.code if self.spot else None,
            "spotLocation": self.spot.location if self.spot else None,
            "enteredAt": _fmt(self.entered_at),
            "exitedAt": _fmt(self.exited_at),
            "isInside": self.is_inside,
            "parkedMinutes": self.parked_minutes(now),
            "maxDays": visitor_parking_max_days(),
            "isOverdue": self.is_overdue(now),
            "registeredByName": self.guard.full_name if self.guard else None,
            "exitedByName": self.exited_by.full_name if self.exited_by else None,
        }


class VehicleMovement(db.Model):
    """Entrada o salida de un vehículo de residente por la portería (HU-040, DAT-05).

    El guardia la registra con un toque y la hora la pone el servidor. Si el
    vehículo está adentro se deduce del último movimiento. La placa se copia aquí
    para que el historial siga siendo legible aunque el vehículo se retire de la ficha.
    """

    __tablename__ = "vehicle_movements"
    __table_args__ = (Index("ix_vehicle_movements_vehicle_id_id", "vehicle_id", "id"),)

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(
        db.Integer,
        db.ForeignKey("vehicles.id", name="fk_vehicle_movements_vehicle_id_vehicles"),
        nullable=False,
    )
    plate = db.Column(db.String(10), nullable=False)
    movement_type = db.Column(db.String(10), nullable=False)
    registered_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_vehicle_movements_registered_by_users"),
        nullable=False,
    )
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)

    vehicle = db.relationship("Vehicle")
    guard = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "vehicleId": self.vehicle_id,
            "plate": self.plate,
            "type": self.movement_type,
            "createdAt": _fmt(self.created_at),
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
    created_at = db.Column(db.DateTime, default=utc_now)

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
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

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


class LoginAttempt(db.Model):
    """Intentos fallidos seguidos de una cuenta o de un PIN (HU-006, RN-002 y DAT-02).

    Hay una fila por cada correo (o por cada guardia, en el caso del PIN) que ha
    fallado alguna vez. Un inicio correcto pone el contador en cero y, al llegar
    al quinto fallo, locked_until guarda hasta cuándo dura el bloqueo. También se
    lleva para los correos que no existen: así el bloqueo no revela qué cuentas
    hay en el sistema.
    """

    __tablename__ = "login_attempts"
    __table_args__ = (
        db.UniqueConstraint("kind", "subject", name="uq_login_attempts_kind_subject"),
    )

    id = db.Column(db.Integer, primary_key=True)
    #: «login» para la contraseña o «pin» para el cambio de turno del guardia.
    kind = db.Column(db.String(10), nullable=False)
    #: El correo en minúscula, o el id del guardia cuando es un PIN.
    subject = db.Column(db.String(160), nullable=False)
    failed_count = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    last_failed_at = db.Column(db.DateTime, nullable=True)
