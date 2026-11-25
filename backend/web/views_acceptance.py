"""La pantalla «Acepto» de la web: la administración lee y acepta los textos legales al entrar por primera vez.

No tiene reglas propias: el estado y la aceptación los manejan ``GET /api/auth/legal-acceptance`` y
``POST /api/auth/accept-legal``, las mismas rutas de la app. La web solo muestra los textos completos, una
casilla y el botón. Mientras la persona no acepte, ``login_required`` la trae de vuelta a esta página.
"""

from urllib.parse import quote

from flask import flash, g, redirect, render_template, request, url_for

from web import bp
from web.api import Api
from web.forms import checked
from web.security import login_required, safe_next


@bp.get("/acepto")
@login_required
def legal_accept():
    status = Api(g.web_user).get("/api/auth/legal-acceptance")
    if not status.ok:
        flash(status.error, "error")
        return redirect(url_for("web.login"))
    if not status.get("required"):
        return redirect(safe_next(request.args.get("next")) or url_for("web.panel"))
    documents = []
    for summary in status.get("documents", []):
        document = Api().get(f"/api/legal/{quote(summary['slug'], safe='')}")
        documents.append(document.data if document.ok else {**summary, "blocks": []})
    return render_template(
        "web/legal_accept.html", documents=documents, version=status.get("version"),
        next_url=safe_next(request.args.get("next")),
    )


@bp.post("/acepto")
@login_required
def legal_accept_submit():
    next_url = safe_next(request.form.get("next"))
    result = Api(g.web_user).post("/api/auth/accept-legal", {
        "accepted": checked("accepted"), "version": request.form.get("version", ""),
    })
    if not result.ok:
        flash(result.error, "error")
        return redirect(url_for("web.legal_accept", next=next_url))
    flash(result.get("message") or "Quedó registrada tu aceptación.", "success")
    return redirect(next_url or url_for("web.panel"))
