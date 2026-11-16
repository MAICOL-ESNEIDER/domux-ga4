"""Red de seguridad de los permisos: ninguna ruta puede quedar abierta por olvido.

Recorre todas las rutas que tiene la aplicación (no una lista a mano) y comprueba tres cosas:

1. Toda ruta pide sesión, salvo las pocas que son públicas a propósito (la lista de abajo).
2. Toda ruta de la API dice qué roles la usan (ADR-015, mínimo privilegio), salvo las de «cualquier
   persona con sesión» (también listadas abajo).
3. De verdad se cumple: sin sesión la API responde 401 y la web lleva al inicio de sesión, y un rol
   que la ruta no nombra recibe 403.

Si alguien agrega una ruta nueva sin decorador, esta prueba falla y dice cuál es.
"""

import re
import unittest

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import generate_password_hash

import auth
from app import create_app
from auth import generate_token
from extensions import db
from models import User
from web import security

#: Rutas públicas a propósito (inicio de sesión, estado del servicio, archivos de diseño, logo de la web y los
#: documentos legales, que se leen antes de entrar).
PUBLIC_ENDPOINTS = {
    "root", "static", "auth.login", "auth.health",
    "web.static", "web.login", "web.login_submit", "web.unit_logo",
    "legal.list_documents", "legal.get_document", "web.legal_index", "web.legal_document",
}

#: Rutas de la API que sirven a cualquier persona con sesión, sea cual sea su rol.
ANY_ROLE_ENDPOINTS = {
    "auth.current_session", "auth.change_own_password", "unit.get_unit_info", "unit.get_unit_logo",
}

ALL_ROLES = {"ADMIN", "GUARD", "RESIDENT"}


def _wrappers(view):
    """Cada capa que envuelve a la función de la ruta (los decoradores), de afuera hacia adentro."""
    while view is not None:
        yield view
        view = getattr(view, "__wrapped__", None)


def _code_of(decorated):
    return decorated.__code__


_TOKEN_CODE = _code_of(auth.token_required(lambda: None))
_ROLE_CODE = _code_of(auth.role_required("ADMIN")(lambda: None))
_LOGIN_CODE = _code_of(security.login_required(lambda: None))


def _has(view, code):
    return any(layer.__code__ == code for layer in _wrappers(view))


def _declared_roles(view):
    """Los roles que nombra role_required en esa ruta, o None si no lo usa."""
    for layer in _wrappers(view):
        if layer.__code__ == _ROLE_CODE:
            for cell in layer.__closure__ or ():
                value = cell.cell_contents
                if isinstance(value, tuple) and value and all(isinstance(item, str) for item in value):
                    return set(value)
    return None


def _sample_path(rule):
    """La dirección de la ruta con datos de relleno en lugar de los parámetros."""
    path = re.sub(r"<int:\w+>", "1", str(rule))
    return re.sub(r"<(?:\w+:)?\w+>", "x", path)


class RouteGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.addClassCleanup(env_setup.release_app, cls.app)
        cls.routes = [
            (rule, cls.app.view_functions[rule.endpoint])
            for rule in cls.app.url_map.iter_rules()
            if rule.endpoint not in PUBLIC_ENDPOINTS
        ]
        cls.api = [(rule, view) for rule, view in cls.routes if str(rule).startswith("/api/")]
        cls.web = [(rule, view) for rule, view in cls.routes if str(rule).startswith("/web/")]

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.users = {}
        for role in sorted(ALL_ROLES):
            user = User(
                name=role.title(), email=f"{role.lower()}-guardas@test.local", role=role, is_active=True,
                password_hash=generate_password_hash("Clave-de-prueba-1*"),
            )
            db.session.add(user)
            self.users[role] = user
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    @staticmethod
    def methods(rule):
        return sorted(rule.methods - {"HEAD", "OPTIONS"})

    def test_every_route_is_either_public_on_purpose_or_has_a_guard(self):
        orphans = [
            f"{rule.endpoint} ({str(rule)})"
            for rule, view in self.routes
            if not (_has(view, _TOKEN_CODE) or _has(view, _LOGIN_CODE))
        ]
        self.assertEqual(orphans, [], "Rutas sin sesión que no están en la lista de públicas")

    def test_every_api_route_names_its_roles(self):
        without_roles = [
            f"{rule.endpoint} ({str(rule)})"
            for rule, view in self.api
            if rule.endpoint not in ANY_ROLE_ENDPOINTS and _declared_roles(view) is None
        ]
        self.assertEqual(without_roles, [], "Rutas de la API que no dicen qué roles las usan")

    def test_the_any_role_list_only_holds_routes_that_exist_and_do_not_name_roles(self):
        existing = {rule.endpoint for rule, _ in self.api}
        self.assertTrue(ANY_ROLE_ENDPOINTS <= existing)
        for rule, view in self.api:
            if rule.endpoint in ANY_ROLE_ENDPOINTS:
                self.assertIsNone(_declared_roles(view), rule.endpoint)

    def test_no_api_route_answers_without_a_session(self):
        for rule, _ in self.api:
            for method in self.methods(rule):
                response = self.client.open(_sample_path(rule), method=method)
                self.assertEqual(
                    response.status_code, 401, f"{method} {rule} respondió {response.status_code} sin sesión"
                )

    def test_a_role_that_the_route_does_not_name_gets_403(self):
        checked = 0
        for rule, view in self.api:
            allowed = _declared_roles(view)
            if allowed is None:
                continue
            for role in sorted(ALL_ROLES - allowed):
                headers = {"Authorization": f"Bearer {generate_token(self.users[role])}"}
                for method in self.methods(rule):
                    response = self.client.open(_sample_path(rule), method=method, headers=headers)
                    self.assertEqual(
                        response.status_code, 403, f"{role} en {method} {rule} respondió {response.status_code}"
                    )
                    checked += 1
        self.assertGreater(checked, 100)

    def test_every_web_page_sends_a_visitor_without_session_to_the_login(self):
        for rule, _ in self.web:
            if "GET" in rule.methods:
                response = self.client.get(_sample_path(rule))
                self.assertEqual(response.status_code, 302, f"GET {rule} respondió {response.status_code}")
                self.assertIn("/web/login", response.headers["Location"], str(rule))

    def test_every_web_form_needs_the_csrf_code_and_then_the_session(self):
        page = self.client.get("/web/login").get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        for rule, _ in self.web:
            if "POST" not in rule.methods:
                continue
            without_code = self.client.post(_sample_path(rule), data={})
            self.assertEqual(without_code.status_code, 400, f"POST {rule} sin código respondió {without_code.status_code}")
            with_code = self.client.post(_sample_path(rule), data={"csrf_token": token})
            self.assertEqual(with_code.status_code, 302, f"POST {rule} con código respondió {with_code.status_code}")
            self.assertIn("/web/login", with_code.headers["Location"], str(rule))

    def test_the_web_refuses_the_session_of_a_guard_and_of_a_resident(self):
        for role in ("GUARD", "RESIDENT"):
            self.client = self.app.test_client()
            page = self.client.get("/web/login").get_data(as_text=True)
            token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
            self.client.post("/web/login", data={
                "csrf_token": token, "email": self.users[role].email, "password": "Clave-de-prueba-1*",
            })
            response = self.client.get("/web/")
            self.assertEqual(response.status_code, 302, role)
            self.assertIn("/web/login", response.headers["Location"], role)


if __name__ == "__main__":
    unittest.main()
