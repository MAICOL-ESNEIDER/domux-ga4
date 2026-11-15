"""Archivo histórico y copia de respaldo (ADR-013, DEC-090 y DEC-103).

Aquí el administrador ve qué registros ya cumplieron su plazo, los pasa al archivo histórico,
descarga cada archivo (JSON comprimido) con su huella SHA-256, lo vuelve a cargar si hace falta y
descarga una copia de respaldo de la base. Todo queda anotado en la auditoría y nada se borra.
"""

import json

from flask import Response, abort, flash, g, redirect, render_template, url_for

from extensions import db
from models import HistoryArchive
from services import history_archive_service as archive_service
from services.audit_service import add_audit_log
from time_utils import colombia_today
from web import bp
from web.forms import checked
from web.security import login_required, password_confirmation_required


def _download(content, filename, mimetype):
    """Una descarga que no se abre en el navegador ni se guarda en caché."""
    response = Response(content, mimetype=mimetype)
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Cache-Control"] = "no-store"
    return response


def _size_text(size):
    if size < 1024:
        return f"{size} bytes"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB".replace(".", ",")
    return f"{size / (1024 * 1024):.1f} MB".replace(".", ",")


def _archive_or_404(archive_id):
    archive = db.session.get(HistoryArchive, archive_id)
    if archive is None:
        abort(404)
    return archive


@bp.get("/archivo-historico")
@login_required
def archive_page():
    pending = archive_service.pending_summary()
    archives = [
        {
            "row": archive,
            "label": archive_service.kind_label(archive.kind),
            "size": _size_text(archive.size_bytes),
        }
        for archive in archive_service.list_archives()
    ]
    return render_template(
        "web/archive.html",
        pending=pending,
        pending_total=sum(item["count"] for item in pending),
        archives=archives,
    )


@bp.post("/archivo-historico/archivar")
@login_required
def archive_run():
    if not checked("confirm"):
        flash("Marca la casilla para confirmar que quieres pasar esos registros al archivo.", "error")
        return redirect(url_for("web.archive_page"))
    try:
        result = archive_service.run_archive(actor=g.web_user)
    except archive_service.ArchiveError as error:
        flash(str(error), "error")
        return redirect(url_for("web.archive_page"))
    if result["archives"]:
        flash(
            f"Listo: {result['records']} registros pasaron a {result['archives']} archivos. "
            "Cada archivo se comprobó antes de sacar los registros de la base.",
            "success",
        )
    else:
        flash("No hay registros que ya hayan cumplido su plazo.", "info")
    return redirect(url_for("web.archive_page"))


@bp.get("/archivo-historico/<int:archive_id>/descargar")
@login_required
@password_confirmation_required("web.archive_page")
def archive_download(archive_id):
    archive = _archive_or_404(archive_id)
    if not archive_service.verify_archive(archive):
        flash("Este archivo no coincide con su huella: pudo haber sido cambiado. No se descargó.", "error")
        return redirect(url_for("web.archive_page"))
    content = archive_service.archive_content(archive)
    add_audit_log(
        "archive", archive.id, "history_downloaded",
        {"tipo": archive_service.kind_label(archive.kind), "mes": archive.period, "sha256": archive.sha256},
        actor=g.web_user,
    )
    db.session.commit()
    return _download(content, archive.file_name, "application/gzip")


@bp.post("/archivo-historico/<int:archive_id>/cargar")
@login_required
def archive_restore(archive_id):
    archive = _archive_or_404(archive_id)
    try:
        restored = archive_service.restore_archive(archive, actor=g.web_user)
    except archive_service.ArchiveError as error:
        flash(str(error), "error")
        return redirect(url_for("web.archive_page"))
    flash(
        f"Listo: {restored} registros volvieron a la base. El archivo se conserva; "
        "la próxima vez que archives, vuelven a salir en un archivo nuevo.",
        "success",
    )
    return redirect(url_for("web.archive_page"))


@bp.get("/archivo-historico/manifiesto")
@login_required
def archive_manifest():
    content = json.dumps(archive_service.manifest(), ensure_ascii=False, indent=2).encode("utf-8")
    return _download(content, f"DOMUX_manifiesto_archivo_{colombia_today().isoformat()}.json", "application/json")


@bp.get("/archivo-historico/copia")
@login_required
@password_confirmation_required("web.archive_page")
def archive_backup():
    try:
        spool, sha256, counts = archive_service.write_backup()
    except Exception:
        db.session.rollback()
        flash("No se pudo armar la copia de respaldo. Inténtalo de nuevo.", "error")
        return redirect(url_for("web.archive_page"))
    add_audit_log(
        "export", None, "copia_respaldo",
        {"lista": "Copia de respaldo", "sha256": sha256, "filas": sum(counts.values())},
        actor=g.web_user,
    )
    db.session.commit()
    filename = f"DOMUX_copia_{colombia_today().isoformat()}_{sha256[:12]}.json.gz"
    response = _download(spool.read(), filename, "application/gzip")
    spool.close()
    response.headers["X-Content-SHA256"] = sha256
    return response
