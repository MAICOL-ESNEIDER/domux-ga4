"""Textos de pantalla de la web: estados, plazos y fechas escritos igual que en la app.

Son funciones puras (sin base de datos ni Flask): reciben lo que respondió la API y devuelven el
texto que lee la administración. Los tonos de los avisos son los de la app (verde, ámbar y rojo) y
siempre van acompañados de una palabra, para que el color no sea lo único que informa (HU-086).
"""

from datetime import date, datetime

#: Estado de una PQRS: texto y tono. Como en la app, «abierta» es la que más urge.
PQRS_STATUSES = {
    "abierta": ("Abierta", "alert"),
    "en_proceso": ("En proceso", "progress"),
    "resuelta": ("Resuelta", "success"),
}

RESERVATION_STATUSES = {
    "pendiente": ("Pendiente", "progress"),
    "activa": ("Activa", "success"),
    "aprobada": ("Aprobada", "success"),
    "rechazada": ("Rechazada", "alert"),
    "cancelada": ("Cancelada", "alert"),
}

#: Categoría de un comunicado (HU-058): texto y tono. Las claves son las de ``models.ANNOUNCEMENT_CATEGORIES``.
ANNOUNCEMENT_CATEGORIES = {
    "mantenimiento": ("Mantenimiento", "progress"),
    "urgente": ("Urgente", "alert"),
    "asamblea": ("Asamblea", "neutral"),
    "seguridad": ("Seguridad", "progress"),
    "zonas_comunes": ("Zonas comunes", "neutral"),
}

#: Semáforo del plazo de una PQRS (HU-073).
SEMAPHORES = {
    "verde": ("En plazo", "success"),
    "amarillo": ("Por vencer", "progress"),
    "rojo": ("Vencida", "alert"),
}

#: De qué trata cada notificación.
NOTIFICATION_TYPES = {
    "pqrs": "PQRS",
    "reservation": "Reservas",
    "announcement": "Comunicados",
    "package": "Paquetes",
    "visit": "Visitas",
    "vehicle": "Vehículos",
    "general": "General",
}

_KINDS = {
    "pqrs": PQRS_STATUSES,
    "reservation": RESERVATION_STATUSES,
    "semaphore": SEMAPHORES,
    "announcement": ANNOUNCEMENT_CATEGORIES,
}


def badge_info(kind, value):
    """El texto y el tono de un aviso de estado: ``badge_info("pqrs", "abierta")``."""
    label, tone = _KINDS.get(kind, {}).get(value, (str(value or "—").replace("_", " ").capitalize(), "neutral"))
    return {"label": label, "tone": tone}


def business_days_text(days):
    """«1 día hábil» o «5 días hábiles»."""
    return "1 día hábil" if days == 1 else f"{days} días hábiles"


def date_es(value):
    """Una fecha como se escribe en Colombia: 13/11/2026 (y la hora, si la trae: 13/11/2026 14:30).

    Recibe una fecha, un ``AAAA-MM-DD`` o la marca ``AAAA-MM-DD HH:MM`` que entrega la API. Lo que
    no se puede leer se devuelve igual, sin romper la página.
    """
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    text = str(value)
    try:
        day = date.fromisoformat(text[:10])
    except ValueError:
        return text
    rest = text[10:].strip()
    return day.strftime("%d/%m/%Y") + (f" {rest}" if rest else "")


def deadline_text(days_remaining, due_date):
    """El plazo de una PQRS con palabras: «Vencida hace 2 días hábiles» o «Quedan 5 días hábiles»."""
    if days_remaining is None:
        return ""
    due = date_es(due_date)
    if days_remaining < 0:
        return f"Vencida hace {business_days_text(-days_remaining)}" + (f" · era el {due}" if due else "")
    if days_remaining == 0:
        return "Vence hoy"
    return f"Quedan {business_days_text(days_remaining)}" + (f" · vence el {due}" if due else "")


def notification_type(value):
    """El tema de una notificación en palabras."""
    return NOTIFICATION_TYPES.get(value or "general", "General")


def slot_length_text(minutes):
    """La duración de una franja con palabras: «30 minutos», «1 hora», «1 hora y media» o «2 horas»."""
    if minutes < 60:
        return f"{minutes} minutos"
    hours, rest = divmod(minutes, 60)
    base = "1 hora" if hours == 1 else f"{hours} horas"
    if rest == 0:
        return base
    return f"{base} y media" if rest == 30 else f"{base} y {rest} minutos"


def plural(count, singular, plural_form):
    """«1 paquete» o «3 paquetes»."""
    return f"{count} {singular if count == 1 else plural_form}"
