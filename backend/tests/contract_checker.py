"""Ayuda de las pruebas del contrato de la API (docs/api/openapi.yaml).

El contrato es un archivo OpenAPI que dice qué rutas tiene el servidor y cómo son sus datos. Esta ayuda lo
carga y revisa que un dato real (lo que respondió el servidor, o lo que se le envió) cumpla el esquema que el
contrato declara. No es un validador completo de OpenAPI: entiende justo lo que usa este contrato (tipos,
nulos, listas de valores, claves obligatorias, patrones y las combinaciones ``oneOf`` y ``allOf``).

Una regla es más estricta que lo habitual a propósito: una clave que el servidor manda y el esquema no
nombra es un error. Así, si alguien agrega un dato a una respuesta y se olvida del contrato, la prueba falla.
"""

import re
from datetime import date
from pathlib import Path

import yaml

#: El contrato vive en la raíz del repositorio, dos carpetas arriba de ``backend/tests``.
SPEC_PATH = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.yaml"

#: Los métodos HTTP que el contrato describe (HEAD y OPTIONS los pone Flask solo).
METHODS = ("get", "post", "put", "delete", "patch")


def load_spec(path=SPEC_PATH):
    """El contrato leído del archivo."""
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def openapi_path(rule):
    """La dirección de una ruta de Flask escrita como OpenAPI: ``/api/x/<int:id>`` pasa a ``/api/x/{id}``."""
    return re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", str(rule))


class Contract:
    """El contrato cargado, con las preguntas que hacen las pruebas."""

    def __init__(self, spec=None):
        self.spec = spec if spec is not None else load_spec()

    # --- Recorrer el contrato -------------------------------------------------------------------

    def resolve(self, node):
        """Sigue los ``$ref`` hasta llegar al contenido; si no es un ``$ref``, lo devuelve igual."""
        seen = 0
        while isinstance(node, dict) and "$ref" in node:
            node = self.pointer(node["$ref"])
            seen += 1
            if seen > 20:
                raise ValueError("Referencias que se repiten sin fin en el contrato")
        return node

    def pointer(self, ref):
        """El contenido al que apunta una referencia como ``#/components/schemas/User``."""
        if not ref.startswith("#/"):
            raise ValueError(f"Solo se entienden referencias internas: {ref}")
        node = self.spec
        for part in ref[2:].split("/"):
            node = node[part]
        return node

    def operations(self):
        """Todas las operaciones como ``(método en mayúsculas, dirección, operación)``."""
        for path, item in self.spec["paths"].items():
            for method in METHODS:
                if method in item:
                    yield method.upper(), path, item[method]

    def operation(self, method, path):
        """La operación de ese método y dirección, o None si el contrato no la tiene."""
        return self.spec["paths"].get(path, {}).get(method.lower())

    def response_schema(self, operation, status, content_type="application/json"):
        """El esquema que el contrato da a la respuesta de ese código, o None si no declara contenido."""
        response = operation["responses"].get(str(status))
        if response is None:
            return None
        response = self.resolve(response)
        media = response.get("content", {}).get(content_type)
        return media.get("schema") if media else None

    def response_content_types(self, operation, status):
        response = operation["responses"].get(str(status))
        return set(self.resolve(response).get("content", {})) if response is not None else set()

    def request_schema(self, operation):
        """El esquema del cuerpo JSON que pide la operación, o None si no lleva cuerpo."""
        body = operation.get("requestBody")
        if not body:
            return None
        media = self.resolve(body).get("content", {}).get("application/json")
        return media.get("schema") if media else None

    # --- Revisar un dato contra un esquema ------------------------------------------------------

    def check(self, value, schema, where="cuerpo"):
        """Lista de problemas que tiene ``value`` frente a ``schema`` (vacía si cumple)."""
        errors = []
        self._walk(value, schema, where, errors)
        return errors

    def _walk(self, value, schema, where, errors):
        schema = self.resolve(schema)
        if value is None:
            if not schema.get("nullable"):
                errors.append(f"{where}: no puede ser nulo")
            return
        if "oneOf" in schema or "anyOf" in schema:
            self._any_of(value, schema.get("oneOf") or schema.get("anyOf"), where, errors)
            return
        for part in schema.get("allOf", ()):
            self._walk(value, part, where, errors)
        kind = schema.get("type")
        if kind and not self._is_type(value, kind):
            errors.append(f"{where}: debía ser {kind} y es {type(value).__name__} ({_short(value)})")
            return
        if "enum" in schema and value not in schema["enum"]:
            errors.append(f"{where}: {_short(value)} no está entre los valores {schema['enum']}")
        if kind == "string":
            self._check_string(value, schema, where, errors)
        elif kind in ("integer", "number"):
            if "minimum" in schema and value < schema["minimum"]:
                errors.append(f"{where}: {value} es menor que {schema['minimum']}")
            if "maximum" in schema and value > schema["maximum"]:
                errors.append(f"{where}: {value} es mayor que {schema['maximum']}")
        elif kind == "array":
            self._check_array(value, schema, where, errors)
        elif kind == "object":
            self._check_object(value, schema, where, errors)

    def _any_of(self, value, options, where, errors):
        attempts = []
        for option in options:
            problems = []
            self._walk(value, option, where, problems)
            if not problems:
                return
            attempts.append(problems)
        best = min(attempts, key=len)
        errors.append(f"{where}: no cumple ninguna de las {len(options)} opciones; la más cercana falla en: {'; '.join(best)}")

    @staticmethod
    def _is_type(value, kind):
        if kind == "string":
            return isinstance(value, str)
        if kind == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if kind == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if kind == "boolean":
            return isinstance(value, bool)
        if kind == "array":
            return isinstance(value, list)
        if kind == "object":
            return isinstance(value, dict)
        raise ValueError(f"Tipo que la ayuda no conoce: {kind}")

    @staticmethod
    def _check_string(value, schema, where, errors):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{where}: «{_short(value)}» no cumple el patrón {schema['pattern']}")
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{where}: tiene menos de {schema['minLength']} caracteres")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{where}: tiene más de {schema['maxLength']} caracteres")
        if schema.get("format") == "date":
            try:
                date.fromisoformat(value)
            except ValueError:
                errors.append(f"{where}: «{_short(value)}» no es un día AAAA-MM-DD")

    def _check_array(self, value, schema, where, errors):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{where}: tiene menos de {schema['minItems']} elementos")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{where}: tiene más de {schema['maxItems']} elementos")
        for index, item in enumerate(value):
            self._walk(item, schema.get("items", {}), f"{where}[{index}]", errors)

    def _check_object(self, value, schema, where, errors):
        properties = schema.get("properties")
        for key in schema.get("required", ()):
            if key not in value:
                errors.append(f"{where}: falta la clave «{key}»")
        if properties is None:
            return
        extra = schema.get("additionalProperties", False)
        for key, item in value.items():
            if key in properties:
                self._walk(item, properties[key], f"{where}.{key}", errors)
            elif extra is False:
                errors.append(f"{where}: la clave «{key}» no está en el contrato")
            elif isinstance(extra, dict):
                self._walk(item, extra, f"{where}.{key}", errors)


def _short(value, limit=60):
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"
