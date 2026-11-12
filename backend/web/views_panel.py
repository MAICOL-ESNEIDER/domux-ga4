"""Inicio de la web: el panel de pendientes (HU-081)."""

from flask import render_template

from web import bp
from web.security import login_required


@bp.get("/")
@login_required
def panel():
    return render_template("web/panel.html")
