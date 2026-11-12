"""Textos de pantalla de la web: estados, plazos y fechas escritos igual que en la app.

Son funciones puras (sin base de datos ni Flask): reciben lo que respondió la API y devuelven el
texto que lee la administración. Los tonos de los avisos son los de la app (verde, ámbar y rojo) y
siempre van acompañados de una palabra, para que el color no sea lo único que informa (HU-086).
"""

from datetime import date, datetime

from models import UNCLAIMED_ORANGE_HOURS, UNCLAIMED_RED_HOURS

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

#: Estado de un paquete (HU-088): «pendiente» es el que ya está en la portería esperando a su dueño.
PACKAGE_STATUSES = {
    "por_llegar": ("Por llegar", "neutral"),
    "pendiente": ("En portería", "progress"),
    "entregado": ("Entregado", "success"),
}

#: Aviso de un paquete que lleva mucho tiempo sin reclamar (RN-018): naranja y rojo, siempre con palabras.
PACKAGE_ALERTS = {
    "naranja": (f"Más de {UNCLAIMED_ORANGE_HOURS} h sin reclamar", "progress"),
    "rojo": (f"Más de {UNCLAIMED_RED_HOURS} h sin reclamar", "alert"),
}

#: Autorización de una visita (HU-088): lo que decidió el residente o se confirmó por llamada.
VISIT_APPROVALS = {
    "pendiente": ("Esperando autorización", "progress"),
    "aprobada": ("Aprobada", "success"),
    "rechazada": ("Rechazada", "alert"),
}

#: Tipo de visita, como lo elige el guardia al registrarla.
VISIT_TYPES = {
    "visitante": "Visitante",
    "domiciliario": "Domiciliario",
    "contratista": "Contratista",
}

#: Qué pasó en cada paso del historial de una visita.
VISIT_EVENTS = {
    "solicitud": "Llegó a la portería y se pidió la autorización",
    "aprobada": "Se aprobó el ingreso",
    "rechazada": "Se rechazó el ingreso",
    "entrada": "Entró a la unidad",
    "salida": "Salió de la unidad",
}

#: Cómo se autorizó o se registró un paso de la visita.
AUTHORIZATION_METHODS = {
    "app": "desde la app",
    "llamada": "por llamada a la portería",
    "qr": "con el código QR del residente",
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
    "package": PACKAGE_STATUSES,
    "package_alert": PACKAGE_ALERTS,
    "visit": VISIT_APPROVALS,
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


def duration_text(minutes):
    """Un tiempo con palabras: «45 min», «2 h 15 min», «3 h», «1 día» o «2 días 3 h». Sin dato, vacío."""
    if minutes is None:
        return ""
    minutes = max(0, int(minutes))
    days, rest = divmod(minutes, 24 * 60)
    hours, mins = divmod(rest, 60)
    if days:
        base = "1 día" if days == 1 else f"{days} días"
        return f"{base} {hours} h" if hours else base
    if hours:
        return f"{hours} h {mins} min" if mins else f"{hours} h"
    return f"{mins} min"


def visit_type_text(value):
    """El tipo de visita en palabras: «Domiciliario»."""
    return VISIT_TYPES.get(value) or str(value or "—").replace("_", " ").capitalize()


def visit_event_text(value):
    """Lo que pasó en un paso del historial de una visita: «Entró a la unidad»."""
    return VISIT_EVENTS.get(value) or str(value or "—").replace("_", " ").capitalize()


def authorization_method_text(value, capital=False):
    """Cómo se autorizó un paso: «desde la app», «por llamada a la portería»… (con ``capital``, empieza en mayúscula)."""
    text = AUTHORIZATION_METHODS.get(value, "")
    return text[:1].upper() + text[1:] if capital else text
