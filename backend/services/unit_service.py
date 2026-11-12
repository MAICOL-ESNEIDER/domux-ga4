"""Datos de la unidad: nombre, NIT, dirección, teléfono de portería y logo (HU-077).

Aquí están las reglas de lo que se puede guardar; las rutas solo leen la solicitud, llaman a estas
funciones y responden. Ninguna guarda en la base (commit): lo hace la ruta, para que el cambio y su
anotación en la auditoría se guarden juntos.

Los datos son los de una sola fila (ComplexProfile). El logo es una imagen PNG, JPG o WebP: se
acepta solo si sus primeros bytes dicen de verdad que lo es (no basta con lo que declare el nombre
del archivo) y no se aceptan SVG, porque un SVG puede llevar scripts.
"""

import base64
import binascii
import hashlib
import re

from flask import Response, request

from errors import ApiError
from extensions import db
from models import ComplexProfile
from services.audit_service import add_audit_log
from time_utils import utc_now

NAME_MAX = 120
ADDRESS_MAX = 200

#: Lo máximo que puede pesar el logo (un logo normal pesa menos de 100 KB).
MAX_LOGO_BYTES = 512 * 1024

#: Lo que devuelve la API mientras la administración no ha guardado los datos.
BLANK_UNIT = {
    "name": None,
    "nit": None,
    "address": None,
    "portalPhone": None,
    "hasLogo": False,
    "logoVersion": None,
    "updatedAt": None,
}

LOGO_FORMAT_MESSAGE = "El logo debe ser una imagen PNG, JPG o WebP (no se aceptan otros formatos, como SVG)."

#: Los pesos con los que la DIAN calcula el dígito de verificación de un NIT, de derecha a izquierda.
NIT_WEIGHTS = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)
NIT_SHAPE = re.compile(r"(?P<number>\d+|\d{1,3}(?:\.\d{3})+)(?:-(?P<check>\d))?")
PHONE_SHAPE = re.compile(r"\+?[\d ()-]+")


# ---------------------------------------------------------------------------
# Lectura de cada dato
# ---------------------------------------------------------------------------

def _text(value, label, max_length):
    """Un texto sin espacios de más y dentro del largo permitido."""
    if not isinstance(value, str) or not value.strip():
        raise ApiError(f"{label} no puede estar vacío.")
    text = " ".join(value.split())
    if len(text) > max_length:
        raise ApiError(f"{label} no puede tener más de {max_length} caracteres.")
    return text


def clean_name(value):
    if value is None:
        raise ApiError("El nombre de la unidad es obligatorio.")
    return _text(value, "El nombre de la unidad", NAME_MAX)


def clean_address(value):
    return _text(value, "La dirección", ADDRESS_MAX)


def nit_check_digit(digits):
    """El dígito de verificación de un NIT escrito solo con números (900123456 → 8)."""
    total = sum(int(digit) * weight for digit, weight in zip(reversed(digits), NIT_WEIGHTS))
    remainder = total % 11
    return remainder if remainder < 2 else 11 - remainder


def clean_nit(value):
    """El NIT como lo escribió la persona (sin espacios), revisando su forma y su dígito de verificación.

    Sirven «900123456-8», «900.123.456-8» y «900123456». Si trae el guion con el dígito de
    verificación, ese dígito tiene que ser el que corresponde al número: así se atrapa un error
    de digitación antes de que lo vean todos los residentes.
    """
    compact = _text(value, "El NIT", 40).replace(" ", "")
    match = NIT_SHAPE.fullmatch(compact)
    if match is None:
        raise ApiError(
            "El NIT solo lleva números, puntos de miles y el guion del dígito de verificación, "
            "por ejemplo 900.123.456-8."
        )
    digits = match.group("number").replace(".", "")
    if not 5 <= len(digits) <= 12:
        raise ApiError("El NIT debe tener entre 5 y 12 números, sin contar el dígito de verificación.")
    check = match.group("check")
    if check is not None and int(check) != nit_check_digit(digits):
        raise ApiError("El dígito de verificación del NIT no coincide con el número. Revísalo.")
    return compact


def clean_phone(value):
    """El teléfono como lo escribió la persona, revisando que tenga entre 7 y 15 números."""
    text = _text(value, "El teléfono de portería", 40)
    digits = re.sub(r"\D", "", text)
    if PHONE_SHAPE.fullmatch(text) is None or not 7 <= len(digits) <= 15:
        raise ApiError(
            "El teléfono de portería solo lleva números, espacios, guiones, paréntesis y un + al inicio, "
            "y debe tener entre 7 y 15 números."
        )
    return text


def sniff_logo_type(raw):
    """El tipo de imagen que dicen los primeros bytes (PNG, JPG o WebP); None si no es ninguno."""
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


def read_logo(value):
    """Los bytes y el tipo de un logo enviado como «data:image/png;base64,…»; error 400 si no sirve."""
    if not isinstance(value, str):
        raise ApiError(LOGO_FORMAT_MESSAGE)
    header, _, payload = value.partition(",")
    header = header.strip().lower()
    if not header.startswith("data:image/") or not header.endswith(";base64"):
        raise ApiError(LOGO_FORMAT_MESSAGE)
    too_heavy = ApiError(
        f"El logo es muy pesado: el máximo es {MAX_LOGO_BYTES // 1024} KB. Reduce la imagen e inténtalo de nuevo."
    )
    # Se mira el largo antes de decodificar para no gastar memoria con un archivo enorme.
    if len(payload) > (MAX_LOGO_BYTES * 4) // 3 + 8:
        raise too_heavy
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise ApiError("El logo no es una imagen válida.") from None
    if len(raw) > MAX_LOGO_BYTES:
        raise too_heavy
    kind = sniff_logo_type(raw)
    if kind is None:
        raise ApiError(LOGO_FORMAT_MESSAGE)
    return raw, kind


# ---------------------------------------------------------------------------
# Lectura y cambio de los datos
# ---------------------------------------------------------------------------

def get_profile():
    """La fila con los datos de la unidad, o None si la administración aún no los guarda."""
    return db.session.get(ComplexProfile, ComplexProfile.SINGLE_ID)


def unit_dict():
    """Los datos de la unidad como los entrega la API (con todo vacío mientras no se hayan guardado)."""
    profile = get_profile()
    return profile.to_dict() if profile is not None else dict(BLANK_UNIT)


def _snapshot(profile):
    return {
        "name": profile.name,
        "nit": profile.nit,
        "address": profile.address,
        "portalPhone": profile.portal_phone,
    }


def update_unit(data, actor):
    """Guarda los datos que trae la solicitud; lo que no trae queda como estaba.

    Un dato opcional (nit, address, portalPhone, logo) enviado como null se borra. El nombre es
    obligatorio: la primera vez hay que enviarlo y después no puede quedar vacío. Si nada cambió no
    se anota nada en la auditoría. En ella se guardan los textos de antes y de después, nunca la
    imagen del logo.
    """
    profile = get_profile()
    creating = profile is None
    if creating and "name" not in data:
        raise ApiError("El nombre de la unidad es obligatorio para guardar sus datos por primera vez.")

    # Primero se revisa todo y recién después se toca la fila: un dato inválido no deja nada a medias.
    changes = {}
    if "name" in data:
        changes["name"] = clean_name(data["name"])
    for key, attribute, clean in (
        ("nit", "nit", clean_nit),
        ("address", "address", clean_address),
        ("portalPhone", "portal_phone", clean_phone),
    ):
        if key in data:
            changes[attribute] = None if data[key] is None else clean(data[key])
    new_logo = read_logo(data["logo"]) if data.get("logo") is not None else None

    if creating:
        profile = ComplexProfile(id=ComplexProfile.SINGLE_ID, name=changes["name"])
        db.session.add(profile)
        before = None
    else:
        before = _snapshot(profile)
    for attribute, value in changes.items():
        setattr(profile, attribute, value)

    logo_change = None
    if "logo" in data:
        if new_logo is None:
            if profile.has_logo:
                logo_change = "removed"
            profile.logo = None
            profile.logo_type = None
            profile.logo_sha256 = None
        else:
            raw, kind = new_logo
            digest = hashlib.sha256(raw).hexdigest()
            if digest != profile.logo_sha256:
                logo_change = "changed"
            profile.logo, profile.logo_type, profile.logo_sha256 = raw, kind, digest

    after = _snapshot(profile)
    if creating or before != after or logo_change:
        profile.updated_at = utc_now()
        profile.updated_by_id = actor.id
        db.session.flush()
        details = {"after": after} if creating else {"before": before, "after": after}
        if logo_change:
            details["logo"] = logo_change
        add_audit_log("complex_profile", profile.id, "created" if creating else "updated", details, actor=actor)
    return profile


def logo_response():
    """La imagen del logo lista para enviar, o None si la unidad no tiene.

    Lleva su huella como ETag y «no-cache»: el navegador y la app la guardan, pero antes de usarla
    preguntan si cambió y, si no cambió, el servidor responde 304 sin enviarla otra vez.
    """
    row = (
        db.session.query(ComplexProfile.logo, ComplexProfile.logo_type, ComplexProfile.logo_sha256)
        .filter(ComplexProfile.id == ComplexProfile.SINGLE_ID)
        .first()
    )
    if row is None or row.logo is None:
        return None
    response = Response(bytes(row.logo), mimetype=row.logo_type)
    response.set_etag(row.logo_sha256)
    response.headers["Cache-Control"] = "private, no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response.make_conditional(request)
