"""Pruebas del PIN del guardia y del cambio de turno en la tablet (HU-010, RN-029 y CU-008).

Cubren CA-HU-010-01 (un guardia toma el turno con su PIN y desde ese momento los
registros quedan a su nombre) y CA-HU-010-02 (con un PIN incorrecto no cambia el
guardia activo), las excepciones de CU-008 (PIN incorrecto y cuenta desactivada)
y el bloqueo de 15 minutos tras 5 intentos fallidos, igual que el de la contraseña
(HU-006).
"""

import unittest
from datetime import timedelta
from functools import lru_cache
from unittest.mock import patch

import env_setup  # noqa: F401  (va antes de importar la app)

import jwt
from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from auth import JWT_ALGORITHM, JWT_SECRET, generate_token
from extensions import db
from models import AuditLog, LoginAttempt, PackageItem, User
from routes.auth import PIN_LOCKED_MESSAGE
from services.login_attempt_service import LOCK_MINUTES, MAX_FAILED_ATTEMPTS
from structure_fixtures import apartment_in
from time_utils import utc_now

PASSWORD = "Clave-de-prueba-1*"
TABLET_PIN = "2468"
RELEVO_PIN = "4821"
OTRO_PIN = "7305"
INACTIVE_PIN = "9136"
NEW_PIN = "5072"
WRONG_PIN = "0000"


@lru_cache(maxsize=None)
def hashed(secret):
    """El hash de un texto, calculado una sola vez: scrypt es lento a propósito."""
    return generate_password_hash(secret)


class GuardPinTestCase(unittest.TestCase):
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
        self.admin = self.make_user("ADMIN", "admin-pin@test.local", "Ada", "Admin")
        # La sesión abierta en la tablet es la de este guardia.
        self.tablet = self.make_user("GUARD", "tablet-pin@test.local", "Tomás", "Turno", TABLET_PIN)
        self.relevo = self.make_user("GUARD", "relevo-pin@test.local", "Rosa", "Relevo", RELEVO_PIN)
        self.otro = self.make_user("GUARD", "otro-pin@test.local", "Oscar", "Otro", OTRO_PIN)
        self.without_pin = self.make_user("GUARD", "sinpin-pin@test.local", "Sara", "SinPin")
        self.inactive = self.make_user(
            "GUARD", "inactivo-pin@test.local", "Iván", "Inactivo", INACTIVE_PIN, active=False
        )
        self.resident = self.make_user(
            "RESIDENT", "residente-pin@test.local", "Rita", "Residente",
            apartment_ref=apartment_in("Torre 1", "101"), occupancy_type="propietario",
        )
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def make_user(self, role, email, name, last_name, pin=None, active=True, **fields):
        user = User(
            name=name, last_name=last_name, email=email, role=role, is_active=active,
            password_hash=hashed(PASSWORD),
            pin_hash=hashed(pin) if pin else None, **fields,
        )
        db.session.add(user)
        return user

    def headers(self, user):
        return {"Authorization": f"Bearer {generate_token(user)}"}

    def shift(self, guard_id, pin, session=None):
        """Lo que hace la tablet: el guardia elegido manda su PIN con la sesión abierta."""
        return self.client.post(
            "/api/auth/guard-shift",
            headers=self.headers(session or self.tablet),
            json={"guardId": guard_id, "pin": pin},
        )

    def set_pin(self, user_id, pin, by=None):
        return self.client.put(
            f"/api/admin/users/{user_id}/pin", headers=self.headers(by or self.admin), json={"pin": pin}
        )

    def fail_times(self, guard, times):
        return [self.shift(guard.id, WRONG_PIN) for _ in range(times)]

    def audit_entries(self, action):
        return AuditLog.query.filter_by(entity_type="user", action=action).all()


class AssignPinTests(GuardPinTestCase):
    """API-USR-06: el administrador asigna el PIN de un guardia."""

    def test_the_administrator_assigns_a_pin_to_a_guard(self):
        self.assertFalse(self.without_pin.pin_hash)

        response = self.set_pin(self.without_pin.id, NEW_PIN)

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertTrue(response.get_json()["user"]["hasPin"])
        db.session.refresh(self.without_pin)
        self.assertTrue(check_password_hash(self.without_pin.pin_hash, NEW_PIN))

    def test_the_pin_is_saved_with_a_hash_and_never_returned(self):
        response = self.set_pin(self.without_pin.id, NEW_PIN)

        db.session.refresh(self.without_pin)
        self.assertNotEqual(self.without_pin.pin_hash, NEW_PIN)
        self.assertNotIn(NEW_PIN, self.without_pin.pin_hash)
        text = response.get_data(as_text=True)
        self.assertNotIn(self.without_pin.pin_hash, text)
        self.assertEqual(
            sorted(key for key in response.get_json()["user"] if "pin" in key.lower()), ["hasPin"]
        )

    def test_a_new_pin_replaces_the_old_one(self):
        self.assertEqual(self.set_pin(self.relevo.id, NEW_PIN).status_code, 200)

        self.assertEqual(self.shift(self.relevo.id, RELEVO_PIN).status_code, 401)
        self.assertEqual(self.shift(self.relevo.id, NEW_PIN).status_code, 200)

    def test_assigning_a_pin_leaves_an_audit_entry_without_the_pin(self):
        self.set_pin(self.without_pin.id, NEW_PIN)

        (entry,) = self.audit_entries("pin_set")
        self.assertEqual(entry.entity_id, self.without_pin.id)
        self.assertEqual(entry.actor_id, self.admin.id)
        self.assertEqual(entry.actor_role, "ADMIN")
        self.assertNotIn(NEW_PIN, entry.details or "")

    def test_the_pin_must_be_exactly_four_digits(self):
        for bad_pin in ("123", "12345", "abcd", "12a4", " 123", "１２３４", "12 4", "", "   ", 1234, None, ["1234"]):
            with self.subTest(pin=bad_pin):
                response = self.set_pin(self.without_pin.id, bad_pin)

                self.assertEqual(response.status_code, 400)
        db.session.refresh(self.without_pin)
        self.assertIsNone(self.without_pin.pin_hash)

    def test_a_pin_may_start_with_zero(self):
        self.assertEqual(self.set_pin(self.without_pin.id, "0042").status_code, 200)

        self.assertEqual(self.shift(self.without_pin.id, "0042").status_code, 200)

    def test_only_guards_have_a_pin(self):
        for target in (self.resident, self.admin):
            with self.subTest(role=target.role):
                response = self.set_pin(target.id, NEW_PIN)

                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.get_json()["error"], "Solo los guardias tienen PIN para cambiar de turno."
                )
        db.session.refresh(self.resident)
        self.assertIsNone(self.resident.pin_hash)

    def test_an_unknown_user_is_not_found(self):
        self.assertEqual(self.set_pin(9999, NEW_PIN).status_code, 404)

    def test_only_the_administrator_assigns_pins(self):
        for session in (self.tablet, self.resident):
            with self.subTest(role=session.role):
                self.assertEqual(self.set_pin(self.without_pin.id, NEW_PIN, by=session).status_code, 403)
        anonymous = self.client.put(f"/api/admin/users/{self.without_pin.id}/pin", json={"pin": NEW_PIN})
        self.assertEqual(anonymous.status_code, 401)
        db.session.refresh(self.without_pin)
        self.assertIsNone(self.without_pin.pin_hash)

    def test_has_pin_shows_in_the_user_list(self):
        response = self.client.get("/api/admin/users?role=GUARD&pageSize=100", headers=self.headers(self.admin))

        by_id = {user["id"]: user for user in response.get_json()["users"]}
        self.assertTrue(by_id[self.relevo.id]["hasPin"])
        self.assertFalse(by_id[self.without_pin.id]["hasPin"])

    def test_a_user_that_stops_being_a_guard_loses_the_pin(self):
        response = self.client.put(
            f"/api/admin/users/{self.relevo.id}", headers=self.headers(self.admin), json={"role": "ADMIN"}
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        db.session.refresh(self.relevo)
        self.assertIsNone(self.relevo.pin_hash)

        # Si vuelve a ser guardia, el administrador debe asignarle un PIN de nuevo.
        response = self.client.put(
            f"/api/admin/users/{self.relevo.id}", headers=self.headers(self.admin), json={"role": "GUARD"}
        )
        self.assertFalse(response.get_json()["user"]["hasPin"])
        self.assertEqual(self.shift(self.relevo.id, RELEVO_PIN).status_code, 409)

    def test_editing_other_data_of_a_guard_keeps_the_pin(self):
        self.client.put(
            f"/api/admin/users/{self.relevo.id}", headers=self.headers(self.admin), json={"phone": "3001234567"}
        )

        self.assertEqual(self.shift(self.relevo.id, RELEVO_PIN).status_code, 200)


class GuardListTests(GuardPinTestCase):
    """API-AUTH-04: los guardias entre los que la tablet deja elegir (CU-008, paso 2)."""

    def test_a_guard_sees_only_the_active_guards_with_a_pin(self):
        response = self.client.get("/api/auth/guards", headers=self.headers(self.tablet))

        self.assertEqual(response.status_code, 200)
        names = [guard["name"] for guard in response.get_json()["guards"]]
        self.assertEqual(names, ["Oscar Otro", "Rosa Relevo", "Tomás Turno"])

    def test_the_list_only_has_the_id_and_the_name(self):
        response = self.client.get("/api/auth/guards", headers=self.headers(self.tablet))

        for guard in response.get_json()["guards"]:
            self.assertEqual(sorted(guard), ["id", "name"])

    def test_a_guard_without_a_pin_appears_once_he_has_one(self):
        self.set_pin(self.without_pin.id, NEW_PIN)

        response = self.client.get("/api/auth/guards", headers=self.headers(self.tablet))

        self.assertIn("Sara SinPin", [guard["name"] for guard in response.get_json()["guards"]])

    def test_only_guards_read_the_list(self):
        for session in (self.admin, self.resident):
            with self.subTest(role=session.role):
                response = self.client.get("/api/auth/guards", headers=self.headers(session))

                self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get("/api/auth/guards").status_code, 401)


class GuardShiftTests(GuardPinTestCase):
    """API-AUTH-03: el guardia que entra toma el turno con su PIN (CA-HU-010-01 y 02)."""

    def test_a_correct_pin_gives_the_session_of_the_new_guard(self):
        response = self.shift(self.relevo.id, RELEVO_PIN)

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual(body["user"]["id"], self.relevo.id)
        self.assertEqual(body["user"]["role"], "GUARD")
        payload = jwt.decode(body["token"], JWT_SECRET, algorithms=[JWT_ALGORITHM])
        self.assertEqual(payload["user_id"], self.relevo.id)
        self.assertEqual(payload["role"], "GUARD")

    def test_the_new_token_opens_the_session_of_the_new_guard(self):
        token = self.shift(self.relevo.id, RELEVO_PIN).get_json()["token"]

        session = self.client.get("/api/auth/session", headers={"Authorization": f"Bearer {token}"})

        self.assertEqual(session.get_json()["user"]["id"], self.relevo.id)

    def test_records_after_the_change_are_in_the_name_of_the_new_guard(self):
        before = self.client.post(
            "/api/packages", headers=self.headers(self.tablet),
            json={"residentId": self.resident.id, "description": "Caja antes del cambio"},
        )
        token = self.shift(self.relevo.id, RELEVO_PIN).get_json()["token"]

        after = self.client.post(
            "/api/packages", headers={"Authorization": f"Bearer {token}"},
            json={"residentId": self.resident.id, "description": "Caja después del cambio"},
        )

        self.assertEqual(before.get_json()["packageItem"]["registeredByName"], "Tomás Turno")
        self.assertEqual(after.get_json()["packageItem"]["registeredByName"], "Rosa Relevo")
        # Los registros anteriores siguen a nombre del guardia anterior.
        registered = {item.description: item.registered_by for item in PackageItem.query.all()}
        self.assertEqual(registered["Caja antes del cambio"], self.tablet.id)
        self.assertEqual(registered["Caja después del cambio"], self.relevo.id)

    def test_a_wrong_pin_does_not_change_the_active_guard(self):
        response = self.shift(self.relevo.id, WRONG_PIN)

        self.assertEqual(response.status_code, 401)
        self.assertNotIn("token", response.get_json())
        self.assertEqual(response.get_json()["error"], "PIN incorrecto. El guardia activo no cambió.")
        # La sesión de la tablet sigue siendo la del guardia que ya estaba.
        session = self.client.get("/api/auth/session", headers=self.headers(self.tablet))
        self.assertEqual(session.get_json()["user"]["id"], self.tablet.id)

    def test_a_guard_can_confirm_himself_with_his_own_pin(self):
        response = self.shift(self.tablet.id, TABLET_PIN)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"]["id"], self.tablet.id)

    def test_a_deactivated_guard_cannot_take_the_shift(self):
        response = self.shift(self.inactive.id, INACTIVE_PIN)

        self.assertEqual(response.status_code, 403)
        self.assertNotIn("token", response.get_json())
        self.assertIn("desactivada", response.get_json()["error"])
        self.assertEqual(LoginAttempt.query.count(), 0)

    def test_a_guard_without_a_pin_cannot_take_the_shift(self):
        response = self.shift(self.without_pin.id, "1357")

        self.assertEqual(response.status_code, 409)
        self.assertIn("todavía no tiene PIN", response.get_json()["error"])
        self.assertEqual(LoginAttempt.query.count(), 0)

    def test_someone_who_is_not_a_guard_cannot_be_chosen(self):
        unknown = self.shift(9999, RELEVO_PIN)
        for target in (self.admin, self.resident):
            with self.subTest(role=target.role):
                response = self.shift(target.id, RELEVO_PIN)

                # Se responde igual que a un guardia que no existe: no se revelan los roles.
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.get_json(), unknown.get_json())
        self.assertEqual(LoginAttempt.query.count(), 0)

    def test_the_guard_and_the_pin_must_be_valid(self):
        bad_requests = (
            {"pin": RELEVO_PIN},
            {"guardId": "abc", "pin": RELEVO_PIN},
            {"guardId": True, "pin": RELEVO_PIN},
            {"guardId": 0, "pin": RELEVO_PIN},
            {"guardId": -3, "pin": RELEVO_PIN},
            {"guardId": 1.5, "pin": RELEVO_PIN},
            {"guardId": self.relevo.id},
            {"guardId": self.relevo.id, "pin": "48"},
            {"guardId": self.relevo.id, "pin": 4821},
            {"guardId": self.relevo.id, "pin": "48 1"},
        )
        for body in bad_requests:
            with self.subTest(body=body):
                response = self.client.post(
                    "/api/auth/guard-shift", headers=self.headers(self.tablet), json=body
                )

                self.assertEqual(response.status_code, 400)
        # Un dato mal escrito no cuenta como intento fallido.
        self.assertEqual(LoginAttempt.query.count(), 0)

    def test_the_body_must_be_a_json_object(self):
        response = self.client.post(
            "/api/auth/guard-shift", headers=self.headers(self.tablet), data="no es json",
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, 400)

    def test_only_guards_use_the_shift_route(self):
        for session in (self.admin, self.resident):
            with self.subTest(role=session.role):
                self.assertEqual(self.shift(self.relevo.id, RELEVO_PIN, session=session).status_code, 403)
        anonymous = self.client.post(
            "/api/auth/guard-shift", json={"guardId": self.relevo.id, "pin": RELEVO_PIN}
        )
        self.assertEqual(anonymous.status_code, 401)

    def test_taking_the_shift_leaves_an_audit_entry(self):
        self.shift(self.relevo.id, RELEVO_PIN)

        (entry,) = self.audit_entries("guard_shift")
        self.assertEqual(entry.entity_id, self.relevo.id)
        self.assertEqual(entry.actor_id, self.relevo.id)
        self.assertIn(f'"previousGuardId": {self.tablet.id}', entry.details)
        self.assertNotIn(RELEVO_PIN, entry.details)

    def test_a_wrong_pin_leaves_no_audit_entry(self):
        self.shift(self.relevo.id, WRONG_PIN)

        self.assertEqual(self.audit_entries("guard_shift"), [])


class PinLockTests(GuardPinTestCase):
    """El PIN se bloquea como la contraseña: 5 fallos seguidos, 15 minutos (HU-006)."""

    def test_the_fifth_wrong_pin_locks_the_pin_for_15_minutes(self):
        responses = self.fail_times(self.relevo, MAX_FAILED_ATTEMPTS)

        self.assertEqual([r.status_code for r in responses], [401] * 4 + [429])
        locked = responses[-1]
        self.assertEqual(locked.get_json()["error"], PIN_LOCKED_MESSAGE)
        self.assertIn("15 minutos", PIN_LOCKED_MESSAGE)
        self.assertEqual(int(locked.headers["Retry-After"]), LOCK_MINUTES * 60)

    def test_a_locked_pin_rejects_even_the_right_pin(self):
        self.fail_times(self.relevo, MAX_FAILED_ATTEMPTS)

        response = self.shift(self.relevo.id, RELEVO_PIN)

        self.assertEqual(response.status_code, 429)
        self.assertNotIn("token", response.get_json())
        self.assertGreater(int(response.headers["Retry-After"]), 0)

    def test_the_lock_ends_after_15_minutes(self):
        self.fail_times(self.relevo, MAX_FAILED_ATTEMPTS)
        later = utc_now() + timedelta(minutes=LOCK_MINUTES, seconds=5)

        with patch("services.login_attempt_service.utc_now", return_value=later):
            response = self.shift(self.relevo.id, RELEVO_PIN)

        self.assertEqual(response.status_code, 200)

    def test_after_the_lock_ends_the_count_starts_again(self):
        self.fail_times(self.relevo, MAX_FAILED_ATTEMPTS)
        later = utc_now() + timedelta(minutes=LOCK_MINUTES, seconds=5)

        with patch("services.login_attempt_service.utc_now", return_value=later):
            responses = self.fail_times(self.relevo, MAX_FAILED_ATTEMPTS - 1)

        self.assertEqual([r.status_code for r in responses], [401] * (MAX_FAILED_ATTEMPTS - 1))

    def test_a_right_pin_before_the_fifth_failure_resets_the_count(self):
        self.fail_times(self.relevo, MAX_FAILED_ATTEMPTS - 1)
        self.assertEqual(self.shift(self.relevo.id, RELEVO_PIN).status_code, 200)

        responses = self.fail_times(self.relevo, MAX_FAILED_ATTEMPTS - 1)

        self.assertEqual([r.status_code for r in responses], [401] * (MAX_FAILED_ATTEMPTS - 1))

    def test_the_lock_is_only_for_the_pin_of_that_guard(self):
        self.fail_times(self.relevo, MAX_FAILED_ATTEMPTS)

        # Otro guardia sí puede tomar el turno...
        self.assertEqual(self.shift(self.otro.id, OTRO_PIN).status_code, 200)
        # ...y el guardia con el PIN bloqueado todavía puede entrar con su contraseña.
        login = self.client.post(
            "/api/auth/login", json={"email": self.relevo.email, "password": PASSWORD}
        )
        self.assertEqual(login.status_code, 200)

    def test_a_locked_login_does_not_lock_the_pin(self):
        for _ in range(MAX_FAILED_ATTEMPTS):
            self.client.post("/api/auth/login", json={"email": self.relevo.email, "password": "otra-clave-mala"})

        self.assertEqual(self.shift(self.relevo.id, RELEVO_PIN).status_code, 200)

    def test_the_attempts_are_counted_by_guard_with_the_kind_pin(self):
        self.fail_times(self.relevo, 3)

        (row,) = LoginAttempt.query.all()
        self.assertEqual((row.kind, row.subject, row.failed_count), ("pin", str(self.relevo.id), 3))

    def test_a_new_pin_from_the_administrator_unlocks_the_guard(self):
        self.fail_times(self.relevo, MAX_FAILED_ATTEMPTS)
        self.assertEqual(self.shift(self.relevo.id, RELEVO_PIN).status_code, 429)

        self.assertEqual(self.set_pin(self.relevo.id, NEW_PIN).status_code, 200)

        self.assertEqual(self.shift(self.relevo.id, NEW_PIN).status_code, 200)


if __name__ == "__main__":
    unittest.main()
