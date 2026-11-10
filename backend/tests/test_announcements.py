"""Pruebas de los comunicados (HU-057, TT-029 y DEF-005).

Comprueban que retirar un comunicado lo oculta en la app pero lo deja en la
base (DEC-090), que queda anotado quién lo retiró y que solo la administración
puede hacerlo.
"""

import unittest

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import generate_password_hash

from app import create_app
from auth import generate_token
from extensions import db
from models import Announcement, AuditLog, User
from structure_fixtures import apartment_for


class AnnouncementRetireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.admin = self.user("ADMIN", "admin-anuncios@test.local")
        self.resident = self.user("RESIDENT", "residente-anuncios@test.local", apartment_ref=apartment_for("Apto 101"))
        self.guard = self.user("GUARD", "guardia-anuncios@test.local")
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def user(self, role, email, **fields):
        person = User(
            name=role.title(),
            email=email,
            password_hash=generate_password_hash("Clave-de-prueba-1*"),
            role=role,
            is_active=True,
            **fields,
        )
        db.session.add(person)
        return person

    def headers(self, user):
        return {"Authorization": f"Bearer {generate_token(user)}"}

    def publish(self, title):
        response = self.client.post(
            "/api/announcements",
            json={"title": title, "message": "Mensaje de prueba para los residentes."},
            headers=self.headers(self.admin),
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()["announcement"]["id"]

    def listed_ids(self, user):
        response = self.client.get("/api/announcements", headers=self.headers(user))
        self.assertEqual(response.status_code, 200)
        return [item["id"] for item in response.get_json()["announcements"]]

    def retire(self, announcement_id, user=None):
        return self.client.put(
            f"/api/announcements/{announcement_id}/retire",
            headers=self.headers(user or self.admin),
        )

    def test_retired_announcement_is_hidden_but_stays_in_database(self):
        kept = self.publish("Asamblea de copropietarios")
        retired = self.publish("Corte de agua")

        response = self.retire(retired)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["announcement"]["isRetired"])
        self.assertEqual(self.listed_ids(self.resident), [kept])
        self.assertEqual(self.listed_ids(self.admin), [kept])
        row = db.session.get(Announcement, retired)
        self.assertIsNotNone(row)
        self.assertIsNotNone(row.retired_at)
        self.assertEqual(row.retired_by_id, self.admin.id)
        log = AuditLog.query.filter_by(
            entity_type="announcement", entity_id=retired, action="retired"
        ).one()
        self.assertEqual(log.actor_id, self.admin.id)

    def test_retiring_twice_answers_conflict(self):
        announcement_id = self.publish("Fumigación")
        self.assertEqual(self.retire(announcement_id).status_code, 200)

        response = self.retire(announcement_id)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Announcement.query.count(), 1)

    def test_old_delete_route_retires_instead_of_deleting(self):
        announcement_id = self.publish("Mantenimiento del ascensor")

        response = self.client.delete(
            f"/api/announcements/{announcement_id}", headers=self.headers(self.admin)
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(db.session.get(Announcement, announcement_id))
        self.assertEqual(self.listed_ids(self.resident), [])

    def test_only_administration_can_retire(self):
        announcement_id = self.publish("Jornada de reciclaje")

        for user in (self.resident, self.guard):
            with self.subTest(role=user.role):
                self.assertEqual(self.retire(announcement_id, user).status_code, 403)

        self.assertEqual(self.listed_ids(self.resident), [announcement_id])

    def test_unknown_announcement_answers_not_found(self):
        self.assertEqual(self.retire(9999).status_code, 404)


if __name__ == "__main__":
    unittest.main()
