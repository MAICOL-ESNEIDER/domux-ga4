import os
import unittest

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "unit-test-only-secret-with-enough-bytes"

from app import create_app
from auth import generate_token
from extensions import db
from models import Pet, ResidentialUnit, User, Vehicle
from werkzeug.security import generate_password_hash


class UserProfileTests(unittest.TestCase):
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
            name="Admin",
            email="admin-profiles@test.local",
            password_hash=generate_password_hash("Admin123*"),
            role="ADMIN",
            is_active=True,
        )
        self.resident = User(
            name="Residente",
            email="resident-profiles@test.local",
            password_hash=generate_password_hash("Resident123*"),
            role="RESIDENT",
            apartment="Torre 1 · Apto 101",
            apartment_number=101,
            occupancy_type="arrendatario",
            is_active=True,
        )
        self.guard = User(
            name="Guardia",
            email="guard-profiles@test.local",
            password_hash=generate_password_hash("Guard123*"),
            role="GUARD",
            is_active=True,
        )
        db.session.add_all([
            self.admin,
            self.resident,
            self.guard,
            ResidentialUnit(apartment="Torre 1 · Apto 101"),
            ResidentialUnit(apartment="Torre 2 · Apto 202"),
        ])
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def headers(self, user):
        return {"Authorization": f"Bearer {generate_token(user)}"}

    def test_admin_user_search_filters_and_paginates(self):
        response = self.client.get(
            "/api/users?page=1&pageSize=1&occupancyType=arrendatario"
            "&apartmentFrom=100&apartmentTo=150",
            headers=self.headers(self.admin),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["total"], 1)
        self.assertEqual(response.json["pageSize"], 1)
        self.assertEqual(response.json["users"][0]["apartmentNumber"], 101)

    def test_resident_profile_rejects_protected_fields_and_allows_profile_fields(self):
        forbidden = self.client.put(
            "/api/profile",
            headers=self.headers(self.resident),
            json={"apartment": "Torre 9 · Apto 999"},
        )
        self.assertEqual(forbidden.status_code, 400)
        self.assertEqual(self.resident.apartment, "Torre 1 · Apto 101")

        allowed = self.client.put(
            "/api/profile",
            headers=self.headers(self.resident),
            json={"phone": "", "email": "resident-updated@test.local", "socialNetworks": ""},
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(self.resident.phone, "")
        self.assertEqual(self.resident.social_networks, "")
        self.assertEqual(self.resident.email, "resident-updated@test.local")

    def test_profile_endpoints_are_role_restricted(self):
        response = self.client.get("/api/profile", headers=self.headers(self.guard))
        self.assertEqual(response.status_code, 403)
        response = self.client.put(
            "/api/admin/units",
            headers=self.headers(self.resident),
            json={"apartment": self.resident.apartment, "members": [], "pets": [], "vehicles": []},
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_must_record_consent_when_creating_resident(self):
        body = {
            "name": "Nuevo",
            "lastName": "Residente",
            "email": "new-resident@test.local",
            "password": "NewUser123*",
            "role": "RESIDENT",
            "apartment": "Torre 3 · Apto 303",
            "occupancyType": "residente",
        }
        missing_consent = self.client.post(
            "/api/users", headers=self.headers(self.admin), json=body
        )
        self.assertEqual(missing_consent.status_code, 400)
        body["dataProcessingConsent"] = True
        created = self.client.post("/api/users", headers=self.headers(self.admin), json=body)
        self.assertEqual(created.status_code, 201)
        new_user = User.query.filter_by(email="new-resident@test.local").one()
        self.assertEqual(new_user.apartment_number, 303)
        self.assertTrue(new_user.data_processing_consent)
        self.assertIsNotNone(new_user.data_processing_consent_at)
        self.assertIsNotNone(ResidentialUnit.query.filter_by(apartment=new_user.apartment).first())

    def test_promoting_account_to_resident_requires_consent(self):
        body = {"role": "RESIDENT", "apartment": "Torre 4 · Apto 404"}
        missing = self.client.put(
            f"/api/users/{self.guard.id}", headers=self.headers(self.admin), json=body
        )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(self.guard.role, "GUARD")
        body["dataProcessingConsent"] = True
        accepted = self.client.put(
            f"/api/users/{self.guard.id}", headers=self.headers(self.admin), json=body
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(self.guard.role, "RESIDENT")
        self.assertTrue(self.guard.data_processing_consent)

    def test_household_presence_filter_is_applied_on_the_server(self):
        unit = ResidentialUnit.query.filter_by(apartment=self.resident.apartment).one()
        db.session.add(Pet(
            unit_id=unit.id,
            name="Luna",
            species="perro",
            breed="criollo",
            age_years=4,
        ))
        db.session.commit()
        response = self.client.get(
            "/api/users?hasPets=true",
            headers=self.headers(self.admin),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([user["id"] for user in response.json["users"]], [self.resident.id])

    def test_unit_profile_saves_household_and_normalizes_plate(self):
        response = self.client.put(
            "/api/admin/units",
            headers=self.headers(self.admin),
            json={
                "apartment": self.resident.apartment,
                "parkingIdentifier": "P-12",
                "storageIdentifier": "CU-3",
                "petInsurance": True,
                "petInsurer": "Aseguradora",
                "funeralPlan": False,
                "members": [{
                    "name": "Ana",
                    "lastName": "Residente",
                    "documentId": "12345",
                    "birthDate": "2010-04-10",
                    "phone": "3000000000",
                    "relationship": "hija",
                }],
                "pets": [{
                    "name": "Luna",
                    "species": "perro",
                    "breed": "criollo",
                    "ageYears": 4,
                }],
                "vehicles": [{
                    "plate": "abc-123",
                    "type": "carro",
                    "makeModel": "Marca Modelo",
                    "year": 2020,
                    "registeredOwner": "Residente",
                    "color": "blanco",
                }],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Vehicle.query.one().plate, "ABC123")
        self.assertEqual(len(response.json["unit"]["members"]), 1)
        self.assertEqual(response.json["unit"]["parkingIdentifier"], "P-12")
        member_search = self.client.get(
            "/api/users?search=12345",
            headers=self.headers(self.admin),
        )
        self.assertEqual(member_search.status_code, 200)
        self.assertEqual(
            [user["id"] for user in member_search.json["users"]],
            [self.resident.id],
        )
        age_filter = self.client.get(
            "/api/users?minAge=10&maxAge=20",
            headers=self.headers(self.admin),
        )
        self.assertEqual(age_filter.status_code, 200)
        self.assertEqual([user["id"] for user in age_filter.json["users"]], [self.resident.id])

    def test_vehicle_plate_cannot_be_reused_in_another_unit(self):
        db.session.add(Vehicle(
            unit_id=ResidentialUnit.query.filter_by(apartment=self.resident.apartment).one().id,
            plate="ABC123",
            vehicle_type="carro",
            make_model="Marca Modelo",
            year=2020,
            registered_owner="Residente",
        ))
        db.session.commit()
        self.assertEqual(Vehicle.query.filter_by(plate="ABC123").count(), 1)
        target_unit = ResidentialUnit.query.filter_by(apartment="Torre 2 · Apto 202").one()
        self.assertNotEqual(Vehicle.query.one().unit_id, target_unit.id)
        response = self.client.put(
            "/api/admin/units",
            headers=self.headers(self.admin),
            json={
                "apartment": "Torre 2 · Apto 202",
                "members": [],
                "pets": [],
                "vehicles": [{
                    "plate": "ABC123",
                    "type": "carro",
                    "makeModel": "Otro Modelo",
                    "year": 2021,
                    "registeredOwner": "Otro",
                }],
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Vehicle.query.count(), 1)


if __name__ == "__main__":
    unittest.main()
