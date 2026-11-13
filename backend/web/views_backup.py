"""Respaldo legal en Excel: el expediente completo y archivar lo terminado.

Antes estaba en la app; ahora se hace solo aquí, en el computador, para que ningún Excel con datos
de la unidad quede guardado en un celular. El respaldo trae las PQRS con su conversación, las
reservas y el registro de auditoría (lo arma la API, ``/api/admin/export/legal-report``); cada
descarga queda anotada en la auditoría. Archivar no borra nada: las PQRS resueltas y las reservas
que ya pasaron salen de la bandeja del día a día y siguen en el respaldo.
"""

import base64
import binascii

from flask import flash, g, redirect, render_template, url_for

from extensions import db
from services.audit_service import add_audit_log
from web import bp
from web.api import Api
from web.exports import xlsx_response
from web.forms import checked
from web.security import login_required


@bp.get("/respaldo")
@login_required
def backup_page():
    return render_template("web/backup.html")


@bp.get("/respaldo/descargar")
@login_required
def backup_download():
    result = Api(g.web_user).get("/api/admin/export/legal-report")
    if not result.ok:
        flash(result.error, "error")
        return redirect(url_for("web.backup_page"))
    try:
        content = base64.b64decode(result.get("base64") or "", validate=True)
    except (binascii.Error, ValueError):
        content = b""
    if not content:
        flash("El servidor no entregó el respaldo. Inténtalo de nuevo.", "error")
        return redirect(url_for("web.backup_page"))
    counts = {key: result.get(key) for key in ("pqrsCount", "reservationsCount", "auditLogsCount")}
    add_audit_log("export", None, "respaldo_legal", {"lista": "Respaldo legal", **counts}, actor=g.web_user)
    db.session.commit()
    return xlsx_response(content, result.get("fileName") or "Respaldo_Legal_DOMUX.xlsx")


@bp.post("/respaldo/archivar")
@login_required
def backup_archive():
    if not checked("confirm"):
        flash("Marca la casilla para confirmar que quieres archivar lo terminado.", "error")
        return redirect(url_for("web.backup_page"))
    result = Api(g.web_user).post("/api/admin/archive-history")
    if result.ok:
        flash(
            f"Listo: se archivaron {result.get('archivedPqrsCount', 0)} PQRS y "
            f"{result.get('archivedReservationsCount', 0)} reservas. Siguen guardadas y se ven con «Archivadas».",
            "success",
        )
    else:
        flash(result.error, "error")
    return redirect(url_for("web.backup_page"))
