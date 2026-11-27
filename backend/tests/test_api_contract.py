"""El contrato de la API (docs/api/openapi.yaml) tiene que decir lo mismo que el servidor.

El contrato es lo que se le entrega a quien quiera conectarse a la API (la app, la web, otro equipo). Si deja de
coincidir con el servidor, miente. Esta prueba lo vigila de dos maneras:

1. **La forma.** Recorre todas las rutas que tiene la aplicación (no una lista a mano) y comprueba que el contrato
   las tiene, con el mismo método, los mismos parámetros de la dirección, los mismos roles y la misma exigencia de
   sesión que el código. También revisa que el archivo esté bien armado (referencias que existen, nombres únicos).
2. **El contenido.** Hace un recorrido real por la API y comprueba que cada respuesta cumple el esquema del contrato
   (tipos, claves obligatorias, valores permitidos) y que cada código de respuesta está documentado. Lo mismo con
   los cuerpos que se envían. Si el servidor agrega o quita un dato y el contrato no se actualiza, falla.

Si agregas o cambias una ruta, actualiza ``docs/api/openapi.yaml`` y esta prueba te dice qué falta.
"""

import logging
import secrets
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import generate_password_hash

from app import create_app
from auth import generate_token
from contract_checker import METHODS, Contract, load_spec, openapi_path
from extensions import db
from models import CommonArea, User
from services import legal_service
from structure_fixtures import apartment_for
from test_legal import PUBLISHED_BODY, document_text, write_documents
from test_route_guards import ANY_ROLE_ENDPOINTS, PUBLIC_ENDPOINTS, _declared_roles
from time_utils import colombia_today
from unit_fixtures import PNG, data_url

ALL_ROLES = {"ADMIN", "GUARD", "RESIDENT"}

#: Rutas de la API que no piden cambiar la contraseña antes (por eso nunca responden 403 por eso).
PASSWORD_CHANGE_EXEMPT = {"auth.current_session", "auth.change_own_password"}


def _api_rules(app):
    """Las rutas de la API con sus métodos, como ``(regla, método)``."""
    for rule in app.url_map.iter_rules():
        if str(rule).startswith("/api/"):
            for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
                yield rule, method


class ContractShapeTests(unittest.TestCase):
    """El contrato coincide con las rutas del servidor y está bien armado."""

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.addClassCleanup(env_setup.release_app, cls.app)
        cls.contract = Contract(load_spec())
        cls.spec = cls.contract.spec

    def test_the_contract_has_every_route_of_the_server_and_nothing_else(self):
        server = {(method, openapi_path(rule)) for rule, method in _api_rules(self.app)}
        documented = {(method, path) for method, path, _ in self.contract.operations()}
        self.assertEqual(sorted(server - documented), [], "Rutas del servidor que el contrato no tiene")
        self.assertEqual(sorted(documented - server), [], "Rutas del contrato que el servidor no tiene")

    def test_each_operation_names_the_same_endpoint_and_path_parameters_as_the_code(self):
        for rule, method in _api_rules(self.app):
            path = openapi_path(rule)
            operation = self.contract.operation(method, path)
            self.assertIsNotNone(operation, f"{method} {path}")
            self.assertEqual(operation["x-endpoint"], rule.endpoint, f"{method} {path}")
            declared = {p["name"] for p in operation.get("parameters", []) if p["in"] == "path"}
            self.assertEqual(declared, set(rule.arguments), f"Parámetros de la dirección de {method} {path}")
            for parameter in operation.get("parameters", []):
                if parameter["in"] == "path":
                    self.assertTrue(parameter["required"], f"{method} {path} {parameter['name']}")

    def test_roles_match_the_ones_each_route_declares(self):
        for rule, method in _api_rules(self.app):
            operation = self.contract.operation(method, openapi_path(rule))
            if rule.endpoint in PUBLIC_ENDPOINTS:
                self.assertNotIn("x-roles", operation, f"{method} {rule}")
                continue
            declared = _declared_roles(self.app.view_functions[rule.endpoint])
            expected = ALL_ROLES if declared is None else declared
            if declared is None:
                self.assertIn(rule.endpoint, ANY_ROLE_ENDPOINTS, f"{rule.endpoint} no dice sus roles")
            self.assertEqual(set(operation["x-roles"]), expected, f"Roles de {method} {rule}")

    def test_only_the_public_routes_skip_the_session(self):
        for rule, method in _api_rules(self.app):
            operation = self.contract.operation(method, openapi_path(rule))
            wanted = [] if rule.endpoint in PUBLIC_ENDPOINTS else [{"bearerAuth": []}]
            self.assertEqual(operation["security"], wanted, f"Sesión de {method} {rule}")

    def test_error_responses_that_the_code_can_always_give_are_documented(self):
        for rule, method in _api_rules(self.app):
            operation = self.contract.operation(method, openapi_path(rule))
            codes = set(operation["responses"])
            if rule.endpoint in PUBLIC_ENDPOINTS:
                continue
            self.assertIn("401", codes, f"{method} {rule} no documenta el 401")
            if rule.endpoint not in PASSWORD_CHANGE_EXEMPT:
                self.assertIn("403", codes, f"{method} {rule} no documenta el 403")
            self.assertTrue(codes & {"200", "201"}, f"{method} {rule} no documenta un éxito")

    def test_the_contract_lists_the_same_legal_documents_as_the_server(self):
        expected = list(legal_service.DOCUMENT_SLUGS)
        operation = self.contract.operation("get", "/api/legal/{slug}")
        slug = next(item for item in operation["parameters"] if item["name"] == "slug")
        self.assertEqual(slug["schema"]["enum"], expected)
        schemas = self.spec["components"]["schemas"]
        self.assertEqual(schemas["LegalDocument"]["properties"]["slug"]["enum"], expected)
        self.assertEqual(schemas["LegalDocumentSummary"]["properties"]["slug"]["enum"], expected)

    def test_every_reference_points_to_something_that_exists(self):
        broken = []

        def walk(node, where):
            if isinstance(node, dict):
                if "$ref" in node:
                    try:
                        self.contract.pointer(node["$ref"])
                    except (KeyError, ValueError):
                        broken.append(f"{where}: {node['$ref']}")
                for key, value in node.items():
                    walk(value, f"{where}/{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{where}/{index}")

        walk(self.spec, "")
        self.assertEqual(broken, [])

    def test_operation_ids_are_unique_and_every_operation_is_described(self):
        ids = []
        tags = {tag["name"] for tag in self.spec["tags"]}
        for method, path, operation in self.contract.operations():
            ids.append(operation["operationId"])
            self.assertTrue(operation.get("summary"), f"{method} {path} sin resumen")
            self.assertTrue(operation.get("description"), f"{method} {path} sin descripción")
            self.assertTrue(operation["tags"] and set(operation["tags"]) <= tags, f"{method} {path} con etiqueta desconocida")
        self.assertEqual(len(ids), len(set(ids)), "operationId repetido")

    def test_every_schema_is_used_by_some_operation_or_schema(self):
        text = repr(self.spec["paths"]) + repr(self.spec["components"]["schemas"]) + repr(self.spec["components"]["responses"])
        unused = [name for name in self.spec["components"]["schemas"] if f"#/components/schemas/{name}'" not in text]
        self.assertEqual(unused, [], "Esquemas del contrato que nadie usa")

    def test_the_contract_only_lists_local_servers_and_no_secrets(self):
        for server in self.spec["servers"]:
            self.assertTrue(server["url"].startswith(("http://localhost", "http://10.0.2.2")), server["url"])
        raw = repr(self.spec).lower()
        for forbidden in ("onrender.com", "bearer ey", "postgres://", "postgresql://"):
            self.assertNotIn(forbidden, raw)
        self.assertEqual(set(self.contract.spec["components"]["securitySchemes"]), {"bearerAuth"})
        self.assertTrue(set(METHODS) >= {method.lower() for method, _, _ in self.contract.operations()})


class ContractValidatorTests(unittest.TestCase):
    """El revisor de esquemas detecta de verdad lo que debe detectar (si no, la prueba de contenido no vale)."""

    def setUp(self):
        self.contract = Contract({
            "components": {"schemas": {"Item": {
                "type": "object", "required": ["id", "name"],
                "properties": {
                    "id": {"type": "integer", "minimum": 1},
                    "name": {"type": "string", "maxLength": 5},
                    "kind": {"type": "string", "enum": ["a", "b"], "nullable": True},
                    "day": {"type": "string", "format": "date"},
                    "when": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
            }}},
        })
        self.item = {"$ref": "#/components/schemas/Item"}

    def problems(self, value, schema=None):
        return self.contract.check(value, schema or self.item)

    def test_a_valid_value_has_no_problems(self):
        self.assertEqual(self.problems({"id": 1, "name": "ab", "kind": None, "day": "2026-12-01", "tags": ["x"]}), [])

    def test_it_reports_missing_keys_and_unknown_keys(self):
        self.assertIn("falta la clave «name»", " ".join(self.problems({"id": 1})))
        self.assertIn("«extra» no está en el contrato", " ".join(self.problems({"id": 1, "name": "a", "extra": 1})))

    def test_it_reports_wrong_types_including_booleans_as_numbers_and_nulls(self):
        self.assertTrue(self.problems({"id": True, "name": "a"}))
        self.assertTrue(self.problems({"id": "1", "name": "a"}))
        self.assertTrue(self.problems({"id": 1, "name": None}))
        self.assertTrue(self.problems({"id": 0, "name": "a"}))

    def test_it_reports_values_outside_the_allowed_ones(self):
        self.assertTrue(self.problems({"id": 1, "name": "demasiado"}))
        self.assertTrue(self.problems({"id": 1, "name": "a", "kind": "c"}))
        self.assertTrue(self.problems({"id": 1, "name": "a", "day": "2026-13-45"}))
        self.assertTrue(self.problems({"id": 1, "name": "a", "when": "2026-12-01T10:00"}))
        self.assertTrue(self.problems({"id": 1, "name": "a", "tags": [1]}))

    def test_one_of_passes_when_any_option_fits_and_fails_when_none_does(self):
        schema = {"oneOf": [{"type": "integer"}, {"type": "string"}]}
        self.assertEqual(self.problems(3, schema), [])
        self.assertEqual(self.problems("a", schema), [])
        self.assertTrue(self.problems([], schema))


class ContractGlobalErrorsTests(unittest.TestCase):
    """Los errores que el servidor responde sin llegar a una ruta, y que el contrato explica en su texto inicial."""

    @classmethod
    def setUpClass(cls):
        logging.disable(logging.INFO)
        cls.addClassCleanup(logging.disable, logging.NOTSET)
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.addClassCleanup(env_setup.release_app, cls.app)
        cls.contract = Contract(load_spec())
        cls.client = cls.app.test_client()

    def assert_error(self, response, status):
        """La respuesta es JSON, trae ese código y tiene la forma del esquema ``Error`` del contrato."""
        self.assertEqual(response.status_code, status, response.get_data(as_text=True)[:300])
        self.assertEqual(response.mimetype, "application/json")
        error = response.get_json()
        self.assertEqual(error["status"], status)
        self.assertEqual(self.contract.check(error, {"$ref": "#/components/schemas/Error"}, "error"), [])

    def test_an_address_that_does_not_exist_answers_404(self):
        self.assert_error(self.client.get("/api/esta-direccion-no-existe"), 404)

    def test_a_method_that_the_address_does_not_have_answers_405(self):
        self.assert_error(self.client.delete("/api/health"), 405)

    def test_a_body_that_is_not_json_answers_400_and_not_415(self):
        self.assert_error(self.client.post("/api/auth/login", data="correo=a", content_type="text/plain"), 400)
        self.assert_error(self.client.post("/api/auth/login", data="{roto", content_type="application/json"), 400)
        self.assert_error(self.client.post("/api/auth/login", data="[1, 2]", content_type="application/json"), 400)

    def test_the_initial_text_of_the_contract_lists_these_codes(self):
        text = self.contract.spec["info"]["description"]
        for code in ("400", "404", "405", "413", "429"):
            self.assertIn(f"| {code} |", text, f"El texto inicial no explica el código {code}")
        self.assertNotIn("| 415 |", text, "El servidor no responde 415: un cuerpo que no es JSON da 400")


class ContractContentTests(unittest.TestCase):
    """Un recorrido real por la API: cada respuesta tiene que cumplir el contrato."""

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        # El recorrido hace cientos de llamadas: sin esto, el registro de cada una llena la pantalla.
        logging.disable(logging.INFO)
        cls.addClassCleanup(logging.disable, logging.NOTSET)
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.addClassCleanup(env_setup.release_app, cls.app)
        cls.contract = Contract(load_spec())

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.client = self.app.test_client()
        self.adapter = self.app.url_map.bind("localhost")
        self.used = set()
        self.passwords = {}
        # Las claves son de un solo uso, al azar: la prueba no depende de ninguna contraseña real.
        self.admin = self.make_user("ADMIN", "Ana", "Administradora")
        self.guard = self.make_user("GUARD", "Gael", "Guardia")
        self.guard2 = self.make_user("GUARD", "Gina", "Guardia")
        self.resident = self.make_user("RESIDENT", "Rosa", "Residente", "Torre 1 · Apto 101")
        self.neighbor = self.make_user("RESIDENT", "Nico", "Vecino", "Torre 2 · Apto 202")
        area = CommonArea(name="Salón social")
        db.session.add(area)
        db.session.commit()
        self.area_id = area.id

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    # --- ayudas -----------------------------------------------------------------------------------

    def make_user(self, role, first, last, apartment=None):
        password = secrets.token_urlsafe(9) + "Aa1*"
        user = User(
            name=first, last_name=last, email=f"{first.lower()}-{secrets.token_hex(3)}@contrato.test", role=role,
            is_active=True, password_hash=generate_password_hash(password),
            apartment_ref=apartment_for(apartment) if apartment else None,
        )
        if role == "RESIDENT":
            user.data_processing_consent = True
            user.occupancy_type = "propietario"
        db.session.add(user)
        db.session.commit()
        self.passwords[user.id] = password
        return user

    def call(self, who, method, path, *, json=None, query=None, expect=200, headers=None):
        """Hace una llamada a la API y comprueba que lo enviado y lo recibido cumplan el contrato.

        ``who`` es la persona (se le firma un token), un token ya hecho, o None para ir sin sesión.
        """
        headers = dict(headers or {})
        if who is not None:
            headers["Authorization"] = f"Bearer {who if isinstance(who, str) else generate_token(who)}"
        response = self.client.open(path, method=method, json=json, query_string=query, headers=headers)
        rule, _ = self.adapter.match(path.split("?")[0], method=method, return_rule=True)
        template = openapi_path(rule)
        label = f"{method} {template}"
        operation = self.contract.operation(method, template)
        self.assertIsNotNone(operation, f"{label} no está en el contrato")
        self.used.add((method, template))
        preview = response.get_data()[:400].decode("utf-8", "replace")
        self.assertEqual(response.status_code, expect, f"{label}: {preview}")
        self.assertIn(str(expect), operation["responses"], f"{label}: el contrato no documenta el código {expect}")
        if json is not None and 200 <= expect < 300:
            schema = self.contract.request_schema(operation)
            self.assertIsNotNone(schema, f"{label}: el contrato no declara un cuerpo")
            self.assertEqual(self.contract.check(json, schema, "solicitud"), [], f"{label}: lo enviado no cumple el contrato")
        if response.is_json:
            schema = self.contract.response_schema(operation, expect)
            self.assertIsNotNone(schema, f"{label}: el contrato no declara el contenido del {expect}")
            self.assertEqual(
                self.contract.check(response.get_json(), schema, "respuesta"), [], f"{label}: la respuesta no cumple el contrato"
            )
        elif response.data:
            self.assertIn(response.mimetype, self.contract.response_content_types(operation, expect), label)
        return response

    def data(self, *args, **kwargs):
        """Lo mismo que ``call`` pero devuelve el JSON de la respuesta."""
        return self.call(*args, **kwargs).get_json()

    # --- el recorrido -------------------------------------------------------------------------------

    def test_a_full_walkthrough_follows_the_contract(self):
        self.walk_session()
        self.walk_legal()
        self.walk_structure()
        self.walk_users()
        self.walk_unit()
        self.walk_documents()
        self.walk_community()
        self.walk_notifications()
        self.walk_admin_reports()
        self.walk_packages()
        self.walk_visits()
        self.walk_vehicles()
        self.walk_errors()
        missing = sorted(
            f"{method} {path}" for method, path, _ in self.contract.operations() if (method, path) not in self.used
        )
        self.assertEqual(missing, [], "Operaciones del contrato que el recorrido no probó")

    def walk_legal(self):
        """Los documentos legales: públicos; primero en preparación y luego uno publicado con todas las clases de bloque."""
        listed = self.data(None, "GET", "/api/legal")["documents"]
        self.assertEqual([item["slug"] for item in listed], list(legal_service.DOCUMENT_SLUGS))
        for item in listed:
            self.assertEqual(self.data(None, "GET", f"/api/legal/{item['slug']}")["slug"], item["slug"])
        self.call(None, "GET", "/api/legal/no-existe", expect=404)
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(legal_service, "LEGAL_DIR", Path(folder)):
            write_documents(folder, terminos=document_text(
                status="vigente", version="1.0", since="2026-12-01", body=PUBLISHED_BODY,
            ))
            published = self.data(None, "GET", "/api/legal/terminos")
            self.assertEqual(published["version"], "1.0")
            self.assertEqual([block["type"] for block in published["blocks"]], ["heading", "paragraph", "heading", "list", "list"])
            self.assertEqual(self.data(None, "GET", "/api/legal")["documents"][3]["status"], "vigente")

    def walk_session(self):
        self.call(None, "GET", "/api/health")
        login = self.data(None, "POST", "/api/auth/login", json={
            "email": self.resident.email, "password": self.passwords[self.resident.id],
        })
        self.call(None, "POST", "/api/auth/login", json={"email": self.resident.email, "password": "no-es-esta"}, expect=401)
        self.call(login["token"], "GET", "/api/auth/session")
        # «Acepto»: la API del contrato corre con la exigencia apagada; igual se ve el estado y se acepta.
        status = self.data(login["token"], "GET", "/api/auth/legal-acceptance")
        self.assertFalse(status["required"])
        self.assertEqual([item["slug"] for item in status["documents"]], ["terminos", "politica-datos", "autorizacion-datos"])
        self.call(login["token"], "POST", "/api/auth/accept-legal", json={"accepted": True, "version": status["version"]})

        # Una cuenta nueva trae una clave temporal: hasta cambiarla, todo responde 403 menos estas dos rutas.
        temporary = "Temp" + secrets.token_hex(4) + "Zz9*"
        created = self.data(self.admin, "POST", "/api/admin/users", expect=201, json={
            "name": "Pablo", "lastName": "Portero", "email": f"pablo-{secrets.token_hex(3)}@contrato.test",
            "password": temporary, "role": "GUARD",
        })["user"]
        self.assertTrue(created["mustChangePassword"])
        fresh = self.data(None, "POST", "/api/auth/login", json={"email": created["email"], "password": temporary})
        self.call(fresh["token"], "GET", "/api/auth/session")
        self.call(fresh["token"], "GET", "/api/unit-info", expect=403)
        chosen = "Nueva" + secrets.token_hex(4) + "Yy8*"
        changed = self.data(fresh["token"], "PUT", "/api/auth/password", json={
            "currentPassword": temporary, "newPassword": chosen,
        })
        self.call(changed["token"], "GET", "/api/unit-info")

        # El turno de portería: el PIN lo pone la administración y quien entra lo escribe en la tablet.
        pin = str(secrets.randbelow(9000) + 1000)
        self.call(self.admin, "PUT", f"/api/admin/users/{self.guard2.id}/pin", json={"pin": pin})
        guards = self.data(self.guard, "GET", "/api/auth/guards")["guards"]
        self.assertIn(self.guard2.id, [guard["id"] for guard in guards])
        self.call(self.guard, "POST", "/api/auth/guard-shift", json={"guardId": self.guard2.id, "pin": pin})

    def walk_structure(self):
        admin = self.admin
        tower = self.data(admin, "POST", "/api/admin/towers", expect=201, json={"name": "Torre 9", "floors": 5})["tower"]
        spare_tower = self.data(admin, "POST", "/api/admin/towers", expect=201, json={"name": "Torre 8", "floors": 3})["tower"]
        self.call(admin, "GET", "/api/admin/towers")
        self.call(admin, "GET", f"/api/admin/towers/{tower['id']}")
        self.call(admin, "PUT", f"/api/admin/towers/{tower['id']}", json={"floors": 6})

        apartment = self.data(admin, "POST", "/api/admin/apartments", expect=201, json={
            "towerId": tower["id"], "code": "101", "floor": 1,
        })["apartment"]
        spare = self.data(admin, "POST", "/api/admin/apartments", expect=201, json={
            "towerId": tower["id"], "code": "102", "floor": 1,
        })["apartment"]
        batch = self.data(admin, "POST", "/api/admin/apartments/batch", expect=201, json={
            "towerId": tower["id"], "floor": 2, "count": 2,
        })["apartments"]
        self.assertEqual([item["code"] for item in batch], ["201", "202"])
        self.call(admin, "GET", "/api/admin/apartments", query={"towerId": tower["id"], "search": "10", "page": 1, "pageSize": 20})
        self.call(admin, "GET", f"/api/admin/apartments/{apartment['id']}")
        self.call(admin, "PUT", f"/api/admin/apartments/{apartment['id']}", json={"code": "103"})
        self.call(admin, "DELETE", f"/api/admin/apartments/{spare['id']}")

        resident_spot = self.data(admin, "POST", "/api/admin/parking-spots", expect=201, json={
            "code": "R-9", "type": "residente", "location": "Sótano 2", "apartmentId": apartment["id"],
        })["parkingSpot"]
        self.visitor_spot = self.data(admin, "POST", "/api/admin/parking-spots", expect=201, json={
            "code": "V-9", "type": "visitante", "location": "Entrada",
        })["parkingSpot"]
        self.call(admin, "GET", "/api/admin/parking-spots", query={"type": "residente", "assigned": "true", "search": "R-", "pageSize": 10})
        self.call(admin, "GET", f"/api/admin/parking-spots/{resident_spot['id']}")
        self.call(admin, "PUT", f"/api/admin/parking-spots/{resident_spot['id']}", json={"location": "Sótano 3"})
        self.call(admin, "DELETE", f"/api/admin/parking-spots/{resident_spot['id']}")

        room = self.data(admin, "POST", "/api/admin/storage-rooms", expect=201, json={
            "code": "CU-9", "apartmentId": apartment["id"],
        })["storageRoom"]
        self.call(admin, "GET", "/api/admin/storage-rooms", query={"assigned": "true"})
        self.call(admin, "GET", f"/api/admin/storage-rooms/{room['id']}")
        self.call(admin, "PUT", f"/api/admin/storage-rooms/{room['id']}", json={"code": "CU-10"})
        self.call(admin, "DELETE", f"/api/admin/storage-rooms/{room['id']}")

        # Una torre con apartamentos no se puede retirar; una vacía, sí.
        self.call(admin, "DELETE", f"/api/admin/towers/{tower['id']}", expect=409)
        self.call(admin, "DELETE", f"/api/admin/towers/{spare_tower['id']}")

    def walk_users(self):
        admin, guard = self.admin, self.guard
        apartment_id = self.resident.apartment_id
        self.call(admin, "GET", "/api/admin/users", query={
            "role": "RESIDENT", "search": "Rosa", "isActive": "true", "page": 1, "pageSize": 10,
        })
        self.call(admin, "GET", "/api/users")
        for base, label in (("/api/admin/users", "a"), ("/api/users", "b")):
            created = self.data(admin, "POST", base, expect=201, json={
                "name": f"Vecina {label}", "lastName": "Nueva", "email": f"vecina-{label}-{secrets.token_hex(3)}@contrato.test",
                "password": "Temp" + secrets.token_hex(4) + "Zz9*", "role": "RESIDENT", "phone": "3001234567",
                "documentId": "10203040" + str(len(label)), "birthDate": "1990-05-14", "occupancyType": "propietario",
                "apartmentId": apartment_id, "dataProcessingConsent": True,
            })["user"]
            self.call(admin, "GET", f"{base}/{created['id']}")
            self.call(admin, "PUT", f"{base}/{created['id']}", json={"phone": "3009998877", "occupancyType": "arrendatario"})
            self.call(admin, "PUT", f"{base}/{created['id']}/password", json={"password": "Otra" + secrets.token_hex(4) + "Xx7*"})

        self.call(admin, "GET", "/api/residents", query={"search": "Rosa"})
        self.call(guard, "GET", "/api/residents", query={"search": "Rosa"})
        self.call(guard, "GET", f"/api/residents/{self.resident.id}/contact")
        self.call(self.resident, "GET", "/api/profile")
        self.call(self.resident, "PUT", "/api/profile", json={
            "phone": "3001112233", "socialNetworks": "@rosa", "currentPassword": self.passwords[self.resident.id],
        })

    def walk_unit(self):
        admin, resident = self.admin, self.resident
        self.call(resident, "GET", "/api/unit-info")
        self.call(resident, "GET", "/api/unit-info/logo", expect=404)
        self.call(admin, "PUT", "/api/admin/unit-info", json={
            "name": "Conjunto del contrato", "address": "Calle 1 # 2-3", "portalPhone": "6041234567",
            "logo": data_url(PNG),
        })
        logo = self.call(resident, "GET", "/api/unit-info/logo")
        self.call(resident, "GET", "/api/unit-info/logo", expect=304, headers={"If-None-Match": logo.headers["ETag"]})

        # Las reglas de la unidad: se ven, se cambian (con un plazo propio) y vuelven al valor de DOMUX.
        self.call(admin, "GET", "/api/admin/unit-rules")
        self.call(admin, "PUT", "/api/admin/unit-rules", json={
            "pqrsTermDays": 20, "pqrsWarningDays": 6, "pqrsTermsByCategory": {"Daño": 5},
            "packageOrangeHours": 36, "packageRedHours": 60, "visitorParkingMaxDays": 4,
        })
        self.call(admin, "PUT", "/api/admin/unit-rules", expect=400, json={"pqrsTermDays": 500})
        self.call(resident, "GET", "/api/unit-info")
        self.call(admin, "PUT", "/api/admin/unit-rules", json={
            "pqrsTermDays": None, "pqrsWarningDays": None, "pqrsTermsByCategory": None,
            "packageOrangeHours": None, "packageRedHours": None, "visitorParkingMaxDays": None,
            "visitMaxStayDays": None, "qrMaxPeople": None, "qrMaxValidDays": None,
            "autoQrMinStayDays": None, "deliveredArchiveDays": None, "motosPerCarSpot": None,
        })

        template = self.data(admin, "GET", "/api/admin/census-template")
        census = self.data(admin, "POST", "/api/admin/import-census", json={
            "fileBase64": template["base64"], "fileName": template["fileName"], "dataProcessingConsent": True,
        })
        self.assertGreaterEqual(census["createdUsers"], 1)

        apartment_id = resident.apartment_id
        unit = self.data(admin, "GET", "/api/admin/units", query={"apartmentId": apartment_id})["unit"]
        self.assertEqual(unit["apartmentId"], apartment_id)
        today = colombia_today()
        self.data(admin, "PUT", "/api/admin/units", json={
            "apartmentId": apartment_id,
            "members": [{"name": "Luis", "lastName": "Residente", "documentId": "55667788", "birthDate": "2015-03-02",
                         "relationship": "hijo"}],
            "pets": [{"name": "Toby", "species": "Perro", "breed": "Criollo", "ageYears": 3, "vaccinesUpToDate": True,
                      "lastVaccinationDate": (today - timedelta(days=30)).isoformat(), "dewormingUpToDate": False}],
            "vehicles": [{"plate": "KLM456", "type": "carro", "makeModel": "Mazda 3", "year": 2020,
                          "registeredOwner": "Rosa Residente"}],
            "petInsurance": False,
        })
        self.call(resident, "GET", "/api/profile/unit")

    def walk_documents(self):
        admin, guard, resident = self.admin, self.guard, self.resident
        pdf = data_url(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n", "application/pdf")
        document = self.data(admin, "POST", "/api/documents", expect=201, json={
            "title": "Manual de convivencia", "category": "convivencia", "description": "Versión de la asamblea.",
            "file": pdf, "fileName": "manual.pdf", "visibleTo": ["propietario", "arrendatario", "guardia"],
            "notify": True,
        })["document"]
        self.call(admin, "POST", "/api/documents", expect=409, json={
            "title": "manual de convivencia", "file": pdf, "visibleTo": [],
        })
        self.call(admin, "POST", "/api/documents", expect=400, json={
            "title": "Archivo dañado", "file": data_url(b"no soy un pdf"), "visibleTo": [],
        })
        self.call(admin, "GET", "/api/documents", query={"includeRetired": "true", "category": "convivencia"})
        self.call(resident, "GET", "/api/documents")
        self.call(guard, "GET", "/api/documents")
        self.call(resident, "GET", f"/api/documents/{document['id']}")
        file = self.call(resident, "GET", f"/api/documents/{document['id']}/file")
        self.call(
            resident, "GET", f"/api/documents/{document['id']}/file", expect=304,
            headers={"If-None-Match": file.headers["ETag"]},
        )
        self.call(admin, "PUT", f"/api/documents/{document['id']}", json={
            "title": "Manual de convivencia 2027", "description": None, "visibleTo": ["propietario"],
        })
        self.call(guard, "GET", f"/api/documents/{document['id']}", expect=404)
        self.call(admin, "DELETE", f"/api/documents/{document['id']}")
        self.call(resident, "GET", f"/api/documents/{document['id']}/file", expect=404)
        self.call(admin, "POST", f"/api/documents/{document['id']}/restore")

    def walk_community(self):
        admin, resident = self.admin, self.resident
        today = colombia_today()
        tower_id = self.resident.apartment_ref.tower_id

        # Comunicados
        notice = self.data(admin, "POST", "/api/announcements", expect=201, json={
            "title": "Corte de agua", "message": "Mañana no habrá agua de 8 a 12.", "category": "mantenimiento",
            "towerId": tower_id, "expiresAt": (today + timedelta(days=5)).isoformat(),
            "eventDate": (today + timedelta(days=1)).isoformat(), "eventTime": "08:00",
            "mediaUrl": data_url(PNG), "mediaType": "image", "mediaDownloadable": True,
        })["announcement"]
        old_route = self.data(admin, "POST", "/api/announcements", expect=201, json={
            "title": "Asamblea", "message": "Se cita a la asamblea general.", "category": "asamblea",
        })["announcement"]
        self.call(resident, "GET", "/api/announcements", query={"unread": "true", "category": "mantenimiento", "pageSize": 10})
        self.call(admin, "GET", "/api/announcements", query={"view": "summary", "towerId": "unit", "search": "asamblea"})
        self.call(admin, "GET", "/api/announcements", query={"view": "summary", "archived": "true"})
        self.call(resident, "GET", f"/api/announcements/{notice['id']}")
        self.call(admin, "GET", f"/api/announcements/{notice['id']}", query={"view": "summary"})
        self.call(resident, "POST", f"/api/announcements/{notice['id']}/read")
        self.call(admin, "PUT", f"/api/announcements/{notice['id']}/retire")
        self.call(admin, "DELETE", f"/api/announcements/{old_route['id']}")

        # PQRS: la radica el residente, la administración responde y el residente la califica.
        yesterday = (today - timedelta(days=1)).isoformat()
        pqrs = self.data(resident, "POST", "/api/pqrs", expect=201, json={
            "subject": "Ruido en la noche", "message": "Hay ruido en el apartamento de arriba.", "category": "Queja",
            "incidentDate": yesterday, "incidentTime": "22:30", "mediaUrl": data_url(PNG), "mediaType": "image",
        })["pqrs"]
        again = self.data(resident, "POST", "/api/pqrs", expect=201, json={
            "subject": "Ruido en la mañana", "message": "Otra vez el ruido.", "category": "Queja",
            "incidentDate": yesterday,
        })["pqrs"]
        for_resident = self.data(admin, "POST", "/api/pqrs", expect=201, json={
            "subject": "Daño en el ascensor", "message": "La administración lo registra a nombre del residente.",
            "category": "Queja", "residentId": resident.id, "incidentDate": yesterday,
        })["pqrs"]
        self.call(resident, "GET", "/api/pqrs")
        self.call(admin, "GET", "/api/pqrs", query={
            "status": "abierta", "category": "Queja", "search": "ruido", "residentId": resident.id, "includeArchived": "false",
        })
        self.call(admin, "GET", "/api/pqrs", query={"view": "summary", "semaphore": "verde", "page": 1, "pageSize": 20})
        self.call(resident, "GET", f"/api/pqrs/{pqrs['id']}")
        self.call(admin, "GET", f"/api/pqrs/{pqrs['id']}", query={"view": "summary"})
        self.call(resident, "POST", f"/api/pqrs/{pqrs['id']}/messages", expect=201, json={
            "message": "Adjunto una foto del problema.", "mediaUrl": data_url(PNG), "mediaType": "image",
        })
        self.call(admin, "PUT", f"/api/pqrs/{pqrs['id']}/respond", json={
            "status": "en_proceso", "adminResponse": "Estamos revisando el caso.",
        })
        self.call(admin, "PUT", f"/api/pqrs/{pqrs['id']}/respond", json={
            "status": "resuelta", "adminResponse": "Se habló con el vecino.",
        })
        self.call(resident, "PUT", f"/api/pqrs/{pqrs['id']}/satisfaction", json={"rating": 4, "comment": "Gracias."})
        self.call(admin, "POST", "/api/pqrs/batch/respond", json={
            "pqrsIds": [again["id"], for_resident["id"]], "status": "en_proceso", "message": "Las dos están en revisión.",
        })

        # Zonas comunes y reservas
        areas = self.data(resident, "GET", "/api/common-areas")["areas"]
        self.assertEqual([area["id"] for area in areas], [self.area_id])
        self.call(admin, "PUT", f"/api/common-areas/{self.area_id}/rules", json={
            "openTime": "08:00", "closeTime": "20:00", "slotMinutes": 120, "capacity": 20, "minAdvanceDays": 0,
            "maxAdvanceDays": 60, "cancelDeadlineDays": 2, "weeklyLimit": 3, "maintenanceWeekday": None,
            "maxConsecutiveSlots": 2, "allowFullDay": False,
        })
        day = today + timedelta(days=3)
        self.call(resident, "GET", "/api/reservations/availability", query={"commonAreaId": self.area_id, "date": day.isoformat()})
        self.call(resident, "GET", "/api/reservations/calendar", query={"commonAreaId": self.area_id, "year": day.year, "month": day.month})
        reservation = self.data(resident, "POST", "/api/reservations", expect=201, json={
            "commonAreaId": self.area_id, "date": day.isoformat(), "timeSlot": "08:00-10:00", "attendees": 10,
            "message": "Cumpleaños de mi hijo.", "mediaUrl": data_url(PNG), "mediaType": "image",
        })["reservation"]
        by_admin = self.data(admin, "POST", "/api/reservations", expect=201, json={
            "commonAreaId": self.area_id, "date": (day + timedelta(days=1)).isoformat(), "timeSlot": "10:00-12:00",
            "residentId": resident.id,
        })["reservation"]
        self.call(resident, "GET", "/api/reservations")
        self.call(admin, "GET", "/api/reservations", query={
            "view": "summary", "status": "por_aprobar", "commonAreaId": self.area_id, "dateFrom": today.isoformat(),
            "dateTo": (today + timedelta(days=30)).isoformat(), "q": "Rosa", "includeArchived": "false",
        })
        self.call(resident, "GET", f"/api/reservations/{reservation['id']}")
        self.call(admin, "GET", f"/api/reservations/{reservation['id']}", query={"view": "summary"})
        self.call(resident, "POST", f"/api/reservations/{reservation['id']}/messages", expect=201, json={
            "message": "¿Se puede usar el parlante?",
        })
        self.call(admin, "PUT", f"/api/reservations/{reservation['id']}/status", json={"status": "aprobada"})
        self.call(resident, "PUT", f"/api/reservations/{by_admin['id']}/cancel")

        # La administración agrega una zona, la cierra con un motivo (nadie reserva mientras tanto), la abre y la retira.
        pool = self.data(admin, "POST", "/api/common-areas", expect=201, json={"name": "Piscina", "capacity": 12})["area"]
        self.call(admin, "GET", "/api/common-areas", query={"includeRetired": "true"})
        self.call(admin, "POST", f"/api/common-areas/{pool['id']}/close", json={"reason": "Falla en la bomba de agua."})
        self.call(resident, "GET", "/api/reservations/availability", query={"commonAreaId": pool["id"], "date": day.isoformat()})
        self.call(resident, "POST", "/api/reservations", expect=409, json={
            "commonAreaId": pool["id"], "date": day.isoformat(), "timeSlot": "08:00-10:00",
        })
        self.call(admin, "POST", f"/api/common-areas/{pool['id']}/open")
        self.call(admin, "DELETE", f"/api/common-areas/{pool['id']}")

    def walk_notifications(self):
        resident = self.resident
        notifications = self.data(resident, "GET", "/api/notifications")["notifications"]
        self.assertTrue(notifications, "El recorrido anterior debió dejar avisos al residente")
        self.call(resident, "PUT", f"/api/notifications/{notifications[0]['id']}/read")
        self.call(resident, "PUT", "/api/notifications/read-all")
        token = "fcm-" + secrets.token_hex(20)
        self.call(resident, "POST", "/api/push-tokens", expect=201, json={"token": token, "deviceId": "telefono-de-prueba"})
        self.call(resident, "DELETE", "/api/push-tokens", json={"token": token})

    def walk_admin_reports(self):
        admin = self.admin
        self.call(admin, "GET", "/api/admin/summary")
        self.call(admin, "GET", "/api/admin/export/legal-report")
        self.call(admin, "POST", "/api/admin/archive-history")

    def walk_packages(self):
        guard, resident = self.guard, self.resident
        today = colombia_today().isoformat()
        package = self.data(guard, "POST", "/api/packages", expect=201, json={
            "residentId": resident.id, "description": "Caja de cartón mediana", "status": "pendiente",
            "carrier": "Servientrega", "trackingNumber": "SV123", "mediaUrl": data_url(PNG), "mediaType": "image",
            "eventDate": today, "eventTime": "10:30",
        })["packageItem"]
        coming = self.data(guard, "POST", "/api/packages", expect=201, json={
            "residentId": resident.id, "description": "Sobre de la DIAN", "status": "pendiente",
        })["packageItem"]
        self.call(guard, "GET", "/api/packages", query={"status": "pendiente", "residentId": resident.id, "search": "caja"})
        self.call(resident, "GET", "/api/packages")
        self.call(guard, "GET", "/api/packages", query={"view": "summary", "status": "todos", "page": 1, "pageSize": 20})
        self.call(resident, "GET", f"/api/packages/{package['id']}")
        self.call(guard, "GET", f"/api/packages/{package['id']}", query={"view": "summary"})
        self.call(guard, "PUT", f"/api/packages/{coming['id']}/status", json={"status": "pendiente"})

        # El residente genera un código para que otra persona recoja la caja y la portería lo usa.
        code = self.data(resident, "POST", f"/api/packages/{package['id']}/pickup-code", expect=201)["pickupCode"]
        found = self.data(guard, "POST", "/api/packages/pickup-lookup", json={"code": code["qrData"]})["packageItem"]
        self.assertEqual(found["id"], package["id"])
        self.call(guard, "PUT", f"/api/packages/{package['id']}/deliver", json={
            "receivedBy": "Hermano de Rosa", "pickupCode": code["pin"],
        })

        # Un paquete no se borra: se archiva y se puede sacar de «Archivados».
        self.call(guard, "DELETE", f"/api/packages/{coming['id']}")
        self.call(guard, "GET", "/api/packages", query={"view": "summary", "status": "archivados"})
        self.call(guard, "PUT", f"/api/packages/{coming['id']}/restore")

    def walk_visits(self):
        guard, resident = self.guard, self.resident
        today = colombia_today()
        visit = self.data(guard, "POST", "/api/visits", expect=201, json={
            "visitorName": "Marta Visitante", "residentId": resident.id, "type": "visitante",
            "visitorDocument": "52123456", "mediaConsent": True, "mediaUrl": data_url(PNG), "mediaType": "image",
            "description": "Viene a almorzar.", "expectedStayMinutes": 120,
        })["visit"]
        courier = self.data(guard, "POST", "/api/visits", expect=201, json={
            "visitorName": "Domiciliario", "residentId": resident.id, "type": "domiciliario", "documentRefused": True,
        })["visit"]
        self.call(resident, "PUT", f"/api/visits/{visit['id']}/decision", json={"decision": "aprobada"})
        self.call(guard, "PUT", f"/api/visits/{courier['id']}/authorize-call")
        stranger = self.data(guard, "POST", "/api/visits", expect=201, json={
            "visitorName": "Persona Desconocida", "residentId": resident.id, "type": "visitante", "documentRefused": True,
        })["visit"]
        self.call(guard, "PUT", f"/api/visits/{stranger['id']}/reject-call")
        self.call(guard, "POST", f"/api/visits/{visit['id']}/entry", json={"expectedStayMinutes": 90})
        self.call(guard, "POST", f"/api/visits/{courier['id']}/entry")
        self.call(guard, "GET", "/api/visits", query={
            "status": "aprobada", "search": "Marta", "inside": "true", "from": today.isoformat(), "to": today.isoformat(),
            "apartmentId": resident.apartment_id,
        })
        self.call(resident, "GET", "/api/visits", query={"view": "summary", "pageSize": 20})
        self.call(guard, "GET", f"/api/visits/{visit['id']}")
        self.call(resident, "GET", f"/api/visits/{visit['id']}", query={"view": "summary"})
        self.call(guard, "POST", f"/api/visits/{courier['id']}/exit", json={"returningToday": False})
        self.inside_visit = visit

        # Un QR de acceso: el residente lo crea y la portería lo lee para dejar entrar y salir a quien lo trae.
        qr = self.data(resident, "POST", "/api/visits/qr-passes", expect=201, json={
            "validFrom": today.isoformat(), "validUntil": (today + timedelta(days=2)).isoformat(), "maxPeople": 2,
            "visitorNames": ["Pedro Invitado"],
        })["qrPass"]
        self.call(resident, "GET", "/api/visits/qr-passes")
        inspected = self.data(self.guard, "GET", f"/api/visits/qr/{qr['token']}")
        self.assertTrue(inspected["canRegister"])
        arrived = self.data(self.guard, "POST", f"/api/visits/qr/{qr['token']}/entry", expect=201, json={
            "visitorName": "Pedro Invitado", "expectedStayMinutes": 60,
        })["visit"]
        self.call(self.guard, "POST", f"/api/visits/qr/{qr['token']}/exit", json={
            "visitId": arrived["id"], "returningToday": True,
        })
        self.call(resident, "PUT", f"/api/visits/qr-passes/{qr['id']}/revoke")

        # Un técnico que la administración espera para las zonas comunes.
        technician = self.data(self.admin, "POST", "/api/visits/expected", expect=201, json={
            "visitorName": "Ascensores Andinos", "description": "Mantenimiento del ascensor",
            "expectedDate": (today + timedelta(days=1)).isoformat(), "expectedTime": "08:00",
        })["visit"]
        self.call(self.guard, "GET", "/api/visits/expected")
        self.call(self.admin, "PUT", f"/api/visits/expected/{technician['id']}/cancel")

    def walk_vehicles(self):
        admin, guard = self.admin, self.guard
        spot = self.visitor_spot
        board = self.data(guard, "GET", "/api/parking/visitor-spots")
        self.assertEqual(board["free"], 1)
        entry = self.data(guard, "POST", "/api/vehicle-entries", expect=201, json={
            "plate": "QWE123", "visitId": self.inside_visit["id"], "spotId": spot["id"],
        })["vehicleEntry"]
        # El parqueadero ya está ocupado y no queda otro: el error explica qué hacer.
        busy = self.call(guard, "POST", "/api/vehicle-entries", expect=409, json={
            "plate": "RTY456", "visitId": self.inside_visit["id"], "spotId": spot["id"],
        }).get_json()
        self.assertTrue(busy["noFreeSpots"])
        self.assertIsNone(busy["suggestedSpot"])
        self.call(admin, "GET", "/api/vehicle-entries", query={
            "inside": "true", "overdue": "false", "plate": "QWE", "apartmentId": self.resident.apartment_id,
            "counts": "true", "pageSize": 10,
        })
        self.call(guard, "GET", "/api/resident-vehicles", query={"search": "KLM"})
        # El buscador general (HU-089): con todo cargado, cada grupo tiene que cumplir el contrato.
        found = self.data(admin, "GET", "/api/search", query={"q": "Rosa"})
        self.assertTrue({group["type"] for group in found["groups"]} >= {"personas", "pqrs", "paquetes", "visitas"})
        found = self.data(admin, "GET", "/api/search", query={"q": "QWE", "in": "vehiculos"})
        self.assertEqual([item["kind"] for item in found["groups"][0]["items"]], ["visitante"])
        self.data(guard, "GET", "/api/search", query={"q": "KLM456", "in": "vehiculos"})
        self.data(guard, "GET", "/api/search", query={"q": "Rosa", "in": "apartamentos"})
        self.assertTrue(self.data(guard, "GET", "/api/search", query={"q": "R"})["tooShort"])
        self.call(guard, "GET", "/api/search", query={"q": "Rosa", "in": "pqrs"}, expect=403)
        self.call(admin, "GET", "/api/search", query={"q": "Rosa", "in": "otra-cosa"}, expect=400)
        self.call(guard, "POST", "/api/resident-vehicles/KLM456/movements", expect=201, json={"type": "entrada"})
        self.call(guard, "PUT", f"/api/vehicle-entries/{entry['id']}/exit")
        self.call(guard, "POST", f"/api/visits/{self.inside_visit['id']}/exit", json={"returningToday": False})

    def walk_errors(self):
        """Los errores más comunes: cada uno tiene el código y la forma que el contrato promete."""
        admin, guard, resident = self.admin, self.guard, self.resident
        error = self.data(admin, "POST", "/api/announcements", expect=400, json={"title": "Sin mensaje"})
        self.assertEqual(error["status"], 400)
        self.assertTrue(error["error"])
        self.call(None, "GET", "/api/packages", expect=401)
        self.call(resident, "GET", "/api/admin/users", expect=403)
        self.call(guard, "GET", "/api/packages/999999", expect=404)

        # Un paquete archivado no se puede archivar otra vez.
        package = self.data(guard, "POST", "/api/packages", expect=201, json={
            "residentId": resident.id, "description": "Paquete para archivar",
        })["packageItem"]
        self.call(guard, "DELETE", f"/api/packages/{package['id']}")
        self.call(guard, "DELETE", f"/api/packages/{package['id']}", expect=409)

        # Una solicitud de más de 12 MB se rechaza antes de leerla.
        heavy = "A" * (13 * 1024 * 1024)
        self.call(admin, "POST", "/api/announcements", expect=413, json={"title": "Pesado", "message": heavy})

        # Al quinto intento fallido seguido el correo queda bloqueado y la respuesta dice cuánto esperar.
        victim = self.make_user("RESIDENT", "Bloqueada", "Prueba", "Torre 1 · Apto 101")
        for _ in range(4):
            self.call(None, "POST", "/api/auth/login", expect=401, json={"email": victim.email, "password": "no-es-esta"})
        locked = self.call(None, "POST", "/api/auth/login", expect=429, json={"email": victim.email, "password": "no-es-esta"})
        self.assertGreater(int(locked.headers["Retry-After"]), 0)
