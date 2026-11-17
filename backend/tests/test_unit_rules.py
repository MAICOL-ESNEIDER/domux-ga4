"""Pruebas de las reglas de la unidad que la administración ajusta (DEC-032, RN-015, RN-018 y RN-025).

Plazos de PQRS (general y por tipo), días del aviso amarillo, horas de alerta de los paquetes sin reclamar
y días del parqueadero de visitantes: antes estaban fijos en el código y ahora los cambia la administración.
"""

import json
import os
import unittest
from datetime import timedelta
from unittest.mock import patch

import env_setup  # noqa: F401  (va antes de importar la app)

from extensions import db
from models import AuditLog, PackageItem, Pqrs, UnitSettings, Visit, VisitorVehicleEntry
from services import rules_service
from services.alert_service import alert_overdue_vehicles
from services.pqrs_rules import pqrs_semaphore
from services.unit_rules import UnitRules, current_rules, forget_rules
from test_pqrs import PqrsTestCase
from time_utils import colombia_day_to_utc, colombia_today, utc_now

DEFAULTS = {
    "pqrsTermDays": 15,
    "pqrsWarningDays": 5,
    "pqrsTermsByCategory": {},
    "packageOrangeHours": 48,
    "packageRedHours": 72,
    "visitorParkingMaxDays": 3,
}


class UnitRulesTestCase(PqrsTestCase):
    """Base con un administrador, dos residentes y un guardia, y atajos para leer y guardar las reglas."""

    def read_rules(self, user=None):
        return self.client.get("/api/admin/unit-rules", headers=self.auth(user or self.admin))

    def save_rules(self, body, user=None):
        return self.client.put("/api/admin/unit-rules", json=body, headers=self.auth(user or self.admin))

    def logs(self):
        return AuditLog.query.filter_by(entity_type="unit_settings").order_by(AuditLog.id).all()

    def pqrs_on(self, days_ago, category="Daño", status="abierta"):
        """Una PQRS radicada hace ``days_ago`` días (a las 3 de la tarde de Colombia)."""
        created = colombia_day_to_utc(colombia_today() - timedelta(days=days_ago)) + timedelta(hours=15)
        pqrs = self.make_pqrs(category=category, status=status)
        pqrs.created_at = pqrs.updated_at = created
        db.session.commit()
        return pqrs

    def package_waiting(self, hours):
        package = PackageItem(
            resident_id=self.resident.id, registered_by=self.guard.id, description="Caja",
            status="pendiente", arrived_at=utc_now() - timedelta(hours=hours),
        )
        db.session.add(package)
        db.session.commit()
        return package

    def visitor_vehicle(self, days_inside):
        visit = Visit(
            resident_id=self.resident.id, registered_by=self.guard.id, visitor_name="Visita", type="visitante",
            approval_status="aprobada", authorization_method="app", entered_at=utc_now(),
        )
        db.session.add(visit)
        db.session.flush()
        entry = VisitorVehicleEntry(
            plate="XYZ789", visit_id=visit.id, registered_by=self.guard.id,
            entered_at=utc_now() - timedelta(days=days_inside),
        )
        db.session.add(entry)
        db.session.commit()
        return entry


class ReadingTests(UnitRulesTestCase):
    def test_before_saving_anything_the_rules_are_the_ones_of_domux(self):
        body = self.read_rules().get_json()

        self.assertEqual(body["rules"], DEFAULTS)
        self.assertEqual(body["defaults"], DEFAULTS)
        self.assertFalse(any(body["customized"].values()))
        self.assertEqual(set(body["customized"]), set(DEFAULTS))
        self.assertIsNone(body["updatedAt"])
        self.assertIsNone(body["updatedByName"])
        self.assertIsNone(db.session.get(UnitSettings, UnitSettings.SINGLE_ID))

    def test_everyone_with_a_session_reads_the_current_rules_with_the_unit_info(self):
        self.save_rules({"pqrsTermDays": 20, "pqrsTermsByCategory": {"Daño": 5}})

        for user in (self.admin, self.guard, self.resident):
            body = self.client.get("/api/unit-info", headers=self.auth(user)).get_json()
            self.assertEqual(body["rules"]["pqrsTermDays"], 20)
            self.assertEqual(body["rules"]["pqrsTermsByCategory"], {"Daño": 5})
            self.assertEqual(body["rules"]["packageRedHours"], 72)

    def test_the_rules_are_in_the_unit_info_even_if_nothing_was_saved(self):
        body = self.client.get("/api/unit-info", headers=self.auth(self.resident)).get_json()

        self.assertEqual(body["rules"], DEFAULTS)

    def test_only_the_administrator_reads_or_changes_the_rules_screen(self):
        for user in (self.guard, self.resident):
            self.assertEqual(self.read_rules(user).status_code, 403)
            self.assertEqual(self.save_rules({"pqrsTermDays": 20}, user).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/unit-rules").status_code, 401)
        self.assertEqual(self.client.put("/api/admin/unit-rules", json={"pqrsTermDays": 20}).status_code, 401)
        self.assertIsNone(db.session.get(UnitSettings, UnitSettings.SINGLE_ID))
        self.assertEqual(self.logs(), [])


class SavingTests(UnitRulesTestCase):
    def test_saving_keeps_the_rules_and_says_who_and_which_ones_changed(self):
        response = self.save_rules({"pqrsTermDays": 20, "packageOrangeHours": 24, "packageRedHours": 48})

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["message"], "Reglas de la unidad guardadas")
        self.assertEqual(body["rules"], {**DEFAULTS, "pqrsTermDays": 20, "packageOrangeHours": 24, "packageRedHours": 48})
        self.assertEqual(body["defaults"], DEFAULTS)
        self.assertTrue(body["customized"]["pqrsTermDays"])
        self.assertTrue(body["customized"]["packageRedHours"])
        self.assertFalse(body["customized"]["pqrsWarningDays"])
        self.assertEqual(body["updatedByName"], "Admin")
        self.assertTrue(body["updatedAt"])
        self.assertEqual(self.read_rules().get_json()["rules"], body["rules"])

    def test_what_is_not_sent_stays_as_it_was(self):
        self.save_rules({"pqrsTermDays": 20, "visitorParkingMaxDays": 5})
        self.save_rules({"pqrsWarningDays": 7})

        rules = self.read_rules().get_json()["rules"]
        self.assertEqual((rules["pqrsTermDays"], rules["pqrsWarningDays"], rules["visitorParkingMaxDays"]), (20, 7, 5))

    def test_null_brings_a_rule_back_to_the_value_of_domux(self):
        self.save_rules({"pqrsTermDays": 20, "pqrsWarningDays": 7, "pqrsTermsByCategory": {"Daño": 5}})

        body = self.save_rules({"pqrsTermDays": None, "pqrsTermsByCategory": None}).get_json()

        self.assertEqual(body["rules"]["pqrsTermDays"], 15)
        self.assertEqual(body["rules"]["pqrsTermsByCategory"], {})
        self.assertFalse(body["customized"]["pqrsTermDays"])
        self.assertFalse(body["customized"]["pqrsTermsByCategory"])
        self.assertEqual(body["rules"]["pqrsWarningDays"], 7)

    def test_sending_everything_as_null_the_first_time_creates_nothing(self):
        body = self.save_rules({key: None for key in DEFAULTS}).get_json()

        self.assertEqual(body["rules"], DEFAULTS)
        self.assertIsNone(db.session.get(UnitSettings, UnitSettings.SINGLE_ID))
        self.assertEqual(self.logs(), [])

    def test_a_body_without_any_rule_is_refused(self):
        self.assertEqual(self.save_rules({}).status_code, 400)
        response = self.save_rules({"algoQueNoExiste": 3})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Debes proporcionar al menos una regla para actualizar.")
        self.assertEqual(self.client.put("/api/admin/unit-rules", data="no es json",
                                         headers=self.auth(self.admin)).status_code, 400)

    def test_every_change_is_written_in_the_audit_log_with_before_and_after(self):
        self.save_rules({"pqrsTermDays": 20})
        self.save_rules({"pqrsTermDays": 25, "visitorParkingMaxDays": 2})

        created, updated = self.logs()
        self.assertEqual((created.action, updated.action), ("created", "updated"))
        self.assertEqual(created.actor_id, self.admin.id)
        details = json.loads(updated.details)
        self.assertEqual(details["before"]["pqrsTermDays"], 20)
        self.assertEqual(details["after"]["pqrsTermDays"], 25)
        self.assertEqual(details["before"]["visitorParkingMaxDays"], 3)
        self.assertEqual(details["after"]["visitorParkingMaxDays"], 2)

    def test_saving_the_same_values_again_does_not_touch_the_audit_log(self):
        self.save_rules({"pqrsTermDays": 20, "pqrsTermsByCategory": {"Daño": 5}})
        before = len(self.logs())
        stamp = db.session.get(UnitSettings, UnitSettings.SINGLE_ID).updated_at

        self.assertEqual(self.save_rules({"pqrsTermDays": 20, "pqrsTermsByCategory": {"Daño": 5}}).status_code, 200)

        self.assertEqual(len(self.logs()), before)
        self.assertEqual(db.session.get(UnitSettings, UnitSettings.SINGLE_ID).updated_at, stamp)

    def test_there_is_only_one_row_however_many_times_it_is_saved(self):
        for days in (20, 21, 22):
            self.save_rules({"pqrsTermDays": days})

        self.assertEqual(UnitSettings.query.count(), 1)


class LimitsTests(UnitRulesTestCase):
    def assert_refused(self, body, text):
        response = self.save_rules(body)
        self.assertEqual(response.status_code, 400, body)
        self.assertIn(text, response.get_json()["error"], body)
        self.assertIsNone(db.session.get(UnitSettings, UnitSettings.SINGLE_ID), body)
        self.assertEqual(self.logs(), [], body)

    def test_each_rule_has_a_minimum_and_a_maximum(self):
        for key, low, high, text in (
            ("pqrsTermDays", 1, 90, "El plazo para responder una PQRS"),
            ("pqrsWarningDays", 1, 30, "El aviso amarillo de una PQRS"),
            ("packageOrangeHours", 1, 720, "El aviso naranja de un paquete"),
            ("packageRedHours", 2, 1440, "El aviso rojo de un paquete"),
            ("visitorParkingMaxDays", 1, 30, "El tiempo máximo de un vehículo visitante"),
        ):
            for bad in (low - 1, high + 1):
                with self.subTest(rule=key, value=bad):
                    self.assert_refused({key: bad}, text)

    def test_the_limits_themselves_are_accepted(self):
        for body in (
            {"pqrsTermDays": 1, "pqrsWarningDays": 1},
            {"pqrsTermDays": 90, "pqrsWarningDays": 30},
            {"packageOrangeHours": 1, "packageRedHours": 2},
            {"packageOrangeHours": 720, "packageRedHours": 1440},
            {"visitorParkingMaxDays": 1},
            {"visitorParkingMaxDays": 30},
        ):
            with self.subTest(body=body):
                self.assertEqual(self.save_rules(body).status_code, 200)

    def test_only_whole_numbers_are_accepted(self):
        for bad in ("15", 15.5, 15.0, True, [15], {"a": 1}):
            with self.subTest(value=bad):
                self.assert_refused({"pqrsTermDays": bad}, "debe ser un número entero")

    def test_the_yellow_notice_cannot_be_longer_than_the_general_term(self):
        self.assert_refused({"pqrsTermDays": 4}, "Baja los días del aviso amarillo (máximo 4)")
        self.assert_refused({"pqrsWarningDays": 20}, "el plazo general es de 15")
        self.assertEqual(self.save_rules({"pqrsTermDays": 4, "pqrsWarningDays": 3}).status_code, 200)
        # Con el plazo ya guardado en 4, subir el aviso sin subir el plazo también se rechaza.
        response = self.save_rules({"pqrsWarningDays": 6})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.read_rules().get_json()["rules"]["pqrsWarningDays"], 3)

    def test_the_red_package_notice_must_come_after_the_orange_one(self):
        self.assert_refused({"packageOrangeHours": 80}, "debe llegar después del naranja")
        self.assert_refused({"packageRedHours": 48}, "debe llegar después del naranja")
        self.assert_refused({"packageOrangeHours": 30, "packageRedHours": 30}, "debe llegar después del naranja")
        self.assertEqual(self.save_rules({"packageOrangeHours": 80, "packageRedHours": 100}).status_code, 200)

    def test_a_refused_change_leaves_everything_as_it_was(self):
        self.save_rules({"pqrsTermDays": 20})

        response = self.save_rules({"pqrsTermDays": 25, "visitorParkingMaxDays": 99})

        self.assertEqual(response.status_code, 400)
        rules = self.read_rules().get_json()["rules"]
        self.assertEqual((rules["pqrsTermDays"], rules["visitorParkingMaxDays"]), (20, 3))
        self.assertEqual(len(self.logs()), 1)


class CategoryTermTests(UnitRulesTestCase):
    def test_a_type_of_pqrs_can_have_its_own_term(self):
        body = self.save_rules({"pqrsTermsByCategory": {"Daño": 5, "Sugerencia": 30}}).get_json()

        self.assertEqual(body["rules"]["pqrsTermsByCategory"], {"Daño": 5, "Sugerencia": 30})
        self.assertTrue(body["customized"]["pqrsTermsByCategory"])
        self.assertEqual(body["rules"]["pqrsTermDays"], 15)

    def test_the_list_replaces_the_previous_one_and_an_empty_list_removes_them_all(self):
        self.save_rules({"pqrsTermsByCategory": {"Daño": 5, "Queja": 10}})

        self.assertEqual(
            self.save_rules({"pqrsTermsByCategory": {"Queja": 12}}).get_json()["rules"]["pqrsTermsByCategory"],
            {"Queja": 12},
        )
        body = self.save_rules({"pqrsTermsByCategory": {}}).get_json()
        self.assertEqual(body["rules"]["pqrsTermsByCategory"], {})
        self.assertFalse(body["customized"]["pqrsTermsByCategory"])

    def test_only_the_known_types_are_accepted_and_with_valid_days(self):
        for bad, text in (
            ({"Urgencia": 5}, "«Urgencia» no es un tipo de PQRS"),
            ({"daño": 5}, "«daño» no es un tipo de PQRS"),
            ({"Daño": 0}, "El plazo de «Daño» debe estar entre 1 y 90"),
            ({"Daño": 91}, "El plazo de «Daño» debe estar entre 1 y 90"),
            ({"Daño": "5"}, "El plazo de «Daño» debe ser un número entero"),
            ({"Daño": None}, "El plazo de «Daño» debe ser un número entero"),
            ([["Daño", 5]], "Los plazos por tipo deben ser un objeto"),
            ("Daño", "Los plazos por tipo deben ser un objeto"),
        ):
            with self.subTest(value=bad):
                response = self.save_rules({"pqrsTermsByCategory": bad})
                self.assertEqual(response.status_code, 400)
                self.assertIn(text, response.get_json()["error"])
        self.assertIsNone(db.session.get(UnitSettings, UnitSettings.SINGLE_ID))

    def test_the_known_types_are_the_ones_of_the_app(self):
        listed = "Petición, Queja, Reclamo, Sugerencia y Daño"
        response = self.save_rules({"pqrsTermsByCategory": {"Otra": 5}})

        self.assertIn(listed, response.get_json()["error"])


class EffectOnPqrsTests(UnitRulesTestCase):
    def test_the_general_term_moves_the_due_date_and_the_traffic_light_of_every_open_pqrs(self):
        pqrs = self.pqrs_on(days_ago=7, category="Petición")
        before = pqrs.to_dict()

        self.save_rules({"pqrsTermDays": 30})
        after = pqrs.to_dict()

        self.assertGreater(after["dueDate"], before["dueDate"])
        self.assertGreater(after["daysRemaining"], before["daysRemaining"])
        self.assertEqual(after["semaphore"], "verde")

    def test_a_type_with_its_own_term_uses_it_and_the_others_keep_the_general_one(self):
        damage = self.pqrs_on(days_ago=3, category="Daño")
        petition = self.pqrs_on(days_ago=3, category="Petición")
        self.assertEqual(damage.to_dict()["dueDate"], petition.to_dict()["dueDate"])

        self.save_rules({"pqrsTermsByCategory": {"Daño": 5}})

        self.assertLess(damage.to_dict()["dueDate"], petition.to_dict()["dueDate"])
        self.assertEqual(damage.to_dict()["semaphore"], "amarillo")
        self.assertEqual(petition.to_dict()["semaphore"], "verde")

    def test_a_pqrs_past_its_new_term_turns_red(self):
        recent = self.pqrs_on(days_ago=10, category="Daño")
        self.assertEqual(recent.to_dict()["semaphore"], "verde")

        self.save_rules({"pqrsTermsByCategory": {"Daño": 3}})

        self.assertEqual(recent.to_dict()["semaphore"], "rojo")
        self.assertLess(recent.to_dict()["daysRemaining"], 0)

    def test_the_days_of_the_yellow_notice_decide_when_the_light_changes(self):
        pqrs = self.pqrs_on(days_ago=12, category="Petición")
        remaining = pqrs.to_dict()["daysRemaining"]
        self.assertGreaterEqual(remaining, 2)

        self.save_rules({"pqrsWarningDays": remaining - 1})
        self.assertEqual(pqrs.to_dict()["semaphore"], "verde")
        self.save_rules({"pqrsWarningDays": remaining})
        self.assertEqual(pqrs.to_dict()["semaphore"], "amarillo")

    def test_the_list_the_inbox_and_the_summary_all_count_with_the_same_term(self):
        self.pqrs_on(days_ago=10, category="Daño")
        self.save_rules({"pqrsTermsByCategory": {"Daño": 3}})

        listed = self.client.get("/api/pqrs", headers=self.auth(self.resident)).get_json()["pqrs"][0]
        light = self.client.get(
            "/api/pqrs", headers=self.auth(self.admin), query_string={"view": "summary"},
        ).get_json()["pqrs"][0]
        panel = self.client.get("/api/admin/summary", headers=self.auth(self.admin)).get_json()

        self.assertEqual(listed["semaphore"], "rojo")
        self.assertEqual(light["semaphore"], "rojo")
        self.assertEqual(panel["urgentPqrs"][0]["semaphore"], "rojo")
        self.assertEqual(panel["counts"]["pqrsOverdue"], 1)

    def test_the_filter_by_traffic_light_follows_the_new_rules(self):
        self.pqrs_on(days_ago=10, category="Daño")
        red = lambda: self.client.get(  # noqa: E731
            "/api/pqrs", headers=self.auth(self.admin), query_string={"view": "summary", "semaphore": "rojo"},
        ).get_json()["total"]
        self.assertEqual(red(), 0)

        self.save_rules({"pqrsTermsByCategory": {"Daño": 3}})

        self.assertEqual(red(), 1)

    def test_a_resolved_pqrs_still_has_no_traffic_light(self):
        resolved = self.pqrs_on(days_ago=30, category="Daño", status="resuelta")

        self.save_rules({"pqrsTermDays": 1, "pqrsWarningDays": 1})

        self.assertIsNone(resolved.to_dict()["semaphore"])

    def test_the_pure_function_takes_the_rules_it_is_given_without_asking_the_database(self):
        rules = UnitRules(pqrs_term_days=10, pqrs_warning_days=2, pqrs_terms_by_category={"Daño": 4})
        today = colombia_today()

        with_rules = pqrs_semaphore(today, today, "Daño", rules)
        general = pqrs_semaphore(today, today, "Petición", rules)

        self.assertEqual(with_rules["daysRemaining"], 4)
        self.assertEqual(general["daysRemaining"], 10)
        self.assertEqual(with_rules["color"], "verde")  # 4 > 2 días de aviso


class EffectOnPackagesTests(UnitRulesTestCase):
    def test_a_package_is_orange_and_red_with_the_hours_of_the_unit(self):
        package = self.package_waiting(hours=60)
        self.assertEqual(package.claim_alert(), "naranja")

        self.save_rules({"packageOrangeHours": 72, "packageRedHours": 96})
        self.assertIsNone(package.claim_alert())

        self.save_rules({"packageOrangeHours": 12, "packageRedHours": 24})
        self.assertEqual(package.claim_alert(), "rojo")

    def test_the_lists_carry_the_alert_decided_by_the_unit(self):
        self.package_waiting(hours=30)
        light = lambda: self.client.get(  # noqa: E731
            "/api/packages", headers=self.auth(self.guard), query_string={"view": "summary"},
        ).get_json()["packages"][0]["claimAlert"]
        full = lambda: self.client.get(  # noqa: E731
            "/api/packages", headers=self.auth(self.guard),
        ).get_json()["packages"][0]["claimAlert"]
        self.assertEqual((light(), full()), (None, None))

        self.save_rules({"packageOrangeHours": 24, "packageRedHours": 48})

        self.assertEqual((light(), full()), ("naranja", "naranja"))

    def test_the_summary_for_the_administration_counts_with_the_unit_hours(self):
        self.package_waiting(hours=30)
        self.package_waiting(hours=60)
        counts = lambda: self.client.get(  # noqa: E731
            "/api/admin/summary", headers=self.auth(self.admin),
        ).get_json()["counts"]
        self.assertEqual((counts()["packagesOver48"], counts()["packagesOver72"]), (1, 0))

        self.save_rules({"packageOrangeHours": 24, "packageRedHours": 48})

        now = counts()
        self.assertEqual((now["packagesOver48"], now["packagesOver72"]), (2, 1))

    def test_the_search_describes_the_alert_with_the_unit_hours(self):
        self.package_waiting(hours=60)

        def subtitle():
            found = self.client.get(
                "/api/search", query_string={"q": "Caja", "in": "paquetes"}, headers=self.auth(self.admin),
            ).get_json()
            return found["groups"][0]["items"][0]["subtitle"]

        self.assertIn("Más de 48 h sin reclamar", subtitle())

        self.save_rules({"packageOrangeHours": 24, "packageRedHours": 200})

        self.assertIn("Más de 24 h sin reclamar", subtitle())


class EffectOnParkingTests(UnitRulesTestCase):
    def test_the_visitor_vehicle_deadline_uses_the_days_of_the_unit(self):
        entry = self.visitor_vehicle(days_inside=2)
        self.assertFalse(entry.is_overdue())
        self.assertEqual(entry.deadline() - entry.entered_at, timedelta(days=3))

        self.save_rules({"visitorParkingMaxDays": 1})

        self.assertTrue(entry.is_overdue())
        self.assertEqual(entry.deadline() - entry.entered_at, timedelta(days=1))
        self.assertEqual(entry.to_dict()["maxDays"], 1)

    def test_the_guards_are_alerted_when_a_vehicle_passes_the_days_of_the_unit(self):
        self.visitor_vehicle(days_inside=2)
        self.assertEqual(alert_overdue_vehicles(), 0)
        db.session.rollback()

        self.save_rules({"visitorParkingMaxDays": 1})

        self.assertEqual(alert_overdue_vehicles(), 1)

    def test_the_parking_board_tells_the_maximum_days(self):
        board = lambda: self.client.get(  # noqa: E731
            "/api/parking/visitor-spots", headers=self.auth(self.guard),
        ).get_json()["maxDays"]
        self.assertEqual(board(), 3)

        self.save_rules({"visitorParkingMaxDays": 7})

        self.assertEqual(board(), 7)

    def test_the_environment_variable_is_only_the_default_and_the_saved_value_wins(self):
        with patch.dict(os.environ, {"VISITOR_PARKING_MAX_DAYS": "5"}):
            forget_rules()
            self.assertEqual(current_rules().visitor_parking_max_days, 5)
            self.assertEqual(self.read_rules().get_json()["defaults"]["visitorParkingMaxDays"], 5)

            self.save_rules({"visitorParkingMaxDays": 2})
            self.assertEqual(current_rules().visitor_parking_max_days, 2)

            self.save_rules({"visitorParkingMaxDays": None})
            self.assertEqual(current_rules().visitor_parking_max_days, 5)


class ReadingOncePerRequestTests(UnitRulesTestCase):
    def test_a_change_in_the_row_is_seen_by_the_next_reading_of_the_same_request(self):
        self.assertEqual(current_rules().pqrs_term_days, 15)  # queda guardada para esta solicitud

        rules_service.update_rules({"pqrsTermDays": 40}, self.admin)

        self.assertEqual(current_rules().pqrs_term_days, 40)

    def test_the_rules_are_read_once_even_if_many_pqrs_are_rated(self):
        for _ in range(6):
            self.pqrs_on(days_ago=3)
        statements = []

        from sqlalchemy import event
        forget_rules()
        engine = db.engine

        def count(_connection, _cursor, statement, *_rest):
            if "unit_settings" in statement:
                statements.append(statement)

        event.listen(engine, "before_cursor_execute", count)
        try:
            for item in Pqrs.query.all():
                item.to_dict()
        finally:
            event.remove(engine, "before_cursor_execute", count)

        self.assertEqual(len(statements), 1)


if __name__ == "__main__":
    unittest.main()
