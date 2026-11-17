"""Zonas comunes completas (DEC-032): la administración agrega, renombra, cierra con motivo, abre y retira zonas.

Cada conjunto tiene sus propias zonas y las cambia con sus asambleas, así que nada de esto está en el código.
Aquí se comprueba lo que ve cada rol y lo que pasa con las reservas cuando una zona se cierra o se retira.
"""

import unittest
from datetime import timedelta

import env_setup  # noqa: F401  (va antes de importar la app)

import test_reservations  # la base con la administración, los residentes y la zona «Salón social»
from extensions import db
from models import AuditLog, CommonArea, Notification, Reservation
from time_utils import colombia_today

CLOSED_TITLE = "Zona común cerrada"
REASON = "Falla en la bomba de agua; el técnico viene el jueves."


class ZoneManagementTestCase(test_reservations.ReservationTestCase):
    def day(self, days_ahead):
        return (colombia_today() + timedelta(days=days_ahead)).isoformat()

    def post(self, path, user=None, **body):
        return self.client.post(path, headers=self.headers(user or self.admin), json=body or None)

    def create_zone(self, expected=201, user=None, **body):
        response = self.post("/api/common-areas", user=user, **body)
        self.assertEqual(response.status_code, expected, response.get_json())
        return response

    def close_zone(self, area, expected=200, reason=REASON, user=None):
        body = {} if reason is None else {"reason": reason}
        response = self.post(f"/api/common-areas/{area.id}/close", user=user, **body)
        self.assertEqual(response.status_code, expected, response.get_json())
        return response

    def open_zone(self, area, expected=200, user=None):
        response = self.post(f"/api/common-areas/{area.id}/open", user=user)
        self.assertEqual(response.status_code, expected, response.get_json())
        return response

    def retire_zone(self, area, expected=200, user=None):
        response = self.client.delete(
            f"/api/common-areas/{area.id}", headers=self.headers(user or self.admin)
        )
        self.assertEqual(response.status_code, expected, response.get_json())
        return response

    def zone(self, area):
        db.session.expire_all()
        return db.session.get(CommonArea, area.id)

    def stored(self, days_ahead=3, status="aprobada", slot="10:00-12:00", area=None, resident=None):
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

    def book(self, area, days_ahead=3, slot="10:00-12:00", user=None, **fields):
        body = {"commonAreaId": area.id, "date": self.day(days_ahead), "timeSlot": slot, **fields}
        return self.client.post("/api/reservations", headers=self.headers(user or self.resident), json=body)

    def listed(self, user=None, query=""):
        response = self.client.get(f"/api/common-areas{query}", headers=self.headers(user or self.resident))
        self.assertEqual(response.status_code, 200)
        return {item["name"]: item for item in response.get_json()["areas"]}


class CreatingZonesTests(ZoneManagementTestCase):
    def test_administration_adds_a_zone_with_the_default_rules(self):
        response = self.create_zone(name="  Piscina  ")

        area = response.get_json()["area"]
        self.assertEqual(area["name"], "Piscina")
        self.assertEqual((area["openTime"], area["closeTime"], area["slotMinutes"]), ("08:00", "22:00", 120))
        self.assertIsNone(area["capacity"])
        self.assertTrue(area["isOpen"])
        self.assertIsNone(area["closedReason"])
        self.assertIsNone(area["retiredAt"])
        self.assertIn("Piscina", self.listed())
        audit = AuditLog.query.filter_by(entity_type="common_area", action="created").one()
        self.assertEqual(audit.entity_id, area["id"])
        self.assertEqual(audit.actor_id, self.admin.id)

    def test_the_zone_can_be_created_with_its_own_rules(self):
        area = self.create_zone(
            name="Salón de juegos", openTime="10:00", closeTime="20:00", slotMinutes=60, capacity=15,
            weeklyLimit=1, allowFullDay=True, maintenanceWeekday=0,
        ).get_json()["area"]

        self.assertEqual((area["openTime"], area["closeTime"], area["slotMinutes"]), ("10:00", "20:00", 60))
        self.assertEqual((area["capacity"], area["weeklyLimit"], area["maintenanceWeekday"]), (15, 1, 0))
        self.assertTrue(area["allowFullDay"])
        self.assertEqual(len(area["slots"]), 10)

    def test_a_new_zone_can_be_reserved_right_away(self):
        area = db.session.get(CommonArea, self.create_zone(name="Terraza").get_json()["area"]["id"])

        self.assertEqual(self.book(area).status_code, 201)

    def test_the_name_is_required_and_has_a_reasonable_length(self):
        for body in ({}, {"capacity": 5}, {"name": 5}, {"name": "A"}, {"name": "x" * 101}):
            with self.subTest(body=body):
                self.create_zone(expected=400, **body)
        self.assertEqual(CommonArea.query.count(), 1)

    def test_rules_that_make_no_sense_create_nothing(self):
        self.create_zone(expected=400, name="Cancha", openTime="20:00", closeTime="08:00")
        self.create_zone(expected=400, name="Cancha", slotMinutes=45)
        self.assertEqual(CommonArea.query.count(), 1)

    def test_two_current_zones_cannot_share_a_name_even_with_other_capitals(self):
        self.create_zone(name="Piscina")

        self.create_zone(expected=409, name="piscina")
        self.create_zone(expected=409, name="  PISCINA ")
        self.assertEqual(CommonArea.query.filter(CommonArea.name.ilike("piscina")).count(), 1)

    def test_only_administration_adds_zones(self):
        for user in (self.resident, self.guard):
            with self.subTest(role=user.role):
                self.create_zone(expected=403, user=user, name="Piscina")
        self.assertEqual(CommonArea.query.count(), 1)

    def test_the_name_can_be_changed_with_the_rules(self):
        response = self.client.put(
            f"/api/common-areas/{self.area.id}/rules",
            headers=self.headers(self.admin),
            json={"name": " Salón comunal ", "capacity": 50},
        )

        self.assertEqual(response.status_code, 200, response.get_json())
        area = self.zone(self.area)
        self.assertEqual((area.name, area.capacity), ("Salón comunal", 50))
        audit = AuditLog.query.filter_by(entity_type="common_area", action="rules_changed").one()
        self.assertIn("Salón social", audit.details)
        self.assertIn("Salón comunal", audit.details)

    def test_renaming_to_the_name_of_another_zone_is_refused_but_its_own_capitals_are_fine(self):
        self.create_zone(name="Piscina")
        url = f"/api/common-areas/{self.area.id}/rules"

        clash = self.client.put(url, headers=self.headers(self.admin), json={"name": "piscina"})
        own = self.client.put(url, headers=self.headers(self.admin), json={"name": "SALÓN SOCIAL"})

        self.assertEqual(clash.status_code, 409)
        self.assertEqual(own.status_code, 200)
        self.assertEqual(self.zone(self.area).name, "SALÓN SOCIAL")


class ClosingZonesTests(ZoneManagementTestCase):
    def test_closing_a_zone_saves_the_reason_and_everyone_sees_it(self):
        response = self.close_zone(self.area)

        body = response.get_json()
        self.assertFalse(body["area"]["isOpen"])
        self.assertEqual(body["area"]["closedReason"], REASON)
        self.assertRegex(body["area"]["closedAt"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
        self.assertEqual(body["upcomingReservations"], 0)
        for user in (self.resident, self.guard, self.admin):
            with self.subTest(role=user.role):
                seen = self.listed(user)["Salón social"]
                self.assertFalse(seen["isOpen"])
                self.assertEqual(seen["closedReason"], REASON)
        saved = self.zone(self.area)
        self.assertEqual(saved.closed_by_id, self.admin.id)
        audit = AuditLog.query.filter_by(entity_type="common_area", action="closed").one()
        self.assertIn("bomba", audit.details)

    def test_a_zone_that_was_never_closed_is_open(self):
        seen = self.listed()["Salón social"]

        self.assertTrue(seen["isOpen"])
        self.assertIsNone(seen["closedReason"])
        self.assertIsNone(seen["closedAt"])

    def test_the_reason_is_required_and_has_a_reasonable_length(self):
        for reason in (None, "   ", "Mal", "x" * 301, 7):
            with self.subTest(reason=reason):
                url = f"/api/common-areas/{self.area.id}/close"
                body = {} if reason is None else {"reason": reason}
                response = self.client.post(url, headers=self.headers(self.admin), json=body or None)
                self.assertEqual(response.status_code, 400)
        self.assertTrue(self.zone(self.area).closed_at is None)

    def test_only_administration_closes_and_opens_zones(self):
        for user in (self.resident, self.guard):
            with self.subTest(role=user.role):
                self.close_zone(self.area, expected=403, user=user)
        self.close_zone(self.area)
        for user in (self.resident, self.guard):
            with self.subTest(role=user.role, action="open"):
                self.open_zone(self.area, expected=403, user=user)
        self.assertFalse(self.listed()["Salón social"]["isOpen"])

    def test_an_unknown_zone_is_not_found(self):
        response = self.post("/api/common-areas/9999/close", reason=REASON)

        self.assertEqual(response.status_code, 404)

    def test_nobody_can_request_a_reservation_in_a_closed_zone(self):
        self.close_zone(self.area)

        mine = self.book(self.area)
        for_resident = self.book(self.area, user=self.admin, residentId=self.resident.id)

        for response in (mine, for_resident):
            self.assertEqual(response.status_code, 409)
            self.assertIn("cerrada por la administración", response.get_json()["error"])
            self.assertIn("bomba de agua", response.get_json()["error"])
        self.assertEqual(Reservation.query.count(), 0)

    def test_the_availability_of_a_closed_zone_offers_no_slot_and_tells_why(self):
        self.close_zone(self.area)

        response = self.client.get(
            f"/api/reservations/availability?commonAreaId={self.area.id}&date={self.day(3)}",
            headers=self.headers(self.resident),
        )

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["availableSlots"], [])
        self.assertTrue(body["closed"])
        self.assertEqual(body["zoneClosedReason"], REASON)

    def test_an_open_zone_has_no_closure_reason_in_its_availability(self):
        response = self.client.get(
            f"/api/reservations/availability?commonAreaId={self.area.id}&date={self.day(3)}",
            headers=self.headers(self.resident),
        )

        self.assertIsNone(response.get_json()["zoneClosedReason"])
        self.assertFalse(response.get_json()["closed"])

    def test_reservations_the_zone_already_had_are_kept_and_administration_is_told(self):
        approved = self.stored(3, "aprobada")
        pending = self.stored(4, "pendiente", slot="12:00-14:00", resident=self.other_resident)
        cancelled = self.stored(5, "cancelada")
        past = self.stored(-2, "aprobada")

        response = self.close_zone(self.area)

        self.assertEqual(response.get_json()["upcomingReservations"], 2)
        for reservation, status in ((approved, "aprobada"), (pending, "pendiente"), (cancelled, "cancelada"), (past, "aprobada")):
            db.session.refresh(reservation)
            self.assertEqual(reservation.status, status)
        notice = Notification.query.filter_by(user_id=self.admin.id, title=CLOSED_TITLE).one()
        self.assertIn("Quedan 2 reservas próximas y se mantienen; revísalas en Reservas", notice.message)
        self.assertIn("bomba de agua; el técnico viene el jueves. Quedan", notice.message)
        self.assertEqual(notice.type, "reservation")
        residents = Notification.query.filter(Notification.user_id.in_([self.resident.id, self.other_resident.id]))
        self.assertEqual(residents.filter_by(title=CLOSED_TITLE).count(), 0)

    def test_every_active_administrator_is_told(self):
        second = test_reservations.User(
            name="Segunda", email="second-admin@test.local", password_hash="x", role="ADMIN", is_active=True,
        )
        inactive = test_reservations.User(
            name="Baja", email="old-admin@test.local", password_hash="x", role="ADMIN", is_active=False,
        )
        db.session.add_all([second, inactive])
        db.session.commit()
        self.stored(3, "aprobada")

        self.close_zone(self.area)

        told = {n.user_id for n in Notification.query.filter_by(title=CLOSED_TITLE)}
        self.assertEqual(told, {self.admin.id, second.id})

    def test_without_upcoming_reservations_nobody_gets_a_notice(self):
        self.close_zone(self.area)

        self.assertEqual(Notification.query.filter_by(title=CLOSED_TITLE).count(), 0)

    def test_one_upcoming_reservation_is_written_in_the_singular(self):
        self.stored(3, "aprobada")

        self.close_zone(self.area)

        notice = Notification.query.filter_by(title=CLOSED_TITLE).one()
        self.assertIn("Queda 1 reserva próxima y se mantiene; revísala en Reservas", notice.message)

    def test_closing_again_only_changes_the_reason(self):
        self.stored(3, "aprobada")
        self.close_zone(self.area)
        first = self.zone(self.area).closed_at

        again = self.close_zone(self.area, reason="Reabre el lunes, ya llegó el repuesto.")

        saved = self.zone(self.area)
        self.assertEqual(saved.closed_reason, "Reabre el lunes, ya llegó el repuesto.")
        self.assertEqual(saved.closed_at, first)
        self.assertFalse(again.get_json()["area"]["isOpen"])
        self.assertEqual(Notification.query.filter_by(title=CLOSED_TITLE).count(), 1)
        actions = [a.action for a in AuditLog.query.filter_by(entity_type="common_area").order_by(AuditLog.id)]
        self.assertEqual(actions, ["closed", "closure_reason_changed"])

    def test_a_pending_request_cannot_be_approved_while_the_zone_is_closed_but_can_be_rejected(self):
        first = self.stored(3, "pendiente")
        second = self.stored(4, "pendiente", slot="12:00-14:00", resident=self.other_resident)
        self.close_zone(self.area)

        approve = self.client.put(
            f"/api/reservations/{first.id}/status", headers=self.headers(self.admin), json={"status": "aprobada"}
        )
        reject = self.client.put(
            f"/api/reservations/{second.id}/status", headers=self.headers(self.admin), json={"status": "rechazada"}
        )

        self.assertEqual(approve.status_code, 409)
        self.assertIn("Reabre la zona", approve.get_json()["error"])
        self.assertEqual(reject.status_code, 200)
        db.session.refresh(first)
        db.session.refresh(second)
        self.assertEqual((first.status, second.status), ("pendiente", "rechazada"))

    def test_reopening_lets_the_pending_request_be_approved_and_new_ones_be_made(self):
        pending = self.stored(3, "pendiente")
        self.close_zone(self.area)

        opened = self.open_zone(self.area)

        self.assertTrue(opened.get_json()["area"]["isOpen"])
        self.assertIsNone(opened.get_json()["area"]["closedReason"])
        saved = self.zone(self.area)
        self.assertIsNone(saved.closed_at)
        self.assertIsNone(saved.closed_by_id)
        approve = self.client.put(
            f"/api/reservations/{pending.id}/status", headers=self.headers(self.admin), json={"status": "aprobada"}
        )
        self.assertEqual(approve.status_code, 200)
        self.assertEqual(self.book(self.area, 6).status_code, 201)
        audit = AuditLog.query.filter_by(entity_type="common_area", action="opened").one()
        self.assertIn("bomba", audit.details)

    def test_opening_a_zone_that_is_already_open_is_refused(self):
        self.open_zone(self.area, expected=409)

    def test_closing_one_zone_does_not_touch_the_others(self):
        other = CommonArea(name="Gimnasio")
        db.session.add(other)
        db.session.commit()

        self.close_zone(self.area)

        self.assertEqual(self.book(other).status_code, 201)
        self.assertTrue(self.listed()["Gimnasio"]["isOpen"])

    def test_the_rules_of_a_closed_zone_can_still_be_edited(self):
        self.close_zone(self.area)

        response = self.client.put(
            f"/api/common-areas/{self.area.id}/rules", headers=self.headers(self.admin), json={"capacity": 30}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.zone(self.area).closed_at is None)


class RetiringZonesTests(ZoneManagementTestCase):
    def test_retiring_a_zone_hides_it_but_keeps_it(self):
        response = self.retire_zone(self.area)

        self.assertIsNotNone(response.get_json()["area"]["retiredAt"])
        self.assertNotIn("Salón social", self.listed())
        self.assertNotIn("Salón social", self.listed(self.admin))
        saved = self.zone(self.area)
        self.assertEqual(saved.retired_by_id, self.admin.id)
        self.assertEqual(CommonArea.query.count(), 1)
        audit = AuditLog.query.filter_by(entity_type="common_area", action="retired").one()
        self.assertEqual(audit.entity_id, self.area.id)

    def test_administration_can_ask_for_the_retired_zones_too(self):
        self.retire_zone(self.area)

        seen = self.listed(self.admin, "?includeRetired=true")

        self.assertIn("Salón social", seen)
        self.assertIsNotNone(seen["Salón social"]["retiredAt"])

    def test_the_retired_zones_come_after_the_current_ones(self):
        self.create_zone(name="Zeta")
        self.retire_zone(self.area)

        names = [item["name"] for item in self.client.get(
            "/api/common-areas?includeRetired=true", headers=self.headers(self.admin)
        ).get_json()["areas"]]

        self.assertEqual(names, ["Zeta", "Salón social"])

    def test_residents_never_get_the_retired_zones_even_if_they_ask(self):
        self.retire_zone(self.area)

        for user in (self.resident, self.guard):
            with self.subTest(role=user.role):
                self.assertNotIn("Salón social", self.listed(user, "?includeRetired=true"))

    def test_a_bad_value_in_the_filter_is_refused(self):
        response = self.client.get("/api/common-areas?includeRetired=quizas", headers=self.headers(self.admin))

        self.assertEqual(response.status_code, 400)

    def test_nobody_can_reserve_a_retired_zone(self):
        self.retire_zone(self.area)

        self.assertEqual(self.book(self.area).status_code, 400)
        self.assertEqual(self.book(self.area, user=self.admin, residentId=self.resident.id).status_code, 400)

    def test_the_availability_and_the_calendar_of_a_retired_zone_do_not_exist(self):
        self.retire_zone(self.area)
        today = colombia_today()

        availability = self.client.get(
            f"/api/reservations/availability?commonAreaId={self.area.id}&date={self.day(3)}",
            headers=self.headers(self.resident),
        )
        calendar = self.client.get(
            f"/api/reservations/calendar?commonAreaId={self.area.id}&year={today.year}&month={today.month}",
            headers=self.headers(self.resident),
        )

        self.assertEqual((availability.status_code, calendar.status_code), (404, 404))

    def test_a_zone_with_upcoming_reservations_cannot_be_retired(self):
        for status in ("pendiente", "aprobada", "activa"):
            with self.subTest(status=status):
                reservation = self.stored(3, status)

                response = self.retire_zone(self.area, expected=409)

                self.assertIn("1 reserva próxima", response.get_json()["error"])
                self.assertIsNone(self.zone(self.area).retired_at)
                db.session.delete(reservation)
                db.session.commit()

    def test_cancelled_rejected_past_and_archived_reservations_do_not_block_the_retirement(self):
        self.stored(3, "cancelada")
        self.stored(4, "rechazada", slot="12:00-14:00")
        self.stored(-2, "aprobada", slot="14:00-16:00")
        archived = self.stored(5, "aprobada", slot="16:00-18:00")
        archived.is_archived = True
        db.session.commit()

        self.retire_zone(self.area)

    def test_the_old_reservations_of_a_retired_zone_still_show_its_name(self):
        old = self.stored(-5, "aprobada")
        self.retire_zone(self.area)

        response = self.client.get("/api/reservations", headers=self.headers(self.resident))

        names = {item["id"]: item["commonAreaName"] for item in response.get_json()["reservations"]}
        self.assertEqual(names[old.id], "Salón social")

    def test_a_retired_zone_is_not_changed_closed_or_opened(self):
        self.retire_zone(self.area)

        edit = self.client.put(
            f"/api/common-areas/{self.area.id}/rules", headers=self.headers(self.admin), json={"capacity": 9}
        )
        self.close_zone(self.area, expected=409)
        self.open_zone(self.area, expected=409)
        self.retire_zone(self.area, expected=409)

        self.assertEqual(edit.status_code, 409)

    def test_the_name_of_a_retired_zone_can_be_used_again(self):
        self.retire_zone(self.area)

        again = self.create_zone(name="Salón social").get_json()["area"]

        self.assertNotEqual(again["id"], self.area.id)
        self.assertIn("Salón social", self.listed())

    def test_only_administration_retires_zones(self):
        for user in (self.resident, self.guard):
            with self.subTest(role=user.role):
                self.retire_zone(self.area, expected=403, user=user)
        self.assertIsNone(self.zone(self.area).retired_at)

    def test_an_unknown_zone_is_not_found(self):
        response = self.client.delete("/api/common-areas/9999", headers=self.headers(self.admin))

        self.assertEqual(response.status_code, 404)

    def test_a_closed_zone_can_be_retired_once_it_has_no_reservations(self):
        self.close_zone(self.area)

        self.retire_zone(self.area)

        self.assertIsNotNone(self.zone(self.area).retired_at)
        self.assertIsNotNone(self.zone(self.area).closed_at)


class UpcomingReservationsCountTests(ZoneManagementTestCase):
    def test_the_administration_sees_how_many_upcoming_reservations_each_zone_has(self):
        self.stored(3, "aprobada")
        self.stored(4, "pendiente", slot="12:00-14:00", resident=self.other_resident)
        self.stored(5, "cancelada")
        gym = CommonArea(name="Gimnasio")
        db.session.add(gym)
        db.session.commit()

        seen = self.listed(self.admin)

        self.assertEqual(seen["Salón social"]["upcomingReservations"], 2)
        self.assertEqual(seen["Gimnasio"]["upcomingReservations"], 0)

    def test_residents_and_guards_do_not_get_the_counts(self):
        self.stored(3, "aprobada")

        for user in (self.resident, self.guard):
            with self.subTest(role=user.role):
                self.assertNotIn("upcomingReservations", self.listed(user)["Salón social"])


if __name__ == "__main__":
    unittest.main()
