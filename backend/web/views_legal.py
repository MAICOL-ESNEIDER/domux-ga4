"""Documentos legales en la web: política de datos, términos, cookies y los demás.

Son páginas públicas a propósito: se leen antes de iniciar sesión (la página de inicio de sesión enlaza
aquí) y también con la sesión abierta. Como el resto de la web, no tienen reglas propias: piden los textos a
la misma API que usa la app (``GET /api/legal``), así que lo que se lee aquí es lo mismo que en el celular.
"""

from urllib.parse import quote

from flask import abort, g, render_template

from web import bp
from web.api import Api
from web.security import current_admin


def _show_admin_menu():
    """Si quien lee es un administrador con la sesión abierta, la página sale con su menú de siempre."""
    user, _reason = current_admin()
    if user is not None:
        g.web_user = user


@bp.get("/legal")
def legal_index():
    """La lista de documentos legales con su estado."""
    _show_admin_menu()
    result = Api().get("/api/legal")
    if not result.ok:
        abort(result.status)
    return render_template("web/legal_index.html", documents=result.get("documents", []))


@bp.get("/legal/<slug>")
def legal_document(slug):
    """Un documento legal completo."""
    _show_admin_menu()
    result = Api().get(f"/api/legal/{quote(slug, safe='')}")
    if not result.ok:
        abort(result.status)
    return render_template("web/legal_document.html", document=result.data)
