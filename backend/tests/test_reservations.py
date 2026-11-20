import os
import unittest
from datetime import date, datetime, timedelta

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "unit-test-only-secret-with-enough-bytes"

from app import create_app
from auth import generate_token
from extensions import db
from models import AuditLog, CommonArea, Notification, Reservation, ReservationMessage, User
from services.reservation_service import (
    COLOMBIA_TIMEZONE,
    finalize_expired_reservations,
)
from validators import STANDARD_TIME_SLOTS, VALID_TIME_SLOTS
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
        self.assertEqual(
            AuditLog.query.filter_by(
                entity_type="RESERVATION", entity_id=reservation.id, action="created"
            ).count(),
            1,
        )

    def test_expired_reservations_are_finalized_using_colombia_time(self):
        today = datetime.now(COLOMBIA_TIMEZONE).date()
        yesterday = (today - timedelta(days=1)).isoformat()
        active_today = Reservation(
            resident_id=self.resident.id,
            common_area_id=self.area.id,
            date=today.isoformat(),
            time_slot="08:00-10:00",
            status="activa",
        )
        approved_yesterday = Reservation(
            resident_id=self.resident.id,
            common_area_id=self.area.id,
            date=yesterday,
            time_slot="18:00-20:00",
            status="aprobada",
        )
        pending_yesterday = Reservation(
            resident_id=self.other_resident.id,
            common_area_id=self.area.id,
            date=yesterday,
            time_slot="12:00-14:00",
            status="pendiente",
        )
        db.session.add_all([active_today, approved_yesterday, pending_yesterday])
        db.session.commit()

        simulated_now = datetime(
            today.year,
            today.month,
            today.day,
            10,
            1,
            tzinfo=COLOMBIA_TIMEZONE,
        )
        finalized = finalize_expired_reservations(simulated_now)

        self.assertEqual(finalized, 2)
        self.assertEqual(active_today.status, "finalizada")
        self.assertEqual(approved_yesterday.status, "finalizada")
        self.assertEqual(pending_yesterday.status, "pendiente")

    def test_reservation_listing_finalizes_past_active_reservations(self):
        reservation = Reservation(
            resident_id=self.resident.id,
            common_area_id=self.area.id,
            date=(datetime.now(COLOMBIA_TIMEZONE).date() - timedelta(days=1)).isoformat(),
            time_slot="18:00-20:00",
            status="activa",
        )
        db.session.add(reservation)
        db.session.commit()

        response = self.client.get(
            "/api/reservations",
            headers=self.headers(self.admin),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(reservation.status, "finalizada")

    def test_minor_without_parental_consent_cannot_request_reservation(self):
        today = date.today()
        try:
            birth_date = today.replace(year=today.year - 15)
        except ValueError:
            birth_date = today.replace(year=today.year - 15, day=28)
        self.resident.birth_date = birth_date.isoformat()
        self.resident.parental_consent = False
        db.session.commit()

        response = self.create_request()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json["error"],
            "Los menores de edad requieren autorización parental registrada por administración para solicitar reservas.",
        )
        self.assertEqual(Reservation.query.count(), 0)

    def test_resident_cannot_create_two_active_reservations_on_same_day(self):
        first = self.create_request(slot="10:00-12:00")
        second = self.create_request(slot="12:00-14:00")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(
            second.json["error"],
            "Límite diario alcanzado: solo puedes tener 1 reserva activa o pendiente por día.",
        )
        self.assertEqual(Reservation.query.count(), 1)

    def test_resident_is_limited_to_two_active_reservations_per_week(self):
        week_start = date.today() + timedelta(days=7 - date.today().weekday())
        first = self.create_request(date=week_start.isoformat(), slot="10:00-12:00")
        second = self.create_request(
            date=(week_start + timedelta(days=2)).isoformat(),
            slot="12:00-14:00",
        )
        third = self.create_request(
            date=(week_start + timedelta(days=4)).isoformat(),
            slot="14:00-16:00",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(third.status_code, 409)
        self.assertEqual(
            third.json["error"],
            "Límite semanal alcanzado: máximo 2 reservas por semana para permitir el uso equitativo de las zonas comunes.",
        )
        self.assertEqual(Reservation.query.count(), 2)

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
        for index, slot in enumerate(STANDARD_TIME_SLOTS):
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

    def test_extended_slots_are_social_hall_only_and_conflicts_use_overlap(self):
        approved_half_day = Reservation(
            resident_id=self.resident.id,
            common_area_id=self.area.id,
            date=self.future_date,
            time_slot="08:00-15:00",
            status="aprobada",
        )
        gym = CommonArea(name="GIMNASIO")
        db.session.add_all([approved_half_day, gym])
        db.session.commit()

        overlapping = self.create_request(
            resident=self.other_resident,
            slot="10:00-12:00",
        )
        adjacent = self.create_request(
            resident=self.other_resident,
            slot="15:00-22:00",
        )
        invalid_zone = self.create_request(
            resident=self.other_resident,
            commonAreaId=gym.id,
            slot="08:00-15:00",
        )

        self.assertEqual(overlapping.status_code, 409)
        self.assertEqual(adjacent.status_code, 201)
        self.assertEqual(invalid_zone.status_code, 400)
        self.assertEqual(
            invalid_zone.json["error"],
            "El día completo o media jornada es exclusivo del Salón Social.",
        )

    def test_invalid_legacy_reservation_can_still_be_rejected(self):
        gym = CommonArea(name="GIMNASIO")
        db.session.add(gym)
        db.session.flush()
        reservation = Reservation(
            resident_id=self.resident.id,
            common_area_id=gym.id,
            date=self.future_date,
            time_slot="08:00-15:00",
            status="pendiente",
        )
        db.session.add(reservation)
        db.session.commit()

        rejected = self.client.put(
            f"/api/reservations/{reservation.id}/status",
            headers=self.headers(self.admin),
            json={"status": "rechazada"},
        )

        self.assertEqual(rejected.status_code, 200)

    def test_archived_active_reservation_does_not_conflict(self):
        archived = Reservation(
            resident_id=self.resident.id,
            common_area_id=self.area.id,
            date=self.future_date,
            time_slot="10:00-12:00",
            status="aprobada",
            is_archived=True,
        )
        db.session.add(archived)
        db.session.commit()

        created = self.create_request(resident=self.other_resident)
        self.assertEqual(created.status_code, 201)
        reservation_id = created.json["reservation"]["id"]
        approved = self.client.put(
            f"/api/reservations/{reservation_id}/status",
            headers=self.headers(self.admin),
            json={"status": "aprobada"},
        )

        self.assertEqual(approved.status_code, 200)
        self.assertEqual(Reservation.query.filter_by(
            date=self.future_date,
            time_slot="10:00-12:00",
            is_archived=False,
            status="aprobada",
        ).count(), 1)

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
        self.assertNotEqual(same_day.status, "cancelada")

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
