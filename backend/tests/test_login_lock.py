"""Pruebas del bloqueo tras 5 intentos fallidos (HU-006, RN-002, SEC-001 y SEC-011).

Cubren los criterios CA-HU-006-01 a CA-HU-006-03: al quinto fallo seguido la
cuenta se bloquea 15 minutos, un inicio correcto antes del quinto pone el
contador en cero y el correo que no existe recibe las mismas respuestas.
"""

import unittest
from datetime import timedelta
from unittest.mock import patch

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from auth import generate_token
from extensions import db
from models import LoginAttempt, User
from routes.auth import FAKE_PASSWORD_HASH, LOCKED_MESSAGE
from services.login_attempt_service import LOCK_MINUTES, MAX_FAILED_ATTEMPTS
from time_utils import utc_now

PASSWORD = "Clave-de-prueba-1*"
WRONG = "otra-clave-equivocada"


class LoginLockTests(unittest.TestCase):
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
        self.admin = self.make_user("admin-bloqueo@test.local", "ADMIN")
        self.guard = self.make_user("guardia-bloqueo@test.local", "GUARD")
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def make_user(self, email, role, active=True):
        user = User(
            name="Prueba", email=email, role=role, is_active=active,
            password_hash=generate_password_hash(PASSWORD),
        )
        db.session.add(user)
        return user

    def login(self, email, password):
        return self.client.post("/api/auth/login", json={"email": email, "password": password})

    def fail_times(self, email, times):
        return [self.login(email, WRONG) for _ in range(times)]

    # --- CA-HU-006-01 -----------------------------------------------------

    def test_a_correct_login_still_works(self):
        response = self.login(self.guard.email, PASSWORD)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["token"])

    def test_wrong_password_gets_the_generic_message(self):
        response = self.login(self.guard.email, WRONG)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "Credenciales inválidas")

    def test_fifth_failure_locks_the_account_for_15_minutes(self):
        responses = self.fail_times(self.guard.email, MAX_FAILED_ATTEMPTS)

        self.assertEqual([r.status_code for r in responses], [401] * 4 + [429])
        locked = responses[-1]
        self.assertEqual(locked.get_json()["error"], LOCKED_MESSAGE)
        self.assertIn("15 minutos", LOCKED_MESSAGE)
        self.assertEqual(int(locked.headers["Retry-After"]), LOCK_MINUTES * 60)

    def test_a_locked_account_rejects_even_the_right_password(self):
        self.fail_times(self.guard.email, MAX_FAILED_ATTEMPTS)

        response = self.login(self.guard.email, PASSWORD)

        self.assertEqual(response.status_code, 429)
        self.assertNotIn("token", response.get_json())

    def test_the_lock_ends_after_15_minutes(self):
        self.fail_times(self.guard.email, MAX_FAILED_ATTEMPTS)
        later = utc_now() + timedelta(minutes=LOCK_MINUTES, seconds=5)

        with patch("services.login_attempt_service.utc_now", return_value=later):
            response = self.login(self.guard.email, PASSWORD)

        self.assertEqual(response.status_code, 200)

    def test_after_the_lock_ends_the_count_starts_again(self):
        self.fail_times(self.guard.email, MAX_FAILED_ATTEMPTS)
        later = utc_now() + timedelta(minutes=LOCK_MINUTES, seconds=5)

        with patch("services.login_attempt_service.utc_now", return_value=later):
            responses = self.fail_times(self.guard.email, MAX_FAILED_ATTEMPTS - 1)

        self.assertEqual([r.status_code for r in responses], [401] * (MAX_FAILED_ATTEMPTS - 1))

    # --- CA-HU-006-02 -----------------------------------------------------

    def test_a_correct_login_before_the_fifth_failure_resets_the_count(self):
        self.fail_times(self.guard.email, MAX_FAILED_ATTEMPTS - 1)
        self.assertEqual(self.login(self.guard.email, PASSWORD).status_code, 200)

        responses = self.fail_times(self.guard.email, MAX_FAILED_ATTEMPTS - 1)

        self.assertEqual([r.status_code for r in responses], [401] * (MAX_FAILED_ATTEMPTS - 1))

    def test_the_count_ignores_capitals_and_spaces_in_the_email(self):
        self.client.post("/api/auth/login", json={"email": "  GUARDIA-BLOQUEO@test.local ", "password": WRONG})
        self.fail_times(self.guard.email, MAX_FAILED_ATTEMPTS - 2)

        last = self.login(self.guard.email, WRONG)

        self.assertEqual(last.status_code, 429)
        self.assertEqual(LoginAttempt.query.count(), 1)

    # --- CA-HU-006-03 y SEC-011 --------------------------------------------

    def test_an_unknown_email_gets_the_same_answers_as_a_real_one(self):
        real = self.fail_times(self.guard.email, MAX_FAILED_ATTEMPTS)
        unknown = self.fail_times("nadie@test.local", MAX_FAILED_ATTEMPTS)

        self.assertEqual([r.status_code for r in unknown], [r.status_code for r in real])
        self.assertEqual(
            [r.get_json()["error"] for r in unknown], [r.get_json()["error"] for r in real]
        )

    def test_an_unknown_email_is_checked_against_a_fake_hash(self):
        with patch("routes.auth.check_password_hash", wraps=check_password_hash) as compare:
            self.login("nadie@test.local", WRONG)

        compare.assert_called_once_with(FAKE_PASSWORD_HASH, WRONG)

    # --- Cuentas desactivadas y clave restablecida -------------------------

    def test_a_deactivated_account_keeps_its_own_message(self):
        retired = self.make_user("retirado-bloqueo@test.local", "RESIDENT", active=False)
        db.session.commit()

        response = self.login(retired.email, PASSWORD)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "Tu cuenta se encuentra inhabilitada")

    def test_resetting_the_password_unlocks_the_account(self):
        self.fail_times(self.guard.email, MAX_FAILED_ATTEMPTS)
        new_password = "Clave-nueva-2*"

        reset = self.client.put(
            f"/api/admin/users/{self.guard.id}/password",
            headers={"Authorization": f"Bearer {generate_token(self.admin)}"},
            json={"password": new_password},
        )

        self.assertEqual(reset.status_code, 200)
        self.assertEqual(self.login(self.guard.email, new_password).status_code, 200)


if __name__ == "__main__":
    unittest.main()
