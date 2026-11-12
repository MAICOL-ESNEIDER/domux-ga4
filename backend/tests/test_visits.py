"""Pruebas del historial de visitas, la estadía prevista y los nombres del QR (HU-030 a HU-033).

Cubren los filtros del historial (apartamento, fechas de Colombia, visitas sin
salida), lo que ve cada rol, el aviso «¿Tu visitante sigue en la unidad?» cuando
pasa la estadía prevista (RN-012) y los nombres de los visitantes en el QR.
"""

import unittest
from datetime import date, datetime, timedelta

import env_setup  # noqa: F401  (va antes de importar la app)

from app import create_app
from auth import generate_token
from extensions import db
from models import Notification, User, Visit
from structure_fixtures import apartment_for
from time_utils import utc_now
from werkzeug.security import generate_password_hash


class VisitTests(unittest.TestCase):
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
        self.resident = self.user("Residente", "resident", "RESIDENT", self.apartment)
        self.housemate = self.user("Compañero", "housemate", "RESIDENT", self.apartment)
        self.neighbor = self.user("Vecino", "neighbor", "RESIDENT", self.other_apartment)
        self.homeless = self.user("Sin apartamento", "homeless", "RESIDENT")
        db.session.add_all([
            self.admin, self.guard, self.resident, self.housemate, self.neighbor, self.homeless,
        ])
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def user(self, name, key, role, apartment=None):
        return User(
            name=name, email=f"{key}@visits.test", role=role, is_active=True,
            password_hash=generate_password_hash("Prueba123*"), apartment_ref=apartment,
        )

    def auth(self, user):
        return {"Authorization": f"Bearer {generate_token(user)}"}

    def make_visit(
        self, resident=None, name="Visita", status="aprobada", entered_ago=None, exited=False,
        created_at=None, stay=None,
    ):
        """Crea una visita directo en la base: entered_ago son minutos desde que entró."""
        visit = Visit(
            resident_id=(resident or self.resident).id, registered_by=self.guard.id,
            visitor_name=name, type="visitante", approval_status=status,
            authorization_method="app" if status != "pendiente" else None,
            expected_stay_minutes=stay,
            entered_at=utc_now() - timedelta(minutes=entered_ago) if entered_ago is not None else None,
            exited_at=utc_now() if exited else None,
        )
        if created_at is not None:
            visit.created_at = created_at
        db.session.add(visit)
        db.session.commit()
        return visit

    def history(self, query="", user=None):
        return self.client.get(f"/api/visits?{query}", headers=self.auth(user or self.admin))

    def names(self, query="", user=None):
        response = self.history(query, user)
        self.assertEqual(response.status_code, 200, response.get_json())
        return [visit["visitorName"] for visit in response.get_json()["visits"]]

    def register(self, **fields):
        body = {"residentId": self.resident.id, "visitorName": "Visita nueva", "type": "visitante"}
        body.update(fields)
        return self.client.post("/api/visits", headers=self.auth(self.guard), json=body)

    def enter(self, visit, body=None):
        return self.client.post(
            f"/api/visits/{visit.id}/entry", headers=self.auth(self.guard), json=body
        )

    def alerts(self, user):
        response = self.client.get("/api/notifications", headers=self.auth(user))
        self.assertEqual(response.status_code, 200)
        return [
            item for item in response.get_json()["notifications"]
            if item["title"] == "¿Tu visitante sigue en la unidad?"
        ]

    # --- Estadía prevista (HU-031) ------------------------------------------

    def test_the_guard_can_note_the_expected_stay_when_registering_the_visit(self):
        response = self.register(expectedStayMinutes=120)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["visit"]["expectedStayMinutes"], 120)
        self.assertEqual(Visit.query.one().expected_stay_minutes, 120)

    def test_the_expected_stay_is_optional(self):
        response = self.register()

        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.get_json()["visit"]["expectedStayMinutes"])
        self.assertFalse(response.get_json()["visit"]["isOverstay"])

    def test_an_invalid_expected_stay_is_refused(self):
        for value in (0, -30, 10081, 1.5, "dos horas", True, [60]):
            with self.subTest(value=value):
                self.assertEqual(self.register(expectedStayMinutes=value).status_code, 400)
        self.assertEqual(Visit.query.count(), 0)
        self.assertEqual(self.register(expectedStayMinutes=10080).status_code, 201)

    def test_the_stay_can_also_be_noted_when_the_visitor_enters(self):
        visit = self.make_visit()

        response = self.enter(visit, {"expectedStayMinutes": 90})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["visit"]["expectedStayMinutes"], 90)
        self.assertIsNotNone(response.get_json()["visit"]["enteredAt"])

    def test_entry_still_works_without_a_body_and_keeps_the_stay_already_noted(self):
        visit = self.make_visit(stay=45)

        response = self.client.post(f"/api/visits/{visit.id}/entry", headers=self.auth(self.guard))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["visit"]["expectedStayMinutes"], 45)

    def test_entry_refuses_an_invalid_stay_or_body(self):
        visit = self.make_visit()

        self.assertEqual(self.enter(visit, {"expectedStayMinutes": 0}).status_code, 400)
        self.assertEqual(self.enter(visit, [60]).status_code, 400)
        self.assertIsNone(db.session.get(Visit, visit.id).entered_at)

    def test_a_qr_entry_can_note_the_stay_too(self):
        token = self.make_qr(max_people=2)["token"]

        response = self.client.post(
            f"/api/visits/qr/{token}/entry", headers=self.auth(self.guard),
            json={"visitorName": "Invitado", "expectedStayMinutes": 30},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["visit"]["expectedStayMinutes"], 30)
        bad = self.client.post(
            f"/api/visits/qr/{token}/entry", headers=self.auth(self.guard),
            json={"visitorName": "Otro", "expectedStayMinutes": -1},
        )
        self.assertEqual(bad.status_code, 400)

    def test_the_resident_is_asked_once_when_the_expected_stay_passes(self):
        late = self.make_visit(name="Se pasó", entered_ago=90, stay=60)

        first, second = self.alerts(self.resident), self.alerts(self.resident)

        self.assertEqual(len(first), 1)
        self.assertEqual(first, second)
        self.assertIn("Se pasó", first[0]["message"])
        self.assertIn("1 hora", first[0]["message"])
        self.assertEqual(first[0]["type"], "visit")
        self.assertIsNotNone(db.session.get(Visit, late.id).overstay_alerted_at)
        self.assertEqual(Notification.query.filter_by(title="¿Tu visitante sigue en la unidad?").count(), 1)

    def test_the_alert_is_for_the_resident_of_the_visit_only(self):
        self.make_visit(entered_ago=90, stay=60)

        self.assertEqual(len(self.alerts(self.neighbor)), 0)
        self.assertEqual(len(self.alerts(self.guard)), 0)
        self.assertEqual(len(self.alerts(self.resident)), 1)

    def test_no_alert_inside_the_stay_without_a_stay_or_after_leaving(self):
        self.make_visit(name="Dentro del plazo", entered_ago=30, stay=60)
        self.make_visit(name="Sin estadía", entered_ago=500)
        self.make_visit(name="Ya salió", entered_ago=500, stay=60, exited=True)
        self.make_visit(name="Aún no entra", stay=60)

        self.assertEqual(self.alerts(self.resident), [])
        self.assertEqual(Notification.query.count(), 0)

    def test_no_alert_for_a_deactivated_resident(self):
        self.make_visit(entered_ago=90, stay=60)
        self.resident.is_active = False
        db.session.commit()

        self.client.get("/api/notifications", headers=self.auth(self.guard))

        self.assertEqual(Notification.query.count(), 0)

    def test_a_new_entry_makes_the_alert_pending_again(self):
        visit = self.make_visit(entered_ago=90, stay=60)
        self.assertEqual(len(self.alerts(self.resident)), 1)
        self.client.post(
            f"/api/visits/{visit.id}/exit", headers=self.auth(self.guard), json={"returningToday": True}
        )

        self.assertEqual(self.enter(visit, {"expectedStayMinutes": 30}).status_code, 200)
        self.assertIsNone(db.session.get(Visit, visit.id).overstay_alerted_at)
        db.session.get(Visit, visit.id).entered_at = utc_now() - timedelta(minutes=45)
        db.session.commit()

        self.assertEqual(len(self.alerts(self.resident)), 2)

    def test_stay_text_is_readable(self):
        from services.alert_service import _stay_text

        self.assertEqual(
            [_stay_text(m) for m in (1, 45, 60, 90, 120, 150, 1440)],
            ["1 minuto", "45 minutos", "1 hora", "1 hora y 30 minutos", "2 horas",
             "2 horas y 30 minutos", "24 horas"],
        )

    # --- Visitas sin salida (HU-032) ----------------------------------------

    def test_inside_lists_the_visits_without_exit_oldest_first(self):
        self.make_visit(name="Reciente", entered_ago=10)
        self.make_visit(name="Antigua", entered_ago=600)
        self.make_visit(name="Ya salió", entered_ago=300, exited=True)
        self.make_visit(name="Pendiente", status="pendiente")
        self.make_visit(name="Aprobada sin entrar")

        self.assertEqual(self.names("inside=true", user=self.guard), ["Antigua", "Reciente"])
        self.assertEqual(
            sorted(self.names("inside=false", user=self.guard)),
            ["Aprobada sin entrar", "Pendiente", "Ya salió"],
        )

    def test_a_visit_inside_reports_its_time_and_whether_it_overstayed(self):
        self.make_visit(name="Se pasó", entered_ago=90, stay=60)
        self.make_visit(name="Va bien", entered_ago=20, stay=60)
        self.make_visit(name="Sin plazo", entered_ago=700)

        visits = {
            visit["visitorName"]: visit
            for visit in self.history("inside=true", user=self.guard).get_json()["visits"]
        }

        self.assertTrue(visits["Se pasó"]["isOverstay"])
        self.assertGreaterEqual(visits["Se pasó"]["insideMinutes"], 90)
        self.assertFalse(visits["Va bien"]["isOverstay"])
        self.assertFalse(visits["Sin plazo"]["isOverstay"])
        self.assertIsNone(visits["Sin plazo"]["expectedStayMinutes"])

    def test_a_visit_that_is_not_inside_has_no_inside_time(self):
        self.make_visit(name="Pendiente", status="pendiente")

        visit = self.history().get_json()["visits"][0]

        self.assertIsNone(visit["insideMinutes"])
        self.assertFalse(visit["isOverstay"])

    # --- Historial por apartamento y fechas (HU-030) ------------------------

    def test_history_filters_by_apartment(self):
        self.make_visit(self.resident, "De la 101")
        self.make_visit(self.housemate, "También de la 101")
        self.make_visit(self.neighbor, "De la 202")

        self.assertEqual(
            sorted(self.names(f"apartmentId={self.apartment.id}")),
            ["De la 101", "También de la 101"],
        )
        self.assertEqual(self.names(f"apartmentId={self.other_apartment.id}"), ["De la 202"])
        self.assertEqual(self.names("apartmentId=9999"), [])
        self.assertEqual(len(self.names("")), 3)

    def test_history_filters_by_colombia_days_both_included(self):
        # 03:30 UTC del 5 de noviembre son las 22:30 del 4 en Colombia (UTC-5).
        self.make_visit(name="Noche del 4", created_at=datetime(2026, 11, 5, 3, 30))
        self.make_visit(name="Mañana del 5", created_at=datetime(2026, 11, 5, 13, 0))
        self.make_visit(name="Tarde del 6", created_at=datetime(2026, 11, 6, 20, 0))
        # 04:59 UTC del 7 todavía es el 6 en Colombia; 05:00 UTC ya es el 7.
        self.make_visit(name="Final del 6", created_at=datetime(2026, 11, 7, 4, 59))
        self.make_visit(name="Inicio del 7", created_at=datetime(2026, 11, 7, 5, 0))

        self.assertEqual(
            sorted(self.names("from=2026-11-05&to=2026-11-06")),
            ["Final del 6", "Mañana del 5", "Tarde del 6"],
        )
        self.assertEqual(self.names("to=2026-11-04"), ["Noche del 4"])
        self.assertEqual(
            sorted(self.names("from=2026-11-06")), ["Final del 6", "Inicio del 7", "Tarde del 6"]
        )
        self.assertEqual(self.names("from=2026-11-07&to=2026-11-07"), ["Inicio del 7"])

    def test_history_combines_filters(self):
        self.make_visit(self.resident, "A", created_at=datetime(2026, 11, 5, 15, 0), entered_ago=10)
        self.make_visit(self.resident, "B", created_at=datetime(2026, 11, 5, 16, 0))
        self.make_visit(self.neighbor, "C", created_at=datetime(2026, 11, 5, 17, 0), entered_ago=10)

        self.assertEqual(
            self.names(f"apartmentId={self.apartment.id}&from=2026-11-05&to=2026-11-05&inside=true"), ["A"]
        )
        self.assertEqual(self.names("search=torre 2&from=2026-11-05"), ["C"])
        self.assertEqual(self.names("status=aprobada&search=Resid"), ["B", "A"])

    def test_history_rejects_invalid_filters(self):
        for query in (
            "from=05-11-2026", "to=ayer", "from=2026-13-01", "from=2026-11-07&to=2026-11-05",
            "apartmentId=uno", "inside=quizas", "status=perdida", "pageSize=0", "pageSize=201", "page=0",
        ):
            with self.subTest(query=query):
                self.assertEqual(self.history(query).status_code, 400)

    def test_history_is_paginated_newest_first(self):
        for index in range(5):
            self.make_visit(name=f"Visita {index}", created_at=datetime(2026, 11, 1 + index, 15, 0))

        page = self.history("pageSize=2&page=2").get_json()

        self.assertEqual([v["visitorName"] for v in page["visits"]], ["Visita 2", "Visita 1"])
        self.assertEqual((page["page"], page["pageSize"], page["total"], page["totalPages"]), (2, 2, 5, 3))

    def test_history_shows_entry_exit_times_and_who_authorized(self):
        visit = self.make_visit(entered_ago=60)
        self.client.put(
            f"/api/visits/{visit.id}/authorize-call", headers=self.auth(self.guard)
        )
        self.client.post(
            f"/api/visits/{visit.id}/exit", headers=self.auth(self.guard), json={"returningToday": False}
        )

        item = self.history().get_json()["visits"][0]

        self.assertIsNotNone(item["enteredAt"])
        self.assertIsNotNone(item["exitedAt"])
        self.assertEqual(item["authorizationMethod"], "app")
        self.assertEqual(item["residentName"], "Residente")
        self.assertEqual(item["apartment"], "Torre 1 · Apto 101")
        self.assertEqual(item["events"][-1]["type"], "salida")

    # --- Lo que ve cada rol (CA-HU-030-02) ----------------------------------

    def test_a_resident_sees_only_the_visits_of_their_apartment(self):
        self.make_visit(self.resident, "Mía")
        self.make_visit(self.housemate, "De mi compañero")
        self.make_visit(self.neighbor, "Del vecino")

        self.assertEqual(sorted(self.names(user=self.resident)), ["De mi compañero", "Mía"])
        self.assertEqual(sorted(self.names(user=self.housemate)), ["De mi compañero", "Mía"])
        self.assertEqual(self.names(user=self.neighbor), ["Del vecino"])

    def test_a_resident_cannot_widen_the_history_with_filters(self):
        self.make_visit(self.neighbor, "Del vecino")

        self.assertEqual(self.names(f"apartmentId={self.other_apartment.id}", user=self.resident), [])
        self.assertEqual(self.names("search=Vecino", user=self.resident), [])
        self.assertEqual(self.names("inside=true", user=self.resident), [])

    def test_a_resident_without_apartment_sees_only_their_own_visits(self):
        self.make_visit(self.homeless, "Mía")
        self.make_visit(self.neighbor, "Del vecino")

        self.assertEqual(self.names(user=self.homeless), ["Mía"])

    def test_the_guard_and_the_admin_see_every_visit(self):
        self.make_visit(self.resident, "Uno")
        self.make_visit(self.neighbor, "Dos")

        self.assertEqual(sorted(self.names(user=self.guard)), ["Dos", "Uno"])
        self.assertEqual(sorted(self.names(user=self.admin)), ["Dos", "Uno"])
        self.assertEqual(self.client.get("/api/visits").status_code, 401)

    # --- Nombres de los visitantes en el QR (HU-033) ------------------------

    def make_qr(self, max_people=3, **fields):
        today = date.today()
        body = {
            "validFrom": today.isoformat(),
            "validUntil": (today + timedelta(days=5)).isoformat(),
            "maxPeople": max_people,
        }
        body.update(fields)
        response = self.client.post("/api/visits/qr-passes", headers=self.auth(self.resident), json=body)
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["qrPass"]

    def test_the_resident_can_write_the_visitor_names_when_creating_the_qr(self):
        qr = self.make_qr(visitorNames=["  Ana   Gómez ", "Luis Pérez", "ana gómez"])

        self.assertEqual(qr["visitorNames"], ["Ana Gómez", "Luis Pérez"])
        listed = self.client.get(
            "/api/visits/qr-passes", headers=self.auth(self.resident)
        ).get_json()["qrPasses"][0]
        self.assertEqual(listed["visitorNames"], ["Ana Gómez", "Luis Pérez"])

    def test_the_names_are_optional(self):
        self.assertEqual(self.make_qr()["visitorNames"], [])
        self.assertEqual(self.make_qr(visitorNames=[])["visitorNames"], [])

    def test_the_qr_refuses_bad_names(self):
        today = date.today()
        base = {
            "validFrom": today.isoformat(),
            "validUntil": (today + timedelta(days=5)).isoformat(),
            "maxPeople": 2,
        }
        cases = {
            "no es una lista": {"visitorNames": "Ana"},
            "elementos que no son texto": {"visitorNames": ["Ana", 3]},
            "nombre vacío": {"visitorNames": ["Ana", "  "]},
            "más nombres que personas": {"visitorNames": ["Ana", "Luis", "Marta"]},
            "nombre larguísimo": {"visitorNames": ["x" * 121]},
        }
        for case, extra in cases.items():
            with self.subTest(case=case):
                response = self.client.post(
                    "/api/visits/qr-passes", headers=self.auth(self.resident), json={**base, **extra}
                )
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get(
            "/api/visits/qr-passes", headers=self.auth(self.resident)).get_json()["qrPasses"], [])

    def test_the_guard_sees_the_names_and_which_are_still_to_arrive(self):
        qr = self.make_qr(visitorNames=["Ana Gómez", "Luis Pérez"])

        scanned = self.client.get(f"/api/visits/qr/{qr['token']}", headers=self.auth(self.guard)).get_json()
        self.assertEqual(scanned["qrPass"]["visitorNames"], ["Ana Gómez", "Luis Pérez"])
        self.assertEqual(scanned["pendingVisitorNames"], ["Ana Gómez", "Luis Pérez"])

        self.client.post(
            f"/api/visits/qr/{qr['token']}/entry", headers=self.auth(self.guard),
            json={"visitorName": "ANA GÓMEZ"},
        )
        after = self.client.get(f"/api/visits/qr/{qr['token']}", headers=self.auth(self.guard)).get_json()
        self.assertEqual(after["pendingVisitorNames"], ["Luis Pérez"])

    def test_a_visitor_not_on_the_list_can_still_enter_while_there_are_spots(self):
        qr = self.make_qr(max_people=2, visitorNames=["Ana Gómez"])

        response = self.client.post(
            f"/api/visits/qr/{qr['token']}/entry", headers=self.auth(self.guard),
            json={"visitorName": "Un invitado más"},
        )

        self.assertEqual(response.status_code, 201)

    def test_the_names_do_not_reach_other_residents(self):
        self.make_qr(visitorNames=["Ana Gómez"])

        theirs = self.client.get(
            "/api/visits/qr-passes", headers=self.auth(self.neighbor)
        ).get_json()["qrPasses"]

        self.assertEqual(theirs, [])


if __name__ == "__main__":
    unittest.main()
