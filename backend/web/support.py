"""Ayudas que comparten las páginas de la web: avisos de resultado y paginación."""

from flask import flash


def flash_result(result, success_default="Listo."):
    """Deja el resultado de una llamada a la API como aviso para la próxima página.

    Si salió bien, el mensaje de éxito que mandó la API (o el de por defecto); si no, el mensaje de
    error en español que mandó la API. Devuelve True si salió bien.
    """
    if result.ok:
        flash(result.message or success_default, "success")
        return True
    flash(result.error, "error")
    return False


def paginate(items, page, size=25):
    """Corta una lista en páginas: devuelve ``(página, total de páginas, filas de esa página)``.

    Una página fuera de rango se lleva a la primera o a la última, así nunca se ve una tabla vacía
    por un enlace viejo.
    """
    total_pages = max(1, (len(items) + size - 1) // size)
    page = min(max(page or 1, 1), total_pages)
    start = (page - 1) * size
    return page, total_pages, items[start:start + size]
