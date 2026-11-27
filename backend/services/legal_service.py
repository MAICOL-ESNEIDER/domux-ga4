"""Documentos legales de DOMUX: política de datos, términos, cookies y los demás textos que pide la ley.

Cada documento es un archivo de texto en ``backend/legal/<nombre>.md``. Este módulo los lee, comprueba que
estén bien armados y los convierte en «bloques» (títulos, párrafos y listas) para que la app y la web los
dibujen sin tener que entender Markdown.

Hoy los textos son un aviso de «documento en preparación»: lo que ya existe son los espacios donde van, en
la app y en la web. Cuando un texto esté listo, se reemplaza el archivo y su ``estado`` pasa a ``vigente``,
sin tocar la app ni la web. ``scripts/verificar_legal.py`` impide entregar la versión final con alguno
todavía pendiente.

Cada archivo empieza con un encabezado entre dos líneas ``---``::

    ---
    titulo: Términos y condiciones de uso
    resumen: Las reglas para usar la app y la web de DOMUX.
    estado: pendiente
    version:
    vigente_desde:
    ---
    ## Primer título del texto

    Un párrafo. Las líneas seguidas forman un solo párrafo.

    - Un elemento de lista
    - Otro elemento

El texto solo admite títulos (``##`` y ``###``), párrafos y listas (con ``-`` o con ``1.``). No hay negrita,
enlaces, tablas ni imágenes: así se ve igual en la app, en la web y en un lector de pantalla.
"""

import re
from datetime import date
from pathlib import Path

#: La carpeta donde viven los textos.
LEGAL_DIR = Path(__file__).resolve().parent.parent / "legal"

#: Los documentos, en el orden en que se muestran. Cada nombre es el del archivo (sin «.md») y también la
#: dirección: ``/api/legal/<nombre>``. Solo estos se sirven; nada más de la carpeta sale al público.
DOCUMENT_SLUGS = (
    "politica-datos",
    "aviso-privacidad",
    "autorizacion-datos",
    "terminos",
    "consultas-reclamos",
    "cookies",
    "responsable",
    "licencias-terceros",
    "compromiso-porteria",
    "compromiso-administracion",
)

#: Para quién es cada documento (dato «para» del encabezado). Sin el dato, es para todos.
AUDIENCES = {"residentes": "RESIDENT", "porteria": "GUARD", "administracion": "ADMIN"}
ALL_ROLES = ["RESIDENT", "GUARD", "ADMIN"]

#: Estado de un documento: todavía sin texto final, o publicado y con validez.
PENDING = "pendiente"
IN_FORCE = "vigente"
STATUSES = (PENDING, IN_FORCE)

#: Los datos que lleva el encabezado de cada archivo. Los tres primeros son obligatorios.
REQUIRED_FIELDS = ("titulo", "resumen", "estado")
OPTIONAL_FIELDS = ("version", "vigente_desde", "para")

#: El título del aviso que llevan los textos en espera; un documento vigente no puede conservarlo.
PLACEHOLDER_HEADING = "documento en preparación"

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
_BULLET = re.compile(r"^-\s+(.+)$")
_NUMBERED = re.compile(r"^\d+[.)]\s+(.+)$")

#: Lo que NO se admite en el texto, con la razón (para avisarle a quien escribe, no para mostrarlo).
_UNSUPPORTED = (
    (re.compile(r"\*\*|__"), "no se usa negrita («**» ni «__»)"),
    (re.compile(r"`"), "no se usan las comillas invertidas («`»)"),
    (re.compile(r"!\[|\]\("), "no se usan enlaces ni imágenes en formato Markdown"),
    (re.compile(r"^\s*\|"), "no se usan tablas; escribe una lista"),
    (re.compile(r"^\s*>"), "no se usan citas con «>»"),
    (re.compile(r"^\s*(```|~~~)"), "no se usan bloques de código"),
    (re.compile(r"^\s*[*+]\s"), "las listas empiezan con «-», no con «*» ni «+»"),
    (re.compile(r"</?[A-Za-z][^>]*>"), "no se usan etiquetas HTML"),
)


class LegalDocumentError(ValueError):
    """Un archivo de la carpeta ``legal`` está mal armado (le falta el encabezado, un dato, etc.)."""


def _folder(directory):
    return Path(directory) if directory is not None else LEGAL_DIR


def _read(slug, directory):
    """El texto completo del archivo de ese documento."""
    path = _folder(directory) / f"{slug}.md"
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise LegalDocumentError(f"falta el archivo {slug}.md") from None


def split_front_matter(text):
    """Separa el encabezado del texto: devuelve ``(datos, cuerpo)``.

    El encabezado va entre dos líneas ``---`` al comienzo; cada línea es ``nombre: valor``. Un valor
    vacío (como ``version:`` sin nada) se guarda como cadena vacía.
    """
    lines = text.replace("\r\n", "\n").lstrip("﻿").split("\n")
    if not lines or lines[0].strip() != "---":
        raise LegalDocumentError("falta el encabezado: el archivo debe empezar con una línea «---»")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise LegalDocumentError("el encabezado no se cierra: falta la segunda línea «---»")
    data = {}
    for number, line in enumerate(lines[1:end], start=2):
        if not line.strip():
            continue
        name, separator, value = line.partition(":")
        if not separator:
            raise LegalDocumentError(f"la línea {number} del encabezado no tiene «:»")
        name = name.strip()
        if name in data:
            raise LegalDocumentError(f"el dato «{name}» está repetido en el encabezado")
        data[name] = value.strip()
    return data, "\n".join(lines[end + 1:])


def parse_blocks(body):
    """Convierte el texto en bloques para dibujarlo.

    Cada bloque es un diccionario:

    - ``{"type": "heading", "level": 1 a 3, "text": "..."}``
    - ``{"type": "paragraph", "text": "..."}``
    - ``{"type": "list", "ordered": true o false, "items": ["...", "..."]}``

    Una línea en blanco separa párrafos y cierra las listas. Las líneas seguidas forman un solo párrafo,
    y una línea con sangría debajo de un elemento de lista sigue ese elemento. Una línea que es solo un
    comentario ``<!-- ... -->`` es una nota para quien escribe y no sale a nadie. Los números de una
    lista numerada los pone quien la dibuja, en orden: no importa con cuál empiece el archivo.
    """
    blocks = []
    paragraph = []
    items = None  # (ordenada, [textos]) mientras hay una lista abierta

    def close_paragraph():
        if paragraph:
            blocks.append({"type": "paragraph", "text": " ".join(paragraph)})
            paragraph.clear()

    def close_list():
        nonlocal items
        if items is not None:
            blocks.append({"type": "list", "ordered": items[0], "items": items[1]})
            items = None

    for raw in body.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            close_paragraph()
            close_list()
            continue
        if line.startswith("<!--") and line.endswith("-->"):
            continue
        heading = _HEADING.match(line)
        if heading:
            close_paragraph()
            close_list()
            blocks.append({"type": "heading", "level": min(len(heading.group(1)), 3), "text": heading.group(2).strip()})
            continue
        bullet, numbered = _BULLET.match(line), _NUMBERED.match(line)
        if bullet or numbered:
            close_paragraph()
            ordered = numbered is not None
            if items is not None and items[0] != ordered:
                close_list()
            if items is None:
                items = (ordered, [])
            items[1].append((numbered or bullet).group(1).strip())
            continue
        if items is not None and raw[:1] in (" ", "\t"):
            items[1][-1] = f"{items[1][-1]} {line}"
            continue
        close_list()
        paragraph.append(line)
    close_paragraph()
    close_list()
    return blocks


def _load(slug, directory):
    """Lee un documento ya armado: sus datos y sus bloques."""
    data, body = split_front_matter(_read(slug, directory))
    missing = [name for name in REQUIRED_FIELDS if not data.get(name)]
    if missing:
        raise LegalDocumentError(f"falta en el encabezado: {', '.join(missing)}")
    if data["estado"] not in STATUSES:
        raise LegalDocumentError(f"el estado «{data['estado']}» no existe; usa «{PENDING}» o «{IN_FORCE}»")
    return {
        "slug": slug,
        "title": data["titulo"],
        "summary": data["resumen"],
        "status": data["estado"],
        "version": data.get("version") or None,
        "effectiveFrom": data.get("vigente_desde") or None,
        "audience": _audience(data.get("para")),
        "blocks": parse_blocks(body),
    }


def _audience(value):
    """Los roles a los que va dirigido: «para: porteria» o «para: residentes, administracion». Vacío = todos."""
    if not value or value.strip() == "todos":
        return list(ALL_ROLES)
    roles = []
    for word in value.split(","):
        role = AUDIENCES.get(word.strip())
        if role is None:
            raise LegalDocumentError(f"el dato «para» no reconoce «{word.strip()}»; usa residentes, porteria o administracion")
        roles.append(role)
    return roles


def list_documents(directory=None):
    """Los documentos en su orden, sin el texto: lo que muestra la lista de la app y de la web."""
    summaries = []
    for slug in DOCUMENT_SLUGS:
        document = _load(slug, directory)
        document.pop("blocks")
        summaries.append(document)
    return summaries


def get_document(slug, directory=None):
    """Un documento completo, o ``None`` si ese nombre no es de un documento legal."""
    if slug not in DOCUMENT_SLUGS:
        return None
    return _load(slug, directory)


def check_document(slug, directory=None):
    """Los problemas de un documento, en frases para quien lo escribe. Lista vacía si está bien armado.

    Un texto «pendiente» está bien armado; que falte escribirlo lo dice ``pending_slugs``, no esta revisión.
    """
    problems = []
    try:
        data, body = split_front_matter(_read(slug, directory))
    except LegalDocumentError as error:
        return [str(error)]

    for name in data:
        if name not in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            problems.append(f"el dato «{name}» del encabezado no existe")
    missing = [name for name in REQUIRED_FIELDS if not data.get(name)]
    if missing:
        problems.append(f"falta en el encabezado: {', '.join(missing)}")
    status = data.get("estado")
    if status and status not in STATUSES:
        problems.append(f"el estado «{status}» no existe; usa «{PENDING}» o «{IN_FORCE}»")

    effective_from = data.get("vigente_desde")
    if effective_from:
        try:
            if not _DATE.match(effective_from):
                raise ValueError
            date.fromisoformat(effective_from)
        except ValueError:
            problems.append(f"«vigente_desde» debe ser una fecha real con la forma AAAA-MM-DD, no «{effective_from}»")

    blocks = parse_blocks(body)
    if not blocks:
        problems.append("el texto está vacío")
    for number, line in enumerate(body.replace("\r\n", "\n").split("\n"), start=1):
        stripped = line.strip()
        if not stripped or (stripped.startswith("<!--") and stripped.endswith("-->")):
            continue
        for pattern, reason in _UNSUPPORTED:
            if pattern.search(line):
                problems.append(f"línea {number} del texto: {reason}")
        heading = _HEADING.match(stripped)
        if heading and len(heading.group(1)) == 1:
            problems.append(f"línea {number} del texto: el título del documento va en «titulo:», usa «##» o «###»")
        elif heading and len(heading.group(1)) > 3:
            problems.append(f"línea {number} del texto: solo hay títulos de «##» y «###»")

    if status == IN_FORCE:
        if not data.get("version"):
            problems.append("un documento vigente necesita «version»")
        if not effective_from:
            problems.append("un documento vigente necesita «vigente_desde»")
        if any(
            block["type"] == "heading" and block["text"].strip().lower() == PLACEHOLDER_HEADING for block in blocks
        ):
            problems.append("está como vigente pero conserva el aviso «Documento en preparación»")
    return problems


def check_all(directory=None):
    """Los problemas de todos los documentos, cada uno con el nombre de su archivo."""
    problems = []
    for slug in DOCUMENT_SLUGS:
        problems.extend(f"{slug}.md: {problem}" for problem in check_document(slug, directory))
    return problems


def pending_slugs(directory=None):
    """Los documentos que todavía no tienen su texto final, en el orden de la lista."""
    pending = []
    for slug in DOCUMENT_SLUGS:
        try:
            status = split_front_matter(_read(slug, directory))[0].get("estado")
        except LegalDocumentError:
            status = None
        if status != IN_FORCE:
            pending.append(slug)
    return pending
