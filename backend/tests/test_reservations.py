import os
import unittest
from datetime import date, timedelta

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "unit-test-only-secret-with-enough-bytes"

from app import create_app
from auth import generate_token
from extensions import db
from models import CommonArea, Notification, Reservation, ReservationMessage, User
from validators import VALID_TIME_SLOTS
from werkzeug.security import generate_password_hash


class ReservationWorkflowTests(unittest.TestCase):
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
            email="admin-reservations@test.local",
            password_hash=generate_password_hash("Admin123*"),
            role="ADMIN",
            is_active=True,
        )
        self.resident = User(
            name="Resident",
            email="resident-reservations@test.local",
            password_hash=generate_password_hash("Resident123*"),
            role="RESIDENT",
            apartment="Apto 101",
            is_active=True,
        )
        self.other_resident = User(
            name="Other",
            email="other-reservations@test.local",
            password_hash=generate_password_hash("Other123*"),
            role="RESIDENT",
            apartment="Apto 202",
            is_active=True,
        )
        self.guard = User(
            name="Guard",
            email="guard-reservations@test.local",
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
        self.future_date = (date.today() + timedelta(days=3)).isoformat()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def headers(self, user):
        return {"Authorization": f"Bearer {generate_token(user)}"}

    def create_request(self, resident=None, slot="10:00-12:00", **fields):
        body = {
            "commonAreaId": self.area.id,
            "date": self.future_date,
            "timeSlot": slot,
        }
        if resident is not None:
            body["residentId"] = resident.id
        body.update(fields)
        return self.client.post(
            "/api/reservations",
            headers=self.headers(resident or self.resident),
            json=body,
        )

    def test_reservation_request_is_pending_and_optional_message_is_saved(self):
        response = self.create_request(
            message="Necesito confirmar el depósito.",
            mediaUrl="data:image/png;base64,AA==",
            mediaType="image",
        )
        self.assertEqual(response.status_code, 201)
        reservation = Reservation.query.one()
        self.assertEqual(reservation.status, "pendiente")
        self.assertEqual(len(reservation.messages), 1)
        self.assertEqual(reservation.messages[0].message, "Necesito confirmar el depósito.")
        self.assertEqual(reservation.messages[0].author_role, "RESIDENT")
        self.assertTrue(
            Notification.query.filter_by(user_id=self.admin.id, type="reservation").count()
        )

    def test_pending_requests_do_not_occupy_but_approval_rechecks_conflicts(self):
        first = self.create_request()
        second = self.create_request(resident=self.other_resident)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        reservations = Reservation.query.order_by(Reservation.id).all()
        self.assertEqual([item.status for item in reservations], ["pendiente", "pendiente"])

        first_approval = self.client.put(
            f"/api/reservations/{reservations[0].id}/status",
            headers=self.headers(self.admin),
            json={"status": "aprobada"},
        )
        self.assertEqual(first_approval.status_code, 200)
        conflicting_approval = self.client.put(
            f"/api/reservations/{reservations[1].id}/status",
            headers=self.headers(self.admin),
            json={"status": "aprobada"},
        )
        self.assertEqual(conflicting_approval.status_code, 409)
        self.assertEqual(reservations[1].status, "pendiente")

    def test_calendar_blocks_only_fully_occupied_days(self):
        for index, slot in enumerate(VALID_TIME_SLOTS):
            db.session.add(Reservation(
                resident_id=self.resident.id,
                common_area_id=self.area.id,
                date=self.future_date,
                time_slot=slot,
                status="aprobada",
            ))
        partial_date = (date.today() + timedelta(days=4)).isoformat()
        db.session.add(Reservation(
            resident_id=self.resident.id,
            common_area_id=self.area.id,
            date=partial_date,
            time_slot=VALID_TIME_SLOTS[0],
            status="aprobada",
        ))
        pending_date = (date.today() + timedelta(days=5)).isoformat()
        db.session.add(Reservation(
            resident_id=self.resident.id,
            common_area_id=self.area.id,
            date=pending_date,
            time_slot=VALID_TIME_SLOTS[0],
            status="pendiente",
        ))
        db.session.commit()
        year, month, _ = map(int, self.future_date.split("-"))
        response = self.client.get(
            f"/api/reservations/calendar?commonAreaId={self.area.id}&year={year}&month={month}",
            headers=self.headers(self.resident),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["blockedDates"], [self.future_date])

    def test_admin_reply_notifies_resident_and_resident_message_notifies_admin(self):
        created = self.create_request()
        reservation_id = created.json["reservation"]["id"]
        admin_reply = self.client.post(
            f"/api/reservations/{reservation_id}/messages",
            headers=self.headers(self.admin),
            json={"message": "No se requiere depósito."},
        )
        self.assertEqual(admin_reply.status_code, 201)
        self.assertEqual(
            Notification.query.filter_by(user_id=self.resident.id, type="reservation").count(),
            1,
        )
        resident_reply = self.client.post(
            f"/api/reservations/{reservation_id}/messages",
            headers=self.headers(self.resident),
            json={"message": "Gracias, entendido."},
        )
        self.assertEqual(resident_reply.status_code, 201)
        self.assertEqual(
            Notification.query.filter_by(user_id=self.admin.id, type="reservation").count(),
            2,
        )
        self.assertEqual(ReservationMessage.query.count(), 2)

    def test_resident_can_cancel_before_date_but_not_on_or_after_reserved_date(self):
        created = self.create_request()
        reservation = Reservation.query.one()
        approval = self.client.put(
            f"/api/reservations/{reservation.id}/status",
            headers=self.headers(self.admin),
            json={"status": "aprobada"},
        )
        self.assertEqual(approval.status_code, 200)
        cancelled = self.client.put(
            f"/api/reservations/{reservation.id}/cancel",
            headers=self.headers(self.resident),
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(reservation.status, "cancelada")
        self.assertTrue(
            Notification.query.filter_by(user_id=self.admin.id, type="reservation").count()
        )

        same_day = Reservation(
            resident_id=self.resident.id,
            common_area_id=self.area.id,
            date=date.today().isoformat(),
            time_slot="12:00-14:00",
            status="aprobada",
        )
        db.session.add(same_day)
        db.session.commit()
        denied = self.client.put(
            f"/api/reservations/{same_day.id}/cancel",
            headers=self.headers(self.resident),
        )
        self.assertEqual(denied.status_code, 400)
        self.assertEqual(same_day.status, "aprobada")

    def test_rejecting_and_cancelling_reservation_notify_resident(self):
        created = self.create_request()
        reservation_id = created.json["reservation"]["id"]
        rejected = self.client.put(
            f"/api/reservations/{reservation_id}/status",
            headers=self.headers(self.admin),
            json={"status": "rechazada"},
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(Notification.query.filter_by(user_id=self.resident.id).count(), 1)
        denied_cancel = self.client.put(
            f"/api/reservations/{reservation_id}/cancel",
            headers=self.headers(self.admin),
        )
        self.assertEqual(denied_cancel.status_code, 400)

        approved = self.create_request(resident=self.other_resident, slot="12:00-14:00")
        second_id = approved.json["reservation"]["id"]
        self.client.put(
            f"/api/reservations/{second_id}/status",
            headers=self.headers(self.admin),
            json={"status": "aprobada"},
        )
        cancelled = self.client.put(
            f"/api/reservations/{second_id}/cancel",
            headers=self.headers(self.admin),
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertGreaterEqual(
            Notification.query.filter_by(user_id=self.other_resident.id).count(),
            2,
        )

    def test_guard_cannot_create_or_message_reservations(self):
        create = self.create_request(resident=self.guard)
        self.assertEqual(create.status_code, 403)
        reservation = Reservation(
            resident_id=self.resident.id,
            common_area_id=self.area.id,
            date=self.future_date,
            time_slot="12:00-14:00",
            status="pendiente",
        )
        db.session.add(reservation)
        db.session.commit()
        reply = self.client.post(
            f"/api/reservations/{reservation.id}/messages",
            headers=self.headers(self.guard),
            json={"message": "No autorizado."},
        )
        self.assertEqual(reply.status_code, 403)

    def test_resident_cannot_cancel_or_message_another_residents_reservation(self):
        reservation = Reservation(
            resident_id=self.other_resident.id,
            common_area_id=self.area.id,
            date=self.future_date,
            time_slot="14:00-16:00",
            status="pendiente",
        )
        db.session.add(reservation)
        db.session.commit()
        message = self.client.post(
            f"/api/reservations/{reservation.id}/messages",
            headers=self.headers(self.resident),
            json={"message": "No autorizado."},
        )
        self.assertEqual(message.status_code, 403)
        cancel = self.client.put(
            f"/api/reservations/{reservation.id}/cancel",
            headers=self.headers(self.resident),
        )
        self.assertEqual(cancel.status_code, 403)
        self.assertEqual(reservation.status, "pendiente")


if __name__ == "__main__":
    unittest.main()
