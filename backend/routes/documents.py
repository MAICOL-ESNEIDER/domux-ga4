"""Rutas de los documentos de la unidad (DEC-032).

La administración sube el manual de convivencia, las reglas, los presupuestos aprobados, los históricos de
gastos y demás documentos, y marca quién los puede ver (propietarios, arrendatarios, otros residentes y
portería). Cada persona consulta solo los que le marcaron; un documento que no es suyo responde 404, como si
no existiera. Las reglas están en services/document_service.py.
"""

from flask import Blueprint, g, jsonify, request

from auth import role_required, token_required
from models import DOCUMENT_AUDIENCES, DOCUMENT_CATEGORIES
from routes.common import bool_arg, json_object, save_changes
from services import document_service as documents

bp = Blueprint("documents", __name__, url_prefix="/api")


def _is_admin():
    return g.current_user.role == "ADMIN"


@bp.get("/documents")
@token_required
@role_required("ADMIN", "GUARD", "RESIDENT")
def list_documents():
    """Los documentos que la persona puede ver, los más nuevos primero y sin el archivo.

    La administración ve todos, con a quién se lo muestra, y con ``includeRetired=true`` también los retirados.
    ``category`` deja solo un tipo de documento. También llegan los tipos y los públicos que existen.
    """
    admin = _is_admin()
    include_retired = bool_arg("includeRetired") is True and admin
    found = documents.visible_documents(
        g.current_user, include_retired=include_retired, category=request.args.get("category") or None,
    )
    return jsonify({
        "documents": [document.to_dict(admin=admin) for document in found],
        "categories": [{"key": key, "label": label} for key, label in DOCUMENT_CATEGORIES.items()],
        "audiences": [{"key": key, "label": label} for key, label in DOCUMENT_AUDIENCES.items()],
    })


@bp.get("/documents/<int:document_id>")
@token_required
@role_required("ADMIN", "GUARD", "RESIDENT")
def get_document(document_id):
    """Un documento, sin el archivo. Si la persona no lo puede ver, responde 404."""
    document = documents.find_visible(g.current_user, document_id)
    return jsonify({"document": document.to_dict(admin=_is_admin())})


@bp.get("/documents/<int:document_id>/file")
@token_required
@role_required("ADMIN", "GUARD", "RESIDENT")
def get_document_file(document_id):
    """El archivo del documento (PDF o imagen). Responde 304 si no cambió desde la última vez que se pidió."""
    return documents.file_response(documents.find_visible(g.current_user, document_id))


@bp.post("/documents")
@token_required
@role_required("ADMIN")
def upload_document():
    """Sube un documento nuevo y marca quién lo puede ver (solo la administración).

    El archivo llega como «data:…;base64,…» (PDF, PNG, JPG o WebP de hasta 6 MB) y se revisa por sus primeros
    bytes. Con ``notify: true`` se avisa a quienes lo pueden ver.
    """
    document, notified = documents.create_document(json_object(required=True), g.current_user)
    save_changes("Ya hay un documento con ese título.")
    return jsonify({
        "message": "Documento publicado",
        "document": document.to_dict(admin=True),
        "notified": notified,
    }), 201


@bp.put("/documents/<int:document_id>")
@token_required
@role_required("ADMIN")
def update_document(document_id):
    """Cambia el título, la descripción, el tipo o quién ve un documento (solo la administración)."""
    document = documents.update_document(documents.find_any(document_id), json_object(required=True), g.current_user)
    save_changes("Ya hay un documento con ese título.")
    return jsonify({"message": "Documento actualizado", "document": document.to_dict(admin=True)})


@bp.delete("/documents/<int:document_id>")
@token_required
@role_required("ADMIN")
def retire_document(document_id):
    """Retira un documento: deja de verse para los demás, pero no se borra (ADR-013)."""
    document = documents.retire_document(documents.find_any(document_id), g.current_user)
    save_changes()
    return jsonify({"message": "Documento retirado", "document": document.to_dict(admin=True)})


@bp.post("/documents/<int:document_id>/restore")
@token_required
@role_required("ADMIN")
def restore_document(document_id):
    """Vuelve a publicar un documento retirado, con los mismos públicos que tenía."""
    document = documents.restore_document(documents.find_any(document_id), g.current_user)
    save_changes("Ya hay un documento con ese título.")
    return jsonify({"message": "Documento publicado de nuevo", "document": document.to_dict(admin=True)})
