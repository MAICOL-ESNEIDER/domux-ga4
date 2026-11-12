"""Cliente interno de la API para la web de administración.

La web no repite ninguna regla: para leer o cambiar algo llama a la misma API que usa la app,
dentro del mismo proceso (sin red) y con el token del administrador de la sesión. Así los permisos
(ADR-015), las validaciones, la auditoría y los mensajes son los de siempre, y lo que se arregla
en la API queda arreglado también en la web.
"""

from dataclasses import dataclass, field

from flask import current_app

from auth import generate_token


@dataclass
class ApiResult:
    """Lo que respondió la API: el código HTTP, el cuerpo JSON y las cabeceras."""

    status: int
    data: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)

    @property
    def ok(self):
        return 200 <= self.status < 300

    @property
    def message(self):
        """El mensaje de éxito que trae la respuesta, si lo trae."""
        return self.data.get("message") if isinstance(self.data, dict) else None

    @property
    def error(self):
        """El mensaje de error en español que la API mandó, o uno general si no mandó ninguno."""
        if self.ok:
            return None
        if isinstance(self.data, dict) and self.data.get("error"):
            return self.data["error"]
        return "No se pudo completar la acción. Inténtalo de nuevo."

    def get(self, key, default=None):
        """Atajo para leer un dato del cuerpo."""
        return self.data.get(key, default) if isinstance(self.data, dict) else default


def _clean(params):
    """Quita los filtros vacíos para no mandarlos a la API (un texto vacío no es un filtro)."""
    return {
        key: value
        for key, value in (params or {}).items()
        if value is not None and value != ""
    }


class Api:
    """Las llamadas a la API en nombre de un usuario (el administrador de la sesión)."""

    def __init__(self, user=None):
        self.user = user

    def request(self, method, path, params=None, body=None):
        headers = {}
        if self.user is not None:
            headers["Authorization"] = f"Bearer {generate_token(self.user)}"
        client = current_app.test_client()
        response = client.open(
            path,
            method=method,
            query_string=_clean(params),
            json=body,
            headers=headers,
        )
        data = response.get_json(silent=True)
        return ApiResult(response.status_code, data if isinstance(data, dict) else {}, dict(response.headers))

    def get(self, path, **params):
        return self.request("GET", path, params=params)

    def post(self, path, body=None):
        return self.request("POST", path, body=body if body is not None else {})

    def put(self, path, body=None):
        return self.request("PUT", path, body=body if body is not None else {})

    def delete(self, path):
        return self.request("DELETE", path)
