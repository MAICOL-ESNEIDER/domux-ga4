"""Documentos de la unidad: subirlos, cambiarlos, retirarlos y entregar a cada persona los que puede ver (DEC-032).

La administración sube el manual de convivencia, las reglas, los presupuestos aprobados, los históricos de
gastos, las actas... y marca quién puede verlos: propietarios, arrendatarios, otros residentes y portería.
Sin ninguna marca el documento es solo de la administración, que los ve todos.

El archivo es un PDF o una imagen (PNG, JPG o WebP) de hasta 6 MB. Su tipo no se cree por lo que diga quien
lo sube: se reconoce por los primeros bytes (como los adjuntos, ``services.media``), así un archivo con la
extensión cambiada, un SVG o una página HTML no se cuela. Nada se borra: un documento retirado deja de verse
para los demás, pero queda guardado y se puede volver a publicar (ADR-013).

Ninguna función guarda en la base (commit): lo hace la ruta, para que el cambio, su anotación en la
auditoría y los avisos se guarden juntos.
"""

import base64
import binascii
import hashlib
import re
import unicodedata
from urllib.parse import quote

from flask import Response, request
from sqlalchemy import and_, false, func, or_, true
from sqlalchemy.orm import selectinload

from errors import ApiError
from extensions import db
from models import DOCUMENT_AUDIENCES, DOCUMENT_CATEGORIES, UnitDocument, User
from services.audit_service import add_audit_log
from services.media import MAX_MEDIA_BYTES, PDF_MIME, is_pdf, megabytes, sniff_media
from services.notification_service import notify_user
from validators import OCCUPANCY_TYPES

TITLE_MAX = 150
DESCRIPTION_MAX = 500
#: Lo más que puede medir el nombre del archivo sin la extensión.
FILE_NAME_MAX = 120

#: Lo que se acepta como documento y la extensión que lleva cada tipo.
DOCUMENT_EXTENSIONS = {
    PDF_MIME: ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
FORMATS_TEXT = "PDF, PNG, JPG o WebP"

#: Lo mismo que ``web.support.FILE_POLICY``: el archivo no puede cargar ni ejecutar nada.
FILE_POLICY = "default-src 'none'; style-src 'unsafe-inline'; sandbox"

_FILE_NAME_FORBIDDEN = set('<>:"|?*\\/')


# --- Revisión de lo que llega ------------------------------------------------------------------------

def parse_title(value):
    """El título del documento: texto de 1 a 150 caracteres."""
    if not isinstance(value, str) or not value.strip():
        raise ApiError("El título del documento es obligatorio.")
    title = re.sub(r"\s+", " ", value).strip()
    if len(title) > TITLE_MAX:
        raise ApiError(f"El título del documento puede tener hasta {TITLE_MAX} caracteres.")
    return title


def parse_description(value):
    """La descripción, opcional: de hasta 500 caracteres; vacía o ``null`` es sin descripción."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ApiError("La descripción del documento debe ser un texto.")
    description = value.strip()
    if not description:
        return None
    if len(description) > DESCRIPTION_MAX:
        raise ApiError(f"La descripción del documento puede tener hasta {DESCRIPTION_MAX} caracteres.")
    return description


def parse_category(value):
    """La llave del tipo de documento («convivencia», «presupuesto»...)."""
    if not isinstance(value, str) or value not in DOCUMENT_CATEGORIES:
        raise ApiError("El tipo de documento no es válido. Elige uno de: " + ", ".join(DOCUMENT_CATEGORIES) + ".")
    return value


def parse_audiences(value):
    """Quién puede ver el documento: una lista con llaves de ``DOCUMENT_AUDIENCES``; vacía es solo la administración."""
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ApiError("Quién puede ver el documento (visibleTo) debe ser una lista de roles; vacía si solo lo ve la administración.")
    unknown = [item for item in value if item not in DOCUMENT_AUDIENCES]
    if unknown:
        raise ApiError(
            f"«{unknown[0]}» no es un público válido. Elige entre: " + ", ".join(DOCUMENT_AUDIENCES) + "."
        )
    return [key for key in DOCUMENT_AUDIENCES if key in value]


def _audience_values(audiences):
    """Las columnas ``for_*`` que corresponden a una lista de públicos."""
    return {column: key in audiences for key, column in UnitDocument.AUDIENCE_COLUMNS.items()}


def parse_file(value):
    """Revisa el archivo que llega como «data:…;base64,…» y devuelve ``(bytes, tipo real)``.

    Solo se aceptan PDF y las imágenes PNG, JPG y WebP, de hasta 6 MB. El tipo sale de los primeros bytes.
    """
    if not isinstance(value, str):
        raise ApiError("El archivo del documento debe llegar como texto «data:…;base64,…».")
    header, separator, payload = value.partition(",")
    header = header.strip().lower()
    if not separator or not header.startswith("data:") or not header.endswith(";base64"):
        raise ApiError("El archivo debe llegar como archivo, no como enlace.")
    try:
        raw = base64.b64decode("".join(payload.split()), validate=True)
    except (binascii.Error, ValueError):
        raise ApiError("No se pudo leer el archivo. Vuelve a elegirlo.") from None
    if not raw:
        raise ApiError("El archivo está vacío. Vuelve a elegirlo.")
    if len(raw) > MAX_MEDIA_BYTES:
        raise ApiError(
            f"El archivo pesa {megabytes(len(raw))} MB y el máximo es "
            f"{MAX_MEDIA_BYTES // (1024 * 1024)} MB. Elige uno más liviano."
        )
    if is_pdf(raw):
        return raw, PDF_MIME
    found = sniff_media(raw)
    if found is None or found[1] != "image" or found[0] not in DOCUMENT_EXTENSIONS:
        raise ApiError(f"El archivo no es un documento que se pueda publicar ({FORMATS_TEXT}).")
    return raw, found[0]


def _clean_name(text):
    """Un nombre de archivo legible: sin carpetas, sin signos que los sistemas no aceptan y sin espacios de sobra."""
    text = text.replace("\\", "/").rsplit("/", 1)[-1]
    text = unicodedata.normalize("NFC", text)
    text = "".join(char for char in text if char.isprintable() and char not in _FILE_NAME_FORBIDDEN)
    return re.sub(r"\s+", " ", text).strip(" .")


def file_name_for(name, mime, title):
    """El nombre con el que se guarda el archivo: el que traía (o el título) con la extensión de su tipo real."""
    base = _clean_name(name) if isinstance(name, str) else ""
    base = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", base)  # la extensión que decía no vale: se pone la real
    if not base:
        base = _clean_name(title)
    return base[:FILE_NAME_MAX].strip(" .") + DOCUMENT_EXTENSIONS[mime]


def _ensure_title_free(title, exclude_id=None):
    """Dos documentos vigentes no pueden llamarse igual (sin importar mayúsculas); uno retirado libera su título."""
    taken = {
        row.title.casefold()
        for row in db.session.query(UnitDocument.id, UnitDocument.title).filter(UnitDocument.retired_at.is_(None))
        if row.id != exclude_id
    }
    if title.casefold() in taken:
        raise ApiError(f"Ya hay un documento llamado «{title}». Cámbiale el título o retira el otro.", 409)


# --- Qué ve cada persona -----------------------------------------------------------------------------

def _audience_condition(user):
    """La condición de la consulta con lo que esa persona puede ver (sin contar si está retirado)."""
    if user.role == "ADMIN":
        return true()
    if user.role == "GUARD":
        return UnitDocument.for_guards.is_(True)
    if user.role == "RESIDENT":
        occupancy = user.occupancy_type if user.occupancy_type in OCCUPANCY_TYPES else "propietario"
        return getattr(UnitDocument, UnitDocument.AUDIENCE_COLUMNS[occupancy]).is_(True)
    return false()


def visible_documents(user, include_retired=False, category=None):
    """Los documentos que esa persona puede ver, los más nuevos primero; sin el archivo.

    La administración ve todos (y los retirados si los pide); los demás, solo los vigentes que les marcaron.
    """
    query = UnitDocument.query.options(
        selectinload(UnitDocument.uploaded_by), selectinload(UnitDocument.retired_by),
    ).filter(_audience_condition(user))
    if not (include_retired and user.role == "ADMIN"):
        query = query.filter(UnitDocument.retired_at.is_(None))
    if category is not None:
        query = query.filter(UnitDocument.category == parse_category(category))
    return query.order_by(UnitDocument.created_at.desc(), UnitDocument.id.desc()).all()


def find_visible(user, document_id):
    """El documento si esa persona lo puede ver; si no existe, está retirado (para ella) o no es suyo, 404."""
    query = UnitDocument.query.options(
        selectinload(UnitDocument.uploaded_by), selectinload(UnitDocument.retired_by),
    ).filter(UnitDocument.id == document_id, _audience_condition(user))
    if user.role != "ADMIN":
        query = query.filter(UnitDocument.retired_at.is_(None))
    document = query.first()
    if document is None:
        raise ApiError("Documento no encontrado", 404)
    return document


def find_any(document_id):
    """El documento, vigente o retirado (solo para la administración); 404 si no existe."""
    document = db.session.get(UnitDocument, document_id)
    if document is None:
        raise ApiError("Documento no encontrado", 404)
    return document


def audience_user_ids(document):
    """Los ids de las personas activas a las que la administración les mostró el documento."""
    residents = [
        key for key in OCCUPANCY_TYPES if getattr(document, UnitDocument.AUDIENCE_COLUMNS[key])
    ]
    conditions = []
    if residents:
        conditions.append(and_(
            User.role == "RESIDENT", func.coalesce(User.occupancy_type, "propietario").in_(residents),
        ))
    if document.for_guards:
        conditions.append(User.role == "GUARD")
    if not conditions:
        return []
    rows = db.session.query(User.id).filter(User.is_active.is_(True), or_(*conditions)).order_by(User.id).all()
    return [row.id for row in rows]


# --- Cambios -----------------------------------------------------------------------------------------

def create_document(data, actor):
    """Sube un documento nuevo; devuelve ``(documento, personas avisadas)``.

    Llegan ``title``, ``category`` (opcional, «otro» por defecto), ``description`` (opcional), ``file``
    («data:…;base64,…»), ``fileName`` (opcional), ``visibleTo`` (la lista de públicos; vacía es solo la
    administración) y ``notify`` (opcional: avisar a quienes lo pueden ver).
    """
    for field, message in (
        ("title", "El título del documento es obligatorio."),
        ("file", "Falta el archivo del documento."),
        ("visibleTo", "Indica quién puede ver el documento (visibleTo); una lista vacía es solo la administración."),
    ):
        if field not in data:
            raise ApiError(message)
    notify = data.get("notify", False)
    if not isinstance(notify, bool):
        raise ApiError("El aviso a quienes lo ven (notify) debe ser verdadero o falso.")
    title = parse_title(data["title"])
    description = parse_description(data.get("description"))
    category = parse_category(data.get("category", "otro"))
    audiences = parse_audiences(data["visibleTo"])
    raw, mime = parse_file(data["file"])
    _ensure_title_free(title)

    document = UnitDocument(
        title=title, description=description, category=category,
        file_name=file_name_for(data.get("fileName"), mime, title), mime_type=mime,
        size_bytes=len(raw), content=raw, content_sha256=hashlib.sha256(raw).hexdigest(),
        uploaded_by_id=actor.id, **_audience_values(audiences),
    )
    db.session.add(document)
    db.session.flush()
    add_audit_log("unit_document", document.id, "uploaded", {
        "title": title, "category": category, "fileName": document.file_name, "sizeBytes": len(raw),
        "visibleTo": audiences, "notified": notify,
    }, actor=actor)
    notified = 0
    if notify:
        for user_id in audience_user_ids(document):
            notify_user(
                user_id, "Nuevo documento", f"{DOCUMENT_CATEGORIES[category]}: {title}", "document",
            )
            notified += 1
    return document, notified


def update_document(document, data, actor):
    """Cambia el título, la descripción, el tipo o quién lo puede ver; solo lo que llega.

    El archivo no se cambia: para publicar otra versión se sube un documento nuevo y se retira este.
    """
    if document.is_retired:
        raise ApiError("Ese documento está retirado y ya no se puede cambiar. Vuelve a publicarlo primero.", 409)
    if "file" in data:
        raise ApiError("El archivo de un documento no se cambia: sube un documento nuevo y retira este.")
    changes = {}
    if "title" in data:
        changes["title"] = parse_title(data["title"])
    if "description" in data:
        changes["description"] = parse_description(data["description"])
    if "category" in data:
        changes["category"] = parse_category(data["category"])
    if "visibleTo" in data:
        changes["visibleTo"] = parse_audiences(data["visibleTo"])
    if not changes:
        raise ApiError("Debes proporcionar al menos un dato para actualizar.")
    if "title" in changes:
        _ensure_title_free(changes["title"], exclude_id=document.id)

    before = {}
    after = {}
    for field, value in changes.items():
        if field == "visibleTo":
            current = document.audiences
            if current != value:
                before[field], after[field] = current, value
                for column, flag in _audience_values(value).items():
                    setattr(document, column, flag)
            continue
        current = getattr(document, field)  # título, descripción y tipo se llaman igual que su columna
        if current != value:
            before[field], after[field] = current, value
            setattr(document, field, value)
    if after:
        add_audit_log("unit_document", document.id, "updated", {"before": before, "after": after}, actor=actor)
    return document


def retire_document(document, actor):
    """Retira el documento: deja de verse para los demás, pero queda guardado."""
    if document.is_retired:
        raise ApiError("Ese documento ya está retirado.", 409)
    document.retire(actor)
    add_audit_log("unit_document", document.id, "retired", {"title": document.title}, actor=actor)
    return document


def restore_document(document, actor):
    """Vuelve a publicar un documento retirado, con los mismos públicos que tenía."""
    if not document.is_retired:
        raise ApiError("Ese documento ya está publicado.", 409)
    _ensure_title_free(document.title, exclude_id=document.id)
    document.retired_at = None
    document.retired_by_id = None
    add_audit_log("unit_document", document.id, "restored", {"title": document.title}, actor=actor)
    return document


# --- El archivo --------------------------------------------------------------------------------------

def _content_disposition(disposition, file_name):
    """La cabecera con el nombre del archivo, también si lleva tildes o eñes."""
    try:
        file_name.encode("ascii")
        return f'{disposition}; filename="{file_name}"'
    except UnicodeEncodeError:
        simple = unicodedata.normalize("NFKD", file_name).encode("ascii", "ignore").decode("ascii") or "documento"
        return f"{disposition}; filename=\"{simple}\"; filename*=UTF-8''{quote(file_name, safe='')}"


def file_response(document, disposition="inline"):
    """El archivo del documento listo para enviar.

    Lleva su huella como ETag y «no-cache»: la app y el navegador lo guardan, pero antes de usarlo preguntan
    si cambió y, si no cambió, el servidor responde 304 sin leer ni enviar el archivo otra vez. No puede
    cargar ni ejecutar nada (política de seguridad propia) y no se interpreta como otro tipo.
    """
    etag = document.content_sha256
    if request.if_none_match.contains(etag):
        response = Response(status=304)
    else:
        response = Response(bytes(document.content), mimetype=document.mime_type)
        response.headers["Content-Disposition"] = _content_disposition(disposition, document.file_name)
    response.set_etag(etag)
    response.headers["Cache-Control"] = "private, no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = FILE_POLICY
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    return response
