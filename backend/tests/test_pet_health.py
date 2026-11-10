"""Pruebas de la salud de las mascotas y del fin del plan funerario (HU-021, DEF-013).

Cada mascota guarda si la vacunación y la desparasitación están al día y la
fecha de la última (RN-028). La ficha del hogar ya no recibe ni muestra el plan
funerario (DEC-015).
"""

import unittest
from datetime import date, timedelta

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import generate_password_hash

from app import create_app
from auth import generate_token
from extensions import db
from models import Pet, User
from structure_fixtures import apartment_for

APARTMENT = "Torre 3 · Apto 303"


def pet(**fields):
    return {"name": "Luna", "species": "perro", "breed": "criollo", "ageYears": 3, **fields}


class PetHealthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.admin = User(
            name="Admin", email="admin-mascotas@test.local", role="ADMIN", is_active=True,
            password_hash=generate_password_hash("Clave-de-prueba-1*"),
        )
        apartment_for(APARTMENT)
        db.session.add(self.admin)
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def save(self, pets, **extra):
        return self.client.put(
            "/api/admin/units",
            headers={"Authorization": f"Bearer {generate_token(self.admin)}"},
            json={"apartment": APARTMENT, "members": [], "pets": pets, "vehicles": [], **extra},
        )

    def test_vaccination_and_deworming_are_saved_and_returned(self):
        response = self.save([pet(
            vaccinesUpToDate=True, lastVaccinationDate="2026-10-01",
            dewormingUpToDate=False, lastDewormingDate="2026-03-15",
        )])

        self.assertEqual(response.status_code, 200)
        saved = response.get_json()["unit"]["pets"][0]
        self.assertEqual(
            {key: saved[key] for key in (
                "vaccinesUpToDate", "lastVaccinationDate", "dewormingUpToDate", "lastDewormingDate"
            )},
            {"vaccinesUpToDate": True, "lastVaccinationDate": "2026-10-01",
             "dewormingUpToDate": False, "lastDewormingDate": "2026-03-15"},
        )

    def test_a_pet_without_health_data_is_pending(self):
        saved = self.save([pet()]).get_json()["unit"]["pets"][0]

        self.assertFalse(saved["vaccinesUpToDate"])
        self.assertIsNone(saved["lastVaccinationDate"])
        self.assertFalse(saved["dewormingUpToDate"])

    def test_invalid_health_data_is_rejected(self):
        tomorrow = (date.today() + timedelta(days=2)).isoformat()
        cases = {
            "al día sin fecha": pet(vaccinesUpToDate=True),
            "fecha futura": pet(dewormingUpToDate=True, lastDewormingDate=tomorrow),
            "fecha mal escrita": pet(lastVaccinationDate="01/10/2026"),
            "sí o no inválido": pet(vaccinesUpToDate="si"),
        }
        for case, item in cases.items():
            with self.subTest(case=case):
                self.assertEqual(self.save([item]).status_code, 400)
        self.assertEqual(Pet.query.count(), 0)

    def test_pet_sent_again_without_id_keeps_its_record(self):
        first_id = self.save([pet()]).get_json()["unit"]["pets"][0]["id"]

        again = self.save([pet(vaccinesUpToDate=True, lastVaccinationDate="2026-11-01")])

        self.assertEqual(again.get_json()["unit"]["pets"][0]["id"], first_id)
        self.assertEqual(Pet.query.count(), 1)

    def test_funeral_plan_is_no_longer_saved_or_shown(self):
        response = self.save([], funeralPlan=True, funeralProvider="Funeraria")

        self.assertEqual(response.status_code, 200)
        unit = response.get_json()["unit"]
        self.assertNotIn("funeralPlan", unit)
        self.assertNotIn("funeralProvider", unit)


if __name__ == "__main__":
    unittest.main()
