"""Pruebas de consultar una torre, un apartamento, un parqueadero o un cuarto útil por su id (HU-076)."""

import unittest

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import generate_password_hash

from app import create_app
from auth import generate_token
from extensions import db
from models import ParkingSpot, StorageRoom, Tower, User
from structure_fixtures import apartment_for, parking_spot, storage_room


class StructureByIdTests(unittest.TestCase):
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
        self.admin = self.person("ADMIN", "admin-id@test.local", "Lucía")
        self.resident = self.person("RESIDENT", "residente-id@test.local", "Marta")
        self.apartment = apartment_for("Torre 1 · Apto 101")
        parking_spot("P-01", apartment=self.apartment)
        storage_room("C-01", apartment=self.apartment)
        db.session.commit()
        self.tower = Tower.query.filter_by(name="Torre 1").one()
        self.spot = ParkingSpot.query.filter_by(code="P-01").one()
        self.room = StorageRoom.query.filter_by(code="C-01").one()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def person(self, role, email, name):
        user = User(
            name=name, email=email, role=role, is_active=True,
            password_hash=generate_password_hash("Clave-de-prueba-1*"),
        )
        db.session.add(user)
        db.session.flush()
        return user

    def get(self, path, user=None):
        return self.client.get(path, headers={"Authorization": f"Bearer {generate_token(user or self.admin)}"})

    def paths(self):
        return (
            (f"/api/admin/towers/{self.tower.id}", "tower", "name", "Torre 1"),
            (f"/api/admin/apartments/{self.apartment.id}", "apartment", "label", "Torre 1 · Apto 101"),
            (f"/api/admin/parking-spots/{self.spot.id}", "parkingSpot", "code", "P-01"),
            (f"/api/admin/storage-rooms/{self.room.id}", "storageRoom", "code", "C-01"),
        )

    def test_the_administrator_reads_each_one_by_its_id(self):
        for path, key, field, expected in self.paths():
            response = self.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertEqual(response.get_json()[key][field], expected, path)

    def test_a_retired_or_unknown_one_is_not_found(self):
        for path, _key, _field, _expected in self.paths():
            self.assertEqual(self.get(path.rsplit("/", 1)[0] + "/9999").status_code, 404, path)
        self.spot.retire(self.admin)
        self.room.retire(self.admin)
        db.session.commit()
        self.assertEqual(self.get(f"/api/admin/parking-spots/{self.spot.id}").status_code, 404)
        self.assertEqual(self.get(f"/api/admin/storage-rooms/{self.room.id}").status_code, 404)

    def test_only_the_administration_reads_them(self):
        for path, _key, _field, _expected in self.paths():
            self.assertEqual(self.get(path, user=self.resident).status_code, 403, path)
            self.assertEqual(self.client.get(path).status_code, 401, path)


if __name__ == "__main__":
    unittest.main()
