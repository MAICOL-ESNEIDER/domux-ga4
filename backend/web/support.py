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


def fetch_all(api, path, key, max_pages=20, **params):
    """Todas las filas de una lista paginada de la API, página por página, para llenar una lista desplegable.

    Devuelve ``(filas, fallo)``: ``fallo`` es la respuesta con error si alguna página no cargó.
    """
    rows = []
    for page in range(1, max_pages + 1):
        result = api.get(path, page=page, pageSize=100, **params)
        if not result.ok:
            return rows, result
        rows.extend(result.get(key, []))
        if page >= result.get("totalPages", 1):
            break
    return rows, None
