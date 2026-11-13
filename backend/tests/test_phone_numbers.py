"""Pruebas de los teléfonos: 10 números de Colombia, con +57 opcional, guardados solo con los números.

Se revisan igual al crear y editar un usuario, en «Mi perfil» del residente, en los miembros del
hogar y al importar el censo.
"""

import unittest

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import generate_password_hash

from app import create_app
from auth import generate_token
from extensions import db
from models import User
from services.excel_service import import_census_from_bytes
from structure_fixtures import apartment_for
from validators import normalize_phone

PROBLEM = "El teléfono debe tener 10 números: un celular empieza por 3 y un fijo por 60. Puedes escribir +57 al inicio."


class NormalizePhoneTests(unittest.TestCase):
    def test_a_colombian_number_is_kept_with_only_its_ten_digits(self):
        for written, saved in (
            ("3001234567", "3001234567"),
            ("300 123 4567", "3001234567"),
            ("300-123-4567", "3001234567"),
            ("+57 300 123 4567", "3001234567"),
            ("+573001234567", "3001234567"),
            ("57 300 123 4567", "3001234567"),
            ("(604) 234-5678", "6042345678"),
            ("+57 (601) 234.5678", "6012345678"),
            ("  3109876543  ", "3109876543"),
        ):
            self.assertEqual(normalize_phone(written), (saved, None), written)

    def test_an_empty_phone_is_allowed_and_stays_empty(self):
        for empty in (None, "", "   "):
            self.assertEqual(normalize_phone(empty), ("", None))

    def test_numbers_that_are_not_ten_colombian_digits_are_refused(self):
        for written in (
            "12345",
            "2345678",          # el fijo viejo de 7 números ya no se usa
            "4001234567",       # no empieza por 3 ni por 60
            "6101234567",
            "30012345678",      # 11 números
            "300 123 45x7",
            "300+1234567",
            "abcdefghij",
            "3" * 31,
        ):
            self.assertEqual(normalize_phone(written), (None, PROBLEM), written)

    def test_another_country_is_refused_with_its_own_message(self):
        self.assertEqual(
            normalize_phone("+1 305 123 4567"), (None, "Solo se aceptan teléfonos de Colombia (+57).")
        )

    def test_the_label_names_the_field(self):
        _, error = normalize_phone("123", "El teléfono del miembro #2")
        self.assertTrue(error.startswith("El teléfono del miembro #2 debe tener 10 números"))
        self.assertEqual(normalize_phone(3001234567), (None, "El teléfono debe ser texto."))


class PhoneEverywhereTests(unittest.TestCase):
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
        self.admin = self.person("ADMIN", "admin-telefonos@test.local", "Lucía")
        self.resident = self.person(
            "RESIDENT", "residente-telefonos@test.local", "Marta", last_name="Ríos",
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

    def call(self, method, path, body, user=None):
        headers = {"Authorization": f"Bearer {generate_token(user or self.admin)}"}
        return self.client.open(path, method=method, json=body, headers=headers)

    def new_guard(self, phone):
        return self.call("POST", "/api/admin/users", {
            "role": "GUARD", "name": "Pedro", "email": "pedro-telefonos@test.local",
            "password": "Clave-de-prueba-2*", "phone": phone,
        })

    def test_creating_a_user_saves_only_the_ten_digits(self):
        response = self.new_guard("+57 310 555 1234")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["user"]["phone"], "3105551234")
        self.assertEqual(User.query.filter_by(email="pedro-telefonos@test.local").one().phone, "3105551234")

    def test_creating_a_user_with_a_wrong_phone_is_refused(self):
        response = self.new_guard("12345")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], PROBLEM)
        self.assertIsNone(User.query.filter_by(email="pedro-telefonos@test.local").first())

    def test_editing_a_user_saves_only_the_ten_digits(self):
        response = self.call("PUT", f"/api/admin/users/{self.resident.id}", {"phone": "311 222 3333"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(db.session.get(User, self.resident.id).phone, "3112223333")
        wrong = self.call("PUT", f"/api/admin/users/{self.resident.id}", {"phone": "+1 305 123 4567"})
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(db.session.get(User, self.resident.id).phone, "3112223333")

    def test_the_resident_profile_saves_only_the_ten_digits(self):
        response = self.call("PUT", "/api/profile", {"phone": "+57 320 000 1111"}, user=self.resident)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(db.session.get(User, self.resident.id).phone, "3200001111")
        wrong = self.call("PUT", "/api/profile", {"phone": "320 000"}, user=self.resident)
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(wrong.get_json()["error"], PROBLEM)

    def household(self, phone):
        return self.call("PUT", "/api/admin/units", {
            "apartment": self.resident.apartment,
            "members": [{
                "name": "Ana", "lastName": "Ríos", "documentId": "12345", "birthDate": "2010-04-10",
                "relationship": "hija", "phone": phone,
            }],
            "pets": [],
            "vehicles": [],
        })

    def test_a_household_member_phone_saves_only_the_ten_digits(self):
        response = self.household("+57 300-999-8888")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["unit"]["members"][0]["phone"], "3009998888")

    def test_a_household_member_with_a_wrong_phone_says_which_member(self):
        response = self.household("999")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.get_json()["error"].startswith("El teléfono del miembro #1 debe tener 10 números"))

    def census(self, phone):
        csv_bytes = (
            "Apartamento,Nombre,Correo,Telefono\n"
            f"Torre 1 Apto 101,Marta,residente-telefonos@test.local,{phone}\n"
        ).encode("utf-8")
        return import_census_from_bytes(csv_bytes, "censo.csv", self.admin)

    def test_the_census_saves_only_the_ten_digits(self):
        result = self.census("+57 315 444 5555")
        self.assertEqual(result["errors"], [])
        self.assertEqual(db.session.get(User, self.resident.id).phone, "3154445555")

    def test_the_census_reports_a_wrong_phone_in_its_row_and_keeps_the_old_one(self):
        result = self.census("2345678")
        self.assertEqual(result["errors"], [f"Fila 2: {PROBLEM}"])
        self.assertEqual(db.session.get(User, self.resident.id).phone, "3000000000")


if __name__ == "__main__":
    unittest.main()
