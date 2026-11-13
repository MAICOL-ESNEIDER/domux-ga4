"""Paquetes: transportadora y guía, y código de entrega para que otra persona recoja (HU-047 y HU-048).

Las rutas de routes/security.py solo leen la solicitud y responden; las reglas
nuevas están aquí. Las funciones lanzan ApiError con un mensaje claro. Ninguna
hace commit, salvo el registro de un intento fallido de código, que debe quedar
guardado aunque la solicitud termine en error (ver check_pickup_code).

El código de entrega son dos formas de lo mismo: un QR (un texto largo al azar)
y un PIN de 6 dígitos. El residente dueño del paquete los genera, se los pasa a
quien va a recoger, y el guardia valida uno de los dos al entregar. Quien tenga
el PIN no puede adivinarlo a ciegas: tras 5 intentos fallidos el código se anula.
"""

import hmac
import secrets

from sqlalchemy import update
from werkzeug.security import check_password_hash, generate_password_hash

from errors import ApiError
from extensions import db
from models import PackagePickupCode
from services.audit_service import add_audit_log
from time_utils import utc_now

#: Largo máximo de la transportadora y del número de guía.
MAX_SHIPPING_LENGTH = 60

#: El PIN de entrega tiene 6 dígitos.
PIN_DIGITS = 6

#: Intentos fallidos antes de anular el código.
MAX_FAILED_ATTEMPTS = 5

#: Lo que lleva el QR antes del token, para distinguirlo de los QR de las visitas.
QR_PREFIX = "DOMUX-PKG:"


# ---------------------------------------------------------------------------
# Transportadora y guía (HU-047)
# ---------------------------------------------------------------------------

def _shipping_text(value, label):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ApiError(f"El campo '{label}' debe ser texto.")
    text = " ".join(value.split())
    if len(text) > MAX_SHIPPING_LENGTH:
        raise ApiError(f"El campo '{label}' no puede tener más de {MAX_SHIPPING_LENGTH} caracteres.")
    return text or None


def clean_shipping(data):
    """Lee la transportadora y el número de guía de la solicitud; ambos son opcionales."""
    return (
        _shipping_text(data.get("carrier"), "transportadora"),
        _shipping_text(data.get("trackingNumber"), "número de guía"),
    )


# ---------------------------------------------------------------------------
# Código de entrega (HU-048)
# ---------------------------------------------------------------------------

def create_pickup_code(package, resident):
    """Genera el código de entrega de un paquete y devuelve (código, PIN en claro).

    Solo el dueño del paquete puede generarlo y solo mientras el paquete esté en
    portería. El PIN solo existe en claro en esta respuesta: en la base queda su
    hash. Si ya había un código vigente, queda anulado (siempre hay uno solo).
    """
    if package.resident_id != resident.id:
        raise ApiError("Solo el dueño del paquete puede generar su código de entrega.", 403)
    if package.is_deleted:
        raise ApiError("Este paquete está archivado. Sácalo de «Archivados» para usarlo.", 409)
    if package.status == "entregado":
        raise ApiError("Este paquete ya fue entregado.", 409)
    if package.status != "pendiente":
        raise ApiError("El paquete todavía no está en portería: el código se genera cuando llegue.", 409)
    now = utc_now()
    previous = package.active_pickup_code
    if previous is not None:
        previous.revoked_at = now
        db.session.flush()  # el índice único pide que el anterior quede anulado antes del nuevo
    pin = f"{secrets.randbelow(10 ** PIN_DIGITS):0{PIN_DIGITS}d}"
    code = PackagePickupCode(
        package_id=package.id,
        token=secrets.token_urlsafe(24),
        pin_hash=generate_password_hash(pin),
        created_by_id=resident.id,
        created_at=now,
    )
    db.session.add(code)
    db.session.flush()
    add_audit_log(
        "package", package.id, "pickup_code_created",
        {"replacedPrevious": previous is not None}, actor=resident,
    )
    return code, pin


def _bare_token(value):
    """El texto de un código sin espacios ni el prefijo que lleva el QR."""
    value = value.strip()
    return value[len(QR_PREFIX):] if value.startswith(QR_PREFIX) else value


def package_for_pickup_token(value):
    """El paquete de un código escaneado por el guardia, si el código sirve todavía."""
    if not isinstance(value, str) or not value.strip():
        raise ApiError("Escanea el QR del código de entrega.")
    code = PackagePickupCode.query.filter_by(token=_bare_token(value)).first()
    if code is None:
        raise ApiError("Código de entrega no encontrado.", 404)
    if code.used_at is not None:
        raise ApiError("Este código ya se usó.", 409)
    if code.revoked_at is not None:
        raise ApiError("Este código fue anulado: el residente debe generar uno nuevo.", 409)
    package = code.package
    if package.status == "entregado":
        raise ApiError("Este paquete ya fue entregado.", 409)
    if package.is_deleted:
        raise ApiError("Este paquete está archivado. Sácalo de «Archivados» para usarlo.", 409)
    return package


def _matches(code, text):
    """Si el texto es el QR o el PIN del código; el QR se compara sin revelar dónde difiere."""
    if hmac.compare_digest(text.encode(), code.token.encode()):
        return True
    return text.isdigit() and check_password_hash(code.pin_hash, text)


def check_pickup_code(package, value, guard):
    """Valida el código (QR o PIN) con el que otra persona recoge el paquete y lo marca como usado.

    Lanza ApiError si el código no sirve: no hay uno vigente, es de otro paquete
    o no coincide. Un intento que no coincide se cuenta y se guarda de inmediato
    (con commit), aunque la solicitud termine en error: al quinto, el código se
    anula y el residente debe generar uno nuevo. Un PIN que no tiene 6 dígitos es
    un error de digitación y no cuenta como intento.
    """
    if not isinstance(value, str) or not value.strip():
        raise ApiError("Escribe el PIN o escanea el QR del código de entrega.")
    text = _bare_token(value)
    if text.isdigit() and len(text) != PIN_DIGITS:
        raise ApiError(f"El PIN tiene {PIN_DIGITS} dígitos.")
    active = package.active_pickup_code
    if active is None:
        if any(code.used_at is not None for code in package.pickup_codes):
            raise ApiError("El código de este paquete ya se usó.", 409)
        raise ApiError("Este paquete no tiene un código de entrega vigente.", 409)
    belongs_elsewhere = PackagePickupCode.query.filter(
        PackagePickupCode.token == text, PackagePickupCode.package_id != package.id
    ).first()
    if belongs_elsewhere is not None:
        raise ApiError("Este código es de otro paquete.", 409)
    if not _matches(active, text):
        # La suma la hace la base, así dos intentos a la vez cuentan los dos.
        active.failed_attempts = PackagePickupCode.failed_attempts + 1
        db.session.flush()
        locked = active.failed_attempts >= MAX_FAILED_ATTEMPTS
        if locked:
            active.revoked_at = utc_now()
        db.session.commit()
        if locked:
            raise ApiError(
                "Demasiados intentos fallidos: el código se anuló. El residente debe generar uno nuevo.", 409
            )
        raise ApiError("El código no coincide con este paquete.")
    # Solo una solicitud puede marcarlo usado: si otra se adelantó, esta ya no entrega.
    claimed = db.session.execute(
        update(PackagePickupCode)
        .where(
            PackagePickupCode.id == active.id,
            PackagePickupCode.used_at.is_(None),
            PackagePickupCode.revoked_at.is_(None),
        )
        .values(used_at=utc_now())
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        raise ApiError("Este código ya se usó.", 409)
    add_audit_log("package", package.id, "pickup_code_used", None, actor=guard)


def close_active_code(package):
    """Anula el código vigente cuando el paquete se entrega sin usarlo (lo recogió su dueño, por ejemplo)."""
    active = package.active_pickup_code
    if active is not None:
        active.revoked_at = utc_now()
