"""Shared request validation for text, credentials, dates, and reservation slots."""

import re
from datetime import date, datetime

PASSWORD_REGEX = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&#._-])"
    r"[A-Za-z\d@$!%*?&#._-]{8,}$"
)
MEDIA_TYPES = ("image", "video", "audio")
OCCUPANCY_TYPES = ("propietario", "arrendatario", "arrendador", "visitante")
VALID_TIME_SLOTS = (
    "08:00-10:00",
    "10:00-12:00",
    "12:00-14:00",
    "14:00-16:00",
    "16:00-18:00",
    "18:00-20:00",
    "20:00-22:00",
)
VALID_PQRS_STATUSES = ("abierta", "en_proceso", "resuelta")
VALID_PACKAGE_STATUSES = ("por_llegar", "pendiente", "entregado")


def require_non_empty_fields(data, required_fields):
    """Return a validation message when the JSON object or a required field is invalid."""
    if not isinstance(data, dict):
        return "El cuerpo de la solicitud debe ser un objeto JSON válido."
    for field_name, label in required_fields:
        value = data.get(field_name)
        if not isinstance(value, str) or not value.strip():
            return f"El campo '{label}' es obligatorio y no puede estar vacío."
    return None


def validate_no_empty_strings(data):
    """Reject whitespace-only strings supplied to any write endpoint."""
    if not isinstance(data, dict):
        return "El cuerpo de la solicitud debe ser un objeto JSON válido."

    def find_empty(value, path):
        if isinstance(value, str) and not value.strip():
            return f"El campo '{path}' no puede estar vacío."
        if isinstance(value, dict):
            for key, nested_value in value.items():
                error = find_empty(nested_value, f"{path}.{key}" if path else key)
                if error:
                    return error
        if isinstance(value, list):
            for index, nested_value in enumerate(value):
                error = find_empty(nested_value, f"{path}[{index}]")
                if error:
                    return error
        return None

    return find_empty(data, "")


def validate_strong_password(password):
    if not isinstance(password, str) or not password:
        return "La contraseña no puede estar vacía."
    if not PASSWORD_REGEX.fullmatch(password):
        return (
            "La contraseña debe tener mínimo 8 caracteres e incluir una letra "
            "mayúscula, una minúscula, un número y un carácter especial "
            "(@$!%*?&#._-)."
        )
    return None


def validate_future_or_today_date(date_str):
    message = validate_iso_date(date_str)
    if message:
        return message
    if datetime.strptime(date_str, "%Y-%m-%d").date() < date.today():
        return "No puedes seleccionar una fecha anterior al día de hoy."
    return None


def validate_iso_date(date_str):
    if not isinstance(date_str, str) or not date_str:
        return "Debes seleccionar una fecha válida del calendario (AAAA-MM-DD)."
    try:
        parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return "Formato de fecha inválido. Usa el calendario en formato AAAA-MM-DD."
    if parsed_date.isoformat() != date_str:
        return "Formato de fecha inválido. Usa el calendario en formato AAAA-MM-DD."
    return None


def validate_time_slot(slot_str):
    if not isinstance(slot_str, str) or slot_str not in VALID_TIME_SLOTS:
        return "Selecciona una franja horaria válida del calendario."
    return None


def validate_time(time_str):
    if not isinstance(time_str, str):
        return "Formato de hora inválido. Usa HH:MM."
    try:
        parsed_time = datetime.strptime(time_str, "%H:%M").time()
    except ValueError:
        return "Formato de hora inválido. Usa HH:MM."
    if parsed_time.strftime("%H:%M") != time_str:
        return "Formato de hora inválido. Usa HH:MM."
    return None


def validate_media_fields(data):
    media_type = data.get("mediaType")
    media_url = data.get("mediaUrl")
    if media_type is not None and media_type not in MEDIA_TYPES:
        return "El tipo de contenido multimedia debe ser image, video o audio."
    if media_type and not media_url:
        return "Debes proporcionar mediaUrl cuando indicas mediaType."
    if media_url and not media_type:
        return "Debes indicar mediaType cuando proporcionas mediaUrl."
    return None


def validate_occupancy_type(value):
    return None if value in OCCUPANCY_TYPES else "Tipo de tenencia inválido."
