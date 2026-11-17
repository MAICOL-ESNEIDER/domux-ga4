"""Datos de prueba que se agregan a los que ya hay (decisión 15 del cronograma, 16/11/2026).

No borran ni cambian nada de lo que ya existe: solo agregan lo que falta para probar cada opción de
la app y de la web. Con la semilla (``seed.py``) quedan 17 usuarios:

* 1 administración: admin@domux.com (ya existía).
* 4 guardias: guardia@domux.com (ya existía) y 3 nuevos, sin PIN: la administración se lo asigna
  desde la app (HU-010).
* 12 residentes: maria@domux.com y carlos@domux.com (ya existían) y 10 nuevos, repartidos en cuatro
  hogares: propietarios que viven ahí, arrendatarios, propietarios que no viven ahí, adultos
  mayores, un joven de 15 años con autorización de sus papás y una de 13 sin ella (para probar que
  así solo puede consultar). Los niños menores de 12 no tienen cuenta: van en la ficha del hogar.

Además: parqueaderos y cuartos útiles con dueño y libres, carros y motos con su titular, mascotas,
la zona «Piscina» con mantenimiento los lunes, los datos de la unidad (si no se habían guardado),
comunicados de cada tipo, PQRS en verde, amarillo, rojo y resueltas, reservas en cada estado,
paquetes de más de 48 y 72 horas, visitas a pie y en carro (una adentro y otra esperando
autorización), códigos QR y notificaciones. Las fechas se cuentan desde el día en que se cargan.

Las contraseñas no están aquí (SEC-004 y SEC-013): cada cuenta nueva usa la variable de su rol, las
mismas de la semilla (``SEED_GUARD_PASSWORD`` y ``SEED_RESIDENT_PASSWORD``). Se cargan una sola vez:
al terminar queda una marca en el registro de auditoría y, con ella, no se vuelven a cargar.
"""

import json
import logging
import os
import secrets
from datetime import timedelta

from werkzeug.security import generate_password_hash

from business_days import is_business_day
from extensions import db
from models import (
    Announcement,
    AnnouncementRead,
    Apartment,
    AuditLog,
    CommonArea,
    ComplexProfile,
    HouseholdMember,
    Notification,
    PackageItem,
    ParkingSpot,
    Pet,
    Pqrs,
    PqrsMessage,
    PqrsSatisfaction,
    Reservation,
    ReservationMessage,
    ResidentialUnit,
    StorageRoom,
    Tower,
    User,
    Vehicle,
    VehicleMovement,
    Visit,
    VisitEvent,
    VisitorVehicleEntry,
    VisitQrPass,
)
from seed import DEMO_PASSWORD_VARS, demo_password, remember_generated_credentials
from services.reservation_service import reservation_conflicts
from services.unit_service import nit_check_digit
from time_utils import colombia_day_to_utc, colombia_today, utc_now

logger = logging.getLogger(__name__)

#: Sube si algún día se agregan más datos de prueba: así la versión nueva se carga aunque la
#: anterior ya esté.
DEMO_DATA_VERSION = 1

#: La marca que queda en el registro de auditoría cuando los datos ya se cargaron.
MARKER_ENTITY = "datos_prueba"
MARKER_ACTION = "datos_prueba_agregados"

#: Con DOMUX_DEMO_DATA=0 el servidor no los carga al arrancar (las pruebas automáticas lo apagan).
SWITCH_VAR = "DOMUX_DEMO_DATA"

#: Solo se agregan a una base que tenga las cuentas de prueba de la semilla: nunca a la de una
#: unidad real.
BASE_ADMIN_EMAIL = "admin@domux.com"
BASE_GUARD_EMAIL = "guardia@domux.com"

#: Los hogares. «maria» y «carlos» son el apartamento de esas cuentas, si siguen teniendo uno;
#: si no, el de la semilla.
HOMES = {
    "maria": ("maria@domux.com", ("Torre 1", "101")),
    "carlos": ("carlos@domux.com", ("Torre 2", "202")),
    "arrendado": (None, ("Torre 2", "101")),
    "mayores": (None, ("Torre 1", "201")),
}

#: Las 3 guardias nuevas (hay 4 con la de la semilla). Documentos y teléfonos inventados.
NEW_GUARDS = (
    {"email": "guardia2@domux.com", "name": "Edwin", "last_name": "Morales", "phone": "3000000202",
     "document_id": "9990000202"},
    {"email": "guardia3@domux.com", "name": "Johana", "last_name": "Pulgarín", "phone": "3000000203",
     "document_id": "9990000203"},
    {"email": "guardia4@domux.com", "name": "Fredy", "last_name": "Salazar", "phone": "3000000204",
     "document_id": "9990000204"},
)

#: Los 10 residentes nuevos (hay 12 con los de la semilla).
NEW_RESIDENTS = (
    # Hogar de María (propietaria que vive ahí): su esposo y su hijo de 15 años.
    {"email": "jorge@domux.com", "name": "Jorge", "last_name": "Cardona Ríos", "home": "maria",
     "occupancy": "residente", "birth_date": "1982-03-14", "phone": "3000000301", "document_id": "9990000301"},
    {"email": "samuel@domux.com", "name": "Samuel", "last_name": "Cardona Gómez", "home": "maria",
     "occupancy": "residente", "birth_date": "2011-05-20", "phone": "3000000302", "parental_consent": True},
    # Hogar de Carlos (arrendatario): su pareja, su hija de 13 años sin autorización de los papás y el
    # dueño del apartamento, que no vive ahí.
    {"email": "diana@domux.com", "name": "Diana", "last_name": "Ríos Zapata", "home": "carlos",
     "occupancy": "residente", "birth_date": "1990-07-02", "phone": "3000000303", "document_id": "9990000303"},
    {"email": "sara@domux.com", "name": "Sara", "last_name": "Pérez Ríos", "home": "carlos",
     "occupancy": "residente", "birth_date": "2013-09-15", "parental_consent": False},
    {"email": "hernan@domux.com", "name": "Hernán", "last_name": "Ospina Vélez", "home": "carlos",
     "occupancy": "propietario", "birth_date": "1965-11-30", "phone": "3000000305", "document_id": "9990000305"},
    # Otro apartamento arrendado: la arrendataria, su hijo de 19 años y la dueña, que no vive ahí.
    {"email": "natalia@domux.com", "name": "Natalia", "last_name": "Correa Giraldo", "home": "arrendado",
     "occupancy": "arrendatario", "birth_date": "1987-04-22", "phone": "3000000306", "document_id": "9990000306"},
    {"email": "tomas@domux.com", "name": "Tomás", "last_name": "Mejía Correa", "home": "arrendado",
     "occupancy": "residente", "birth_date": "2007-08-09", "phone": "3000000307", "document_id": "9990000307"},
    {"email": "marta@domux.com", "name": "Marta Lucía", "last_name": "Henao Arango", "home": "arrendado",
     "occupancy": "propietario", "birth_date": "1958-01-17", "phone": "3000000308", "document_id": "9990000308"},
    # Pareja de adultos mayores, dueños de su apartamento.
    {"email": "gustavo@domux.com", "name": "Gustavo", "last_name": "Restrepo Arango", "home": "mayores",
     "occupancy": "propietario", "birth_date": "1955-06-03", "phone": "3000000309", "document_id": "9990000309"},
    {"email": "gloria@domux.com", "name": "Gloria", "last_name": "Patiño Vélez", "home": "mayores",
     "occupancy": "propietario", "birth_date": "1958-10-12", "phone": "3000000310", "document_id": "9990000310"},
)

#: Las cuentas nuevas y la variable que guarda su contraseña.
NEW_ACCOUNT_VARS = {
    **{guard["email"]: "SEED_GUARD_PASSWORD" for guard in NEW_GUARDS},
    **{resident["email"]: "SEED_RESIDENT_PASSWORD" for resident in NEW_RESIDENTS},
}

#: Integrantes sin cuenta (menores de 12 años): solo salen en la ficha del hogar.
MEMBERS = (
    {"home": "maria", "name": "Valentina", "last_name": "Cardona Gómez", "document_id": "9990001101",
     "birth_date": "2018-02-10", "relationship": "hija"},
    {"home": "carlos", "name": "Martín", "last_name": "Pérez Ríos", "document_id": "9990001102",
     "birth_date": "2022-06-30", "relationship": "hijo"},
)

#: Mascotas: los días son cuántos días antes de la carga fue la última vacuna o desparasitación.
PETS = (
    {"home": "maria", "name": "Luna", "species": "Perro", "breed": "Criollo", "age_years": 4,
     "vaccination_days_ago": 90, "deworming_days_ago": 40},
    # Sin la vacunación al día: así se ve el aviso de la ficha (RN-028).
    {"home": "carlos", "name": "Michi", "species": "Gato", "breed": "Angora", "age_years": 2,
     "vaccination_days_ago": None, "deworming_days_ago": 45},
    {"home": "mayores", "name": "Rocky", "species": "Perro", "breed": "Labrador", "age_years": 9,
     "vaccination_days_ago": 150, "deworming_days_ago": 60},
)

#: Vehículos de los residentes, con su titular. Placas inventadas.
VEHICLES = (
    {"home": "maria", "plate": "DMX101", "type": "carro", "make_model": "Mazda 3", "year": 2021,
     "owner": "María Gómez", "color": "Gris"},
    {"home": "carlos", "plate": "DMX20A", "type": "moto", "make_model": "Yamaha NMAX", "year": 2022,
     "owner": "Carlos Pérez", "color": "Negro"},
    {"home": "arrendado", "plate": "DMX303", "type": "carro", "make_model": "Chevrolet Onix", "year": 2020,
     "owner": "Natalia Correa Giraldo", "color": "Blanco"},
    {"home": "mayores", "plate": "DMX404", "type": "carro", "make_model": "Renault Duster", "year": 2018,
     "owner": "Gustavo Restrepo Arango", "color": "Rojo"},
)

#: Parqueaderos nuevos: (código, tipo, ubicación, hogar o None si queda libre).
PARKING_SPOTS = (
    ("P-T1-201", "residente", "Sótano 1", "mayores"),
    ("P-T2-101", "residente", "Sótano 2", "arrendado"),
    ("P-T2-202", "residente", "Sótano 2", "carlos"),
    ("P-T2-201", "residente", "Sótano 2", None),
    ("V-04", "visitante", "Frente a la portería (motos)", None),
    ("V-05", "visitante", "Frente a la portería (personas con discapacidad)", None),
    # Aquí queda el carro del visitante que está adentro: así no se toca ningún parqueadero que ya existía.
    (VISITOR_CAR_SPOT := "V-06", "visitante", "Frente a la portería", None),
)

#: Cuartos útiles nuevos: (código, hogar o None si queda libre).
STORAGE_ROOMS = (
    ("C-T1-201", "mayores"),
    ("C-T2-101", "arrendado"),
    ("C-T2-202", "carlos"),
    ("C-T2-201", None),
)

#: Una zona con día de mantenimiento, para probar que ese día no se puede reservar (RN-021).
POOL = {
    "name": "Piscina", "capacity": 40, "open_time": "09:00", "close_time": "16:00", "slot_minutes": 60,
    "maintenance_weekday": 0, "max_consecutive_slots": 2, "max_advance_days": 30, "cancel_deadline_days": 1,
}

#: Los datos de la unidad, si la administración todavía no los ha guardado (unidad inventada, DEC-072).
UNIT_PROFILE = {
    "name": "Conjunto Residencial Mirador del Norte P.H.",
    "nit": f"900.000.001-{nit_check_digit('900000001')}",
    "address": "Calle 1 # 1-01, Bello, Antioquia",
    "portal_phone": "604 000 0000",
}


def _enabled():
    return os.environ.get(SWITCH_VAR, "1") != "0"


def already_added():
    """True si esta versión de los datos de prueba ya se cargó."""
    markers = AuditLog.query.filter_by(entity_type=MARKER_ENTITY, action=MARKER_ACTION).all()
    for marker in markers:
        try:
            version = json.loads(marker.details or "{}").get("version")
        except (TypeError, ValueError, AttributeError):
            continue
        if isinstance(version, int) and version >= DEMO_DATA_VERSION:
            return True
    return False


def add_demo_data():
    """Agrega los datos de prueba si faltan. Devuelve True si los agregó en esta llamada.

    No hace nada si están apagados (DOMUX_DEMO_DATA=0), si ya se cargaron, si la base no tiene las
    cuentas de prueba de la semilla o si, en producción, falta la contraseña de algún rol.
    """
    if not _enabled() or already_added():
        return False
    admin = User.query.filter_by(email=BASE_ADMIN_EMAIL, role="ADMIN").first()
    if admin is None:
        return False
    passwords = {var: demo_password(var) for var in set(NEW_ACCOUNT_VARS.values())}
    missing = sorted(var for var, password in passwords.items() if password is None)
    if missing:
        logger.warning("No se agregaron los datos de prueba: faltan %s.", ", ".join(missing))
        return False
    try:
        created = _DemoBuilder(admin, passwords).build()
        db.session.add(AuditLog(
            entity_type=MARKER_ENTITY,
            action=MARKER_ACTION,
            actor_role="SISTEMA",
            details=json.dumps({"version": DEMO_DATA_VERSION, "cuentas": len(created)}, ensure_ascii=False),
        ))
        db.session.commit()
    except Exception:
        # Si otro arranque los cargó al mismo tiempo, o algo no cuadra, no queda nada a medias.
        db.session.rollback()
        logger.exception("No se pudieron agregar los datos de prueba; la base quedó como estaba.")
        return False
    remember_generated_credentials({email: passwords[NEW_ACCOUNT_VARS[email]] for email in created})
    logger.info("Datos de prueba agregados: %s cuentas nuevas y lo necesario para probar cada opción.", len(created))
    return True


class _DemoBuilder:
    """Arma los datos de prueba dentro de una sola transacción (el commit lo hace add_demo_data)."""

    def __init__(self, admin, passwords):
        self.admin = admin
        self.now = utc_now()
        self.today = colombia_today()
        # Un solo hash por rol: las cuentas de un rol comparten contraseña (la de su variable).
        self.hashes = {var: generate_password_hash(password) for var, password in passwords.items()}
        self.homes = {}
        self.users = {}
        self.created = []

    # --- Utilidades -------------------------------------------------------------------------

    def at(self, days=0, hours=0, minutes=0):
        """Un momento relativo a la carga (en UTC, como se guarda todo)."""
        return self.now + timedelta(days=days, hours=hours, minutes=minutes)

    def on_day(self, day, hour, minute=0):
        """Un día y una hora de Colombia, en UTC."""
        return colombia_day_to_utc(day) + timedelta(hours=hour, minutes=minute)

    def business_days_ago(self, count):
        """El día hábil que queda ``count`` días hábiles antes de hoy."""
        day = self.today
        while count > 0:
            day -= timedelta(days=1)
            if is_business_day(day):
                count -= 1
        return day

    def next_weekday(self, weekday, at_least=1):
        """El próximo lunes (0) … domingo (6) que esté al menos ``at_least`` días después de hoy."""
        day = self.today + timedelta(days=at_least)
        while day.weekday() != weekday:
            day += timedelta(days=1)
        return day

    def user(self, email):
        if email not in self.users:
            self.users[email] = User.query.filter_by(email=email).first()
        return self.users[email]

    # --- Estructura -------------------------------------------------------------------------

    def apartment(self, tower_name, code):
        """El apartamento vigente de esa torre y código; si no existe, se agrega con su ficha."""
        tower = Tower.query.filter_by(name=tower_name, retired_at=None).first()
        if tower is None:
            tower = Tower(name=tower_name, floors=10)
            db.session.add(tower)
            db.session.flush()
        apartment = Apartment.query.filter_by(tower_id=tower.id, code=code, retired_at=None).first()
        if apartment is None:
            apartment = Apartment(
                tower=tower, code=code, floor=int(code[:-2] or 1), number=int(code), unit=ResidentialUnit()
            )
            db.session.add(apartment)
            db.session.flush()
        if apartment.unit is None:
            apartment.unit = ResidentialUnit()
            db.session.flush()
        return apartment

    def home(self, key):
        if key not in self.homes:
            email, (tower_name, code) = HOMES[key]
            existing = self.user(email) if email else None
            self.homes[key] = (
                existing.apartment_ref if existing is not None and existing.apartment_ref is not None
                else self.apartment(tower_name, code)
            )
        return self.homes[key]

    def add_structure(self):
        for code, kind, location, home in PARKING_SPOTS:
            if ParkingSpot.query.filter_by(code=code, retired_at=None).first() is None:
                db.session.add(ParkingSpot(
                    code=code, kind=kind, location=location,
                    apartment=self.home(home) if home else None,
                ))
        for code, home in STORAGE_ROOMS:
            if StorageRoom.query.filter_by(code=code, retired_at=None).first() is None:
                db.session.add(StorageRoom(code=code, apartment=self.home(home) if home else None))
        if CommonArea.query.filter_by(name=POOL["name"]).first() is None:
            db.session.add(CommonArea(**POOL))
        if db.session.get(ComplexProfile, ComplexProfile.SINGLE_ID) is None:
            db.session.add(ComplexProfile(id=ComplexProfile.SINGLE_ID, updated_by_id=self.admin.id, **UNIT_PROFILE))
        db.session.flush()

    # --- Personas ---------------------------------------------------------------------------

    def add_accounts(self):
        consent_at = self.at(days=-30)
        for guard in NEW_GUARDS:
            self._account(guard, role="GUARD", apartment=None, occupancy="propietario", consent_at=consent_at)
        for resident in NEW_RESIDENTS:
            self._account(
                resident, role="RESIDENT", apartment=self.home(resident["home"]),
                occupancy=resident["occupancy"], consent_at=consent_at,
            )
        db.session.flush()

    def _account(self, data, role, apartment, occupancy, consent_at):
        if self.user(data["email"]) is not None:
            return
        user = User(
            name=data["name"],
            last_name=data["last_name"],
            email=data["email"],
            phone=data.get("phone", ""),
            document_id=data.get("document_id", ""),
            password_hash=self.hashes[NEW_ACCOUNT_VARS[data["email"]]],
            role=role,
            apartment_ref=apartment,
            occupancy_type=occupancy,
            birth_date=data.get("birth_date"),
            parental_consent=data.get("parental_consent", False),
            data_processing_consent=True,
            data_processing_consent_at=consent_at,
            created_at=consent_at,
        )
        db.session.add(user)
        self.users[data["email"]] = user
        self.created.append(data["email"])

    def add_households(self):
        for member in MEMBERS:
            unit = self.home(member["home"]).unit
            if any(m.document_id == member["document_id"] for m in unit.active_members):
                continue
            db.session.add(HouseholdMember(
                unit=unit, name=member["name"], last_name=member["last_name"],
                document_id=member["document_id"], birth_date=member["birth_date"],
                relationship=member["relationship"],
            ))
        for pet in PETS:
            unit = self.home(pet["home"]).unit
            if any(p.name == pet["name"] and p.species == pet["species"] for p in unit.active_pets):
                continue
            db.session.add(Pet(
                unit=unit, name=pet["name"], species=pet["species"], breed=pet["breed"],
                age_years=pet["age_years"],
                **self._pet_health(pet["vaccination_days_ago"], "vaccines_up_to_date", "last_vaccination_date"),
                **self._pet_health(pet["deworming_days_ago"], "deworming_up_to_date", "last_deworming_date"),
            ))
        for vehicle in VEHICLES:
            if Vehicle.query.filter_by(plate=vehicle["plate"], retired_at=None).first() is not None:
                continue
            db.session.add(Vehicle(
                unit=self.home(vehicle["home"]).unit, plate=vehicle["plate"], vehicle_type=vehicle["type"],
                make_model=vehicle["make_model"], year=vehicle["year"],
                registered_owner=vehicle["owner"], color=vehicle["color"],
            ))
        db.session.flush()

    def _pet_health(self, days_ago, flag, column):
        if days_ago is None:
            return {flag: False, column: None}
        return {flag: True, column: (self.today - timedelta(days=days_ago)).isoformat()}

    # --- Comunidad ----------------------------------------------------------------------------

    def add_announcements(self):
        tower_2 = self.home("carlos").tower
        items = (
            ("mantenimiento", "La piscina cierra los lunes por mantenimiento",
             "Todos los lunes la piscina está cerrada por mantenimiento. Si el lunes es festivo, el "
             "mantenimiento pasa al martes.", None, None, None, -6),
            ("urgente", "Corte de agua el jueves en la mañana",
             "El jueves de 8:00 a. m. a 12:00 m. no habrá agua en las torres por el lavado de los tanques. "
             "Guarda agua desde el miércoles.", None, self.today + timedelta(days=4), None, -1),
            ("asamblea", "Asamblea ordinaria de propietarios",
             "La asamblea es en el salón social. Si no puedes ir, puedes darle un poder a otra persona.",
             None, self.today + timedelta(days=12), (self.today + timedelta(days=12)).isoformat(), -3),
            ("seguridad", f"{tower_2.name}: nueva clave de la puerta del sótano",
             f"Desde hoy la puerta del sótano de la {tower_2.name} tiene clave nueva. Pídela en portería "
             "con tu documento.", tower_2, None, None, 0),
            ("zonas_comunes", "Cómo reservar el salón social",
             "El salón social se reserva desde la app, con anticipación. Revisa las reglas de la zona antes "
             "de reservar.", None, None, None, -10),
            # Ya vencido: sale en «Archivados» (HU-060).
            ("mantenimiento", "Fumigación de las zonas comunes",
             "El sábado se fumigan las zonas comunes. No dejes a tus mascotas en las zonas verdes.",
             None, self.today - timedelta(days=5), None, -15),
        )
        created = {}
        for category, title, message, tower, expires_at, event_date, days in items:
            if Announcement.query.filter_by(title=title).first() is not None:
                continue
            announcement = Announcement(
                title=title, message=message, category=category, tower=tower, expires_at=expires_at,
                event_date=event_date, event_time="19:00" if event_date else None,
                author_id=self.admin.id, created_at=self.at(days=days),
            )
            db.session.add(announcement)
            created[title] = announcement
        db.session.flush()
        # Algunas lecturas, para que el conteo de quién leyó no salga en cero (HU-059).
        readers = {
            items[0][1]: ("maria@domux.com", "jorge@domux.com"),
            items[1][1]: ("natalia@domux.com",),
            items[3][1]: ("diana@domux.com",),
        }
        for title, emails in readers.items():
            if title not in created:
                continue
            for email in emails:
                reader = self.user(email)
                if reader is not None:
                    db.session.add(AnnouncementRead(
                        announcement_id=created[title].id, user_id=reader.id,
                        apartment_id=reader.apartment_id, read_at=self.at(hours=-2),
                    ))

    def add_pqrs(self):
        resident = self.user
        items = (
            # (quién, tipo, asunto, mensaje, estado, radicada hace (días hábiles), por la administración)
            ("jorge@domux.com", "Petición", "Certificado de residencia",
             "Necesito un certificado de residencia para el colegio de mi hija.", "abierta", 0, False),
            ("diana@domux.com", "Queja", "Ruido en el apartamento de arriba",
             "Desde hace una semana hay ruido después de las 11:00 p. m.", "abierta", 11, False),
            ("natalia@domux.com", "Reclamo", "El ascensor se detiene entre pisos",
             "El ascensor se quedó quieto entre el piso 1 y el 2 con nosotros adentro.", "en_proceso", 20, False),
            ("gloria@domux.com", "Sugerencia", "Más bancas en la zona verde",
             "Sería bueno tener más bancas cerca del parque para descansar.", "resuelta", 6, False),
            ("gustavo@domux.com", "Daño", "Gotera en el techo del parqueadero",
             "Lo reportó por teléfono a la administración.", "abierta", 3, True),
        )
        for email, category, subject, message, status, days, by_admin in items:
            owner = resident(email)
            if owner is None or Pqrs.query.filter_by(resident_id=owner.id, subject=subject).first() is not None:
                continue
            created_at = self.on_day(self.business_days_ago(days), 10)
            pqrs = Pqrs(
                resident_id=owner.id, category=category, subject=subject, message=message, status=status,
                created_by_admin_id=self.admin.id if by_admin else None,
                created_at=created_at, updated_at=created_at,
            )
            if category == "Queja":
                pqrs.incident_date = (self.today - timedelta(days=1)).isoformat()
                pqrs.incident_time = "23:30"
            if status == "en_proceso":
                pqrs.conversation.extend([
                    PqrsMessage(author_id=self.admin.id, author_role="ADMIN", created_at=created_at + timedelta(days=1),
                                message="Ya llamamos a la empresa de mantenimiento: viene esta semana."),
                    PqrsMessage(author_id=owner.id, author_role="RESIDENT", created_at=created_at + timedelta(days=3),
                                message="Hoy volvió a pasar en la mañana."),
                ])
            if status == "resuelta":
                answer = "Gracias por la idea. El próximo mes se instalan dos bancas nuevas junto al parque."
                pqrs.admin_response = answer
                pqrs.updated_at = created_at + timedelta(days=2)
                pqrs.conversation.append(PqrsMessage(
                    author_id=self.admin.id, author_role="ADMIN", message=answer,
                    created_at=created_at + timedelta(days=2),
                ))
                pqrs.satisfaction_ratings.append(PqrsSatisfaction(
                    rating=5, comment="Muy amables, gracias.", created_at=created_at + timedelta(days=3),
                ))
            db.session.add(pqrs)
        db.session.flush()

    def add_reservations(self):
        areas = {area.name: area for area in CommonArea.query.all()}
        saturday = self.next_weekday(5, at_least=3)
        items = (
            # (zona, quién, día, franja: "dia" para el día completo o el número de franja, personas, estado)
            ("Salón social", "jorge@domux.com", saturday, "dia", 30, "aprobada"),
            ("Cancha múltiple", "tomas@domux.com", self.today + timedelta(days=1), 0, 10, "pendiente"),
            ("Zona BBQ", "natalia@domux.com", self.next_weekday(6, at_least=3), 0, 12, "rechazada"),
            ("Gimnasio", "gloria@domux.com", self.today + timedelta(days=3), 0, 2, "cancelada"),
            ("Piscina", "diana@domux.com", self.next_weekday(2, at_least=1), 0, 4, "aprobada"),
            # Una ya pasada, para el historial.
            ("Salón social", "maria@domux.com", saturday - timedelta(days=14), "dia", 25, "aprobada"),
        )
        for area_name, email, day, slot, attendees, status in items:
            area, owner = areas.get(area_name), self.user(email)
            if area is None or owner is None or not area.slots:
                continue
            time_slot = area.full_day_slot if slot == "dia" else area.slots[min(slot, len(area.slots) - 1)]
            if time_slot is None:
                continue
            if status in ("aprobada", "activa") and reservation_conflicts(area.id, day.isoformat(), time_slot):
                continue
            reservation = Reservation(
                resident_id=owner.id, common_area_id=area.id, date=day.isoformat(), time_slot=time_slot,
                attendees=attendees, status=status, created_at=self.at(days=-2),
            )
            if status == "rechazada":
                reservation.messages.append(ReservationMessage(
                    author_id=self.admin.id, author_role="ADMIN", created_at=self.at(days=-1),
                    message=f"Ese día la {area.name.lower()} está en mantenimiento. Puedes reservar otro día.",
                ))
            db.session.add(reservation)
        db.session.flush()

    # --- Portería -----------------------------------------------------------------------------

    def guards(self):
        main = self.user(BASE_GUARD_EMAIL) or self.user(NEW_GUARDS[0]["email"])
        second = self.user(NEW_GUARDS[0]["email"]) or main
        return main, second

    def add_packages(self):
        main, second = self.guards()
        items = (
            # (para quién, descripción, transportadora, guía, estado, llegó hace (horas))
            ("jorge@domux.com", "Caja de Amazon", "Servientrega", "SRV-440128", "pendiente", 2),
            ("natalia@domux.com", "Caja de Mercado Libre", "Coordinadora", "COO-781245", "pendiente", 50),
            ("gustavo@domux.com", "Sobre de documentos", "Interrapidísimo", "INT-330981", "pendiente", 80),
            ("diana@domux.com", "Pedido del supermercado", None, None, "por_llegar", None),
            ("tomas@domux.com", "Audífonos", "Envía", "ENV-112233", "entregado", 30),
        )
        for email, description, carrier, tracking, status, hours in items:
            owner = self.user(email)
            if owner is None or PackageItem.query.filter_by(resident_id=owner.id, description=description).first():
                continue
            arrived = self.at(hours=-hours) if hours is not None else None
            package = PackageItem(
                resident_id=owner.id, registered_by=second.id if hours and hours > 24 else main.id,
                description=description, carrier=carrier, tracking_number=tracking, status=status,
                created_at=arrived or self.at(hours=-1), arrived_at=arrived,
            )
            if status == "entregado":
                package.delivered_at = arrived + timedelta(hours=8)
                package.delivered_to = owner.full_name
                package.delivered_by_id = main.id
            db.session.add(package)
        db.session.flush()

    def add_visits(self):
        main, second = self.guards()
        jorge, natalia, diana = self.user("jorge@domux.com"), self.user("natalia@domux.com"), self.user("diana@domux.com")
        gustavo, gloria = self.user("gustavo@domux.com"), self.user("gloria@domux.com")
        if Visit.query.filter_by(visitor_name="Ana María Vélez").first() is not None:
            return

        # A pie y adentro: autorizada por llamada hace una hora (HU-030 y HU-031).
        self._visit(jorge, main, "Ana María Vélez", "9990002001", "visitante", "llamada",
                    asked=self.at(minutes=-70), entered=self.at(minutes=-60), stay=120)
        # En carro y adentro, en un parqueadero de visitantes (HU-035 a HU-037).
        car_visit = self._visit(natalia, second, "Pedro Gómez", "9990002002", "visitante", "app",
                                asked=self.at(hours=-3, minutes=-10), entered=self.at(hours=-3), stay=240)
        spot = ParkingSpot.query.filter_by(
            code=VISITOR_CAR_SPOT, kind="visitante", occupied=False, retired_at=None
        ).first()
        # Una placa no puede tener dos entradas abiertas (RN-013): si ya está adentro, no se agrega otra.
        if VisitorVehicleEntry.query.filter_by(plate="VIS123", exited_at=None).first() is None:
            if spot is not None:
                spot.occupied = True
            db.session.add(VisitorVehicleEntry(
                plate="VIS123", visit=car_visit, apartment_id=natalia.apartment_id, spot=spot,
                entered_at=self.at(hours=-3), registered_by=second.id,
            ))
        # Esperando que el residente la autorice desde la app.
        waiting = self._visit(diana, main, "Domiciliario de Rappi", None, "domiciliario", None,
                              asked=self.at(minutes=-5), description="Pedido del restaurante")
        # Ya salieron: el historial de visitas.
        yesterday = self.today - timedelta(days=1)
        self._visit(gustavo, main, "Lucía Restrepo Patiño", "9990002004", "visitante", "app",
                    asked=self.on_day(yesterday, 14, 50), entered=self.on_day(yesterday, 15),
                    exited=self.on_day(yesterday, 18))
        self._visit(gloria, second, "Wilson Agudelo", "9990002005", "contratista", "llamada",
                    asked=self.on_day(yesterday - timedelta(days=1), 8, 55),
                    entered=self.on_day(yesterday - timedelta(days=1), 9),
                    exited=self.on_day(yesterday - timedelta(days=1), 11), description="Revisión del gas")

        # Códigos QR (HU-027): uno vigente, uno anulado y el de la empleada del hogar por 30 días.
        maria = self.user("maria@domux.com")
        passes = (
            (maria, 0, 2, 3, ["Rosa Gómez", "Luis Gómez"], False),
            (natalia, 0, 1, 1, ["Camilo Rendón"], True),
            (gustavo, 0, 29, 1, ["Rosa Elena Muñoz (empleada del hogar)"], False),
        )
        for owner, start, end, people, names, revoked in passes:
            if owner is None:
                continue
            qr_pass = VisitQrPass(
                resident_id=owner.id, token=secrets.token_urlsafe(32),
                valid_from=(self.today + timedelta(days=start)).isoformat(),
                valid_until=(self.today + timedelta(days=end)).isoformat(),
                max_people=people, revoked=revoked, revoked_at=self.at(hours=-1) if revoked else None,
                created_at=self.at(hours=-6),
            )
            qr_pass.names = names
            db.session.add(qr_pass)
        db.session.flush()
        return waiting

    def _visit(self, resident, guard, name, document, visit_type, method, asked, entered=None, exited=None,
               stay=None, description=None):
        visit = Visit(
            resident_id=resident.id, registered_by=guard.id, visitor_name=name,
            visitor_document=document, document_refused=document is None, media_consent=document is not None,
            type=visit_type, description=description, expected_stay_minutes=stay,
            approval_status="aprobada" if method else "pendiente", authorization_method=method,
            entered_at=entered, exited_at=exited, created_at=asked,
        )
        visit.events.append(VisitEvent(event_type="solicitud", method="app", actor_id=guard.id, created_at=asked))
        if method:
            approver = resident.id if method == "app" else guard.id
            visit.events.append(VisitEvent(
                event_type="aprobada", method=method, actor_id=approver, created_at=asked + timedelta(minutes=5),
            ))
        if entered:
            visit.events.append(VisitEvent(event_type="entrada", method=method, actor_id=guard.id, created_at=entered))
        if exited:
            visit.events.append(VisitEvent(event_type="salida", method=method, actor_id=guard.id, created_at=exited))
        db.session.add(visit)
        return visit

    def add_vehicle_movements(self):
        main, _ = self.guards()
        yesterday = self.today - timedelta(days=1)
        moves = {
            # El carro de María está adentro; el de Gustavo salió hoy.
            "DMX101": (("entrada", self.on_day(yesterday - timedelta(days=1), 19)),
                       ("salida", self.on_day(yesterday, 7)), ("entrada", self.on_day(yesterday, 19, 30))),
            "DMX404": (("entrada", self.on_day(yesterday, 17)), ("salida", self.at(hours=-3))),
        }
        for plate, events in moves.items():
            vehicle = Vehicle.query.filter_by(plate=plate, retired_at=None).first()
            if vehicle is None or VehicleMovement.query.filter_by(vehicle_id=vehicle.id).first() is not None:
                continue
            for movement_type, moment in events:
                db.session.add(VehicleMovement(
                    vehicle_id=vehicle.id, plate=plate, movement_type=movement_type,
                    registered_by=main.id, created_at=moment,
                ))

    def add_notifications(self, waiting_visit):
        saturday = self.next_weekday(5, at_least=3)
        items = (
            ("jorge@domux.com", "Paquete en portería", "Te llegó una caja de Amazon. Recógela en portería.",
             "package", False, -2),
            ("jorge@domux.com", "Reserva aprobada",
             f"Tu reserva del salón social para el {saturday.strftime('%d/%m/%Y')} fue aprobada.",
             "reservation", False, -20),
            ("jorge@domux.com", "Visitante ingresó", "Ana María Vélez ingresó a la unidad.", "visit", True, -1),
            ("natalia@domux.com", "Tu paquete sigue en portería",
             "Tu caja de Mercado Libre lleva más de 48 horas en portería.", "package", False, -2),
            ("natalia@domux.com", "Reserva rechazada",
             "Tu reserva de la zona BBQ no fue aprobada. Revisa el mensaje de la administración.",
             "reservation", False, -24),
            ("gloria@domux.com", "Tu PQRS fue respondida",
             "La administración respondió tu sugerencia «Más bancas en la zona verde».", "pqrs", True, -48),
            ("gustavo@domux.com", "Tu paquete sigue en portería",
             "Tu sobre de documentos lleva más de 72 horas en portería.", "package", False, -8),
        )
        for email, title, message, kind, read, hours in items:
            owner = self.user(email)
            if owner is not None:
                db.session.add(Notification(
                    user_id=owner.id, title=title, message=message, type=kind, is_read=read,
                    created_at=self.at(hours=hours),
                ))
        if waiting_visit is not None:
            db.session.add(Notification(
                user_id=waiting_visit.resident_id, title="Visitante esperando autorización",
                message=f"{waiting_visit.visitor_name} está en portería para ingresar.", type="visit",
                is_read=False, created_at=waiting_visit.created_at,
            ))

    # --- Todo junto ---------------------------------------------------------------------------

    def build(self):
        """Agrega todo y devuelve los correos de las cuentas que se crearon.

        Si otro arranque los agregó al mismo tiempo, un correo o un código repetido detiene todo y
        add_demo_data deshace lo de esta llamada.
        """
        self.add_structure()
        self.add_accounts()
        self.add_households()
        self.add_announcements()
        self.add_pqrs()
        self.add_reservations()
        self.add_packages()
        waiting = self.add_visits()
        self.add_vehicle_movements()
        self.add_notifications(waiting)
        return self.created


def demo_account_vars():
    """Todas las cuentas de prueba (las de la semilla y las de aquí) con la variable de su contraseña."""
    return {**DEMO_PASSWORD_VARS, **NEW_ACCOUNT_VARS}
