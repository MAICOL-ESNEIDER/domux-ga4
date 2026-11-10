"""Pruebas de la portería vehicular (HU-035 a HU-041, RN-013, RN-014 y RN-015).

Cubren los vehículos de visitantes con su parqueadero (entrada, salida, ocupación
y tiempo máximo), la protección contra la doble asignación y los vehículos de
residentes con entrada y salida de un toque.
"""

import os
import unittest
from datetime import timedelta
from unittest.mock import patch

import env_setup  # noqa: F401  (va antes de importar la app)

from app import create_app
from auth import generate_token
from extensions import db
from models import (
    Notification,
    ParkingSpot,
    User,
    Vehicle,
    VehicleMovement,
    Visit,
    VisitorVehicleEntry,
)
from services import vehicle_service
from structure_fixtures import apartment_for, parking_spot
from time_utils import utc_now
from werkzeug.security import generate_password_hash


class VehicleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.apartment = apartment_for("Torre 1 · Apto 101")
        self.other_apartment = apartment_for("Torre 2 · Apto 202")
        self.admin = self.user("Admin", "admin", "ADMIN")
        self.guard = self.user("Guardia", "guard", "GUARD")
        self.other_guard = self.user("Guardia Dos", "guard2", "GUARD")
        self.resident = self.user("Residente", "resident", "RESIDENT", self.apartment)
        self.other_resident = self.user("Vecino", "other", "RESIDENT", self.other_apartment)
        db.session.add_all([self.admin, self.guard, self.other_guard, self.resident, self.other_resident])
        self.spot1 = parking_spot("V-01", kind="visitante", location="Entrada")
        self.spot2 = parking_spot("V-02", kind="visitante", location="Entrada")
        self.resident_spot = parking_spot("P-101", kind="residente", apartment=self.apartment)
        db.session.add(Vehicle(
            unit_id=self.apartment.unit.id, plate="ABC123", vehicle_type="carro",
            make_model="Mazda 3", year=2020, registered_owner="Residente Prueba", color="Rojo",
        ))
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def user(self, name, key, role, apartment=None):
        return User(
            name=name, email=f"{key}@vehicles.test", role=role, is_active=True,
            password_hash=generate_password_hash("Prueba123*"), apartment_ref=apartment,
        )

    def auth(self, user):
        return {"Authorization": f"Bearer {generate_token(user)}"}

    def make_visit(self, resident=None, status="aprobada", inside=True, name="Visita de prueba"):
        visit = Visit(
            resident_id=(resident or self.resident).id, registered_by=self.guard.id,
            visitor_name=name, type="visitante", approval_status=status,
            authorization_method="app",
            entered_at=utc_now() if inside and status == "aprobada" else None,
        )
        db.session.add(visit)
        db.session.commit()
        return visit

    def enter(self, plate="XYZ789", visit=None, guard=None, **extra):
        body = {"plate": plate, "visitId": (visit or self.make_visit()).id}
        body.update(extra)
        return self.client.post(
            "/api/vehicle-entries", headers=self.auth(guard or self.guard), json=body
        )

    def leave(self, entry_id, guard=None):
        return self.client.put(
            f"/api/vehicle-entries/{entry_id}/exit", headers=self.auth(guard or self.guard)
        )

    def board(self, user=None):
        return self.client.get("/api/parking/visitor-spots", headers=self.auth(user or self.guard))

    def spot(self, spot):
        return db.session.get(ParkingSpot, spot.id)

    # --- Entrada y parqueadero sugerido (HU-035 y HU-036) -------------------

    def test_entry_normalizes_plate_and_assigns_the_suggested_spot(self):
        response = self.enter(plate="xyz-789")

        self.assertEqual(response.status_code, 201)
        entry = response.get_json()["vehicleEntry"]
        self.assertEqual(entry["plate"], "XYZ789")
        self.assertEqual(entry["spotCode"], "V-01")
        self.assertEqual(entry["apartment"], "Torre 1 · Apto 101")
        self.assertTrue(entry["isInside"])
        self.assertIsNotNone(entry["enteredAt"])
        self.assertEqual(entry["registeredByName"], "Guardia")
        self.assertTrue(self.spot(self.spot1).occupied)
        self.assertFalse(self.spot(self.spot2).occupied)

    def test_guard_can_choose_another_free_spot(self):
        response = self.enter(spotId=self.spot2.id)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["vehicleEntry"]["spotCode"], "V-02")
        self.assertTrue(self.spot(self.spot2).occupied)
        self.assertFalse(self.spot(self.spot1).occupied)

    def test_the_next_vehicle_gets_the_next_free_spot(self):
        self.enter(plate="XYZ789")
        second = self.enter(plate="JKL456")

        self.assertEqual(second.get_json()["vehicleEntry"]["spotCode"], "V-02")

    def test_entry_needs_a_valid_plate_and_visit(self):
        visit = self.make_visit()
        headers = self.auth(self.guard)
        cases = {
            "sin placa": {"visitId": visit.id},
            "placa inválida": {"plate": "12-ABC", "visitId": visit.id},
            "placa que no es texto": {"plate": 123, "visitId": visit.id},
            "sin visita": {"plate": "XYZ789"},
            "visita que no es número": {"plate": "XYZ789", "visitId": "uno"},
            "parqueadero que no es número": {"plate": "XYZ789", "visitId": visit.id, "spotId": "V-01"},
            "marca withoutSpot inválida": {"plate": "XYZ789", "visitId": visit.id, "withoutSpot": "si"},
        }
        for case, body in cases.items():
            with self.subTest(case=case):
                self.assertEqual(
                    self.client.post("/api/vehicle-entries", headers=headers, json=body).status_code, 400
                )
        self.assertEqual(VisitorVehicleEntry.query.count(), 0)
        self.assertFalse(self.spot(self.spot1).occupied)

    def test_entry_is_refused_without_an_authorized_visit(self):
        # CA-HU-035-02: sin visita autorizada no se registra la entrada (RN-010).
        pending = self.make_visit(status="pendiente")
        rejected = self.make_visit(status="rechazada")
        outside = self.make_visit()
        outside.exited_at = utc_now()
        db.session.commit()

        for visit in (pending, rejected, outside):
            with self.subTest(status=visit.approval_status, exited=visit.exited_at is not None):
                self.assertEqual(self.enter(visit=visit).status_code, 409)
        missing = self.client.post(
            "/api/vehicle-entries", headers=self.auth(self.guard),
            json={"plate": "XYZ789", "visitId": 9999},
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(VisitorVehicleEntry.query.count(), 0)

    def test_a_visit_that_has_not_entered_yet_can_bring_its_vehicle(self):
        approved = self.make_visit(inside=False)

        self.assertEqual(self.enter(visit=approved).status_code, 201)

    def test_one_visit_can_bring_two_vehicles_but_a_plate_cannot_be_inside_twice(self):
        visit = self.make_visit()
        self.assertEqual(self.enter(plate="XYZ789", visit=visit).status_code, 201)
        self.assertEqual(self.enter(plate="JKL456", visit=visit).status_code, 201)

        again = self.enter(plate="xyz789")
        self.assertEqual(again.status_code, 409)
        self.assertIn("XYZ789", again.get_json()["error"])
        self.assertEqual(VisitorVehicleEntry.query.count(), 2)

    def test_only_a_guard_registers_entries_and_exits(self):
        entry_id = self.enter().get_json()["vehicleEntry"]["id"]
        for user in (self.admin, self.resident):
            with self.subTest(role=user.role):
                visit = self.make_visit()
                denied = self.client.post(
                    "/api/vehicle-entries", headers=self.auth(user),
                    json={"plate": "JKL456", "visitId": visit.id},
                )
                self.assertEqual(denied.status_code, 403)
                self.assertEqual(self.leave(entry_id, guard=user).status_code, 403)
        self.assertEqual(
            self.client.post("/api/vehicle-entries", json={"plate": "JKL456"}).status_code, 401
        )

    # --- Parqueadero ocupado y sin parqueaderos libres (HU-039) -------------

    def test_a_taken_spot_is_rejected_and_another_free_one_is_suggested(self):
        # ESC-HU-036-02: otro guardia acaba de ocupar el parqueadero que se eligió.
        self.enter(plate="XYZ789", spotId=self.spot1.id)

        response = self.enter(plate="JKL456", guard=self.other_guard, spotId=self.spot1.id)

        self.assertEqual(response.status_code, 409)
        body = response.get_json()
        self.assertIn("V-01", body["error"])
        self.assertEqual(body["suggestedSpot"]["code"], "V-02")
        self.assertFalse(body["noFreeSpots"])
        self.assertEqual(VisitorVehicleEntry.query.count(), 1)

    def test_the_spot_suggested_for_a_rejected_choice_is_never_the_rejected_one(self):
        self.enter(plate="XYZ789", spotId=self.spot2.id)

        body = self.enter(plate="JKL456", spotId=self.spot2.id).get_json()

        self.assertEqual(body["suggestedSpot"]["code"], "V-01")

    def test_without_free_spots_the_guard_is_told_and_may_register_without_spot(self):
        # ESC-HU-036-03: todos ocupados; el vehículo queda sin parqueadero solo si el guardia lo decide.
        self.enter(plate="XYZ789")
        self.enter(plate="JKL456")
        visit = self.make_visit()

        informed = self.enter(plate="MNO12P", visit=visit)
        self.assertEqual(informed.status_code, 409)
        self.assertTrue(informed.get_json()["noFreeSpots"])
        self.assertIsNone(informed.get_json()["suggestedSpot"])
        self.assertEqual(VisitorVehicleEntry.query.count(), 2)

        taken = self.enter(plate="MNO12P", visit=visit, spotId=self.spot1.id)
        self.assertEqual(taken.status_code, 409)
        self.assertTrue(taken.get_json()["noFreeSpots"])

        registered = self.enter(plate="MNO12P", visit=visit, withoutSpot=True)
        self.assertEqual(registered.status_code, 201)
        self.assertIsNone(registered.get_json()["vehicleEntry"]["spotId"])
        self.assertIn("sin parqueadero", registered.get_json()["message"])
        self.assertEqual(len(self.board().get_json()["withoutSpot"]), 1)

    def test_a_spot_and_withoutspot_together_are_contradictory(self):
        response = self.enter(spotId=self.spot1.id, withoutSpot=True)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.spot(self.spot1).occupied)

    def test_only_visitor_spots_that_exist_can_be_chosen(self):
        retired = parking_spot("V-09", kind="visitante")
        retired.retired_at = utc_now()
        db.session.commit()

        self.assertEqual(self.enter(spotId=self.resident_spot.id).status_code, 400)
        self.assertEqual(self.enter(spotId=retired.id).status_code, 404)
        self.assertEqual(self.enter(spotId=9999).status_code, 404)
        self.assertEqual(VisitorVehicleEntry.query.count(), 0)

    def test_the_spot_is_claimed_with_a_single_conditional_update(self):
        # Dos guardias a la vez: la base deja pasar a uno solo (RN-013).
        self.assertTrue(vehicle_service._set_occupied(self.spot1.id, True))
        self.assertFalse(vehicle_service._set_occupied(self.spot1.id, True))
        self.assertTrue(vehicle_service._set_occupied(self.spot1.id, False))
        self.assertFalse(vehicle_service._set_occupied(self.spot1.id, False))

    def test_auto_assignment_skips_a_spot_lost_in_a_race(self):
        real = vehicle_service._set_occupied
        calls = []

        def lose_the_first_race(spot_id, occupied):
            calls.append(spot_id)
            return False if len(calls) == 1 else real(spot_id, occupied)

        with patch.object(vehicle_service, "_set_occupied", side_effect=lose_the_first_race):
            response = self.enter()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["vehicleEntry"]["spotCode"], "V-02")

    def test_the_database_refuses_two_open_entries_for_the_same_spot_or_plate(self):
        # La última defensa: aunque el código fallara, los índices únicos lo impiden.
        first = self.enter().get_json()["vehicleEntry"]
        visit = self.make_visit()
        for plate, spot_id in (("JKL456", first["spotId"]), ("XYZ789", self.spot2.id)):
            with self.subTest(plate=plate, spot=spot_id):
                db.session.add(VisitorVehicleEntry(
                    plate=plate, visit_id=visit.id, spot_id=spot_id, registered_by=self.guard.id,
                ))
                with self.assertRaises(Exception):
                    db.session.commit()
                db.session.rollback()
        self.assertEqual(VisitorVehicleEntry.query.count(), 1)

    def test_a_lost_race_at_save_time_rolls_back_and_explains(self):
        # Simula que otro guardia ocupó el mismo parqueadero entre la comprobación y el guardado.
        self.enter(plate="XYZ789", spotId=self.spot1.id)
        visit = self.make_visit()

        def pretend_the_spot_was_free(spot_id, occupied):
            return True

        with patch.object(vehicle_service, "_set_occupied", side_effect=pretend_the_spot_was_free):
            response = self.enter(plate="JKL456", visit=visit, spotId=self.spot1.id)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["suggestedSpot"]["code"], "V-02")
        self.assertEqual(VisitorVehicleEntry.query.count(), 1)

    # --- Salida y parqueadero liberado (HU-038, RN-014) ---------------------

    def test_exit_frees_the_spot_immediately_and_it_can_be_reused(self):
        entry = self.enter().get_json()["vehicleEntry"]

        left = self.leave(entry["id"])

        self.assertEqual(left.status_code, 200)
        body = left.get_json()["vehicleEntry"]
        self.assertFalse(body["isInside"])
        self.assertIsNotNone(body["exitedAt"])
        self.assertEqual(body["exitedByName"], "Guardia")
        self.assertIn("V-01", left.get_json()["message"])
        self.assertFalse(self.spot(self.spot1).occupied)
        self.assertEqual(self.enter(plate="JKL456").get_json()["vehicleEntry"]["spotCode"], "V-01")

    def test_the_same_plate_can_come_back_after_leaving(self):
        first = self.enter().get_json()["vehicleEntry"]
        self.leave(first["id"])

        second = self.enter()

        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(second.get_json()["vehicleEntry"]["id"], first["id"])
        self.assertEqual(VisitorVehicleEntry.query.filter_by(plate="XYZ789").count(), 2)

    def test_leaving_twice_or_an_unknown_entry_is_refused(self):
        entry = self.enter().get_json()["vehicleEntry"]
        self.leave(entry["id"])

        self.assertEqual(self.leave(entry["id"]).status_code, 409)
        self.assertEqual(self.leave(9999).status_code, 404)

    def test_a_double_exit_does_not_free_a_spot_assigned_to_someone_else(self):
        first = self.enter(plate="XYZ789").get_json()["vehicleEntry"]
        stale = db.session.get(VisitorVehicleEntry, first["id"])
        self.leave(first["id"])
        self.enter(plate="JKL456")  # toma V-01 otra vez
        self.assertTrue(self.spot(self.spot1).occupied)

        # Un segundo guardia llega con la entrada que ya leyó como abierta.
        with self.assertRaises(Exception) as caught:
            vehicle_service.register_visitor_exit(stale, self.other_guard)

        self.assertEqual(getattr(caught.exception, "status", None), 409)
        self.assertTrue(self.spot(self.spot1).occupied)

    def test_exit_without_spot_has_nothing_to_free(self):
        self.enter(plate="XYZ789")
        self.enter(plate="JKL456")
        entry = self.enter(plate="MNO12P", withoutSpot=True).get_json()["vehicleEntry"]

        left = self.leave(entry["id"])

        self.assertEqual(left.status_code, 200)
        self.assertNotIn("quedó libre", left.get_json()["message"])
        self.assertTrue(self.spot(self.spot1).occupied and self.spot(self.spot2).occupied)

    # --- Vista de ocupación (HU-037) ----------------------------------------

    def test_board_lists_visitor_spots_with_who_occupies_them(self):
        self.enter(plate="XYZ789")

        body = self.board().get_json()

        self.assertEqual([spot["code"] for spot in body["spots"]], ["V-01", "V-02"])
        self.assertEqual((body["total"], body["free"], body["occupied"]), (2, 1, 1))
        self.assertEqual(body["suggestedSpotId"], self.spot2.id)
        occupied, free = body["spots"]
        self.assertTrue(occupied["isOccupied"])
        self.assertEqual(occupied["entry"]["plate"], "XYZ789")
        self.assertEqual(occupied["entry"]["apartment"], "Torre 1 · Apto 101")
        self.assertIn("parkedMinutes", occupied["entry"])
        self.assertFalse(free["isOccupied"])
        self.assertIsNone(free["entry"])
        self.assertEqual(body["maxDays"], 3)
        self.assertEqual(body["overdue"], 0)

    def test_board_ignores_resident_and_retired_spots_and_has_no_suggestion_when_full(self):
        retired = parking_spot("V-03", kind="visitante")
        retired.retired_at = utc_now()
        db.session.commit()
        self.enter(plate="XYZ789")
        self.enter(plate="JKL456")

        body = self.board().get_json()

        self.assertEqual([spot["code"] for spot in body["spots"]], ["V-01", "V-02"])
        self.assertEqual(body["free"], 0)
        self.assertIsNone(body["suggestedSpotId"])

    def test_board_is_for_the_guard_and_the_admin_only(self):
        self.assertEqual(self.board(self.admin).status_code, 200)
        self.assertEqual(self.board(self.guard).status_code, 200)
        self.assertEqual(self.board(self.resident).status_code, 403)
        self.assertEqual(self.client.get("/api/parking/visitor-spots").status_code, 401)

    # --- Tiempo máximo de parqueo (HU-041, RN-015) --------------------------

    def age_entry(self, entry_id, days):
        db.session.get(VisitorVehicleEntry, entry_id).entered_at = utc_now() - timedelta(days=days)
        db.session.commit()

    def test_a_vehicle_past_the_maximum_time_alerts_every_guard_once(self):
        entry = self.enter().get_json()["vehicleEntry"]
        self.age_entry(entry["id"], days=4)

        first = self.client.get("/api/notifications", headers=self.auth(self.guard))
        second = self.client.get("/api/notifications", headers=self.auth(self.guard))

        alerts = [item for item in first.get_json()["notifications"] if item["type"] == "vehicle"]
        self.assertEqual(len(alerts), 1)
        self.assertIn("XYZ789", alerts[0]["message"])
        self.assertIn("V-01", alerts[0]["message"])
        self.assertIn("3 días", alerts[0]["message"])
        self.assertEqual(second.get_json()["notifications"], first.get_json()["notifications"])
        self.assertEqual(Notification.query.filter_by(type="vehicle").count(), 2)
        for guard in (self.guard, self.other_guard):
            self.assertEqual(Notification.query.filter_by(type="vehicle", user_id=guard.id).count(), 1)
        for other in (self.admin, self.resident):
            self.assertEqual(Notification.query.filter_by(type="vehicle", user_id=other.id).count(), 0)

    def test_a_vehicle_inside_the_maximum_time_does_not_alert(self):
        entry = self.enter().get_json()["vehicleEntry"]
        self.age_entry(entry["id"], days=2)

        self.client.get("/api/notifications", headers=self.auth(self.guard))

        self.assertEqual(Notification.query.filter_by(type="vehicle").count(), 0)
        self.assertFalse(self.board().get_json()["spots"][0]["entry"]["isOverdue"])

    def test_a_vehicle_that_already_left_does_not_alert(self):
        entry = self.enter().get_json()["vehicleEntry"]
        self.age_entry(entry["id"], days=5)
        self.leave(entry["id"])

        self.client.get("/api/notifications", headers=self.auth(self.guard))

        self.assertEqual(Notification.query.filter_by(type="vehicle").count(), 0)

    def test_the_board_and_the_list_flag_overdue_vehicles(self):
        late = self.enter(plate="XYZ789").get_json()["vehicleEntry"]
        self.enter(plate="JKL456")
        self.age_entry(late["id"], days=4)

        board = self.board().get_json()
        listed = self.client.get(
            "/api/vehicle-entries?overdue=true", headers=self.auth(self.guard)
        ).get_json()

        self.assertEqual(board["overdue"], 1)
        self.assertTrue(board["spots"][0]["entry"]["isOverdue"])
        self.assertFalse(board["spots"][1]["entry"]["isOverdue"])
        self.assertEqual([item["plate"] for item in listed["vehicleEntries"]], ["XYZ789"])
        self.assertEqual(Notification.query.filter_by(type="vehicle").count(), 2)

    def test_the_unit_can_change_the_maximum_time(self):
        entry = self.enter().get_json()["vehicleEntry"]
        self.age_entry(entry["id"], days=4)

        with patch.dict(os.environ, {"VISITOR_PARKING_MAX_DAYS": "5"}):
            listed = self.client.get(
                "/api/vehicle-entries?overdue=true", headers=self.auth(self.guard)
            ).get_json()
            max_days = self.board().get_json()["maxDays"]
        self.assertEqual((listed["vehicleEntries"], max_days), ([], 5))
        self.assertEqual(Notification.query.filter_by(type="vehicle").count(), 0)

        with patch.dict(os.environ, {"VISITOR_PARKING_MAX_DAYS": "1"}):
            alert = self.client.get("/api/notifications", headers=self.auth(self.guard))
        message = [i for i in alert.get_json()["notifications"] if i["type"] == "vehicle"][0]["message"]
        self.assertIn("El máximo es 1 día.", message)

    def test_an_invalid_maximum_time_falls_back_to_three_days(self):
        for value in ("", "abc", "0", "-2", "1.5"):
            with self.subTest(value=value), patch.dict(os.environ, {"VISITOR_PARKING_MAX_DAYS": value}):
                self.assertEqual(self.board().get_json()["maxDays"], 3)

    def test_alerts_wait_if_there_is_no_active_guard(self):
        entry = self.enter().get_json()["vehicleEntry"]
        self.age_entry(entry["id"], days=4)
        for guard in (self.guard, self.other_guard):
            guard.is_active = False
        db.session.commit()

        self.client.get("/api/notifications", headers=self.auth(self.admin))

        self.assertEqual(Notification.query.filter_by(type="vehicle").count(), 0)
        self.assertIsNone(db.session.get(VisitorVehicleEntry, entry["id"]).overdue_alerted_at)

    # --- Historial (HU-041) -------------------------------------------------

    def test_history_filters_by_state_plate_and_apartment_and_paginates(self):
        gone = self.enter(plate="XYZ789").get_json()["vehicleEntry"]
        self.leave(gone["id"])
        self.enter(plate="JKL456", visit=self.make_visit(resident=self.other_resident))
        self.enter(plate="MNO12P")
        headers = self.auth(self.admin)

        def plates(query):
            body = self.client.get(f"/api/vehicle-entries?{query}", headers=headers).get_json()
            return [item["plate"] for item in body["vehicleEntries"]]

        self.assertEqual(plates(""), ["MNO12P", "JKL456", "XYZ789"])
        self.assertEqual(plates("inside=true"), ["MNO12P", "JKL456"])
        self.assertEqual(plates("inside=false"), ["XYZ789"])
        self.assertEqual(plates("plate=jkl"), ["JKL456"])
        self.assertEqual(plates("plate=-45"), ["JKL456"])
        self.assertEqual(plates(f"apartmentId={self.other_apartment.id}"), ["JKL456"])
        self.assertEqual(plates("overdue=false"), ["MNO12P", "JKL456", "XYZ789"])
        paged = self.client.get(
            "/api/vehicle-entries?pageSize=2&page=2", headers=headers
        ).get_json()
        self.assertEqual([item["plate"] for item in paged["vehicleEntries"]], ["XYZ789"])
        self.assertEqual((paged["total"], paged["totalPages"]), (3, 2))

    def test_history_rejects_invalid_filters_and_other_roles(self):
        headers = self.auth(self.guard)
        for query in ("inside=quizas", "overdue=tal vez", "apartmentId=uno", "pageSize=0", "page=0"):
            with self.subTest(query=query):
                self.assertEqual(
                    self.client.get(f"/api/vehicle-entries?{query}", headers=headers).status_code, 400
                )
        self.assertEqual(
            self.client.get("/api/vehicle-entries", headers=self.auth(self.resident)).status_code, 403
        )

    def test_percent_and_underscore_in_a_plate_filter_are_not_wildcards(self):
        self.enter(plate="XYZ789")

        body = self.client.get("/api/vehicle-entries?plate=%25", headers=self.auth(self.guard)).get_json()

        self.assertEqual(body["vehicleEntries"], [])

    # --- Vehículos de residentes (HU-040) -----------------------------------

    def movement(self, plate, kind, user=None):
        return self.client.post(
            f"/api/resident-vehicles/{plate}/movements",
            headers=self.auth(user or self.guard), json={"type": kind},
        )

    def search(self, text, user=None):
        return self.client.get(
            f"/api/resident-vehicles?search={text}", headers=self.auth(user or self.guard)
        )

    def test_guard_finds_a_resident_vehicle_by_part_of_its_plate(self):
        for text in ("abc123", "ABC", "bc1", "123", "ab-c"):
            with self.subTest(text=text):
                found = self.search(text).get_json()["vehicles"]
                self.assertEqual(len(found), 1)
        vehicle = self.search("ABC").get_json()["vehicles"][0]
        self.assertEqual(vehicle["plate"], "ABC123")
        self.assertEqual(vehicle["apartment"], "Torre 1 · Apto 101")
        self.assertEqual(vehicle["registeredOwner"], "Residente Prueba")
        self.assertFalse(vehicle["isInside"])
        self.assertIsNone(vehicle["lastMovementType"])
        self.assertEqual(self.search("ZZZ").get_json()["vehicles"], [])

    def test_search_needs_at_least_two_characters_and_ignores_retired_vehicles(self):
        self.assertEqual(self.search("A").status_code, 400)
        self.assertEqual(self.client.get(
            "/api/resident-vehicles", headers=self.auth(self.guard)).status_code, 400)
        Vehicle.query.filter_by(plate="ABC123").one().retired_at = utc_now()
        db.session.commit()

        self.assertEqual(self.search("ABC").get_json()["vehicles"], [])
        self.assertEqual(self.movement("ABC123", "entrada").status_code, 404)

    def test_one_tap_entry_and_exit_use_the_server_time_and_track_the_state(self):
        entered = self.movement("ABC123", "entrada")

        self.assertEqual(entered.status_code, 201)
        body = entered.get_json()
        self.assertEqual(body["movement"]["type"], "entrada")
        self.assertEqual(body["movement"]["registeredByName"], "Guardia")
        self.assertIsNotNone(body["movement"]["createdAt"])
        self.assertTrue(body["vehicle"]["isInside"])
        self.assertNotIn("warning", body)
        self.assertTrue(self.search("ABC").get_json()["vehicles"][0]["isInside"])

        left = self.movement("abc-123", "salida")

        self.assertEqual(left.status_code, 201)
        self.assertFalse(left.get_json()["vehicle"]["isInside"])
        self.assertFalse(self.search("ABC").get_json()["vehicles"][0]["isInside"])
        self.assertEqual(VehicleMovement.query.count(), 2)

    def test_a_repeated_movement_is_saved_with_a_warning_so_the_gate_is_not_blocked(self):
        self.movement("ABC123", "entrada")

        repeated = self.movement("ABC123", "entrada")

        self.assertEqual(repeated.status_code, 201)
        self.assertIn("ya tenía registrada una entrada", repeated.get_json()["warning"])
        self.assertEqual(VehicleMovement.query.count(), 2)

    def test_an_exit_without_a_previous_entry_is_saved_with_a_warning(self):
        response = self.movement("ABC123", "salida")

        self.assertEqual(response.status_code, 201)
        self.assertIn("no tenía una entrada", response.get_json()["warning"])

    def test_movement_rejects_bad_data_and_unknown_vehicles(self):
        self.assertEqual(self.movement("ABC123", "paso").status_code, 400)
        self.assertEqual(self.movement("ABC123", None).status_code, 400)
        self.assertEqual(self.movement("12", "entrada").status_code, 400)
        self.assertEqual(self.movement("ZZZ999", "entrada").status_code, 404)
        self.assertEqual(VehicleMovement.query.count(), 0)

    def test_resident_vehicles_are_for_the_guard_and_the_admin_only(self):
        self.assertEqual(self.search("ABC", user=self.admin).status_code, 200)
        self.assertEqual(self.search("ABC", user=self.resident).status_code, 403)
        self.assertEqual(self.movement("ABC123", "entrada", user=self.admin).status_code, 403)
        self.assertEqual(self.movement("ABC123", "entrada", user=self.resident).status_code, 403)
        self.assertEqual(self.client.get("/api/resident-vehicles?search=ABC").status_code, 401)

    # --- Parqueaderos ocupados en la estructura -----------------------------

    def test_an_occupied_visitor_spot_cannot_be_retired_or_changed_to_resident(self):
        self.enter(spotId=self.spot1.id)
        path = f"/api/admin/parking-spots/{self.spot1.id}"

        retire = self.client.delete(path, headers=self.auth(self.admin))
        change = self.client.put(path, headers=self.auth(self.admin), json={"type": "residente"})
        rename = self.client.put(path, headers=self.auth(self.admin), json={"location": "Portería"})

        self.assertEqual((retire.status_code, change.status_code, rename.status_code), (409, 409, 200))
        self.assertEqual(self.spot(self.spot1).kind, "visitante")
        self.assertIsNone(self.spot(self.spot1).retired_at)


if __name__ == "__main__":
    unittest.main()
