"""Pruebas de «un usuario por su id» y de que nadie se cierre la puerta a sí mismo (HU-075)."""

import unittest

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import generate_password_hash

from app import create_app
from auth import generate_token
from extensions import db
from models import User
from structure_fixtures import apartment_for


class AdminUserAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.admin = self.person("ADMIN", "admin-acceso@test.local", "Lucía")
        self.other_admin = self.person("ADMIN", "otra-admin-acceso@test.local", "Elena")
        self.guard = self.person("GUARD", "guardia-acceso@test.local", "Guardia")
        self.resident = self.person(
            "RESIDENT", "residente-acceso@test.local", "Marta", last_name="Ríos",
            apartment_ref=apartment_for("Torre 1 · 101"), phone="3000000000", occupancy_type="propietario",
        )
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def person(self, role, email, name, **fields):
        user = User(
            name=name, email=email, role=role, is_active=True,
            password_hash=generate_password_hash("Clave-de-prueba-1*"), **fields,
        )
        db.session.add(user)
        db.session.flush()
        return user

    def call(self, method, path, user=None, body=None):
        headers = {"Authorization": f"Bearer {generate_token(user or self.admin)}"}
        return self.client.open(path, method=method, json=body, headers=headers)

    # --- Un usuario por su id ---------------------------------------------------------------------

    def test_the_administrator_reads_one_user(self):
        response = self.call("GET", f"/api/admin/users/{self.resident.id}")
        self.assertEqual(response.status_code, 200)
        user = response.get_json()["user"]
        self.assertEqual(user["id"], self.resident.id)
        self.assertEqual(user["fullName"], "Marta Ríos")
        self.assertEqual(user["role"], "RESIDENT")
        self.assertNotIn("password", str(user).lower())

    def test_an_unknown_user_is_not_found(self):
        response = self.call("GET", "/api/admin/users/9999")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "Usuario no encontrado")

    def test_only_the_administration_reads_a_user(self):
        for person in (self.resident, self.guard):
            self.assertEqual(self.call("GET", f"/api/admin/users/{self.admin.id}", user=person).status_code, 403)
        self.assertEqual(self.client.get(f"/api/admin/users/{self.admin.id}").status_code, 401)

    # --- Nadie se cierra la puerta a sí mismo -------------------------------------------------------

    def test_an_administrator_cannot_deactivate_their_own_account(self):
        response = self.call("PUT", f"/api/admin/users/{self.admin.id}", body={"isActive": False})
        self.assertEqual(response.status_code, 409)
        self.assertIn("No puedes desactivar tu propia cuenta", response.get_json()["error"])
        self.assertTrue(db.session.get(User, self.admin.id).is_active)

    def test_an_administrator_cannot_change_their_own_role(self):
        response = self.call("PUT", f"/api/admin/users/{self.admin.id}", body={"role": "GUARD"})
        self.assertEqual(response.status_code, 409)
        self.assertIn("No puedes cambiar tu propio rol", response.get_json()["error"])
        self.assertEqual(db.session.get(User, self.admin.id).role, "ADMIN")

    def test_an_administrator_can_still_edit_their_own_data(self):
        response = self.call(
            "PUT", f"/api/admin/users/{self.admin.id}", body={"phone": "3111111111", "isActive": True, "role": "ADMIN"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(db.session.get(User, self.admin.id).phone, "3111111111")

    def test_another_administrator_can_deactivate_and_reactivate_an_account(self):
        off = self.call("PUT", f"/api/admin/users/{self.admin.id}", user=self.other_admin, body={"isActive": False})
        self.assertEqual(off.status_code, 200)
        self.assertFalse(db.session.get(User, self.admin.id).is_active)
        on = self.call("PUT", f"/api/admin/users/{self.admin.id}", user=self.other_admin, body={"isActive": True})
        self.assertEqual(on.status_code, 200)
        self.assertTrue(db.session.get(User, self.admin.id).is_active)


if __name__ == "__main__":
    unittest.main()
