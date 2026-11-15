"""Archivo histórico mensual y copia de respaldo (ADR-013, DEC-090 y DEC-103).

Nada se borra: cuando un registro cumple su plazo en la base de datos pasa a un archivo JSON
comprimido, por tipo y por mes, que se guarda en la tabla ``history_archives`` con su huella
SHA-256. El orden siempre es el mismo:

1. se arma el archivo con los registros del mes (y lo que cuelga de ellos: mensajes, eventos…);
2. se guarda y se vuelve a leer para comprobar la huella y que estén todos los registros;
3. solo entonces esos registros salen de sus tablas.

Si la comprobación falla no sale nada de la base. Un archivo se puede volver a cargar. Las
contraseñas, los PIN y los códigos de acceso no se archivan ni van en la copia de respaldo.

Plazos (DEC-090): visitas, códigos QR, vehículos, paquetes, reservas, PQRS y comunicados, 5 años;
notificaciones, 1 año. Los usuarios, el hogar y la estructura de la unidad no salen de la base.
"""

import base64
import gzip
import hashlib
import io
import json
import secrets
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import Date, DateTime, LargeBinary
from werkzeug.security import generate_password_hash

from extensions import db
from models import (
    Announcement,
    AnnouncementRead,
    HistoryArchive,
    LoginAttempt,
    Notification,
    PackageItem,
    PackagePickupCode,
    Pqrs,
    PqrsMessage,
    PqrsSatisfaction,
    Reservation,
    ReservationMessage,
    VehicleMovement,
    Visit,
    VisitEvent,
    VisitorVehicleEntry,
    VisitQrPass,
)
from services.audit_service import add_audit_log
from time_utils import utc_now

#: Versión del formato del archivo, por si cambia más adelante.
FORMAT_VERSION = 1
#: Registros principales por archivo: los meses con muchas fotos se parten para no llenar la memoria.
CHUNK_SIZE = 200
#: Días que se guarda una fila de intentos fallidos que ya no bloquea a nadie.
LOGIN_ATTEMPT_DAYS = 30

#: Columnas con secretos: no se archivan ni van en la copia de respaldo.
SECRET_COLUMNS = {
    "users": {"password_hash", "pin_hash"},
    "package_pickup_codes": {"token", "pin_hash"},
    "visit_qr_passes": {"token"},
}
#: Tablas que no van en la copia de respaldo: solo tienen secretos o ya son archivos.
BACKUP_SKIPPED_TABLES = {"login_attempts", "device_push_tokens", "history_archives", "alembic_version"}


class ArchiveError(Exception):
    """Algo impidió archivar o volver a cargar; el mensaje se le muestra al administrador."""


@dataclass(frozen=True)
class Kind:
    key: str
    label: str
    model: type
    years: int
    date_column: str = "created_at"
    #: Lo que cuelga de cada registro y se va con él: (modelo, columna que apunta al registro).
    children: tuple = ()


KINDS = (
    Kind("visitas", "Visitas", Visit, 5,
         children=((VisitEvent, "visit_id"), (VisitorVehicleEntry, "visit_id"))),
    Kind("vehiculos-visitantes", "Vehículos de visitantes", VisitorVehicleEntry, 5, date_column="entered_at"),
    Kind("qr", "Códigos QR de visita", VisitQrPass, 5),
    Kind("paquetes", "Paquetes", PackageItem, 5, children=((PackagePickupCode, "package_id"),)),
    Kind("reservas", "Reservas", Reservation, 5, children=((ReservationMessage, "reservation_id"),)),
    Kind("pqrs", "PQRS", Pqrs, 5, children=((PqrsMessage, "pqrs_id"), (PqrsSatisfaction, "pqrs_id"))),
    Kind("comunicados", "Comunicados", Announcement, 5, children=((AnnouncementRead, "announcement_id"),)),
    Kind("movimientos-vehiculos", "Entradas y salidas de vehículos", VehicleMovement, 5),
    Kind("notificaciones", "Notificaciones", Notification, 1),
)
KINDS_BY_KEY = {kind.key: kind for kind in KINDS}


def kind_label(key):
    kind = KINDS_BY_KEY.get(key)
    return kind.label if kind else key


def cutoff_for(kind, now=None):
    """Lo anterior a esta fecha ya cumplió su plazo: el primer día de este mes, hace ``years`` años.

    Así cada archivo trae un mes completo y un mes no se archiva a medias.
    """
    now = now or utc_now()
    return datetime(now.year - kind.years, now.month, 1)


def _pending_query(kind, now):
    model = kind.model
    column = getattr(model, kind.date_column)
    query = db.session.query(model.id, column).filter(column < cutoff_for(kind, now))
    if kind.key == "vehiculos-visitantes":
        # Los que entraron con una visita se van en el archivo de esa visita.
        query = query.filter(VisitorVehicleEntry.visit_id.is_(None))
    if kind.key == "qr":
        # Un código sale cuando ya no queda ninguna visita suya en la base.
        query = query.filter(~db.session.query(Visit.id).filter(Visit.qr_pass_id == VisitQrPass.id).exists())
    return query


def pending_summary(now=None):
    """Cuántos registros de cada tipo ya cumplieron su plazo y siguen en la base."""
    summary = []
    for kind in KINDS:
        count = _pending_query(kind, now).count()
        summary.append({"key": kind.key, "label": kind.label, "years": kind.years, "count": count})
    return summary


# --- Pasar filas a JSON y de vuelta -------------------------------------------------------------

def _plain(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (bytes, memoryview)):
        return base64.b64encode(bytes(value)).decode("ascii")
    return value


def _row_dict(table, row):
    hidden = SECRET_COLUMNS.get(table.name, ())
    return {
        column.name: _plain(row[column.name])
        for column in table.columns
        if column.name not in hidden
    }


def _table_rows(table, condition):
    result = db.session.execute(table.select().where(condition).order_by(table.c.id))
    return [_row_dict(table, row) for row in result.mappings()]


def _typed(column, value):
    if value is None:
        return None
    if isinstance(column.type, DateTime):
        return datetime.fromisoformat(value)
    if isinstance(column.type, Date):
        return date.fromisoformat(value)
    if isinstance(column.type, LargeBinary):
        return base64.b64decode(value)
    return value


def _compress(payload):
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    buffer = io.BytesIO()
    # mtime=0: el mismo contenido da siempre el mismo archivo y la misma huella.
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as handle:
        handle.write(raw)
    return buffer.getvalue()


def read_archive(content):
    """Abre un archivo comprimido y devuelve su contenido; falla si está dañado."""
    try:
        return json.loads(gzip.decompress(content).decode("utf-8"))
    except (OSError, EOFError, ValueError) as error:
        raise ArchiveError("El archivo está dañado y no se puede leer.") from error


# --- Archivar -------------------------------------------------------------------------------------

def _build_payload(kind, period, ids, now):
    table = kind.model.__table__
    tables = {table.name: _table_rows(table, table.c.id.in_(ids))}
    for child_model, fk in kind.children:
        child = child_model.__table__
        tables[child.name] = _table_rows(child, child.c[fk].in_(ids))
    return {
        "manifest": {
            "app": "DOMUX",
            "format": FORMAT_VERSION,
            "kind": kind.key,
            "label": kind.label,
            "period": period,
            "recordCount": len(tables[table.name]),
            "tables": {name: len(rows) for name, rows in tables.items()},
            "createdAt": now.isoformat(),
            "note": "Sin contraseñas, PIN ni códigos de acceso (DEC-090).",
        },
        "tables": tables,
    }


def _verify_saved(archive_id, kind, ids, sha256):
    """Vuelve a leer el archivo recién guardado: misma huella y todos los registros adentro."""
    stored = db.session.execute(
        db.select(HistoryArchive.content).where(HistoryArchive.id == archive_id)
    ).scalar_one()
    stored = bytes(stored)
    if hashlib.sha256(stored).hexdigest() != sha256:
        raise ArchiveError("El archivo guardado no coincide con su huella. No salió nada de la base.")
    payload = read_archive(stored)
    saved_ids = {row["id"] for row in payload["tables"].get(kind.model.__table__.name, [])}
    if saved_ids != set(ids):
        raise ArchiveError("Al archivo le faltan registros. No salió nada de la base.")


def _archive_chunk(kind, period, ids, actor, now):
    payload = _build_payload(kind, period, ids, now)
    content = _compress(payload)
    sha256 = hashlib.sha256(content).hexdigest()
    archive = HistoryArchive(
        kind=kind.key,
        period=period,
        record_count=len(ids),
        size_bytes=len(content),
        sha256=sha256,
        content=content,
        created_at=now,
        created_by_id=actor.id if actor else None,
    )
    db.session.add(archive)
    db.session.flush()
    archive_id = archive.id
    db.session.expire(archive)
    _verify_saved(archive_id, kind, ids, sha256)

    # Comprobado: ahora sí salen de la base, primero lo que cuelga de cada registro.
    for child_model, fk in kind.children:
        child = child_model.__table__
        db.session.execute(child.delete().where(child.c[fk].in_(ids)))
    table = kind.model.__table__
    db.session.execute(table.delete().where(table.c.id.in_(ids)))
    add_audit_log(
        "archive", archive_id, "history_archived",
        {"tipo": kind.label, "mes": period, "registros": len(ids), "sha256": sha256},
        actor=actor,
    )
    db.session.commit()
    return archive_id


def run_archive(actor=None, now=None):
    """Pasa al archivo todo lo que ya cumplió su plazo. Devuelve cuántos archivos y registros.

    Cada archivo se guarda por separado: si uno falla, los anteriores ya quedaron bien y de ese
    no sale nada de la base.
    """
    now = now or utc_now()
    archives = 0
    records = 0
    # Lo que quedó a medias en la sesión no debe mezclarse con el archivo.
    db.session.rollback()
    for kind in KINDS:
        by_period = defaultdict(list)
        for row_id, moment in _pending_query(kind, now).order_by(kind.model.id):
            by_period[moment.strftime("%Y-%m")].append(row_id)
        for period in sorted(by_period):
            ids = by_period[period]
            for start in range(0, len(ids), CHUNK_SIZE):
                chunk = ids[start:start + CHUNK_SIZE]
                try:
                    _archive_chunk(kind, period, chunk, actor, now)
                except ArchiveError:
                    db.session.rollback()
                    raise
                except Exception as error:
                    db.session.rollback()
                    raise ArchiveError(
                        f"No se pudo archivar {kind.label} de {period}. No salió nada de la base."
                    ) from error
                archives += 1
                records += len(chunk)
    purged = purge_login_attempts(now)
    db.session.commit()
    return {"archives": archives, "records": records, "loginAttemptsPurged": purged}


# --- Consultar, comprobar y volver a cargar -----------------------------------------------------

def list_archives():
    return HistoryArchive.query.order_by(HistoryArchive.period.desc(), HistoryArchive.id.desc()).all()


def archive_content(archive):
    return bytes(archive.content)


def verify_archive(archive):
    """True si el archivo guardado sigue igual que el día en que se creó."""
    return hashlib.sha256(archive_content(archive)).hexdigest() == archive.sha256


def manifest():
    """La lista de todos los archivos con su huella, para guardarla aparte y comparar después."""
    return {
        "app": "DOMUX",
        "format": FORMAT_VERSION,
        "generatedAt": utc_now().isoformat(),
        "archives": [archive.to_dict() for archive in list_archives()],
    }


def _restore_secrets(table_name, row):
    """Los secretos no se archivaron: al volver, la fila recibe valores nuevos que nadie conoce."""
    if table_name in ("package_pickup_codes", "visit_qr_passes"):
        row["token"] = secrets.token_urlsafe(32)
    if table_name == "package_pickup_codes":
        row["pin_hash"] = generate_password_hash(secrets.token_hex(16))
    return row


def _missing_targets(table, rows):
    """Para cada columna opcional que apunta a otra tabla: los ids que ya no están en la base."""
    missing = {}
    for column in table.columns:
        if not column.foreign_keys or not column.nullable:
            continue
        target = next(iter(column.foreign_keys)).column
        wanted = {row.get(column.name) for row in rows} - {None}
        if not wanted:
            continue
        found = set(db.session.execute(db.select(target).where(target.in_(wanted))).scalars())
        if wanted - found:
            missing[column.name] = wanted - found
    return missing


def restore_archive(archive, actor=None):
    """Vuelve a cargar en la base los registros de un archivo. Devuelve cuántos volvieron."""
    kind = KINDS_BY_KEY.get(archive.kind)
    if kind is None:
        raise ArchiveError("Este archivo es de un tipo que esta versión no conoce.")
    if archive.restored_at is not None:
        raise ArchiveError("Este archivo ya se volvió a cargar.")
    if not verify_archive(archive):
        raise ArchiveError("El archivo no coincide con su huella: pudo haber sido cambiado. No se cargó nada.")
    payload = read_archive(archive_content(archive))
    main = kind.model.__table__
    order = [main] + [child_model.__table__ for child_model, _ in kind.children]
    restored = 0
    try:
        for table in order:
            rows = payload["tables"].get(table.name, [])
            if not rows:
                continue
            ids = [row["id"] for row in rows]
            if db.session.execute(db.select(table.c.id).where(table.c.id.in_(ids))).first():
                raise ArchiveError("Parte de estos registros ya está en la base. No se cargó nada.")
            missing = _missing_targets(table, rows)
            prepared = []
            for row in rows:
                values = {
                    column.name: _typed(column, row.get(column.name))
                    for column in table.columns
                    if column.name in row
                }
                for name, gone in missing.items():
                    if values.get(name) in gone:
                        values[name] = None
                prepared.append(_restore_secrets(table.name, values))
            db.session.execute(table.insert(), prepared)
            if table is main:
                restored = len(prepared)
        archive.restored_at = utc_now()
        add_audit_log(
            "archive", archive.id, "history_restored",
            {"tipo": kind.label, "mes": archive.period, "registros": restored},
            actor=actor,
        )
        db.session.commit()
    except ArchiveError:
        db.session.rollback()
        raise
    except Exception as error:
        db.session.rollback()
        raise ArchiveError("No se pudo volver a cargar el archivo. La base quedó como estaba.") from error
    return restored


# --- Limpieza de intentos de inicio de sesión --------------------------------------------------

def purge_login_attempts(now=None):
    """Quita las filas de intentos fallidos que ya no sirven; queda guardado con el próximo commit.

    Se van las que están en cero y sin bloqueo (la persona ya entró bien) y las que llevan más de
    30 días sin un fallo nuevo. Un bloqueo vigente nunca se toca.
    """
    now = now or utc_now()
    not_locked = db.or_(LoginAttempt.locked_until.is_(None), LoginAttempt.locked_until <= now)
    stale = db.or_(
        LoginAttempt.failed_count == 0,
        LoginAttempt.last_failed_at.is_(None),
        LoginAttempt.last_failed_at < now - timedelta(days=LOGIN_ATTEMPT_DAYS),
    )
    return LoginAttempt.query.filter(not_locked, stale).delete(synchronize_session=False)


# --- Copia de respaldo ----------------------------------------------------------------------------

def write_backup(now=None):
    """Arma la copia de respaldo en un archivo temporal comprimido.

    Devuelve (archivo listo para leer, huella SHA-256, filas por tabla). Va tabla por tabla y de a
    pocas filas para no llenar la memoria con las fotos.
    """
    now = now or utc_now()
    spool = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    counts = {}
    tables = [t for t in db.metadata.sorted_tables if t.name not in BACKUP_SKIPPED_TABLES]
    with gzip.GzipFile(fileobj=spool, mode="wb", mtime=0) as handle:
        def write(text):
            handle.write(text.encode("utf-8"))

        header = {
            "app": "DOMUX",
            "format": FORMAT_VERSION,
            "createdAt": now.isoformat(),
            "note": "Copia de respaldo sin contraseñas, PIN ni códigos de acceso. "
                    "Los archivos históricos se descargan aparte.",
        }
        write('{"manifest":' + json.dumps(header, ensure_ascii=False) + ',"tables":{')
        for position, table in enumerate(tables):
            write(("," if position else "") + json.dumps(table.name) + ":[")
            total = 0
            query = table.select()
            if "id" in table.c:
                query = query.order_by(table.c.id)
            result = db.session.execute(query.execution_options(yield_per=100))
            for row in result.mappings():
                write(("," if total else "") + json.dumps(_row_dict(table, row), ensure_ascii=False))
                total += 1
            write("]")
            counts[table.name] = total
        write("}}")
    spool.seek(0)
    digest = hashlib.sha256()
    for block in iter(lambda: spool.read(1024 * 1024), b""):
        digest.update(block)
    spool.seek(0)
    return spool, digest.hexdigest(), counts
