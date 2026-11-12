"""Web de administración de DOMUX (HU-074 a HU-081, HU-087 y HU-088).

Son las páginas que la administración abre en Chrome o Edge desde el computador. Las sirve este
mismo servidor (Flask con plantillas Jinja2) y no tienen reglas propias: cada acción llama a la API
de la app dentro del mismo proceso (ver ``api.py``), así los permisos, las validaciones, la
auditoría y los mensajes son exactamente los mismos que en el celular (RN-001, RN-004, RN-008,
RN-019, RN-024 y RN-026).

Solo entra la administración (RN-006): un residente o un guardia no pasa, aunque su contraseña sea
correcta. La sesión vive en una cookie firmada que el navegador no puede leer, cada formulario
lleva su código contra CSRF y las páginas salen con cabeceras de seguridad (``security.py``).
"""

from flask import Blueprint

bp = Blueprint(
    "web",
    __name__,
    url_prefix="/web",
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)


def init_web(app):
    """Registra la web en la app: seguridad, páginas y la ruta «/»."""
    from web import security

    security.configure(app)
    # Cada módulo registra sus páginas en el blueprint al importarse.
    from web import (  # noqa: F401
        pages,
        views_auth,
        views_panel,
    )

    app.register_blueprint(bp)
