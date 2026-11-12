"""Lectura de los formularios de la web.

La web solo reúne lo que escribió la persona y lo manda a la API; las reglas (largos, formatos,
duplicados, permisos) son las de siempre y la API responde con su mensaje en español.
"""

from flask import request


def text(name):
    """El texto escrito en el campo, sin espacios sobrantes; vacío si el campo no llegó."""
    return (request.form.get(name) or "").strip()


def number(name):
    """Un número entero escrito en el campo; vacío es ``None``.

    Lo que no se entiende como número se manda tal cual para que la API lo rechace con su mensaje.
    """
    raw = text(name)
    if not raw:
        return None
    return int(raw) if raw.isascii() and raw.lstrip("-").isdigit() else raw


def checked(name):
    """Si la casilla llegó marcada (una casilla sin marcar no viaja en el formulario)."""
    return request.form.get(name) is not None


def compact(values):
    """Quita los campos sin valor: la API no acepta textos vacíos, y un campo que no llega es «sin cambio»."""
    return {key: value for key, value in values.items() if value is not None and value != ""}
