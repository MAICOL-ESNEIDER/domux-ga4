"""Documentación interactiva de la API (Swagger): la página donde se ven y se prueban todas las rutas.

Son dos direcciones públicas y de solo lectura, fuera de ``/api`` a propósito (no son rutas del contrato):

- ``/docs``: la página de Swagger UI, que lee el contrato y dibuja cada ruta con un botón «Try it out».
- ``/docs/openapi.yaml``: el contrato (``docs/api/openapi.yaml``). El servidor se despliega solo con la carpeta
  ``backend``, así que lleva su propia copia en ``backend/openapi``; una prueba (``test_api_docs.py``) comprueba
  que las dos copias sean idénticas, y ``scripts/sync_openapi.py`` la actualiza.

Al servirlo, se le agrega «este servidor» como primer servidor (ver ``THIS_SERVER``). El contrato no trae datos de nadie. Para probar rutas protegidas se entra con ``POST /api/auth/login`` y se
pega el token en el botón «Authorize».
"""

from pathlib import Path

from flask import Blueprint, Response

bp = Blueprint("docs", __name__)

SPEC_PATH = Path(__file__).resolve().parent.parent / "openapi" / "openapi.yaml"

SWAGGER_UI_VERSION = "5.17.14"

PAGE = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>API de DOMUX · Documentación</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@{version}/swagger-ui.css">
  <style>body {{ margin: 0; }}</style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@{version}/swagger-ui-bundle.js"></script>
  <script>
    window.onload = function () {{
      window.ui = SwaggerUIBundle({{
        url: "/docs/openapi.yaml",
        dom_id: "#swagger-ui",
        deepLinking: true,
        persistAuthorization: true,
        tryItOutEnabled: true
      }});
    }};
  </script>
</body>
</html>
"""


@bp.get("/docs")
def swagger_page():
    """La página de Swagger UI."""
    return Response(PAGE.format(version=SWAGGER_UI_VERSION), mimetype="text/html")


#: Primer servidor que se le agrega al contrato al servirlo: una dirección relativa («/»), que Swagger UI resuelve
#: con el servidor desde el que se abrió la página. Así «Try it out» prueba el mismo servidor (Render, local...)
#: sin que el contrato oficial tenga que nombrar ninguna dirección real.
THIS_SERVER = "servers:\n- url: /\n  description: Este servidor (el que estás usando)\n"


def contract_for_this_server():
    """El contrato oficial con «este servidor» como primera opción de la lista de servidores."""
    text = SPEC_PATH.read_text(encoding="utf-8")
    return text.replace("servers:\n", THIS_SERVER, 1)


@bp.get("/docs/openapi.yaml")
def openapi_spec():
    """El contrato de la API en YAML."""
    return Response(contract_for_this_server(), mimetype="application/yaml")
