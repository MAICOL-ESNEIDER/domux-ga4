"""Pruebas del retiro lógico en la ficha del hogar (TT-032 y DEF-007).

Guardar la ficha ya no borra y vuelve a crear los registros: lo que sigue
conserva su id, lo que se quita queda retirado con la fecha y quién lo hizo, y
una placa retirada puede registrarse de nuevo (IDX-013).
"""

import unittest

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import generate_password_hash

from app import create_app
from auth import generate_token
from extensions import db
from models import AuditLog, HouseholdMember, Pet, User, Vehicle
from structure_fixtures import apartment_for

APTO_101 = "Torre 1 · Apto 101"
APTO_202 = "Torre 2 · Apto 202"


def member(name, document, **fields):
    return {"name": name, "documentId": document, "birthDate": "2012-05-20",
            "relationship": "hija", **fields}


def pet(name, **fields):
    return {"name": name, "species": "perro", "breed": "criollo", "ageYears": 3, **fields}


def vehicle(plate, **fields):
    return {"plate": plate, "type": "carro", "makeModel": "Marca Modelo", "year": 2020,
            "registeredOwner": "Residente", **fields}


class HouseholdRetireTests(unittest.TestCase):
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
            name="Admin", email="admin-ficha@test.local", role="ADMIN", is_active=True,
            password_hash=generate_password_hash("Clave-de-prueba-1*"),
        )
        self.resident = User(
            name="Residente", email="residente-ficha@test.local", role="RESIDENT",
            apartment_ref=apartment_for(APTO_101), is_active=True,
            password_hash=generate_password_hash("Clave-de-prueba-1*"),
        )
        apartment_for(APTO_202)
        db.session.add_all([self.admin, self.resident])
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def save(self, apartment=APTO_101, members=(), pets=(), vehicles=()):
        return self.client.put(
            "/api/admin/units",
            headers={"Authorization": f"Bearer {generate_token(self.admin)}"},
            json={"apartment": apartment, "members": list(members), "pets": list(pets),
                  "vehicles": list(vehicles)},
        )

    def test_saving_keeps_ids_and_retires_what_was_removed(self):
        first = self.save(
            members=[member("Ana", "111"), member("Luis", "222")],
            pets=[pet("Luna")],
            vehicles=[vehicle("ABC123"), vehicle("XYZ789")],
        ).get_json()["unit"]
        ana, luis = first["members"]
        luna = first["pets"][0]
        car, other_car = first["vehicles"]

        # Se reenvían tal como llegaron del servidor, igual que hace la app
        # (Ana no tiene apellido: antes ese "" vacío hacía fallar el guardado).
        response = self.save(
            members=[ana],
            pets=[dict(luna, ageYears=4)],
            vehicles=[car],
        )

        self.assertEqual(response.status_code, 200)
        unit = response.get_json()["unit"]
        self.assertEqual([item["id"] for item in unit["members"]], [ana["id"]])
        self.assertEqual(unit["pets"][0]["id"], luna["id"])
        self.assertEqual(unit["pets"][0]["ageYears"], 4)
        self.assertEqual([item["id"] for item in unit["vehicles"]], [car["id"]])
        # Nada se borró: Luis y el segundo carro siguen en la base, retirados.
        self.assertEqual(HouseholdMember.query.count(), 2)
        self.assertEqual(Vehicle.query.count(), 2)
        for row in (db.session.get(HouseholdMember, luis["id"]),
                    db.session.get(Vehicle, other_car["id"])):
            self.assertIsNotNone(row.retired_at)
            self.assertEqual(row.retired_by_id, self.admin.id)
        log = AuditLog.query.filter_by(action="household_updated").order_by(AuditLog.id.desc()).first()
        self.assertIn('"retired": 1', log.details)

    def test_items_sent_again_without_id_are_matched_by_document_and_plate(self):
        first = self.save(members=[member("Ana", "111")], vehicles=[vehicle("ABC123")])
        ids = (first.get_json()["unit"]["members"][0]["id"],
               first.get_json()["unit"]["vehicles"][0]["id"])

        again = self.save(members=[member("Ana María", "111")], vehicles=[vehicle("abc-123")])

        self.assertEqual(again.status_code, 200)
        unit = again.get_json()["unit"]
        self.assertEqual((unit["members"][0]["id"], unit["vehicles"][0]["id"]), ids)
        self.assertEqual(unit["members"][0]["name"], "Ana María")
        self.assertEqual(HouseholdMember.query.count(), 1)
        self.assertEqual(Vehicle.query.count(), 1)

    def test_retired_plate_can_be_registered_again_in_another_unit(self):
        self.save(vehicles=[vehicle("ABC123")])
        self.save(vehicles=[])

        moved = self.save(apartment=APTO_202, vehicles=[vehicle("ABC123")])
        back = self.save(vehicles=[vehicle("ABC123")])

        self.assertEqual(moved.status_code, 200)
        self.assertEqual(back.status_code, 409)
        self.assertEqual(Vehicle.query.filter_by(plate="ABC123").count(), 2)
        self.assertEqual(Vehicle.query.filter_by(plate="ABC123", retired_at=None).count(), 1)

    def test_retired_records_do_not_count_in_the_resident_filters(self):
        self.save(members=[member("Ana", "111")], pets=[pet("Luna")], vehicles=[vehicle("ABC123")])
        self.save()
        headers = {"Authorization": f"Bearer {generate_token(self.admin)}"}

        for query in ("hasPets=true", "hasVehicles=true", "search=111"):
            with self.subTest(query=query):
                response = self.client.get(f"/api/users?{query}", headers=headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json()["users"], [])
        self.assertEqual(Pet.query.count(), 1)

    def test_invalid_item_id_is_rejected(self):
        response = self.save(pets=[pet("Luna", id="uno")])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Pet.query.count(), 0)


if __name__ == "__main__":
    unittest.main()
