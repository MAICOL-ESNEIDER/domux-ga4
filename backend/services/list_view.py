"""Lo que comparten las listas livianas de la API (``?view=summary``).

Las listas de siempre (PQRS y reservas) entregan todas las filas de una vez, con sus conversaciones y
sus adjuntos en base64: sirven para el celular de un residente, pero no para la web de administración.
Cada una tiene una vista liviana, paginada y sin adjuntos, que se pide con ``view=summary``.
"""

from errors import ApiError

#: El único valor de ``view`` que existe además de la vista completa.
SUMMARY_VIEW = "summary"


def parse_view(value):
    """La vista pedida con ``?view=``: None (la completa de siempre) o «summary» (la liviana)."""
    if value in (None, ""):
        return None
    if value != SUMMARY_VIEW:
        raise ApiError("El parámetro 'view' solo acepta el valor 'summary'.")
    return SUMMARY_VIEW


def full_name(first, last):
    """El nombre y el apellido de una persona, sin espacios de más."""
    return f"{(first or '').strip()} {(last or '').strip()}".strip()
