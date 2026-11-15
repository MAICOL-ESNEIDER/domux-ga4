"""Pruebas del cierre de sesiones viejas (SEC-001).

El token de sesión dura 7 días. Antes, el guardia que entregaba el turno podía seguir usando el
suyo, y una contraseña restablecida no cerraba las sesiones abiertas con la anterior. Ahora cada
token lleva la «versión» de las sesiones de la persona: cuando sube, los tokens viejos no sirven.
"""

import unittest
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import env_setup  # noqa: F401  (va antes de importar la app)

import jwt
from werkzeug.security import generate_password_hash

from app import create_app
from auth import JWT_ALGORITHM, JWT_SECRET, generate_token
from extensions import db
from models import User

PASSWORD = "Clave-de-prueba-1*"
NEW_PASSWORD = "Otra-clave-de-prueba-2*"
RELEVO_PIN = "4821"
TABLET_PIN = "2468"


@lru_cache(maxsize=None)
def hashed(secret):
    """El hash de un texto, calculado una sola vez: scrypt es lento a propósito."""
    return generate_password_hash(secret)


class SessionClosingTestCase(unittest.TestCase):
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
        self.admin = self.make_user("ADMIN", "admin-sesion@test.local", "Ada")
        self.tablet = self.make_user("GUARD", "tablet-sesion@test.local", "Tomás", TABLET_PIN)
        self.relevo = self.make_user("GUARD", "relevo-sesion@test.local", "Rosa", RELEVO_PIN)
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def make_user(self, role, email, name, pin=None):
        user = User(
            name=name, email=email, role=role, is_active=True, password_hash=hashed(PASSWORD),
            pin_hash=hashed(pin) if pin else None,
        )
        db.session.add(user)
        return user

    def session(self, token):
        return self.client.get("/api/auth/session", headers={"Authorization": f"Bearer {token}"})

    def shift(self, token, guard, pin):
        return self.client.post(
            "/api/auth/guard-shift", headers={"Authorization": f"Bearer {token}"},
            json={"guardId": guard.id, "pin": pin},
        )

    def test_el_guardia_que_entrega_el_turno_ya_no_puede_usar_su_sesion(self):
        old_token = generate_token(self.tablet)
        self.assertEqual(self.session(old_token).status_code, 200)

        response = self.shift(old_token, self.relevo, RELEVO_PIN)

        self.assertEqual(response.status_code, 200)
        closed = self.session(old_token)
        self.assertEqual(closed.status_code, 401)
        self.assertIn("inicia sesión de nuevo", closed.get_json()["error"])
        self.assertEqual(self.session(response.get_json()["token"]).status_code, 200)

    def test_con_un_pin_incorrecto_la_sesion_de_la_tablet_sigue_sirviendo(self):
        token = generate_token(self.tablet)

        response = self.shift(token, self.relevo, "0000")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.session(token).status_code, 200)

    def test_el_mismo_guardia_que_confirma_su_turno_no_pierde_la_sesion(self):
        token = generate_token(self.tablet)

        response = self.shift(token, self.tablet, TABLET_PIN)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.session(token).status_code, 200)

    def test_el_guardia_que_entrego_puede_volver_a_tomar_el_turno(self):
        first = self.shift(generate_token(self.tablet), self.relevo, RELEVO_PIN).get_json()["token"]

        back = self.shift(first, self.tablet, TABLET_PIN)

        self.assertEqual(back.status_code, 200)
        self.assertEqual(self.session(back.get_json()["token"]).status_code, 200)
        self.assertEqual(self.session(first).status_code, 401)

    def test_restablecer_la_contrasena_cierra_las_sesiones_abiertas(self):
        old_token = generate_token(self.relevo)

        response = self.client.put(
            f"/api/admin/users/{self.relevo.id}/password",
            headers={"Authorization": f"Bearer {generate_token(self.admin)}"},
            json={"password": NEW_PASSWORD},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.session(old_token).status_code, 401)
        login = self.client.post("/api/auth/login", json={"email": self.relevo.email, "password": NEW_PASSWORD})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(self.session(login.get_json()["token"]).status_code, 200)

    def test_un_token_de_antes_de_esta_regla_sirve_hasta_que_se_cierran_las_sesiones(self):
        legacy = jwt.encode(
            {"user_id": self.tablet.id, "role": "GUARD", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            JWT_SECRET, algorithm=JWT_ALGORITHM,
        )
        self.assertEqual(self.session(legacy).status_code, 200)

        self.shift(legacy, self.relevo, RELEVO_PIN)

        self.assertEqual(self.session(legacy).status_code, 401)
