"""Pruebas del buscador de residentes de portería: poco a la vista y el teléfono solo al elegir.

El guardia no recibe nada hasta escribir 2 letras y ve máximo 5 residentes, con nombre y
apartamento. El teléfono llega aparte, solo del residente que elige, y queda anotado quién lo vio.
"""

import unittest

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import generate_password_hash

from app import create_app
from auth import generate_token
from extensions import db
from models import AuditLog, User
from structure_fixtures import apartment_for


class GuardResidentSearchTests(unittest.TestCase):
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
        self.admin = self.person("ADMIN", "admin-buscador@test.local", "Lucía")
        self.guard = self.person("GUARD", "guardia-buscador@test.local", "Pedro")
        # Siete residentes que se llaman «Gómez» y uno que no.
        self.gomez = [
            self.person(
                "RESIDENT", f"gomez{number}@test.local", f"Ana {number}", last_name="Gómez",
                apartment_ref=apartment_for(f"Torre 1 · Apto {100 + number}"), phone=f"300000000{number}",
            )
            for number in range(1, 8)
        ]
        self.marta = self.person(
            "RESIDENT", "marta-buscador@test.local", "Marta", last_name="Ríos",
            apartment_ref=apartment_for("Torre 2 · Apto 201"), phone="3112223333",
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

    def get(self, path, user=None):
        return self.client.get(path, headers={"Authorization": f"Bearer {generate_token(user or self.guard)}"})

    def test_the_guard_sees_nobody_before_writing_two_letters(self):
        for path in ("/api/residents", "/api/residents?search=", "/api/residents?search=M", "/api/residents?search=%20M%20"):
            with self.subTest(path=path):
                response = self.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json(), {"residents": [], "more": False})

    def test_the_guard_sees_name_and_apartment_but_not_the_phone(self):
        body = self.get("/api/residents?search=Ma").get_json()

        self.assertEqual([item["name"] for item in body["residents"]], ["Marta Ríos"])
        self.assertEqual(body["residents"][0], {
            "id": self.marta.id, "name": "Marta Ríos", "apartment": "Torre 2 · Apto 201",
            "apartmentNumber": self.marta.apartment_number,
        })
        self.assertFalse(body["more"])
        self.assertNotIn("3112223333", str(body))

    def test_the_guard_sees_at_most_five_and_is_told_to_write_more(self):
        body = self.get("/api/residents?search=Gómez").get_json()

        self.assertEqual(len(body["residents"]), 5)
        self.assertTrue(body["more"])
        narrower = self.get("/api/residents?search=Apto 107").get_json()
        self.assertEqual([item["id"] for item in narrower["residents"]], [self.gomez[6].id])
        self.assertFalse(narrower["more"])

    def test_the_administration_keeps_the_full_search(self):
        body = self.get("/api/residents", user=self.admin).get_json()

        self.assertEqual(len(body["residents"]), 8)
        self.assertFalse(body["more"])
        self.assertIn("phone", body["residents"][0])
        self.assertIn("email", body["residents"][0])

    def test_the_chosen_resident_comes_with_the_phone_and_the_view_is_noted(self):
        response = self.get(f"/api/residents/{self.marta.id}/contact")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["resident"], {
            "id": self.marta.id, "name": "Marta Ríos", "apartment": "Torre 2 · Apto 201",
            "apartmentNumber": self.marta.apartment_number, "phone": "3112223333",
        })
        log = AuditLog.query.filter_by(entity_type="user", entity_id=self.marta.id, action="contact_viewed").one()
        self.assertEqual(log.actor_id, self.guard.id)

    def test_the_administration_reads_the_contact_without_a_note(self):
        response = self.get(f"/api/residents/{self.marta.id}/contact", user=self.admin)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["resident"]["phone"], "3112223333")
        self.assertEqual(AuditLog.query.filter_by(action="contact_viewed").count(), 0)

    def test_only_active_residents_have_a_contact_and_only_for_staff(self):
        self.marta.is_active = False
        db.session.commit()
        self.assertEqual(self.get(f"/api/residents/{self.marta.id}/contact").status_code, 404)
        self.assertEqual(self.get(f"/api/residents/{self.admin.id}/contact").status_code, 404)
        self.assertEqual(self.get("/api/residents/99999/contact").status_code, 404)
        resident = self.gomez[0]
        self.assertEqual(self.get(f"/api/residents/{resident.id}/contact", user=resident).status_code, 403)
        self.assertEqual(self.client.get(f"/api/residents/{resident.id}/contact").status_code, 401)
        self.assertEqual(AuditLog.query.filter_by(action="contact_viewed").count(), 0)


if __name__ == "__main__":
    unittest.main()
