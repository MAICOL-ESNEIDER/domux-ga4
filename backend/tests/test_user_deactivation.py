"""Pruebas de la desactivación de usuarios (TT-027, DEF-003 y DEF-011).

Al desactivar a un residente se anulan sus QR vigentes y se borran sus tokens
de avisos al celular; los comunicados ya no le llegan y la portería no puede
usar sus QR. Su historial se conserva.
"""

import json
import unittest
from datetime import timedelta

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import generate_password_hash

from app import create_app
from auth import generate_token
from extensions import db
from models import AuditLog, DevicePushToken, Notification, User, VisitQrPass
from structure_fixtures import apartment_for
from time_utils import colombia_today


def days_from_today(days):
    return (colombia_today() + timedelta(days=days)).isoformat()


class UserDeactivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.admin = self.user("ADMIN", "admin-desactivar@test.local")
        self.guard = self.user("GUARD", "guardia-desactivar@test.local")
        self.resident = self.user("RESIDENT", "residente-desactivar@test.local", apartment_ref=apartment_for("Apto 101"))
        self.neighbor = self.user("RESIDENT", "vecina-desactivar@test.local", apartment_ref=apartment_for("Apto 102"))
        db.session.flush()
        self.current_pass = self.qr_pass("qr-vigente", days_from_today(0), days_from_today(2))
        self.expired_pass = self.qr_pass("qr-vencido", days_from_today(-5), days_from_today(-1))
        db.session.add(DevicePushToken(user_id=self.resident.id, token="token-del-celular"))
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def user(self, role, email, **fields):
        person = User(
            name=role.title(), email=email, role=role, is_active=True,
            password_hash=generate_password_hash("Clave-de-prueba-1*"), **fields,
        )
        db.session.add(person)
        return person

    def qr_pass(self, token, valid_from, valid_until):
        qr_pass = VisitQrPass(
            resident_id=self.resident.id, token=token,
            valid_from=valid_from, valid_until=valid_until, max_people=2,
        )
        db.session.add(qr_pass)
        return qr_pass

    def headers(self, user):
        return {"Authorization": f"Bearer {generate_token(user)}"}

    def set_active(self, user, active):
        return self.client.put(
            f"/api/users/{user.id}", json={"isActive": active}, headers=self.headers(self.admin)
        )

    def test_deactivating_a_resident_revokes_current_qr_and_removes_push_tokens(self):
        response = self.set_active(self.resident, False)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(db.session.get(VisitQrPass, self.current_pass.id).revoked)
        self.assertIsNotNone(db.session.get(VisitQrPass, self.current_pass.id).revoked_at)
        # El QR que ya había vencido queda como estaba: es historial.
        self.assertFalse(db.session.get(VisitQrPass, self.expired_pass.id).revoked)
        self.assertEqual(DevicePushToken.query.filter_by(user_id=self.resident.id).count(), 0)
        log = AuditLog.query.filter_by(action="deactivated", entity_id=self.resident.id).one()
        self.assertEqual(
            json.loads(log.details), {"revokedQrPasses": 1, "removedPushTokens": 1}
        )

    def test_reactivating_is_recorded_without_touching_the_history(self):
        self.set_active(self.resident, False)

        response = self.set_active(self.resident, True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            AuditLog.query.filter_by(action="reactivated", entity_id=self.resident.id).count(), 1
        )
        self.assertTrue(db.session.get(VisitQrPass, self.current_pass.id).revoked)

    def test_guard_cannot_use_the_qr_of_a_deactivated_resident(self):
        # Aunque el QR no esté anulado (por ejemplo, desactivado por otra vía).
        self.resident.is_active = False
        db.session.commit()

        inspect = self.client.get("/api/visits/qr/qr-vigente", headers=self.headers(self.guard))
        entry = self.client.post(
            "/api/visits/qr/qr-vigente/entry",
            json={"visitorName": "Visitante"},
            headers=self.headers(self.guard),
        )

        self.assertFalse(inspect.get_json()["canRegister"])
        self.assertEqual(entry.status_code, 404)

    def test_announcements_only_reach_active_residents(self):
        self.set_active(self.resident, False)

        response = self.client.post(
            "/api/announcements",
            json={"title": "Corte de agua", "message": "Mañana de 8 a 12."},
            headers=self.headers(self.admin),
        )

        self.assertEqual(response.status_code, 201)
        receivers = {row.user_id for row in Notification.query.filter_by(type="announcement")}
        self.assertEqual(receivers, {self.neighbor.id})


if __name__ == "__main__":
    unittest.main()
