"""Preferencias de la web: cómo ve cada persona la web en su equipo.

La apariencia (Automático, Mixto u Oscuro), el tamaño del texto y las cuentas recordadas se guardan en
el navegador de cada persona (ver ``static/domux.js``): el servidor no guarda nada de esto y por eso
esta página no llama a la API ni cambia datos. Sin JavaScript solo se muestran las opciones por defecto.
"""

from flask import render_template

from web import bp
from web.security import login_required


@bp.get("/preferencias")
@login_required
def preferences():
    return render_template("web/preferences.html")
