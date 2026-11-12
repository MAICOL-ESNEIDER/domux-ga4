import unittest
from datetime import date, timedelta

import env_setup  # noqa: F401  (va antes de importar la app)

from app import create_app, migrate_pqrs_conversations
from auth import generate_token
from business_days import business_days_between, is_business_day
from extensions import db
from models import AuditLog, Notification, Pqrs, PqrsMessage, PqrsSatisfaction, User
from structure_fixtures import apartment_for
from time_utils import colombia_day_to_utc, colombia_today
from werkzeug.security import generate_password_hash


class PqrsTestCase(unittest.TestCase):
    """Base con un administrador, dos residentes y un guardia."""

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
            email="admin@test.local",
            password_hash=generate_password_hash("Admin123*"),
            role="ADMIN",
            is_active=True,
        )
        self.resident = User(
            name="Resident",
            email="resident@test.local",
            password_hash=generate_password_hash("Resident123*"),
            role="RESIDENT",
            apartment_ref=apartment_for("Torre 1 · 101"),
            is_active=True,
        )
        self.other_resident = User(
            name="Other",
            email="other@test.local",
            password_hash=generate_password_hash("Other123*"),
            role="RESIDENT",
            apartment_ref=apartment_for("Torre 2 · 202"),
            is_active=True,
        )
        self.guard = User(
            name="Guard",
            email="guard@test.local",
            password_hash=generate_password_hash("Guard123*"),
            role="GUARD",
            is_active=True,
        )
        db.session.add_all([self.admin, self.resident, self.other_resident, self.guard])
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def auth(self, user):
        return {"Authorization": f"Bearer {generate_token(user)}"}

    def make_pqrs(self, resident=None, status="abierta", category="Daño"):
        pqrs = Pqrs(
            resident_id=(resident or self.resident).id,
            category=category,
            subject="Ascensor",
            message="El ascensor no funciona",
            status=status,
            admin_response="Revisaremos el caso" if status == "resuelta" else None,
        )
        db.session.add(pqrs)
        db.session.flush()
        pqrs.conversation.append(PqrsMessage(
            author_id=(resident or self.resident).id,
            author_role="RESIDENT",
            message=pqrs.message,
        ))
        db.session.commit()
        return pqrs


class PqrsWorkflowTests(PqrsTestCase):
    def test_admin_can_create_pqrs_for_a_resident(self):
        response = self.client.post(
            "/api/pqrs",
            headers=self.auth(self.admin),
            json={
                "residentId": self.resident.id,
                "subject": "Luminaria",
                "message": "No enciende la luz del pasillo",
                "category": "Daño",
            },
        )

        self.assertEqual(response.status_code, 201)
        pqrs = Pqrs.query.one()
        self.assertEqual(pqrs.resident_id, self.resident.id)
        self.assertEqual(pqrs.conversation[0].author_role, "ADMIN")
        self.assertEqual(Notification.query.filter_by(user_id=self.resident.id).count(), 1)
        self.assertEqual(
            AuditLog.query.filter_by(entity_type="PQRS", entity_id=pqrs.id, action="created").count(),
            1,
        )

    def test_minor_without_parental_consent_cannot_create_pqrs(self):
        today = colombia_today()
        try:
            birth_date = today.replace(year=today.year - 15)
        except ValueError:
            birth_date = today.replace(year=today.year - 15, day=28)
        self.resident.birth_date = birth_date.isoformat()
        self.resident.parental_consent = False
        db.session.commit()

        response = self.client.post(
            "/api/pqrs",
            headers=self.auth(self.resident),
            json={"subject": "Tema", "message": "Descripción"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json["error"],
            "Las cuentas de menores de edad sin autorización parental están en modo consulta y no pueden radicar PQRS.",
        )
        self.assertEqual(Pqrs.query.count(), 0)

    def test_guard_cannot_create_pqrs(self):
        response = self.client.post(
            "/api/pqrs",
            headers=self.auth(self.guard),
            json={"residentId": self.resident.id, "subject": "Tema", "message": "Descripción"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Pqrs.query.count(), 0)

    def test_admin_cannot_resolve_pqrs_without_text_response(self):
        pqrs = self.make_pqrs()
        response = self.client.put(
            f"/api/pqrs/{pqrs.id}/respond",
            headers=self.auth(self.admin),
            json={"status": "resuelta", "adminResponse": "   "},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(db.session.get(Pqrs, pqrs.id).status, "abierta")
        self.assertEqual(len(db.session.get(Pqrs, pqrs.id).conversation), 1)

    def test_resident_message_reopens_resolved_pqrs_and_notifies_admin(self):
        pqrs = self.make_pqrs(status="resuelta")
        response = self.client.post(
            f"/api/pqrs/{pqrs.id}/messages",
            headers=self.auth(self.resident),
            json={"message": "El problema sigue ocurriendo."},
        )

        self.assertEqual(response.status_code, 201)
        updated = db.session.get(Pqrs, pqrs.id)
        self.assertEqual(updated.status, "abierta")
        self.assertEqual([item.author_role for item in updated.conversation], ["RESIDENT", "RESIDENT"])
        self.assertEqual(Notification.query.filter_by(user_id=self.admin.id).count(), 1)

    def test_resident_cannot_write_to_another_residents_pqrs(self):
        pqrs = self.make_pqrs()
        response = self.client.post(
            f"/api/pqrs/{pqrs.id}/messages",
            headers=self.auth(self.other_resident),
            json={"message": "Intento no autorizado"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(db.session.get(Pqrs, pqrs.id).conversation), 1)

    def test_satisfaction_only_for_own_resolved_pqrs_and_keeps_reopen_history(self):
        pqrs = self.make_pqrs(status="resuelta")
        path = f"/api/pqrs/{pqrs.id}/satisfaction"
        rating = self.client.put(
            path,
            headers=self.auth(self.resident),
            json={"rating": 5, "comment": "Atención rápida"},
        )
        self.assertEqual(rating.status_code, 200)
        self.assertEqual(PqrsSatisfaction.query.filter_by(pqrs_id=pqrs.id).count(), 1)
        updated_rating = self.client.put(
            path,
            headers=self.auth(self.resident),
            json={"rating": 4},
        )
        self.assertEqual(updated_rating.status_code, 200)
        self.assertEqual(PqrsSatisfaction.query.filter_by(pqrs_id=pqrs.id).count(), 1)

        reopened = self.client.post(
            f"/api/pqrs/{pqrs.id}/messages",
            headers=self.auth(self.resident),
            json={"message": "Se presentó de nuevo."},
        )
        self.assertEqual(reopened.status_code, 201)
        cannot_rate = self.client.put(
            path,
            headers=self.auth(self.resident),
            json={"rating": 3},
        )
        self.assertEqual(cannot_rate.status_code, 400)

        resolved = self.client.put(
            f"/api/pqrs/{pqrs.id}/respond",
            headers=self.auth(self.admin),
            json={"status": "resuelta", "adminResponse": "Ya fue reparado."},
        )
        self.assertEqual(resolved.status_code, 200)
        second_rating = self.client.put(
            path,
            headers=self.auth(self.resident),
            json={"rating": 4},
        )
        self.assertEqual(second_rating.status_code, 200)
        self.assertEqual(PqrsSatisfaction.query.filter_by(pqrs_id=pqrs.id).count(), 2)

    def test_batch_response_is_atomic_and_notifies_once_per_resident(self):
        first = self.make_pqrs()
        second = self.make_pqrs()
        failed = self.client.post(
            "/api/pqrs/batch/respond",
            headers=self.auth(self.admin),
            json={
                "pqrsIds": [first.id, second.id, 9999],
                "status": "en_proceso",
                "message": "Estamos revisando el ascensor.",
            },
        )
        self.assertEqual(failed.status_code, 404)
        self.assertEqual(failed.get_json()["failedPqrsIds"], [9999])
        self.assertEqual(PqrsMessage.query.filter_by(author_role="ADMIN").count(), 0)
        self.assertEqual(Notification.query.filter_by(user_id=self.resident.id).count(), 0)

        success = self.client.post(
            "/api/pqrs/batch/respond",
            headers=self.auth(self.admin),
            json={
                "pqrsIds": [first.id, second.id],
                "status": "en_proceso",
                "message": "Estamos revisando el ascensor.",
            },
        )
        self.assertEqual(success.status_code, 200)
        self.assertEqual(success.get_json()["updatedCount"], 2)
        self.assertEqual(PqrsMessage.query.filter_by(author_role="ADMIN").count(), 2)
        self.assertEqual(Notification.query.filter_by(user_id=self.resident.id).count(), 1)

    def test_legacy_description_and_response_are_migrated_once(self):
        legacy = Pqrs(
            resident_id=self.resident.id,
            category="Petición",
            subject="Solicitud antigua",
            message="Descripción original",
            status="resuelta",
            admin_response="Respuesta anterior",
        )
        db.session.add(legacy)
        db.session.commit()
        pqrs_id = legacy.id

        migrate_pqrs_conversations()
        migrated = db.session.get(Pqrs, pqrs_id)
        self.assertEqual(
            [(item.author_role, item.message) for item in migrated.conversation],
            [("RESIDENT", "Descripción original"), ("ADMIN", "Respuesta anterior")],
        )
        migrate_pqrs_conversations()
        self.assertEqual(len(migrated.conversation), 2)


class PqrsRadicadoTests(PqrsTestCase):
    """HU-072 y HU-073: número de radicado único y semáforo del plazo en días hábiles."""

    def create_through_api(self, user=None, **fields):
        body = {"subject": "Humedad", "message": "Hay humedad en el techo.", **fields}
        return self.client.post("/api/pqrs", headers=self.auth(user or self.resident), json=body)

    def made_days_ago(self, business_days, status="abierta"):
        """Una PQRS radicada hace ese número de días hábiles (contados hasta hoy)."""
        today = colombia_today()
        created_day = today
        while business_days_between(created_day, today) < business_days:
            created_day -= timedelta(days=1)
        pqrs = self.make_pqrs(status=status)
        pqrs.created_at = colombia_day_to_utc(created_day) + timedelta(hours=15)
        db.session.commit()
        return pqrs

    def listed(self, user, query=""):
        response = self.client.get(f"/api/pqrs{query}", headers=self.auth(user))
        self.assertEqual(response.status_code, 200)
        return response.get_json()["pqrs"]

    def listed_item(self, user, pqrs):
        """La PQRS pedida tal como la ve ese usuario en la lista."""
        return next(item for item in self.listed(user) if item["id"] == pqrs.id)

    def test_every_new_pqrs_gets_its_own_radicado(self):
        first = self.create_through_api().get_json()["pqrs"]
        second = self.create_through_api(self.other_resident).get_json()["pqrs"]

        year = colombia_today().year
        self.assertRegex(first["radicado"], rf"^PQRS-{year}-\d{{6}}$")
        self.assertRegex(second["radicado"], rf"^PQRS-{year}-\d{{6}}$")
        self.assertNotEqual(first["radicado"], second["radicado"])
        self.assertEqual(first["radicado"], f"PQRS-{year}-{first['id']:06d}")
        self.assertEqual(Pqrs.query.filter_by(radicado=first["radicado"]).count(), 1)

    def test_pqrs_created_without_the_route_also_get_a_radicado(self):
        pqrs = self.make_pqrs()

        self.assertEqual(pqrs.radicado, f"PQRS-{colombia_today().year}-{pqrs.id:06d}")
        self.assertEqual(db.session.get(Pqrs, pqrs.id).radicado, pqrs.radicado)

    def test_a_pqrs_created_by_administration_also_has_a_radicado(self):
        response = self.create_through_api(self.admin, residentId=self.resident.id)

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.get_json()["pqrs"]["radicado"].startswith("PQRS-"))

    def test_the_radicado_is_in_the_list_for_the_resident_and_for_administration(self):
        pqrs = self.make_pqrs()

        for user in (self.resident, self.admin):
            with self.subTest(role=user.role):
                self.assertEqual(self.listed(user)[0]["radicado"], pqrs.radicado)

    def test_the_radicado_never_changes_when_the_pqrs_is_answered(self):
        pqrs = self.make_pqrs()
        radicado = pqrs.radicado

        self.client.put(
            f"/api/pqrs/{pqrs.id}/respond",
            headers=self.auth(self.admin),
            json={"status": "resuelta", "adminResponse": "Listo."},
        )

        self.assertEqual(db.session.get(Pqrs, pqrs.id).radicado, radicado)

    def test_a_pqrs_can_be_found_by_its_radicado(self):
        wanted = self.make_pqrs()
        self.make_pqrs()

        found = self.listed(self.admin, f"?search={wanted.radicado}")

        self.assertEqual([item["id"] for item in found], [wanted.id])

    def test_green_with_more_than_five_business_days_left(self):
        for elapsed, remaining in ((0, 15), (9, 6)):
            with self.subTest(elapsed=elapsed):
                pqrs = self.made_days_ago(elapsed)
                item = self.listed_item(self.resident, pqrs)
                self.assertEqual(item["semaphore"], "verde")
                self.assertEqual(item["daysRemaining"], remaining)

    def test_yellow_with_five_or_fewer_business_days_left(self):
        for elapsed, remaining in ((10, 5), (15, 0)):
            with self.subTest(elapsed=elapsed):
                pqrs = self.made_days_ago(elapsed, status="en_proceso")
                item = self.listed_item(self.admin, pqrs)
                self.assertEqual(item["semaphore"], "amarillo")
                self.assertEqual(item["daysRemaining"], remaining)

    def test_red_once_the_term_expired(self):
        self.made_days_ago(16)

        item = self.listed(self.admin)[0]

        self.assertEqual(item["semaphore"], "rojo")
        self.assertEqual(item["daysRemaining"], -1)

    def test_the_due_date_is_shown_and_is_a_business_day(self):
        self.made_days_ago(3)

        due = date.fromisoformat(self.listed(self.admin)[0]["dueDate"])

        self.assertTrue(is_business_day(due))
        self.assertGreater(due, colombia_today())

    def test_a_resolved_pqrs_has_no_semaphore(self):
        self.made_days_ago(40, status="resuelta")

        item = self.listed(self.admin)[0]

        self.assertIsNone(item["semaphore"])
        self.assertIsNone(item["daysRemaining"])
        self.assertIsNone(item["dueDate"])

    def test_reopening_a_pqrs_keeps_counting_from_its_original_date(self):
        pqrs = self.made_days_ago(30, status="resuelta")

        self.client.post(
            f"/api/pqrs/{pqrs.id}/messages",
            headers=self.auth(self.resident),
            json={"message": "Sigue el problema."},
        )

        item = self.listed(self.resident)[0]
        self.assertEqual(item["status"], "abierta")
        self.assertEqual(item["semaphore"], "rojo")

    def test_a_new_pqrs_starts_green_with_fifteen_business_days(self):
        created = self.create_through_api().get_json()["pqrs"]

        self.assertEqual(created["semaphore"], "verde")
        self.assertEqual(created["daysRemaining"], 15)


if __name__ == "__main__":
    unittest.main()
