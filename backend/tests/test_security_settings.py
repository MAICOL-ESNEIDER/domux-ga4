"""Pruebas de la configuración segura del servidor (TT-010).

Comprueban que la clave de los tokens sea obligatoria en producción, que la API no
acepte llamadas de páginas externas sin permiso y que las contraseñas de las
cuentas de prueba salgan del entorno sin mostrarse nunca en la consola.
"""

import io
import logging
import os
import secrets
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import check_password_hash

import seed
from app import create_app
from auth import load_jwt_secret
from extensions import db
from models import User

SEED_VARS = ("SEED_ADMIN_PASSWORD", "SEED_GUARD_PASSWORD", "SEED_RESIDENT_PASSWORD")


def strong_password():
    """Crea una contraseña de prueba al azar que cumple la política."""
    return secrets.token_urlsafe(9).replace("-", "x").replace("_", "y") + "Aa1*"


def environment_without(*names, **values):
    """Copia el entorno actual sin algunas variables y con otras cambiadas."""
    env = {key: value for key, value in os.environ.items() if key not in names}
    env.update(values)
    return env


class JwtSecretTests(unittest.TestCase):
    def test_production_without_secret_refuses_to_start(self):
        env = environment_without("JWT_SECRET", "APP_ENV", RENDER="true")
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError):
                load_jwt_secret()

    def test_development_without_secret_uses_temporary_random_key(self):
        env = environment_without("JWT_SECRET", "RENDER", "APP_ENV")
        with mock.patch.dict(os.environ, env, clear=True):
            first = load_jwt_secret()
            second = load_jwt_secret()
        self.assertEqual(len(first), 64)
        self.assertNotEqual(first, second)

    def test_configured_secret_is_used(self):
        value = secrets.token_hex(32)
        with mock.patch.dict(os.environ, {"JWT_SECRET": value}):
            self.assertEqual(load_jwt_secret(), value)


class CorsTests(unittest.TestCase):
    def test_external_pages_are_not_allowed_by_default(self):
        env = environment_without("CORS_ORIGINS")
        with mock.patch.dict(os.environ, env, clear=True):
            app = create_app()
        response = app.test_client().get(
            "/api/health", headers={"Origin": "https://pagina-ajena.example"}
        )
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_configured_origin_is_allowed(self):
        origin = "https://admin.domux.example"
        with mock.patch.dict(os.environ, {"CORS_ORIGINS": origin}):
            app = create_app()
        response = app.test_client().get("/api/health", headers={"Origin": origin})
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), origin)


class DemoAccountTests(unittest.TestCase):
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
        self.passwords = {name: strong_password() for name in SEED_VARS}

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def test_seed_uses_environment_passwords_and_never_prints_them(self):
        output, errors, logs = io.StringIO(), io.StringIO(), io.StringIO()
        handler = logging.StreamHandler(logs)
        logging.getLogger().addHandler(handler)
        try:
            env = environment_without("RENDER", "APP_ENV", **self.passwords)
            with mock.patch.dict(os.environ, env, clear=True):
                with redirect_stdout(output), redirect_stderr(errors):
                    seed.seed_if_empty()
        finally:
            logging.getLogger().removeHandler(handler)

        admin = User.query.filter_by(email="admin@domux.com").one()
        self.assertTrue(
            check_password_hash(admin.password_hash, self.passwords["SEED_ADMIN_PASSWORD"])
        )
        printed = output.getvalue() + errors.getvalue() + logs.getvalue()
        for password in self.passwords.values():
            self.assertNotIn(password, printed)

    def test_sync_applies_a_changed_password(self):
        env = environment_without("RENDER", "APP_ENV", **self.passwords)
        with mock.patch.dict(os.environ, env, clear=True):
            seed.seed_if_empty()
        new_password = strong_password()
        changed = dict(self.passwords, SEED_GUARD_PASSWORD=new_password)
        env = environment_without("RENDER", "APP_ENV", **changed)
        with mock.patch.dict(os.environ, env, clear=True):
            seed.sync_demo_passwords()
        guard = User.query.filter_by(email="guardia@domux.com").one()
        self.assertTrue(check_password_hash(guard.password_hash, new_password))

    def test_missing_variable_in_production_is_reported_by_name(self):
        env = environment_without("RENDER", "APP_ENV", **self.passwords)
        with mock.patch.dict(os.environ, env, clear=True):
            seed.seed_if_empty()
        others = {k: v for k, v in self.passwords.items() if k != "SEED_ADMIN_PASSWORD"}
        env = environment_without("SEED_ADMIN_PASSWORD", RENDER="true", **others)
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertLogs("seed", level="WARNING") as logs:
                seed.sync_demo_passwords()
        self.assertEqual(len(logs.output), 1)
        self.assertIn("SEED_ADMIN_PASSWORD no está configurada", logs.output[0])

    def test_production_without_variables_creates_no_demo_accounts(self):
        env = environment_without(*SEED_VARS, RENDER="true")
        with mock.patch.dict(os.environ, env, clear=True):
            seed.seed_if_empty()
        self.assertEqual(User.query.count(), 0)

    def test_weak_password_is_replaced_in_development(self):
        weak = dict(self.passwords, SEED_ADMIN_PASSWORD="1234")
        env = environment_without("RENDER", "APP_ENV", **weak)
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch.object(seed, "_save_generated_credentials") as save:
                seed.seed_if_empty()
        saved = save.call_args.args[0]
        self.assertEqual(set(saved), {"admin@domux.com"})
        admin = User.query.filter_by(email="admin@domux.com").one()
        self.assertFalse(check_password_hash(admin.password_hash, "1234"))
        self.assertTrue(check_password_hash(admin.password_hash, saved["admin@domux.com"]))


if __name__ == "__main__":
    unittest.main()
