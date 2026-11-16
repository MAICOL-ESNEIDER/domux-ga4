"""Lo que arma la zona «Descargas» de la web: qué registros salen, de qué fechas y de dónde.

El administrador elige los tipos (PQRS, reservas, visitas…), las fechas y, si quiere, un apartamento.
Los registros se buscan en dos sitios y salen juntos, sin que la persona tenga que saber dónde están:

* la base de datos, con lo que sigue en las listas; y
* el archivo histórico (ADR-013), con lo que ya cumplió su plazo y está comprimido. Se lee tal
  cual, sin volver a cargarlo en la base.

Las fotos y demás adjuntos no van en el Excel: solo los datos.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from extensions import db
from models import (
    Announcement,
    Apartment,
    CommonArea,
    HistoryArchive,
    PackageItem,
    Pqrs,
    Reservation,
    User,
    Visit,
    VisitorVehicleEntry,
)
from services import history_archive_service as archive_service
from time_utils import colombia_day_to_utc, colombia_today, to_colombia
from web import texts

#: Columnas pesadas (fotos y archivos) que no hacen falta para el Excel y no se leen de la base.
HEAVY_COLUMNS = frozenset({"media_url", "visitor_photo_url"})

IN_DATABASE = "Base de datos"
IN_ARCHIVE = "Archivo histórico"

ROLE_TEXTS = {"ADMIN": "Administración", "GUARD": "Portería", "RESIDENT": "Residente"}
OCCUPANCY_TEXTS = {"propietario": "Propietario", "arrendatario": "Arrendatario", "residente": "Residente"}

#: Los periodos que se eligen con un toque; «fechas» usa las dos fechas escritas.
PERIODS = (
    ("mes", "Este mes"),
    ("mes_pasado", "El mes pasado"),
    ("anio", "Este año"),
    ("todo", "Todo el tiempo"),
    ("fechas", "Elegir fechas"),
)


class Lookups:
    """Nombres que el Excel necesita y que los registros solo traen como número."""

    def __init__(self):
        self.users = {
            user.id: (user.full_name, user.apartment_id)
            for user in User.query.all()
        }
        self.apartments = {apartment.id: apartment.label for apartment in Apartment.query.all()}
        self.areas = {area.id: area.name for area in CommonArea.query.all()}

    def person(self, user_id):
        return self.users.get(user_id, ("", None))[0]

    def apartment_of(self, user_id):
        return self.users.get(user_id, ("", None))[1]

    def apartment(self, apartment_id):
        return self.apartments.get(apartment_id, "")

    def home(self, user_id):
        return self.apartment(self.apartment_of(user_id))


def _moment(value):
    """Una fecha guardada (en la base es fecha; en el archivo, texto) como fecha con hora, o None."""
    if isinstance(value, datetime) or value is None:
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _when(value):
    """Fecha y hora de Colombia como se escriben aquí: 13/11/2026 14:30."""
    moment = _moment(value)
    return to_colombia(moment).strftime("%d/%m/%Y %H:%M") if moment else ""


def _label(kind, value):
    return texts.badge_info(kind, value)["label"] if value else ""


def _yes(value):
    return "Sí" if value else "No"


@dataclass(frozen=True)
class DownloadType:
    key: str
    label: str
    model: type
    date_column: str
    #: Dónde está este tipo en el archivo histórico: (tipo de archivo, tabla dentro del archivo).
    archive_sources: tuple
    #: (encabezado, función(fila, nombres)) de cada columna.
    columns: tuple
    #: Función(fila, nombres) con el apartamento al que pertenece la fila, o None si no depende de uno.
    apartment: object = None


TYPES = (
    DownloadType(
        "pqrs", "PQRS", Pqrs, "created_at", (("pqrs", "pqrs"),),
        (
            ("Radicado", lambda row, names: row.get("radicado")),
            ("Radicada", lambda row, names: _when(row.get("created_at"))),
            ("Residente", lambda row, names: names.person(row.get("resident_id"))),
            ("Apartamento", lambda row, names: names.home(row.get("resident_id"))),
            ("Tipo", lambda row, names: row.get("category")),
            ("Asunto", lambda row, names: row.get("subject")),
            ("Mensaje", lambda row, names: row.get("message")),
            ("Estado", lambda row, names: _label("pqrs", row.get("status"))),
            ("Respuesta de la administración", lambda row, names: row.get("admin_response")),
            ("Fecha del hecho", lambda row, names: texts.date_es(row.get("incident_date"))),
            ("Última actualización", lambda row, names: _when(row.get("updated_at"))),
        ),
        lambda row, names: names.apartment_of(row.get("resident_id")),
    ),
    DownloadType(
        "reservas", "Reservas", Reservation, "created_at", (("reservas", "reservations"),),
        (
            ("Zona", lambda row, names: names.areas.get(row.get("common_area_id"), "")),
            ("Fecha de la reserva", lambda row, names: texts.date_es(row.get("date"))),
            ("Horario", lambda row, names: row.get("time_slot")),
            ("Residente", lambda row, names: names.person(row.get("resident_id"))),
            ("Apartamento", lambda row, names: names.home(row.get("resident_id"))),
            ("Asistentes", lambda row, names: row.get("attendees")),
            ("Estado", lambda row, names: _label("reservation", row.get("status"))),
            ("Pedida el", lambda row, names: _when(row.get("created_at"))),
        ),
        lambda row, names: names.apartment_of(row.get("resident_id")),
    ),
    DownloadType(
        "visitas", "Visitas", Visit, "created_at", (("visitas", "visits"),),
        (
            ("Registrada", lambda row, names: _when(row.get("created_at"))),
            ("Visitante", lambda row, names: row.get("visitor_name")),
            ("Documento", lambda row, names: (
                "No quiso darlo" if row.get("document_refused") else row.get("visitor_document")
            )),
            ("Tipo", lambda row, names: texts.VISIT_TYPES.get(row.get("type"), row.get("type"))),
            ("Residente", lambda row, names: names.person(row.get("resident_id"))),
            ("Apartamento", lambda row, names: names.home(row.get("resident_id"))),
            ("Autorización", lambda row, names: _label("visit", row.get("approval_status"))),
            ("Entró", lambda row, names: _when(row.get("entered_at"))),
            ("Salió", lambda row, names: _when(row.get("exited_at"))),
            ("Registró", lambda row, names: names.person(row.get("registered_by"))),
        ),
        lambda row, names: names.apartment_of(row.get("resident_id")),
    ),
    DownloadType(
        "paquetes", "Paquetes", PackageItem, "created_at", (("paquetes", "packages"),),
        (
            ("Llegó", lambda row, names: _when(row.get("arrived_at") or row.get("created_at"))),
            ("Residente", lambda row, names: names.person(row.get("resident_id"))),
            ("Apartamento", lambda row, names: names.home(row.get("resident_id"))),
            ("Descripción", lambda row, names: row.get("description")),
            ("Transportadora", lambda row, names: row.get("carrier")),
            ("Guía", lambda row, names: row.get("tracking_number")),
            ("Estado", lambda row, names: _label("package", row.get("status"))),
            ("Entregado el", lambda row, names: _when(row.get("delivered_at"))),
            ("Lo recibió", lambda row, names: row.get("delivered_to")),
            ("Archivado", lambda row, names: _yes(row.get("is_deleted"))),
        ),
        lambda row, names: names.apartment_of(row.get("resident_id")),
    ),
    DownloadType(
        "vehiculos", "Vehículos de visitantes", VisitorVehicleEntry, "entered_at",
        (("vehiculos-visitantes", "visitor_vehicle_entries"), ("visitas", "visitor_vehicle_entries")),
        (
            ("Placa", lambda row, names: row.get("plate")),
            ("Apartamento", lambda row, names: names.apartment(row.get("apartment_id"))),
            ("Entró", lambda row, names: _when(row.get("entered_at"))),
            ("Salió", lambda row, names: _when(row.get("exited_at"))),
            ("Registró", lambda row, names: names.person(row.get("registered_by"))),
        ),
        lambda row, names: row.get("apartment_id"),
    ),
    DownloadType(
        "comunicados", "Comunicados", Announcement, "created_at", (("comunicados", "announcements"),),
        (
            ("Publicado", lambda row, names: _when(row.get("created_at"))),
            ("Título", lambda row, names: row.get("title")),
            ("Mensaje", lambda row, names: row.get("message")),
            ("Categoría", lambda row, names: _label("announcement", row.get("category"))),
            ("Publicó", lambda row, names: names.person(row.get("author_id"))),
        ),
    ),
)
TYPES_BY_KEY = {kind.key: kind for kind in TYPES}

#: Los usuarios no tienen fechas ni archivo: sale la lista actual.
USERS_KEY = "usuarios"
USERS_LABEL = "Usuarios"
USER_HEADERS = ("Nombre", "Correo", "Teléfono", "Documento", "Rol", "Apartamento", "Ocupación", "Cuenta activa")

#: Lo que se puede marcar en la página, en orden: (clave, nombre).
CHOICES = tuple((kind.key, kind.label) for kind in TYPES) + ((USERS_KEY, USERS_LABEL),)


def period_range(period, since_text="", until_text="", today=None):
    """Las dos fechas (desde, hasta), las dos incluidas, del periodo elegido; None es «sin límite».

    Devuelve también el problema, si las fechas escritas no sirven.
    """
    today = today or colombia_today()
    if period == "mes":
        return today.replace(day=1), today, None
    if period == "mes_pasado":
        last = today.replace(day=1) - timedelta(days=1)
        return last.replace(day=1), last, None
    if period == "anio":
        return today.replace(month=1, day=1), today, None
    if period == "todo":
        return None, None, None
    try:
        since = date.fromisoformat(since_text) if since_text else None
        until = date.fromisoformat(until_text) if until_text else None
    except ValueError:
        return None, None, "Escribe las fechas completas, con día, mes y año."
    if since is None and until is None:
        return None, None, "Elige al menos una de las dos fechas, o usa «Todo el tiempo»."
    if since and until and since > until:
        return None, None, "La fecha «Desde» no puede ser posterior a «Hasta»."
    return since, until, None


def period_text(since, until):
    if since is None and until is None:
        return "Todo el tiempo"
    if since is None:
        return f"Hasta el {until.strftime('%d/%m/%Y')}"
    if until is None:
        return f"Desde el {since.strftime('%d/%m/%Y')}"
    return f"Del {since.strftime('%d/%m/%Y')} al {until.strftime('%d/%m/%Y')}"


def _bounds(since, until):
    """Los dos momentos en UTC entre los que debe estar la fecha del registro (el segundo, sin incluir)."""
    start = colombia_day_to_utc(since) if since else None
    end = colombia_day_to_utc(until + timedelta(days=1)) if until else None
    return start, end


def _database_rows(kind, start, end):
    table = kind.model.__table__
    columns = [column for column in table.columns if column.name not in HEAVY_COLUMNS]
    moment = table.c[kind.date_column]
    query = db.select(*columns)
    if start is not None:
        query = query.where(moment >= start)
    if end is not None:
        query = query.where(moment < end)
    return [dict(row) for row in db.session.execute(query.order_by(moment, table.c.id)).mappings()]


def _archive_rows(kind, start, end):
    """Las filas de este tipo que están en archivos históricos sin volver a cargar."""
    query = HistoryArchive.query.filter(
        HistoryArchive.kind.in_([source for source, _table in kind.archive_sources]),
        HistoryArchive.restored_at.is_(None),
    )
    # El mes del archivo acota la búsqueda; se deja un mes de margen por la diferencia de hora.
    if start is not None:
        query = query.filter(HistoryArchive.period >= (start - timedelta(days=31)).strftime("%Y-%m"))
    if end is not None:
        query = query.filter(HistoryArchive.period <= (end + timedelta(days=31)).strftime("%Y-%m"))
    tables = dict(kind.archive_sources)
    rows = []
    for archive in query.order_by(HistoryArchive.period, HistoryArchive.id):
        payload = archive_service.read_archive(archive_service.archive_content(archive))
        for row in payload.get("tables", {}).get(tables[archive.kind], []):
            moment = _moment(row.get(kind.date_column))
            if moment is None or (start is not None and moment < start) or (end is not None and moment >= end):
                continue
            rows.append(row)
    return rows


def collect(keys, since, until, apartment_id=None):
    """Arma las hojas del Excel. Devuelve una lista de diccionarios, uno por tipo elegido:

    ``{"key", "label", "headers", "rows", "count", "archived"}`` — ``archived`` es cuántas de las
    filas salieron del archivo histórico.
    """
    names = Lookups()
    start, end = _bounds(since, until)
    sheets = []
    for kind in TYPES:
        if kind.key not in keys:
            continue
        found = [(row, IN_DATABASE) for row in _database_rows(kind, start, end)]
        found += [(row, IN_ARCHIVE) for row in _archive_rows(kind, start, end)]
        if apartment_id and kind.apartment is not None:
            found = [item for item in found if kind.apartment(item[0], names) == apartment_id]
        found.sort(key=lambda item: (_moment(item[0].get(kind.date_column)) or datetime.min, item[0].get("id") or 0))
        rows = [
            [value(row, names) for _header, value in kind.columns] + [origin]
            for row, origin in found
        ]
        sheets.append({
            "key": kind.key,
            "label": kind.label,
            "headers": [header for header, _value in kind.columns] + ["Dónde está"],
            "rows": rows,
            "count": len(rows),
            "archived": sum(1 for _row, origin in found if origin == IN_ARCHIVE),
        })
    if USERS_KEY in keys:
        users = User.query.order_by(User.name, User.last_name, User.id).all()
        if apartment_id:
            users = [user for user in users if user.apartment_id == apartment_id]
        rows = [
            [
                user.full_name, user.email, user.phone, user.document_id, ROLE_TEXTS.get(user.role, user.role),
                user.apartment or "", OCCUPANCY_TEXTS.get(user.occupancy_type, "") if user.role == "RESIDENT" else "",
                _yes(user.is_active),
            ]
            for user in users
        ]
        sheets.append({
            "key": USERS_KEY, "label": USERS_LABEL, "headers": list(USER_HEADERS), "rows": rows,
            "count": len(rows), "archived": 0,
        })
    return sheets


def apartment_choices():
    """Los apartamentos vigentes para el filtro: (id, «Torre 1 · Apto 101»), en orden."""
    apartments = [apartment for apartment in Apartment.query.all() if not apartment.is_retired]
    return sorted(((apartment.id, apartment.label) for apartment in apartments), key=lambda item: item[1])
