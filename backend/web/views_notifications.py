"""Notificaciones en la web (HU-064): la misma bandeja de la app, para leerla en el computador."""

from flask import flash, g, redirect, render_template, request, url_for

from web import bp
from web.api import Api
from web.security import login_required
from web.support import flash_result, paginate

PAGE_SIZE = 20


@bp.get("/notificaciones")
@login_required
def notifications_list():
    result = Api(g.web_user).get("/api/notifications")
    if not result.ok:
        flash(result.error, "error")
    items = result.get("notifications", [])
    unread_total = sum(1 for item in items if not item["isRead"])
    only_unread = request.args.get("filtro") == "sin-leer"
    if only_unread:
        items = [item for item in items if not item["isRead"]]
    page, pages, rows = paginate(items, request.args.get("page", 1, type=int), PAGE_SIZE)
    return render_template(
        "web/notifications.html",
        rows=rows, page=page, pages=pages, only_unread=only_unread, unread_total=unread_total,
    )


@bp.post("/notificaciones/<int:notification_id>/leida")
@login_required
def notification_read(notification_id):
    flash_result(Api(g.web_user).put(f"/api/notifications/{notification_id}/read"))
    return redirect(url_for("web.notifications_list", **_kept_filters()))


@bp.post("/notificaciones/leidas")
@login_required
def notifications_read_all():
    flash_result(Api(g.web_user).put("/api/notifications/read-all"))
    return redirect(url_for("web.notifications_list"))


def _kept_filters():
    """Los filtros de la lista que se conservan al marcar una notificación (viajan en el formulario)."""
    return {"filtro": "sin-leer"} if request.form.get("filtro") == "sin-leer" else {}
