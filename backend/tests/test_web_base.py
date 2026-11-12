"""Pruebas de la base de la web de administración (HU-074, RN-006 y RNF-005).

Cubren el inicio de sesión (solo la administración entra, CA-HU-074-01 y CA-HU-074-02), el cierre y el
vencimiento de la sesión, el código contra CSRF, las cabeceras de seguridad y que la API de la app
siga respondiendo igual que antes.
"""

import re
import time
import unittest
from pathlib import Path

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import generate_password_hash

from app import create_app
from extensions import db
from models import AuditLog, User
from structure_fixtures import apartment_for
from web.security import IDLE_SECONDS, safe_next

#: Contraseña de las cuentas de prueba (solo existe en estas pruebas).
PASSWORD = "Clave-de-prueba-1*"

TEMPLATES = Path(__file__).resolve().parent.parent / "web" / "templates"


class WebBaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.addClassCleanup(env_setup.release_app, cls.app)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.admin = self.user("ADMIN", "admin-web@test.local", name="Lucía", last_name="Vargas")
        self.guard = self.user("GUARD", "guardia-web@test.local")
        self.resident = self.user(
            "RESIDENT", "residente-web@test.local",
            apartment_ref=apartment_for("Apto 101"), phone="3000000000", occupancy_type="propietario",
        )
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def user(self, role, email, name=None, **fields):
        person = User(
            name=name or role.title(), email=email, role=role, is_active=True,
            password_hash=generate_password_hash(PASSWORD), **fields,
        )
        db.session.add(person)
        return person

    # --- Ayudas -----------------------------------------------------------------------------------

    def csrf(self, path="/web/login"):
        """El código contra CSRF que la página entrega a este navegador."""
        page = self.client.get(path)
        found = re.search(r'name="csrf_token" value="([^"]+)"', page.get_data(as_text=True))
        self.assertIsNotNone(found, "la página no trae el código contra CSRF")
        return found.group(1)

    def log_in(self, email="admin-web@test.local", password=PASSWORD, next_url=""):
        return self.client.post("/web/login", data={
            "csrf_token": self.csrf(), "email": email, "password": password, "next": next_url,
        })

    def text(self, response):
        return response.get_data(as_text=True)

    def audit_actions(self):
        return [entry.action for entry in AuditLog.query.order_by(AuditLog.id).all()]

    # --- La dirección principal y las cabeceras ---------------------------------------------------

    def test_root_redirects_to_the_web(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/web/"))

    def test_panel_asks_for_login(self):
        response = self.client.get("/web/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/web/login"))

    def test_web_pages_carry_security_headers_and_the_api_does_not(self):
        page = self.client.get("/web/login")
        self.assertEqual(page.status_code, 200)
        policy = page.headers["Content-Security-Policy"]
        self.assertIn("default-src 'self'", policy)
        self.assertIn("script-src 'self'", policy)
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertEqual(page.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(page.headers["X-Frame-Options"], "DENY")
        self.assertEqual(page.headers["Cache-Control"], "no-store")
        self.assertEqual(page.headers["Referrer-Policy"], "same-origin")

        api = self.client.get("/api/health")
        self.assertEqual(api.status_code, 200)
        self.assertNotIn("Content-Security-Policy", api.headers)

    def test_session_cookie_is_hidden_from_scripts_and_limited_to_the_web(self):
        cookies = self.client.get("/web/login").headers.getlist("Set-Cookie")
        cookie = next(value for value in cookies if value.startswith("domux_web="))
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertIn("Path=/web", cookie)

    def test_static_files_are_public_and_revalidated_by_the_browser(self):
        response = self.client.get("/web/static/domux.css")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/css", response.headers["Content-Type"])
        self.assertNotIn("no-store", response.headers.get("Cache-Control", ""))
        self.assertTrue(response.headers.get("ETag"))
        response.close()
        # Sin cambios, el servidor responde 304 y no vuelve a enviar el archivo.
        again = self.client.get("/web/static/domux.css", headers={"If-None-Match": response.headers["ETag"]})
        self.assertEqual(again.status_code, 304)
        again.close()
        # Los demás archivos que cargan las páginas existen (si falta uno, la página se ve rota).
        for name in ("domux.js", "nojs.css", "img/domux-logo.svg"):
            with self.subTest(file=name):
                found = self.client.get(f"/web/static/{name}")
                self.assertEqual(found.status_code, 200)
                found.close()

    def test_templates_use_no_inline_scripts_or_styles(self):
        """La política de seguridad bloquea lo que va dentro de la página; aquí se evita escribirlo."""
        for template in TEMPLATES.rglob("*.html"):
            source = template.read_text(encoding="utf-8")
            with self.subTest(template=template.name):
                self.assertNotRegex(source, r'\sstyle\s*=', "estilos dentro de la página")
                self.assertNotRegex(source, r'<style[\s>]', "bloque de estilos dentro de la página")
                self.assertNotRegex(source, r'\son[a-z]+\s*=', "eventos escritos en el HTML")
                self.assertNotRegex(source, r'<script(?![^>]*\ssrc=)', "script dentro de la página")

    # --- Inicio de sesión ------------------------------------------------------------------------

    def test_administrator_logs_in_and_reaches_the_panel(self):
        response = self.log_in()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/web/"))

        panel = self.client.get("/web/")
        self.assertEqual(panel.status_code, 200)
        body = self.text(panel)
        self.assertIn("Lucía", body)
        self.assertIn("Cerrar sesión", body)
        self.assertIn("Administración", body)
        self.assertIn("web_login", self.audit_actions())

    def test_logged_in_administrator_skips_the_login_page(self):
        self.log_in()
        response = self.client.get("/web/login")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/web/"))

    def test_resident_and_guard_cannot_enter_even_with_the_right_password(self):
        for email, role in (("residente-web@test.local", "RESIDENT"), ("guardia-web@test.local", "GUARD")):
            with self.subTest(role=role):
                response = self.log_in(email=email)
                self.assertEqual(response.status_code, 403)
                self.assertIn("solo para la administración", self.text(response))
                # No quedó ninguna sesión abierta.
                self.assertEqual(self.client.get("/web/").status_code, 302)
        self.assertEqual(self.audit_actions().count("web_login_denied"), 2)
        self.assertNotIn("web_login", self.audit_actions())

    def test_wrong_password_gives_the_same_message_as_the_app(self):
        response = self.log_in(password="otra-clave-cualquiera")
        body = self.text(response)
        self.assertEqual(response.status_code, 401)
        self.assertIn("Credenciales inválidas", body)
        self.assertIn("admin-web@test.local", body)  # el correo se conserva para no escribirlo de nuevo
        self.assertNotIn("otra-clave-cualquiera", body)  # la contraseña nunca vuelve a la página

        unknown = self.log_in(email="nadie@test.local", password="otra-clave-cualquiera")
        self.assertEqual(unknown.status_code, 401)
        self.assertIn("Credenciales inválidas", self.text(unknown))

    def test_five_failures_lock_the_account_for_fifteen_minutes(self):
        statuses = [self.log_in(password="mal-%d" % number).status_code for number in range(5)]
        self.assertEqual(statuses, [401, 401, 401, 401, 429])
        blocked = self.log_in()  # aunque ahora la contraseña sea la correcta
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("bloqueada", self.text(blocked))

    def test_empty_fields_are_asked_for(self):
        response = self.client.post("/web/login", data={"csrf_token": self.csrf(), "email": "", "password": ""})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Escribe tu correo y tu contraseña", self.text(response))

    def test_inactive_account_cannot_enter(self):
        self.admin.is_active = False
        db.session.commit()
        response = self.log_in()
        self.assertEqual(response.status_code, 401)
        self.assertIn("inhabilitada", self.text(response))

    # --- CSRF -------------------------------------------------------------------------------------

    def test_forms_without_the_csrf_code_are_refused(self):
        self.client.get("/web/login")
        for data in ({"email": "a@b.co", "password": "x"}, {"csrf_token": "falso", "email": "a@b.co", "password": "x"}):
            with self.subTest(data=sorted(data)):
                response = self.client.post("/web/login", data=data)
                self.assertEqual(response.status_code, 400)
                self.assertIn("El formulario venció", self.text(response))
                self.assertEqual(response.content_type.split(";")[0], "text/html")

    def test_logout_needs_the_code_and_closes_the_session(self):
        self.log_in()
        self.assertEqual(self.client.post("/web/logout").status_code, 400)
        self.assertEqual(self.client.get("/web/").status_code, 200)  # sigue dentro

        response = self.client.post("/web/logout", data={"csrf_token": self.csrf("/web/")})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/web/").status_code, 302)
        self.assertIn("Cerraste la sesión", self.text(self.client.get("/web/login")))

    def test_the_code_changes_after_logging_in(self):
        before = self.csrf()
        self.log_in()
        self.assertNotEqual(before, self.csrf("/web/"))

    # --- La sesión vence o deja de valer -----------------------------------------------------------

    def test_session_closes_after_thirty_idle_minutes(self):
        self.log_in()
        with self.client.session_transaction("/web/") as web_session:
            web_session["seen"] = int(time.time()) - IDLE_SECONDS - 5
        response = self.client.get("/web/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("inactividad", self.text(self.client.get("/web/login")))

    def test_activity_keeps_the_session_alive(self):
        self.log_in()
        with self.client.session_transaction("/web/") as web_session:
            web_session["seen"] = int(time.time()) - IDLE_SECONDS + 60
        self.assertEqual(self.client.get("/web/").status_code, 200)
        with self.client.session_transaction("/web/") as web_session:
            self.assertGreater(web_session["seen"], int(time.time()) - 30)

    def test_deactivating_the_account_closes_the_web_at_once(self):
        self.log_in()
        self.admin.is_active = False
        db.session.commit()
        self.assertEqual(self.client.get("/web/").status_code, 302)
        self.assertIn("ya no es válida", self.text(self.client.get("/web/login")))

    def test_a_session_of_a_non_administrator_is_never_accepted(self):
        self.log_in()
        with self.client.session_transaction("/web/") as web_session:
            web_session["uid"] = self.resident.id
        self.assertEqual(self.client.get("/web/").status_code, 302)

    def test_login_remembers_the_page_but_never_leaves_the_web(self):
        for target in ("https://malo.example/web/x", "//malo.example/web/x", "/api/admin/users", "javascript:alert(1)"):
            with self.subTest(target=target):
                client = self.app.test_client()
                page = client.get("/web/login")
                token = re.search(r'name="csrf_token" value="([^"]+)"', page.get_data(as_text=True)).group(1)
                response = client.post("/web/login", data={
                    "csrf_token": token, "email": "admin-web@test.local", "password": PASSWORD, "next": target,
                })
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.headers["Location"].endswith("/web/"))

    def test_safe_next_accepts_only_pages_of_the_web(self):
        self.assertEqual(safe_next("/web/pqrs?status=abierta"), "/web/pqrs?status=abierta")
        for target in (None, "", "/web/login", "/web/static/domux.css", "/api/health", "//malo.example/web/x",
                       "https://malo.example/web/x", "javascript:alert(1)", "web/pqrs"):
            with self.subTest(target=target):
                self.assertIsNone(safe_next(target))

    # --- Errores y la API --------------------------------------------------------------------------

    def test_unknown_web_page_answers_with_a_page_and_the_api_keeps_json(self):
        page = self.client.get("/web/no-existe")
        self.assertEqual(page.status_code, 404)
        self.assertEqual(page.content_type.split(";")[0], "text/html")
        self.assertIn("No encontramos esa página", self.text(page))

        api = self.client.get("/api/no-existe")
        self.assertEqual(api.status_code, 404)
        self.assertIn("error", api.get_json())

    def test_error_page_of_a_logged_in_administrator_keeps_the_menu(self):
        self.log_in()
        page = self.client.get("/web/no-existe")
        self.assertEqual(page.status_code, 404)
        self.assertIn("Cerrar sesión", self.text(page))

    def test_app_login_keeps_working(self):
        response = self.client.post("/api/auth/login", json={"email": "admin-web@test.local", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.get_json())
        # y sigue pidiendo JSON
        form = self.client.post("/api/auth/login", data={"email": "a@b.co", "password": "x"})
        self.assertEqual(form.status_code, 400)


if __name__ == "__main__":
    unittest.main()
