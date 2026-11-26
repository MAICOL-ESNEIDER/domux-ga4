"""Actividad inventada para mostrar DOMUX funcionando en la exposición (solo agrega, nunca borra).

Se suma a las cuentas y los datos de ``demo_data.py``: comunicados, PQRS, reservas, paquetes, visitas
y vehículos de una unidad residencial imaginaria, con fotos, videos, audios y PDF también inventados
(``expo_media/``; se crean con ``scripts/crear_medios_expo.py``, sin bajar nada de internet). Todos los
nombres, placas y documentos son ficticios.

Se carga una sola vez cuando se pide con ``DOMUX_EXPO_ACCION=cargar``; queda una marca en el registro
de auditoría y con ella no se repite.
"""

import base64
import json
import logging
from datetime import timedelta
from pathlib import Path

from demo_data import _DemoBuilder
from extensions import db
from models import (
    Announcement,
    AnnouncementRead,
    AuditLog,
    CommonArea,
    Notification,
    PackageItem,
    ParkingSpot,
    Pqrs,
    PqrsMessage,
    PqrsSatisfaction,
    Reservation,
    ReservationMessage,
    User,
    Vehicle,
    VehicleMovement,
    Visit,
    VisitorVehicleEntry,
)
from services.media import sniff_media, is_pdf
from services.reservation_service import reservation_conflicts

logger = logging.getLogger(__name__)

EXPO_DATA_VERSION = 1
MARKER_ENTITY = "datos_expo"
MARKER_ACTION = "datos_expo_agregados"
MEDIA_DIR = Path(__file__).parent / "expo_media"

_cache = {}


def media(name):
    """(texto «data:…;base64,…», clase) de un archivo de ``expo_media/``. Sin el archivo devuelve (None, None)."""
    if name is None:
        return None, None
    if name not in _cache:
        path = MEDIA_DIR / name
        if not path.exists():
            logger.warning("[EXPO] Falta el archivo %s.", name)
            _cache[name] = (None, None)
        else:
            raw = path.read_bytes()
            if is_pdf(raw):
                mime, kind = "application/pdf", "document"
            else:
                sniffed = sniff_media(raw)
                mime, kind = sniffed if sniffed else (None, None)
            encoded = base64.b64encode(raw).decode("ascii")
            _cache[name] = (f"data:{mime};base64,{encoded}", kind) if mime else (None, None)
    return _cache[name]


def already_loaded():
    for marker in AuditLog.query.filter_by(entity_type=MARKER_ENTITY, action=MARKER_ACTION).all():
        try:
            if json.loads(marker.details or "{}").get("version", 0) >= EXPO_DATA_VERSION:
                return True
        except (TypeError, ValueError, AttributeError):
            continue
    return False


class _ExpoBuilder(_DemoBuilder):
    def __init__(self, admin):
        super().__init__(admin, {})

    # --- Comunicados --------------------------------------------------------------------------

    def add_announcements(self):
        tower_2 = self.home("carlos").tower
        items = (
            # (categoría, título, mensaje, torre, vence en (días), evento en (días), archivo, descargable, hace (días))
            ("mantenimiento", "Jornada de fumigación este sábado",
             "El sábado desde las 7:00 a. m. se fumigan las zonas comunes de todas las torres. Cierra las ventanas "
             "de los pasillos y no dejes a tus mascotas en las zonas verdes hasta el mediodía.",
             None, 6, None, "aviso-fumigacion.jpg", True, -1),
            ("mantenimiento", "Ascensor de la Torre 2 en mantenimiento",
             "El ascensor de la Torre 2 estará fuera de servicio por mantenimiento mientras el técnico cambia el "
             "motor. Usa las escaleras o el ascensor de la Torre 1. Gracias por tu paciencia.",
             tower_2, 3, None, "ascensor-fuera-de-servicio.jpg", False, -2),
            ("zonas_comunes", "Puntos de reciclaje: cómo separar",
             "Verde para orgánicos, azul para papel, cartón, plástico y vidrio, gris para lo demás. Si separas bien, "
             "el conjunto paga menos por el aseo. Mira la foto del punto de reciclaje del bloque B.",
             None, None, None, "punto-reciclaje.jpg", True, -8),
            ("zonas_comunes", "La piscina estrena revisión semanal",
             "Cada semana revisamos la calidad del agua y los equipos. Mira el video de cómo se hace la revisión.",
             None, None, None, "video-piscina.mp4", False, -5),
            ("asamblea", "Acta del último consejo de administración",
             "Publicamos el acta del último consejo con las decisiones sobre los ascensores y los horarios.",
             None, None, None, "acta-reunion-consejo.pdf", True, -9),
            ("zonas_comunes", "Reglas para usar el salón comunal",
             "Antes de reservar el salón comunal lee las reglas en el PDF: aforo, horarios, música y entrega.",
             None, None, None, "manual-uso-salon-comunal.pdf", True, -12),
            ("seguridad", "Simulacro de evacuación",
             "Haremos un simulacro de evacuación. Escucha la alarma del audio para reconocer la sirena. Al oírla, "
             "baja por las escaleras sin usar el ascensor y sigue las indicaciones de la portería.",
             None, 10, 9, "audio-sirena-alarma.m4a", False, -3),
            ("urgente", "Fuga de agua en el sótano 1: ya se repara",
             "Hubo una fuga de agua en el sótano 1. El plomero ya está reparando. Mueve tu carro si está cerca de la "
             "zona de la foto.", None, 2, None, "fuga-agua-sotano.jpg", False, 0),
            # Ya vencido: aparece en «Archivados».
            ("mantenimiento", "Lavado de tanques (ya pasó)",
             "El lavado de los tanques de agua ya terminó. Gracias por guardar agua.", None, -4, None, None, False, -14),
        )
        created = []
        for category, title, message, tower, expires, event, file_name, downloadable, days in items:
            if Announcement.query.filter_by(title=title).first() is not None:
                continue
            url, kind = media(file_name)
            announcement = Announcement(
                title=title, message=message, category=category, tower=tower,
                expires_at=(self.today + timedelta(days=expires)) if expires is not None else None,
                event_date=(self.today + timedelta(days=event)).isoformat() if event is not None else None,
                event_time="19:00" if event is not None else None,
                media_url=url, media_type=kind, media_downloadable=bool(url) and downloadable,
                author_id=self.admin.id, created_at=self.at(days=days),
            )
            db.session.add(announcement)
            created.append(announcement)
        db.session.flush()
        readers = ("maria@domux.com", "jorge@domux.com", "diana@domux.com", "natalia@domux.com", "gloria@domux.com")
        for index, announcement in enumerate(created[:6]):
            for email in readers[: 1 + (index * 2) % 5]:
                reader = self.user(email)
                if reader is not None:
                    db.session.add(AnnouncementRead(
                        announcement_id=announcement.id, user_id=reader.id,
                        apartment_id=reader.apartment_id, read_at=self.at(hours=-3 - index),
                    ))

    # --- PQRS ---------------------------------------------------------------------------------

    def add_pqrs(self):
        yesterday = (self.today - timedelta(days=1)).isoformat()
        items = (
            # (quién, tipo, asunto, mensaje, estado, días hábiles desde la radicación, suceso, archivo, descargable)
            ("jorge@domux.com", "Daño", "Fuga de agua en el sótano 1",
             "Hay agua cayendo del techo junto a mi parqueadero. Adjunto la foto y un video corto.",
             "en_proceso", 2, (yesterday, "07:45"), "fuga-agua-sotano.jpg", True),
            ("diana@domux.com", "Queja", "Lámpara apagada en el piso 4",
             "Hace tres noches la lámpara del pasillo del piso 4 no enciende y se pone oscuro.",
             "abierta", 1, (yesterday, "20:15"), "lampara-pasillo.jpg", True),
            ("natalia@domux.com", "Reclamo", "Carro ocupando dos parqueaderos",
             "Un carro rojo lleva dos días ocupando dos espacios y no puedo parquear el mío.",
             "resuelta", 6, ((self.today - timedelta(days=8)).isoformat(), "18:30"), "carro-mal-parqueado.jpg", True),
            ("gloria@domux.com", "Queja", "Ruido en la noche",
             "Grabé el ruido que viene del apartamento de arriba pasadas las once de la noche.",
             "abierta", 12, ((self.today - timedelta(days=15)).isoformat(), "23:20"), "audio-ruido-vecino.m4a", False),
            ("gustavo@domux.com", "Petición", "Certificado de paz y salvo",
             "Necesito el paz y salvo del apartamento para un trámite del banco. Adjunto el soporte de pago.",
             "resuelta", 4, None, "soporte-pago-parqueadero.pdf", False),
            ("maria@domux.com", "Sugerencia", "Más puntos de reciclaje",
             "Sería bueno poner un punto de reciclaje también en la Torre 1.",
             "resuelta", 9, None, "punto-reciclaje.jpg", True),
            ("carlos@domux.com", "Reclamo", "Cobro del parqueadero de visitantes",
             "Me cobraron dos noches de parqueadero de visitantes y mi invitado solo se quedó una. Adjunto el soporte.",
             "en_proceso", 5, ((self.today - timedelta(days=5)).isoformat(), "10:00"), "soporte-pago-parqueadero.pdf", False),
            ("tomas@domux.com", "Petición", "Permiso para una reunión pequeña",
             "Quisiera saber si puedo usar la zona BBQ para el cumpleaños de mi mamá.",
             "abierta", 0, None, None, False),
        )
        for email, category, subject, message, status, days, event, file_name, downloadable in items:
            owner = self.user(email)
            if owner is None or Pqrs.query.filter_by(resident_id=owner.id, subject=subject).first() is not None:
                continue
            created_at = self.on_day(self.business_days_ago(days), 9, 30)
            url, kind = media(file_name)
            pqrs = Pqrs(
                resident_id=owner.id, category=category, subject=subject, message=message, status=status,
                incident_date=event[0] if event else None, incident_time=event[1] if event else None,
                media_url=url, media_type=kind, media_downloadable=bool(url) and downloadable,
                created_at=created_at, updated_at=created_at,
            )
            pqrs.conversation.append(PqrsMessage(
                author_id=owner.id, author_role="RESIDENT", message=message, media_url=url, media_type=kind,
                media_downloadable=bool(url) and downloadable, created_at=created_at,
            ))
            if status in ("en_proceso", "resuelta"):
                answer = {
                    "Fuga de agua en el sótano 1": "Ya llegó el plomero. Está cambiando el tubo; mañana queda listo.",
                    "Carro ocupando dos parqueaderos": "Hablamos con el propietario y ya movió el carro. Gracias por avisar.",
                    "Certificado de paz y salvo": "Ya está al día. Pasa por la administración o descárgalo desde el correo.",
                    "Más puntos de reciclaje": "Buena idea. Instalamos un punto nuevo junto a la entrada de la Torre 1.",
                    "Cobro del parqueadero de visitantes": "Revisamos el registro de portería y corregiremos el cobro.",
                }.get(subject, "Recibimos tu solicitud y la estamos revisando.")
                video, video_kind = (media("video-fuga-agua.mp4") if "Fuga" in subject else (None, None))
                pqrs.conversation.append(PqrsMessage(
                    author_id=self.admin.id, author_role="ADMIN", message=answer, media_url=video,
                    media_type=video_kind, media_downloadable=False, created_at=created_at + timedelta(days=1),
                ))
                pqrs.admin_response = answer
                pqrs.updated_at = created_at + timedelta(days=1)
            if status == "resuelta":
                pqrs.satisfaction_ratings.append(PqrsSatisfaction(
                    rating=5 if "reciclaje" in subject else 4, comment="Gracias por la respuesta.",
                    created_at=created_at + timedelta(days=2),
                ))
            db.session.add(pqrs)
        db.session.flush()

    # --- Reservas -----------------------------------------------------------------------------

    def add_reservations(self):
        areas = {area.name: area for area in CommonArea.query.all()}
        items = (
            # (zona, quién, en cuántos días, franja ("dia" o número), personas, estado, mensaje de la administración)
            ("Salón social", "natalia@domux.com", 11, "dia", 40, "aprobada", None),
            ("Salón social", "jorge@domux.com", 18, "dia", 25, "pendiente", None),
            ("Zona BBQ", "diana@domux.com", 5, 0, 10, "aprobada", None),
            ("Zona BBQ", "gloria@domux.com", 6, 0, 8, "rechazada",
             "Ese día la zona BBQ tiene mantenimiento de la chimenea. Puedes reservar otro día."),
            ("Cancha múltiple", "tomas@domux.com", 2, 1, 12, "aprobada", None),
            ("Gimnasio", "maria@domux.com", 1, 2, 3, "aprobada", None),
            ("Piscina", "carlos@domux.com", 3, 1, 5, "pendiente", None),
            ("Cancha múltiple", "gustavo@domux.com", 4, 0, 6, "cancelada", None),
            ("Salón social", "jorge@domux.com", -20, "dia", 30, "aprobada", None),
        )
        for area_name, email, offset, slot, attendees, status, note in items:
            area, owner = areas.get(area_name), self.user(email)
            if area is None or owner is None or not area.slots:
                continue
            day = self.today + timedelta(days=offset)
            time_slot = area.full_day_slot if slot == "dia" else area.slots[min(slot, len(area.slots) - 1)]
            if time_slot is None:
                continue
            if Reservation.query.filter_by(
                resident_id=owner.id, common_area_id=area.id, date=day.isoformat(), time_slot=time_slot
            ).first() is not None:
                continue
            if status in ("aprobada", "activa") and reservation_conflicts(area.id, day.isoformat(), time_slot):
                continue
            reservation = Reservation(
                resident_id=owner.id, common_area_id=area.id, date=day.isoformat(), time_slot=time_slot,
                attendees=attendees, status=status, created_at=self.at(days=-3),
            )
            if note:
                reservation.messages.append(ReservationMessage(
                    author_id=self.admin.id, author_role="ADMIN", message=note, created_at=self.at(days=-1),
                ))
            db.session.add(reservation)
        db.session.flush()

    # --- Portería -----------------------------------------------------------------------------

    def add_packages(self):
        main, second = self.guards()
        photo, photo_kind = media("paquetes-porteria.jpg")
        items = (
            ("maria@domux.com", "Caja grande de Falabella", "Servientrega", "SRV-558210", "pendiente", 5, True),
            ("carlos@domux.com", "Sobre con documentos del banco", "Interrapidísimo", "INT-902144", "pendiente", 26, False),
            ("diana@domux.com", "Paquete de Rappi Aliados", "Coordinadora", "COO-337019", "pendiente", 52, True),
            ("hernan@domux.com", "Caja de repuestos", "Envía", "ENV-771203", "pendiente", 76, False),
            ("jorge@domux.com", "Zapatos deportivos", "Deprisa", "DEP-120045", "por_llegar", None, False),
            ("gloria@domux.com", "Medicamentos de la droguería", None, None, "por_llegar", None, False),
            ("natalia@domux.com", "Libros de la editorial", "Servientrega", "SRV-558990", "entregado", 20, True),
            ("tomas@domux.com", "Teclado inalámbrico", "Coordinadora", "COO-337455", "entregado", 44, False),
        )
        for email, description, carrier, tracking, status, hours, with_photo in items:
            owner = self.user(email)
            if owner is None or PackageItem.query.filter_by(resident_id=owner.id, description=description).first():
                continue
            arrived = self.at(hours=-hours) if hours is not None else None
            package = PackageItem(
                resident_id=owner.id, registered_by=second.id if (hours or 0) > 24 else main.id,
                description=description, carrier=carrier, tracking_number=tracking, status=status,
                media_url=photo if with_photo else None, media_type=photo_kind if with_photo else None,
                created_at=arrived or self.at(hours=-1), arrived_at=arrived,
            )
            if status == "entregado":
                package.delivered_at = arrived + timedelta(hours=6)
                package.delivered_to = owner.full_name
                package.delivered_by_id = main.id
            db.session.add(package)
        db.session.flush()

    def add_visits(self):
        main, second = self.guards()
        day = self.today
        history = (
            # (residente, guardia, nombre, documento, tipo, medio, días atrás, hora de entrada, horas adentro, nota)
            ("maria@domux.com", main, "Sofía Londoño Mejía", "9990003001", "visitante", "app", 1, 16, 3, None),
            ("jorge@domux.com", second, "Mauricio Sierra Ruiz", "9990003002", "visitante", "llamada", 1, 11, 2, None),
            ("diana@domux.com", main, "Servicio Técnico Redes del Norte", "9990003003", "contratista", "app", 2, 9, 3, "Revisión del internet"),
            ("natalia@domux.com", second, "Laura Cárdenas Pérez", "9990003004", "visitante", "app", 2, 19, 4, None),
            ("gustavo@domux.com", main, "Dr. Ricardo Toro (médico)", "9990003005", "visitante", "llamada", 3, 10, 1, "Control médico a domicilio"),
            ("gloria@domux.com", second, "Plomería Express S. A. S.", "9990003006", "contratista", "llamada", 3, 14, 2, "Cambio de llave del lavamanos"),
            ("hernan@domux.com", main, "Camila Ospina", "9990003007", "visitante", "app", 4, 18, 5, None),
            ("carlos@domux.com", second, "Domiciliario de Domicilios.com", None, "domiciliario", "app", 4, 20, 0, "Pedido de comida"),
            ("tomas@domux.com", main, "Equipo de fútbol amigos de Tomás", "9990003009", "visitante", "app", 5, 15, 3, None),
            ("maria@domux.com", second, "Empresa de aseo Brillo Hogar", "9990003010", "contratista", "llamada", 6, 8, 4, "Aseo profundo"),
        )
        for email, guard, name, document, visit_type, method, days, hour, hours_in, note in history:
            resident = self.user(email)
            if resident is None or Visit.query.filter_by(visitor_name=name).first() is not None:
                continue
            visit_day = day - timedelta(days=days)
            entered = self.on_day(visit_day, hour)
            self._visit(
                resident, guard, name, document, visit_type, method,
                asked=entered - timedelta(minutes=8), entered=entered,
                exited=entered + timedelta(hours=hours_in) if hours_in else entered + timedelta(minutes=10),
                description=note,
            )
        # Un visitante que está adentro ahora y llegó en carro al parqueadero de visitantes.
        resident = self.user("diana@domux.com")
        name = "Federico Zuluaga Bernal"
        if resident is not None and Visit.query.filter_by(visitor_name=name).first() is None:
            arrived = self.at(minutes=-95)
            visit = self._visit(resident, main, name, "9990003011", "visitante", "app", asked=arrived - timedelta(minutes=5),
                                entered=arrived, stay=180)
            spot = ParkingSpot.query.filter_by(kind="visitante", occupied=False, retired_at=None).order_by(ParkingSpot.id).first()
            if spot is not None and VisitorVehicleEntry.query.filter_by(plate="EXP481", exited_at=None).first() is None:
                spot.occupied = True
                db.session.add(VisitorVehicleEntry(
                    plate="EXP481", visit=visit, apartment_id=resident.apartment_id, spot=spot,
                    entered_at=arrived, registered_by=main.id,
                ))
        # Vehículos de visitantes que ya salieron (historial de la portería).
        past = Visit.query.filter(Visit.visitor_name.in_(("Sofía Londoño Mejía", "Laura Cárdenas Pérez", "Camila Ospina"))).all()
        for index, visit in enumerate(past):
            plate = f"EXP{200 + index}"
            if visit.entered_at is None or VisitorVehicleEntry.query.filter_by(plate=plate).first() is not None:
                continue
            db.session.add(VisitorVehicleEntry(
                plate=plate, visit=visit, apartment_id=visit.resident.apartment_id, spot=None,
                entered_at=visit.entered_at, exited_at=visit.exited_at, registered_by=main.id,
            ))
        db.session.flush()

    def add_vehicle_movements(self):
        main, second = self.guards()
        vehicle = Vehicle.query.filter_by(plate="DMX303", retired_at=None).first()
        if vehicle is None or VehicleMovement.query.filter_by(vehicle_id=vehicle.id).first() is not None:
            return
        for days, hour, kind, guard in ((2, 7, "salida", main), (2, 19, "entrada", second), (1, 7, "salida", main), (1, 18, "entrada", main)):
            db.session.add(VehicleMovement(
                vehicle_id=vehicle.id, plate=vehicle.plate, movement_type=kind, registered_by=guard.id,
                created_at=self.on_day(self.today - timedelta(days=days), hour, 15),
            ))

    def add_notifications(self, _waiting=None):
        items = (
            ("maria@domux.com", "Paquete en portería", "Te llegó una caja grande de Falabella. Recógela en portería.", "package", False, -5),
            ("maria@domux.com", "Nuevo comunicado", "Jornada de fumigación este sábado.", "announcement", False, -24),
            ("jorge@domux.com", "Tu PQRS tiene respuesta", "La administración respondió «Fuga de agua en el sótano 1».", "pqrs", False, -20),
            ("natalia@domux.com", "Reserva aprobada", "Tu reserva del salón social fue aprobada.", "reservation", True, -48),
            ("diana@domux.com", "Visitante ingresó", "Federico Zuluaga Bernal ingresó a la unidad.", "visit", False, -2),
            ("carlos@domux.com", "Tu PQRS está en trámite", "Estamos revisando el cobro del parqueadero de visitantes.", "pqrs", False, -30),
        )
        for email, title, message, kind, read, hours in items:
            owner = self.user(email)
            if owner is not None and Notification.query.filter_by(user_id=owner.id, title=title, message=message).first() is None:
                db.session.add(Notification(user_id=owner.id, title=title, message=message, type=kind,
                                            is_read=read, created_at=self.at(hours=hours)))

    def build(self):
        self.add_announcements()
        self.add_pqrs()
        self.add_reservations()
        self.add_packages()
        self.add_visits()
        self.add_vehicle_movements()
        self.add_notifications()


def add_expo_activity():
    """Agrega la actividad de la exposición si falta. Devuelve True si la agregó en esta llamada."""
    if already_loaded():
        return False
    admin = User.query.filter_by(email="admin@domux.com", role="ADMIN").first()
    if admin is None or User.query.filter_by(email="jorge@domux.com").first() is None:
        logger.warning("[EXPO] No se cargó la actividad: faltan las cuentas de prueba de DOMUX.")
        return False
    try:
        _ExpoBuilder(admin).build()
        db.session.add(AuditLog(
            entity_type=MARKER_ENTITY, action=MARKER_ACTION, actor_role="SISTEMA",
            details=json.dumps({"version": EXPO_DATA_VERSION}),
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("[EXPO] No se pudo cargar la actividad; la base quedó como estaba.")
        return False
    logger.warning("[EXPO] Actividad de la exposición cargada.")
    return True
