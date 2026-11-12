"""Inicio de la web: el panel de pendientes (HU-081).

Muestra lo que la administración debe atender hoy y lleva a cada lista. Los números salen de
``GET /api/admin/summary``; aquí solo se dibujan.
"""

from flask import flash, g, render_template

from time_utils import colombia_today
from web import bp
from web.api import Api
from web.security import login_required


@bp.get("/")
@login_required
def panel():
    result = Api(g.web_user).get("/api/admin/summary")
    if not result.ok:
        flash(result.error, "error")
    return render_template(
        "web/panel.html",
        loaded=result.ok,
        counts=result.get("counts", {}),
        urgent_pqrs=result.get("urgentPqrs", []),
        pending_reservations=result.get("pendingReservations", []),
        today=colombia_today(),
    )
