"""La pantalla «Acepto»: cada persona acepta, al entrar por primera vez, los textos legales de DOMUX.

Se aceptan juntos tres textos de ``backend/legal``: los términos de uso, la política de tratamiento de datos
y la autorización para tratarlos (Ley 1581 de 2012). La aceptación guarda cuándo y qué versión de los textos
leyó la persona. Si un texto cambia de versión, la versión guardada deja de coincidir y se vuelve a pedir.

Mientras no acepte, la API solo le deja ver su sesión, leer los textos y aceptar (ver ``auth.token_required``).
Este módulo no toca la base de datos ni los modelos: solo decide con los datos que recibe.
"""

from functools import lru_cache
from pathlib import Path

from config import legal_acceptance_enforced
from services import legal_service

#: Los textos que se aceptan juntos, en el orden en que se muestran.
ACCEPTANCE_SLUGS = ("terminos", "politica-datos", "autorizacion-datos")

#: Lo que dice la versión cuando un texto todavía no tiene número de versión.
NO_VERSION = "sin-version"

#: Las rutas que sí puede usar quien aún no aceptó: ver su sesión, leer los textos y aceptar.
ACCEPTANCE_ENDPOINTS = frozenset({
    "auth.current_session", "auth.accept_legal", "auth.legal_acceptance_status",
    "legal.list_documents", "legal.get_document",
})
ACCEPTANCE_MESSAGE = "Antes de continuar debes leer y aceptar los textos legales de DOMUX."


def acceptance_documents(directory=None):
    """Los resúmenes (sin el texto) de los documentos que se aceptan, en el orden en que se muestran."""
    by_slug = {document["slug"]: document for document in legal_service.list_documents(directory)}
    return [by_slug[slug] for slug in ACCEPTANCE_SLUGS]


def _signature(directory):
    """Cuándo se modificó cada archivo: si no cambia, la versión tampoco y no hace falta volver a leerlos."""
    folder = Path(directory) if directory is not None else legal_service.LEGAL_DIR
    return tuple((folder / f"{slug}.md").stat().st_mtime_ns for slug in ACCEPTANCE_SLUGS)


@lru_cache(maxsize=8)
def _version(directory, signature):
    parts = []
    for slug in ACCEPTANCE_SLUGS:
        document = legal_service.get_document(slug, directory)
        parts.append(f"{slug}:{document['version'] or NO_VERSION}")
    return "|".join(parts)


def current_version(directory=None):
    """La versión que se está aceptando: las versiones de los tres textos, unidas.

    Cambia cuando cambia la versión de cualquiera de ellos, y solo entonces. Como se pide cada vez que se
    arma un usuario, se recuerda mientras los archivos no cambien.
    """
    return _version(str(directory) if directory is not None else None, _signature(directory))


def acceptance_pending(user):
    """true si esta persona todavía debe aceptar (nunca aceptó, o los textos cambiaron desde que aceptó)."""
    if not legal_acceptance_enforced():
        return False
    if user.legal_accepted_at is None:
        return True
    return user.legal_accepted_version != current_version()
