import os
import unittest

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "unit-test-only-secret-with-enough-bytes"

from app import create_app, migrate_pqrs_conversations
from auth import generate_token
from extensions import db
from models import Notification, Pqrs, PqrsMessage, PqrsSatisfaction, User
from werkzeug.security import generate_password_hash


class PqrsWorkflowTests(unittest.TestCase):
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
            apartment="Torre 1 · 101",
            is_active=True,
        )
        self.other_resident = User(
            name="Other",
            email="other@test.local",
            password_hash=generate_password_hash("Other123*"),
            role="RESIDENT",
            apartment="Torre 2 · 202",
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


if __name__ == "__main__":
    unittest.main()
