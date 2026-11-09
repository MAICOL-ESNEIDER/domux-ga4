import os
import unittest

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "unit-test-only-secret-with-enough-bytes"

from app import create_app
from auth import generate_token
from extensions import db
from models import CommonArea, Notification, Pqrs, Reservation, User
from werkzeug.security import generate_password_hash


class AdminResidentActionTests(unittest.TestCase):
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
            name="Administradora",
            email="admin-actions@test.local",
            password_hash=generate_password_hash("Admin123*"),
            role="ADMIN",
            is_active=True,
        )
        self.resident = User(
            name="Residente",
            email="resident-actions@test.local",
            password_hash=generate_password_hash("Resident123*"),
            role="RESIDENT",
            apartment="Torre 1 · Apto 101",
            is_active=True,
        )
        self.other_resident = User(
            name="Otro residente",
            email="other-actions@test.local",
            password_hash=generate_password_hash("Other123*"),
            role="RESIDENT",
            apartment="Torre 2 · Apto 202",
            is_active=True,
        )
        self.guard = User(
            name="Guardia",
            email="guard-actions@test.local",
            password_hash=generate_password_hash("Guard123*"),
            role="GUARD",
            is_active=True,
        )
        self.area = CommonArea(name="Salón social")
        db.session.add_all([
            self.admin, self.resident, self.other_resident, self.guard, self.area
        ])
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def headers(self, user):
        return {"Authorization": f"Bearer {generate_token(user)}"}

    def test_admin_creates_pqrs_for_resident_with_audit_and_notification(self):
        response = self.client.post(
            "/api/pqrs",
            headers=self.headers(self.admin),
            json={
                "residentId": self.resident.id,
                "subject": "Llave del acceso",
                "message": "La residente solicita apoyo con su llave.",
                "category": "Petición",
            },
        )
        self.assertEqual(response.status_code, 201)
        pqrs = Pqrs.query.one()
        self.assertEqual(pqrs.resident_id, self.resident.id)
        self.assertEqual(pqrs.created_by_admin_id, self.admin.id)
        self.assertEqual(pqrs.conversation[0].author_id, self.admin.id)
        self.assertTrue(response.json["pqrs"]["createdByAdministration"])
        self.assertEqual(Notification.query.filter_by(user_id=self.resident.id).count(), 1)

    def test_admin_creates_reservation_for_resident_with_audit_and_notification(self):
        response = self.client.post(
            "/api/reservations",
            headers=self.headers(self.admin),
            json={
                "residentId": self.resident.id,
                "commonAreaId": self.area.id,
                "date": "2099-06-20",
                "timeSlot": "10:00-12:00",
            },
        )
        self.assertEqual(response.status_code, 201)
        reservation = Reservation.query.one()
        self.assertEqual(reservation.resident_id, self.resident.id)
        self.assertEqual(reservation.created_by_admin_id, self.admin.id)
        self.assertTrue(response.json["reservation"]["createdByAdministration"])
        self.assertEqual(Notification.query.filter_by(user_id=self.resident.id).count(), 1)

    def test_resident_cannot_create_requests_for_another_resident(self):
        pqrs_response = self.client.post(
            "/api/pqrs",
            headers=self.headers(self.resident),
            json={
                "residentId": self.other_resident.id,
                "subject": "Solicitud",
                "message": "Solicitud de prueba",
            },
        )
        self.assertEqual(pqrs_response.status_code, 201)
        self.assertEqual(Pqrs.query.one().resident_id, self.resident.id)
        self.assertIsNone(Pqrs.query.one().created_by_admin_id)

        reservation_response = self.client.post(
            "/api/reservations",
            headers=self.headers(self.resident),
            json={
                "residentId": self.other_resident.id,
                "commonAreaId": self.area.id,
                "date": "2099-06-20",
                "timeSlot": "10:00-12:00",
            },
        )
        self.assertEqual(reservation_response.status_code, 201)
        self.assertEqual(Reservation.query.one().resident_id, self.resident.id)
        self.assertIsNone(Reservation.query.one().created_by_admin_id)

    def test_guard_cannot_create_on_behalf_of_a_resident(self):
        pqrs_response = self.client.post(
            "/api/pqrs",
            headers=self.headers(self.guard),
            json={
                "residentId": self.resident.id,
                "subject": "Solicitud",
                "message": "Solicitud de prueba",
            },
        )
        self.assertEqual(pqrs_response.status_code, 403)
        reservation_response = self.client.post(
            "/api/reservations",
            headers=self.headers(self.guard),
            json={
                "residentId": self.resident.id,
                "commonAreaId": self.area.id,
                "date": "2099-06-20",
                "timeSlot": "10:00-12:00",
            },
        )
        self.assertEqual(reservation_response.status_code, 403)
        self.assertEqual(Pqrs.query.count(), 0)
        self.assertEqual(Reservation.query.count(), 0)

    def test_admin_can_respond_to_the_pqrs_created_for_resident(self):
        created = self.client.post(
            "/api/pqrs",
            headers=self.headers(self.admin),
            json={
                "residentId": self.resident.id,
                "subject": "Solicitud",
                "message": "Solicitud de prueba",
            },
        )
        pqrs_id = created.json["pqrs"]["id"]
        response = self.client.put(
            f"/api/pqrs/{pqrs_id}/respond",
            headers=self.headers(self.admin),
            json={"status": "en_proceso", "adminResponse": "Ya estamos revisando."},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Pqrs.query.one().created_by_admin_id, self.admin.id)
        self.assertEqual(len(Pqrs.query.one().conversation), 2)
        self.assertEqual(Notification.query.filter_by(user_id=self.resident.id).count(), 2)

    def test_admin_can_filter_pqrs_by_resident_but_resident_cannot(self):
        first = Pqrs(
            resident_id=self.resident.id,
            subject="Solicitud propia",
            message="Detalle",
        )
        second = Pqrs(
            resident_id=self.other_resident.id,
            subject="Solicitud ajena",
            message="Detalle",
        )
        db.session.add_all([first, second])
        db.session.commit()
        admin_response = self.client.get(
            f"/api/pqrs?residentId={self.resident.id}",
            headers=self.headers(self.admin),
        )
        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual([item["residentId"] for item in admin_response.json["pqrs"]], [self.resident.id])
        resident_response = self.client.get(
            f"/api/pqrs?residentId={self.other_resident.id}",
            headers=self.headers(self.resident),
        )
        self.assertEqual(resident_response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
