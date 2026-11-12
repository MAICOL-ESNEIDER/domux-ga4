"""Reservas en la web (HU-079): aprobar o rechazar las que esperan la decisión de la administración."""

from flask import flash, g, redirect, request, url_for

from web import bp
from web.api import Api
from web.security import login_required, safe_next
from web.support import flash_result

#: Lo que la administración puede decidir sobre una reserva pendiente.
DECISIONS = {"aprobada": "aprobada", "rechazada": "rechazada"}


@bp.post("/reservas/<int:res_id>/decision")
@login_required
def reservation_decide(res_id):
    """Aprueba o rechaza una reserva con las mismas reglas de la app (RN-019: sin cruces)."""
    decision = DECISIONS.get(request.form.get("decision", ""))
    if decision is None:
        flash("Elige si quieres aprobar o rechazar la reserva.", "error")
    else:
        result = Api(g.web_user).put(f"/api/reservations/{res_id}/status", {"status": decision})
        if result.ok:
            flash(f"Reserva {decision}. Se le avisó al residente.", "success")
        else:
            flash_result(result)
    return redirect(safe_next(request.form.get("next")) or url_for("web.panel"))
