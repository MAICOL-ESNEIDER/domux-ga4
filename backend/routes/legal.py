"""Documentos legales: política de datos, términos, cookies y los demás textos que pide la ley.

Son las dos únicas rutas de la API, junto con el estado del servicio y el inicio de sesión, que se abren
sin sesión. Es a propósito: la persona debe poder leer cómo se tratan sus datos antes de entrar (la pantalla
de inicio de sesión de la app y de la web enlaza aquí). No devuelven datos de nadie, solo los textos de la
carpeta ``backend/legal`` (ver ``services/legal_service.py``).
"""

from flask import Blueprint, jsonify

from errors import error_response
from services import legal_service

bp = Blueprint("legal", __name__, url_prefix="/api")


@bp.get("/legal")
def list_documents():
    """La lista de documentos con su estado («pendiente» o «vigente»), sin el texto."""
    return jsonify({"documents": legal_service.list_documents()})


@bp.get("/legal/<slug>")
def get_document(slug):
    """Un documento completo, con su texto convertido en bloques (títulos, párrafos y listas)."""
    document = legal_service.get_document(slug)
    if document is None:
        return error_response(404, "No existe ese documento legal.")
    return jsonify(document)
