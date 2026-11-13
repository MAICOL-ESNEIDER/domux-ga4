import base64
import unittest
from datetime import date, timedelta

import env_setup  # noqa: F401  (va antes de importar la app)

from app import create_app
from auth import generate_token
from business_days import colombian_holidays
from extensions import db
from models import AuditLog, CommonArea, Notification, Reservation, ReservationMessage, User
from services.zone_rules import DEFAULT_SLOTS, human_date
from structure_fixtures import apartment_for
from time_utils import colombia_today
from werkzeug.security import generate_password_hash


class ReservationTestCase(unittest.TestCase):
    """Base con una administración, dos residentes, un guardia y la zona «Salón social»."""

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
            apartment_ref=apartment_for("Apto 101"),
            is_active=True,
        )
        self.other_resident = User(
            name="Other",
            email="other-reservations@test.local",
            password_hash=generate_password_hash("Other123*"),
            role="RESIDENT",
            apartment_ref=apartment_for("Apto 202"),
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
        self.future_date = (colombia_today() + timedelta(days=3)).isoformat()

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


class ReservationWorkflowTests(ReservationTestCase):
    def test_reservation_request_is_pending_and_optional_message_is_saved(self):
        response = self.create_request(
            message="Necesito confirmar el depósito.",
            mediaUrl="data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nfoto").decode(),
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

    def test_minor_without_parental_consent_cannot_request_reservation(self):
        today = colombia_today()
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
        week_start = colombia_today() + timedelta(days=7 - colombia_today().weekday())
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
            "Límite semanal alcanzado: máximo 2 reservas por semana en Salón social "
            "para permitir el uso equitativo de las zonas comunes.",
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
        for index, slot in enumerate(DEFAULT_SLOTS):
            db.session.add(Reservation(
                resident_id=self.resident.id,
                common_area_id=self.area.id,
                date=self.future_date,
                time_slot=slot,
                status="aprobada",
            ))
        partial_date = (colombia_today() + timedelta(days=4)).isoformat()
        db.session.add(Reservation(
            resident_id=self.resident.id,
            common_area_id=self.area.id,
            date=partial_date,
            time_slot=DEFAULT_SLOTS[0],
            status="aprobada",
        ))
        pending_date = (colombia_today() + timedelta(days=5)).isoformat()
        db.session.add(Reservation(
            resident_id=self.resident.id,
            common_area_id=self.area.id,
            date=pending_date,
            time_slot=DEFAULT_SLOTS[0],
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
        self.assertEqual(created.status_code, 201)
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
            date=colombia_today().isoformat(),
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


class ZoneRulesTests(ReservationTestCase):
    """HU-055, RN-020 a RN-022: cada zona guarda sus reglas y las reservas nuevas las usan."""

    def setUp(self):
        super().setUp()
        self.gym = CommonArea(name="Gimnasio")
        db.session.add(self.gym)
        db.session.commit()

    def day(self, days_ahead):
        return (colombia_today() + timedelta(days=days_ahead)).isoformat()

    def set_rules(self, area=None, expected=200, **rules):
        response = self.client.put(
            f"/api/common-areas/{(area or self.area).id}/rules",
            headers=self.headers(self.admin),
            json=rules,
        )
        self.assertEqual(response.status_code, expected, response.get_json())
        return response

    def book(self, days_ahead, slot="10:00-12:00", area=None, resident=None, **fields):
        body = {
            "commonAreaId": (area or self.area).id,
            "date": self.day(days_ahead),
            "timeSlot": slot,
            **fields,
        }
        return self.client.post(
            "/api/reservations", headers=self.headers(resident or self.resident), json=body
        )

    def stored(self, days_ahead, status="aprobada", slot="10:00-12:00", area=None, resident=None):
        reservation = Reservation(
            resident_id=(resident or self.resident).id,
            common_area_id=(area or self.area).id,
            date=self.day(days_ahead),
            time_slot=slot,
            status=status,
        )
        db.session.add(reservation)
        db.session.commit()
        return reservation

    def cancel(self, reservation, user=None):
        return self.client.put(
            f"/api/reservations/{reservation.id}/cancel", headers=self.headers(user or self.resident)
        )

    def availability(self, days_ahead, area=None):
        response = self.client.get(
            f"/api/reservations/availability?commonAreaId={(area or self.area).id}"
            f"&date={self.day(days_ahead)}",
            headers=self.headers(self.resident),
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def next_week_day(self, offset):
        """Un día de la semana que viene (0 es el lunes), para no chocar con el límite diario."""
        today = colombia_today()
        return (today + timedelta(days=7 - today.weekday() + offset) - today).days

    # --- Las reglas y quién las cambia -------------------------------------------------

    def test_a_zone_without_changes_has_the_default_rules(self):
        response = self.client.get("/api/common-areas", headers=self.headers(self.resident))

        zone = next(item for item in response.get_json()["areas"] if item["name"] == "Salón social")
        self.assertEqual(zone["openTime"], "08:00")
        self.assertEqual(zone["closeTime"], "22:00")
        self.assertEqual(zone["slotMinutes"], 120)
        self.assertEqual(zone["slots"], list(DEFAULT_SLOTS))
        self.assertIsNone(zone["capacity"])
        self.assertEqual(zone["minAdvanceDays"], 0)
        self.assertEqual(zone["maxAdvanceDays"], 60)
        self.assertEqual(zone["cancelDeadlineDays"], 3)
        self.assertEqual(zone["weeklyLimit"], 2)
        self.assertIsNone(zone["maintenanceWeekday"])

    def test_guards_can_also_see_the_rules_of_the_zones(self):
        response = self.client.get("/api/common-areas", headers=self.headers(self.guard))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()["areas"]), 2)

    def test_administration_changes_the_rules_and_they_are_saved(self):
        response = self.set_rules(
            openTime="06:00", closeTime="20:00", slotMinutes=60, capacity=30,
            minAdvanceDays=1, maxAdvanceDays=30, cancelDeadlineDays=2, weeklyLimit=3,
            maintenanceWeekday=0,
        )

        zone = response.get_json()["area"]
        self.assertEqual(zone["openTime"], "06:00")
        self.assertEqual(zone["closeTime"], "20:00")
        self.assertEqual(zone["slotMinutes"], 60)
        self.assertEqual(len(zone["slots"]), 14)
        self.assertEqual(zone["slots"][0], "06:00-07:00")
        self.assertEqual(zone["slots"][-1], "19:00-20:00")
        self.assertEqual(zone["capacity"], 30)
        self.assertEqual(
            [zone[key] for key in (
                "minAdvanceDays", "maxAdvanceDays", "cancelDeadlineDays", "weeklyLimit",
                "maintenanceWeekday",
            )],
            [1, 30, 2, 3, 0],
        )
        saved = db.session.get(CommonArea, self.area.id)
        self.assertEqual((saved.open_time, saved.weekly_limit), ("06:00", 3))

    def test_only_the_changed_rules_are_touched_and_the_change_is_audited(self):
        self.set_rules(weeklyLimit=4)

        zone = db.session.get(CommonArea, self.area.id)
        self.assertEqual(zone.weekly_limit, 4)
        self.assertEqual(zone.open_time, "08:00")
        self.assertEqual(db.session.get(CommonArea, self.gym.id).weekly_limit, 2)
        log = AuditLog.query.filter_by(
            entity_type="common_area", entity_id=self.area.id, action="rules_changed"
        ).one()
        self.assertEqual(log.actor_id, self.admin.id)
        self.assertIn("weekly_limit", log.details)

    def test_null_goes_back_to_the_default_or_to_undefined(self):
        self.set_rules(capacity=25, cancelDeadlineDays=2, weeklyLimit=5, maintenanceWeekday=3)

        self.set_rules(capacity=None, cancelDeadlineDays=None, weeklyLimit=None, maintenanceWeekday=None)

        zone = db.session.get(CommonArea, self.area.id)
        self.assertIsNone(zone.capacity)
        self.assertEqual(zone.cancel_deadline_days, 3)
        self.assertEqual(zone.weekly_limit, 2)
        self.assertIsNone(zone.maintenance_weekday)

    def test_only_administration_can_change_the_rules(self):
        for user in (self.resident, self.guard):
            with self.subTest(role=user.role):
                response = self.client.put(
                    f"/api/common-areas/{self.area.id}/rules",
                    headers=self.headers(user),
                    json={"weeklyLimit": 9},
                )
                self.assertEqual(response.status_code, 403)
        self.assertEqual(db.session.get(CommonArea, self.area.id).weekly_limit, 2)

    def test_unknown_zone_and_empty_changes_are_refused(self):
        unknown = self.client.put(
            "/api/common-areas/9999/rules", headers=self.headers(self.admin), json={"weeklyLimit": 2}
        )
        nothing = self.client.put(
            f"/api/common-areas/{self.area.id}/rules", headers=self.headers(self.admin), json={}
        )
        unrelated = self.client.put(
            f"/api/common-areas/{self.area.id}/rules",
            headers=self.headers(self.admin),
            json={"color": "azul"},
        )

        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(nothing.status_code, 400)
        self.assertEqual(unrelated.status_code, 400)

    def test_rules_that_make_no_sense_are_refused_and_nothing_changes(self):
        invalid = [
            {"openTime": "25:00"},
            {"openTime": "8:00"},
            {"closeTime": "07:00"},                      # cierra antes de abrir (abre a las 08:00)
            {"openTime": "21:30"},                       # no cabe una franja de 120 minutos
            {"slotMinutes": 45},
            {"slotMinutes": True},
            {"slotMinutes": "120"},
            {"capacity": 0},
            {"capacity": "muchos"},
            {"capacity": 2001},
            {"minAdvanceDays": -1},
            {"minAdvanceDays": 31},
            {"maxAdvanceDays": 0},
            {"minAdvanceDays": 10, "maxAdvanceDays": 5},
            {"cancelDeadlineDays": 0},
            {"cancelDeadlineDays": 4},                   # solo se puede bajar de 3, no subir
            {"weeklyLimit": 0},
            {"weeklyLimit": 15},
            {"weeklyLimit": 1.5},
            {"maintenanceWeekday": 7},
            {"maintenanceWeekday": False},
        ]
        for rules in invalid:
            with self.subTest(rules=rules):
                self.set_rules(expected=400, **rules)

        zone = db.session.get(CommonArea, self.area.id).to_dict()
        self.assertEqual(zone["openTime"], "08:00")
        self.assertEqual(zone["weeklyLimit"], 2)
        self.assertEqual(AuditLog.query.filter_by(action="rules_changed").count(), 0)

    # --- Horario y franjas -------------------------------------------------------------

    def test_new_reservations_use_the_new_schedule_without_changing_the_code(self):
        self.set_rules(openTime="06:00", closeTime="20:00", slotMinutes=60)

        early = self.book(3, "06:00-07:00")
        # La franja de 2 horas de antes ahora son dos franjas seguidas, y la zona permite una a la vez.
        old_slot = self.book(4, "10:00-12:00")
        misaligned = self.book(4, "10:30-11:30")

        self.assertEqual(early.status_code, 201)
        self.assertEqual(old_slot.status_code, 400)
        self.assertIn("En Salón social se puede reservar una franja a la vez", old_slot.get_json()["error"])
        self.assertEqual(misaligned.status_code, 400)
        self.assertIn("Ese horario no existe en Salón social", misaligned.get_json()["error"])

    def test_a_slot_outside_the_schedule_is_refused_for_everyone(self):
        self.set_rules(openTime="10:00", closeTime="16:00")

        for slot in ("08:00-10:00", "16:00-18:00", "9999"):
            with self.subTest(slot=slot):
                self.assertEqual(self.book(3, slot).status_code, 400)
        by_admin = self.client.post(
            "/api/reservations",
            headers=self.headers(self.admin),
            json={
                "commonAreaId": self.area.id, "date": self.day(3), "timeSlot": "08:00-10:00",
                "residentId": self.resident.id,
            },
        )
        self.assertEqual(by_admin.status_code, 400)
        self.assertEqual(Reservation.query.count(), 0)

    def test_availability_lists_the_slots_of_the_zone_schedule(self):
        self.set_rules(openTime="09:00", closeTime="15:00", slotMinutes=180)

        result = self.availability(3)

        self.assertEqual(result["availableSlots"], ["09:00-12:00", "12:00-15:00"])
        self.assertEqual(result["occupiedSlots"], [])
        self.assertFalse(result["closed"])

    def test_zones_keep_independent_schedules(self):
        self.set_rules(self.gym, openTime="05:00", closeTime="09:00", slotMinutes=60)

        self.assertEqual(self.availability(3, self.gym)["availableSlots"][0], "05:00-06:00")
        self.assertEqual(self.availability(3)["availableSlots"][0], "08:00-10:00")
        self.assertEqual(self.book(3, "05:00-06:00", area=self.gym).status_code, 201)
        self.assertEqual(self.book(4, "05:00-06:00").status_code, 400)

    def test_slots_that_overlap_after_a_schedule_change_still_conflict(self):
        self.stored(3, slot="10:00-12:00", resident=self.other_resident)
        self.set_rules(slotMinutes=60)

        result = self.availability(3)

        self.assertIn("10:00-11:00", result["occupiedSlots"])
        self.assertIn("11:00-12:00", result["occupiedSlots"])
        self.assertIn("12:00-13:00", result["availableSlots"])
        self.assertEqual(self.book(3, "11:00-12:00").status_code, 409)
        self.assertEqual(self.book(3, "12:00-13:00").status_code, 201)

    def test_back_to_back_slots_do_not_conflict(self):
        neighbor = User(
            name="Neighbor",
            email="neighbor-reservations@test.local",
            password_hash=generate_password_hash("Neighbor123*"),
            role="RESIDENT",
            apartment_ref=apartment_for("Apto 303"),
            is_active=True,
        )
        db.session.add(neighbor)
        db.session.commit()
        self.stored(3, slot="10:00-12:00", resident=self.other_resident)

        after = self.book(3, "12:00-14:00")
        before = self.book(3, "08:00-10:00", resident=neighbor)

        self.assertEqual(after.status_code, 201)
        self.assertEqual(before.status_code, 201)

    def test_the_calendar_marks_a_day_full_only_when_no_slot_is_left(self):
        self.set_rules(openTime="08:00", closeTime="14:00")  # tres franjas de 2 horas
        for slot in ("08:00-10:00", "10:00-12:00", "12:00-14:00"):
            self.stored(3, slot=slot)
        for slot in ("08:00-10:00", "10:00-12:00"):
            self.stored(4, slot=slot)
        today = colombia_today() + timedelta(days=3)

        response = self.client.get(
            f"/api/reservations/calendar?commonAreaId={self.area.id}"
            f"&year={today.year}&month={today.month}",
            headers=self.headers(self.resident),
        )

        blocked = response.get_json()["blockedDates"]
        self.assertIn(self.day(3), blocked)
        self.assertNotIn(self.day(4), blocked)

    # --- Aforo -------------------------------------------------------------------------

    def test_attendees_cannot_exceed_the_capacity_of_the_zone(self):
        self.set_rules(capacity=10)

        too_many = self.book(3, attendees=11)
        exact = self.book(4, attendees=10)

        self.assertEqual(too_many.status_code, 400)
        self.assertIn("aforo de Salón social es de 10", too_many.get_json()["error"])
        self.assertEqual(exact.status_code, 201)
        self.assertEqual(exact.get_json()["reservation"]["attendees"], 10)

    def test_attendees_must_be_a_positive_whole_number(self):
        self.set_rules(capacity=10)

        for value in (0, -2, "cinco", True, 2.5):
            with self.subTest(value=value):
                self.assertEqual(self.book(3, attendees=value).status_code, 400)
        self.assertEqual(Reservation.query.count(), 0)

    def test_without_a_capacity_any_number_of_people_is_accepted(self):
        response = self.book(3, attendees=500)

        self.assertEqual(response.status_code, 201)

    def test_attendees_are_optional(self):
        response = self.book(3)

        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.get_json()["reservation"]["attendees"])

    # --- Anticipación ------------------------------------------------------------------

    def test_a_reservation_needs_the_minimum_advance_of_the_zone(self):
        self.set_rules(minAdvanceDays=2)

        too_soon = self.book(1)
        in_time = self.book(2)

        self.assertEqual(too_soon.status_code, 400)
        self.assertIn("al menos 2 días de anticipación", too_soon.get_json()["error"])
        self.assertEqual(in_time.status_code, 201)

    def test_a_reservation_cannot_be_too_far_in_advance(self):
        self.set_rules(maxAdvanceDays=10)

        too_far = self.book(11)
        allowed = self.book(10)

        self.assertEqual(too_far.status_code, 400)
        self.assertIn("máximo 10 días de anticipación", too_far.get_json()["error"])
        self.assertEqual(allowed.status_code, 201)

    def test_administration_can_book_on_behalf_of_a_resident_outside_the_advance_rules(self):
        self.set_rules(minAdvanceDays=5)

        response = self.client.post(
            "/api/reservations",
            headers=self.headers(self.admin),
            json={
                "commonAreaId": self.area.id, "date": self.day(0), "timeSlot": "10:00-12:00",
                "residentId": self.resident.id,
            },
        )

        self.assertEqual(response.status_code, 201)

    # --- Límite semanal por zona -------------------------------------------------------

    def test_weekly_limit_is_per_zone_and_comes_from_the_zone(self):
        self.set_rules(weeklyLimit=1)

        first = self.book(self.next_week_day(0))
        second_same_zone = self.book(self.next_week_day(2))
        other_zone = self.book(self.next_week_day(2), area=self.gym)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second_same_zone.status_code, 409)
        self.assertEqual(
            second_same_zone.get_json()["error"],
            "Límite semanal alcanzado: máximo 1 reserva por semana en Salón social "
            "para permitir el uso equitativo de las zonas comunes.",
        )
        self.assertEqual(other_zone.status_code, 201)

    def test_a_higher_weekly_limit_lets_the_resident_book_more(self):
        self.set_rules(weeklyLimit=3)

        results = [self.book(self.next_week_day(offset)).status_code for offset in (0, 1, 2, 3)]

        self.assertEqual(results, [201, 201, 201, 409])

    def test_the_default_weekly_limit_is_two(self):
        results = [self.book(self.next_week_day(offset)).status_code for offset in (0, 1, 2)]

        self.assertEqual(results, [201, 201, 409])

    def test_the_week_starts_on_monday(self):
        self.set_rules(weeklyLimit=1)

        sunday = self.book(self.next_week_day(-1))   # domingo: es de la semana anterior
        monday = self.book(self.next_week_day(0))

        self.assertEqual(sunday.status_code, 201)
        self.assertEqual(monday.status_code, 201)

    def test_cancelled_and_rejected_reservations_do_not_count_for_the_limit(self):
        self.set_rules(weeklyLimit=1)
        self.stored(self.next_week_day(0), status="cancelada")
        self.stored(self.next_week_day(1), status="rechazada", slot="12:00-14:00")

        self.assertEqual(self.book(self.next_week_day(2)).status_code, 201)

    # --- Cancelación -------------------------------------------------------------------

    def test_without_its_own_term_a_zone_allows_cancelling_up_to_three_days_before(self):
        on_time = self.stored(3)
        late = self.stored(2, slot="12:00-14:00")

        accepted = self.cancel(on_time)
        refused = self.cancel(late)

        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(on_time.status, "cancelada")
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(late.status, "aprobada")
        message = refused.get_json()["error"]
        self.assertIn("3 días antes", message)
        self.assertIn(human_date(colombia_today() - timedelta(days=1)), message)

    def test_a_zone_can_lower_the_term_to_two_days(self):
        self.set_rules(cancelDeadlineDays=2)
        on_time = self.stored(2)
        late = self.stored(1, slot="12:00-14:00")

        self.assertEqual(self.cancel(on_time).status_code, 200)
        refused = self.cancel(late)

        self.assertEqual(refused.status_code, 400)
        self.assertIn("2 días antes", refused.get_json()["error"])

    def test_the_term_is_the_one_of_the_zone_of_each_reservation(self):
        self.set_rules(self.gym, cancelDeadlineDays=1)
        in_gym = self.stored(1, area=self.gym)
        in_hall = self.stored(1)

        self.assertEqual(self.cancel(in_gym).status_code, 200)
        self.assertEqual(self.cancel(in_hall).status_code, 400)

    def test_pending_reservations_follow_the_same_term(self):
        pending = self.stored(2, status="pendiente")

        self.assertEqual(self.cancel(pending).status_code, 400)

    def test_administration_can_cancel_after_the_term(self):
        late = self.stored(1)

        response = self.cancel(late, self.admin)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(late.status, "cancelada")

    def test_the_reservation_tells_until_when_it_can_be_cancelled(self):
        on_time = self.stored(5)
        late = self.stored(2, slot="12:00-14:00")
        done = self.stored(6, status="cancelada", slot="14:00-16:00")

        payload = {
            item["id"]: item
            for item in self.client.get(
                "/api/reservations", headers=self.headers(self.resident)
            ).get_json()["reservations"]
        }

        self.assertEqual(payload[on_time.id]["cancelUntil"], self.day(2))
        self.assertTrue(payload[on_time.id]["canCancel"])
        self.assertEqual(payload[late.id]["cancelUntil"], self.day(-1))
        self.assertFalse(payload[late.id]["canCancel"])
        self.assertFalse(payload[done.id]["canCancel"])

    def test_cancelling_frees_the_slot_in_the_calendar(self):
        reservation = self.stored(4)
        self.assertIn("10:00-12:00", self.availability(4)["occupiedSlots"])

        self.assertEqual(self.cancel(reservation).status_code, 200)

        self.assertIn("10:00-12:00", self.availability(4)["availableSlots"])

    # --- Mantenimiento (RN-021) --------------------------------------------------------

    def next_weekday(self, weekday, holiday=False):
        """La próxima fecha con ese día de la semana, que sea festiva o no."""
        day = colombia_today() + timedelta(days=1)
        while day.weekday() != weekday or (day in colombian_holidays(day.year)) != holiday:
            day += timedelta(days=1)
        return day

    def test_a_zone_is_closed_for_maintenance_on_its_maintenance_day(self):
        day = self.next_weekday(0)
        self.set_rules(maintenanceWeekday=0, maxAdvanceDays=365)
        ahead = (day - colombia_today()).days

        refused = self.book(ahead)
        availability = self.availability(ahead)

        self.assertEqual(refused.status_code, 400)
        self.assertIn("cerrada por mantenimiento", refused.get_json()["error"])
        self.assertIn("cada lunes", refused.get_json()["error"])
        self.assertTrue(availability["closed"])
        self.assertEqual(availability["availableSlots"], [])

    def test_the_other_days_of_the_week_stay_open(self):
        self.set_rules(maintenanceWeekday=0)
        wednesday = self.next_weekday(2)

        response = self.book((wednesday - colombia_today()).days)

        self.assertEqual(response.status_code, 201)

    def test_when_the_maintenance_day_is_a_holiday_it_moves_to_the_next_day(self):
        holiday_monday = self.next_weekday(0, holiday=True)
        self.set_rules(maintenanceWeekday=0, maxAdvanceDays=365)
        monday = (holiday_monday - colombia_today()).days

        open_on_holiday = self.book(monday)
        closed_next_day = self.book(monday + 1, resident=self.other_resident)

        self.assertEqual(open_on_holiday.status_code, 201)
        self.assertEqual(closed_next_day.status_code, 400)
        self.assertIn("cerrada por mantenimiento", closed_next_day.get_json()["error"])

    def test_the_calendar_lists_the_days_closed_for_maintenance(self):
        self.set_rules(maintenanceWeekday=2)
        today = colombia_today()

        response = self.client.get(
            f"/api/reservations/calendar?commonAreaId={self.area.id}"
            f"&year={today.year}&month={today.month}",
            headers=self.headers(self.resident),
        )

        closed = [date.fromisoformat(day) for day in response.get_json()["closedDates"]]
        holidays = colombian_holidays(today.year)
        self.assertTrue(closed)
        self.assertTrue(all(day.month == today.month for day in closed))
        for day in closed:
            # Cerrada el miércoles o, si el miércoles fue festivo, el jueves siguiente.
            self.assertTrue(
                (day.weekday() == 2 and day not in holidays)
                or (day.weekday() == 3 and day - timedelta(days=1) in holidays),
                f"{day} no debería estar cerrado",
            )

    def test_a_zone_without_maintenance_day_never_closes(self):
        today = colombia_today()

        response = self.client.get(
            f"/api/reservations/calendar?commonAreaId={self.area.id}"
            f"&year={today.year}&month={today.month}",
            headers=self.headers(self.resident),
        )

        self.assertEqual(response.get_json()["closedDates"], [])


    # --- Varias franjas seguidas y el día completo ------------------------------------------------

    def test_by_default_a_zone_takes_one_slot_at_a_time_and_says_so(self):
        response = self.client.get("/api/common-areas", headers=self.headers(self.resident))
        hall = next(area for area in response.get_json()["areas"] if area["id"] == self.area.id)

        self.assertEqual((hall["maxConsecutiveSlots"], hall["allowFullDay"]), (1, False))
        self.assertEqual(hall["fullDaySlot"], "08:00-22:00")
        two_slots = self.book(3, "10:00-14:00")
        self.assertEqual(two_slots.status_code, 400)
        self.assertEqual(two_slots.get_json()["error"], "En Salón social se puede reservar una franja a la vez.")

    def test_several_slots_in_a_row_up_to_the_zone_maximum(self):
        self.set_rules(maxConsecutiveSlots=2)

        two = self.book(3, "10:00-14:00")
        three = self.book(4, "10:00-16:00")

        self.assertEqual(two.status_code, 201, two.get_json())
        self.assertEqual(Reservation.query.one().time_slot, "10:00-14:00")
        self.assertEqual(three.status_code, 400)
        self.assertEqual(three.get_json()["error"], "En Salón social se puede reservar hasta 2 franjas seguidas.")

    def test_the_whole_day_only_where_the_zone_allows_it(self):
        refused = self.book(3, "08:00-22:00")
        self.set_rules(allowFullDay=True)
        availability = self.availability(4)
        whole_day = self.book(4, "08:00-22:00")
        two_slots = self.book(5, "08:00-12:00")

        self.assertEqual(refused.status_code, 400)
        self.assertTrue(availability["allowFullDay"])
        self.assertEqual(availability["fullDaySlot"], "08:00-22:00")
        self.assertEqual(availability["maxConsecutiveSlots"], 1)
        self.assertEqual(whole_day.status_code, 201, whole_day.get_json())
        self.assertEqual(two_slots.status_code, 400)
        self.assertEqual(
            two_slots.get_json()["error"], "En Salón social se puede reservar una franja a la vez o el día completo."
        )

    def test_a_long_reservation_takes_every_slot_it_covers(self):
        # La reserva larga es de otro residente: así no cuenta el límite de una reserva por día.
        self.stored(3, slot="10:00-14:00", resident=self.other_resident)

        availability = self.availability(3)
        inside = self.book(3, "12:00-14:00")
        next_to_it = self.book(3, "14:00-16:00")

        self.assertIn("10:00-12:00", availability["occupiedSlots"])
        self.assertIn("12:00-14:00", availability["occupiedSlots"])
        self.assertIn("14:00-16:00", availability["availableSlots"])
        self.assertEqual(inside.status_code, 409)
        self.assertEqual(inside.get_json()["error"], "Ese horario ya no está disponible")
        self.assertEqual(next_to_it.status_code, 201)

    def test_the_whole_day_is_not_free_if_any_slot_is_taken(self):
        self.set_rules(allowFullDay=True)
        self.stored(3, slot="16:00-18:00", resident=self.other_resident)

        response = self.book(3, "08:00-22:00")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "Ese horario ya no está disponible")
        self.assertEqual(Reservation.query.count(), 1)

    def test_approving_a_long_reservation_checks_every_slot(self):
        self.set_rules(maxConsecutiveSlots=3)
        long_request = self.book(3, "10:00-16:00")
        self.assertEqual(long_request.status_code, 201)
        self.stored(3, slot="14:00-16:00", resident=self.other_resident)

        response = self.client.put(
            f"/api/reservations/{long_request.get_json()['reservation']['id']}/status",
            headers=self.headers(self.admin),
            json={"status": "aprobada"},
        )

        self.assertEqual(response.status_code, 409)

    def test_ranges_that_do_not_start_and_end_on_slots_are_refused(self):
        self.set_rules(maxConsecutiveSlots=3)

        for slot in ("09:00-11:00", "10:00-11:00", "12:00-10:00", "10:00-10:00", "10:00-24:00"):
            with self.subTest(slot=slot):
                response = self.book(3, slot)
                self.assertEqual(response.status_code, 400)
                self.assertIn("Ese horario no existe en Salón social", response.get_json()["error"])

    def test_the_new_rules_are_checked_and_null_goes_back_to_the_default(self):
        too_many = self.set_rules(expected=400, maxConsecutiveSlots=8)
        zero = self.set_rules(expected=400, maxConsecutiveSlots=0)
        not_a_flag = self.set_rules(expected=400, allowFullDay="sí")
        self.set_rules(maxConsecutiveSlots=3, allowFullDay=True)
        changed = (self.area.max_consecutive_slots, self.area.allow_full_day)
        self.set_rules(maxConsecutiveSlots=None, allowFullDay=None)
        db.session.refresh(self.area)

        self.assertIn("La zona tiene 7 franjas al día", too_many.get_json()["error"])
        self.assertIn("entre 1 y 48", zero.get_json()["error"])
        self.assertIn("sí o no", not_a_flag.get_json()["error"])
        self.assertEqual(changed, (3, True))
        self.assertEqual((self.area.max_consecutive_slots, self.area.allow_full_day), (1, False))

    def test_a_shorter_day_cannot_keep_more_slots_in_a_row_than_it_has(self):
        self.set_rules(maxConsecutiveSlots=5)

        response = self.set_rules(expected=400, slotMinutes=240)

        self.assertIn("La zona tiene 3 franjas al día", response.get_json()["error"])

if __name__ == "__main__":
    unittest.main()
