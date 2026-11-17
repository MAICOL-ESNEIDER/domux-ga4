"""El buscador general con el filtro «Buscar en» (HU-089).

Lo usan la web de administración y la app, para la administración y la portería. Las reglas de qué
ve cada rol están en services/global_search.py.
"""

from flask import Blueprint, g, jsonify, request

from auth import role_required, token_required
from services import global_search

bp = Blueprint("search", __name__, url_prefix="/api")


@bp.get("/search")
@token_required
@role_required("ADMIN", "GUARD")
def search():
    """Busca el texto ``q`` en el lugar ``in`` (``todo`` si no se dice) y devuelve los grupos."""
    return jsonify(global_search.search(request.args.get("q"), request.args.get("in"), g.current_user))
