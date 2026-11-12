"""Base común de las pruebas de las páginas de la web de administración.

Deja listos una administradora, un guardia y una residente con su apartamento, y entrega las ayudas
para entrar a la web, mandar formularios con su código contra CSRF y leer el texto de las páginas.
"""

import re
import unittest

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import generate_password_hash

from app import create_app
from extensions import db
from models import User
from structure_fixtures import apartment_for

#: Contraseña de las cuentas de prueba (solo existe en las pruebas).
PASSWORD = "Clave-de-prueba-1*"

_TOKEN = re.compile(r'name="csrf_token" value="([^"]+)"')


class WebTestCase(unittest.TestCase):
    """Una administradora (Lucía Vargas), un guardia y una residente (Marta Ríos, Torre 1 · Apto 101)."""

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
        self.admin = self.make_user("ADMIN", "admin-web@test.local", "Lucía", last_name="Vargas")
        self.guard = self.make_user("GUARD", "guardia-web@test.local", "Guardia")
        self.resident = self.make_user(
            "RESIDENT", "residente-web@test.local", "Marta", last_name="Ríos",
            apartment_ref=apartment_for("Torre 1 · 101"), phone="3000000000", occupancy_type="propietario",
        )
        db.session.commit()
        self.client = self.app.test_client()
        self._token = None

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def make_user(self, role, email, name, **fields):
        user = User(
            name=name, email=email, role=role, is_active=True,
            password_hash=generate_password_hash(PASSWORD), **fields,
        )
        db.session.add(user)
        db.session.flush()
        return user

    # --- Entrar y mandar formularios --------------------------------------------------------------

    def token_of(self, path):
        """El código contra CSRF que entrega esa página a este navegador."""
        found = _TOKEN.search(self.client.get(path).get_data(as_text=True))
        self.assertIsNotNone(found, f"{path} no trae el código contra CSRF")
        return found.group(1)

    def log_in(self, email="admin-web@test.local", password=PASSWORD):
        response = self.client.post("/web/login", data={
            "csrf_token": self.token_of("/web/login"), "email": email, "password": password,
        })
        self._token = None
        return response

    def post(self, path, data=None, follow=False):
        """Manda un formulario con el código contra CSRF de la sesión abierta."""
        if self._token is None:
            self._token = self.token_of("/web/")
        form = {"csrf_token": self._token, **(data or {})}
        return self.client.post(path, data=form, follow_redirects=follow)

    def text(self, response):
        return response.get_data(as_text=True)

    def page(self, path):
        """El texto de una página que se espera que cargue bien."""
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, f"{path} respondió {response.status_code}")
        return self.text(response)
