import os
import unittest
from datetime import timedelta
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"

from app import create_app
from auth import generate_token
from extensions import db
from models import AuditLog, CommonArea, Notification, Pqrs, Reservation, User
from werkzeug.security import check_password_hash, generate_password_hash
from time_utils import now_colombia


class AdminResidentActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app({"TESTING": True})
        cls.app.config.update(TESTING=True)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.admin = User(
            name="Administradora",
            email="admin-actions@test.local",
            password_hash=generate_password_hash("Admin123*"),
            role="ADMIN",
            is_active=True,
        )
        self.resident = User(
            name="Residente",
            email="resident-actions@test.local",
            password_hash=generate_password_hash("Resident123*"),
            role="RESIDENT",
            apartment="Torre 1 · Apto 101",
            is_active=True,
        )
        self.other_resident = User(
            name="Otro residente",
            email="other-actions@test.local",
            password_hash=generate_password_hash("Other123*"),
            role="RESIDENT",
            apartment="Torre 2 · Apto 202",
            is_active=True,
        )
        self.guard = User(
            name="Guardia",
            email="guard-actions@test.local",
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

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def headers(self, user):
        return {"Authorization": f"Bearer {generate_token(user)}"}

    def test_resident_can_change_password_and_audit_the_action(self):
        old_token = generate_token(self.resident)
        response = self.client.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {old_token}"},
            json={
                "currentPassword": "Resident123*",
                "newPassword": "UpdatedResident123*",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json["message"],
            "Contraseña actualizada exitosamente.",
        )
        self.assertIsInstance(response.json["token"], str)
        old_session = self.client.get(
            "/api/auth/session",
            headers={"Authorization": f"Bearer {old_token}"},
        )
        new_session = self.client.get(
            "/api/auth/session",
            headers={"Authorization": f"Bearer {response.json['token']}"},
        )
        self.assertEqual(old_session.status_code, 401)
        self.assertEqual(new_session.status_code, 200)
        self.assertTrue(check_password_hash(self.resident.password_hash, "UpdatedResident123*"))
        audit = AuditLog.query.filter_by(
            entity_type="USER",
            entity_id=self.resident.id,
            action="password_changed",
        ).one()
        self.assertEqual(audit.actor_id, self.resident.id)
        self.assertEqual(audit.actor_role, "RESIDENT")
        self.assertNotIn("UpdatedResident123*", audit.details or "")

    def test_password_change_clears_required_flag_and_saves_recovery_email(self):
        self.resident.must_change_password = True
        db.session.commit()

        response = self.client.post(
            "/api/auth/change-password",
            headers=self.headers(self.resident),
            json={
                "currentPassword": "Resident123*",
                "newPassword": "UpdatedResident123*",
                "recoveryEmail": "recovery@test.local",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["user"]["mustChangePassword"])
        self.assertEqual(response.json["user"]["recoveryEmail"], "recovery@test.local")
        self.assertFalse(self.resident.must_change_password)
        self.assertEqual(self.resident.recovery_email, "recovery@test.local")

    def test_password_change_rejects_invalid_or_primary_recovery_email(self):
        for recovery_email in ("not-an-email", self.resident.email):
            with self.subTest(recovery_email=recovery_email):
                response = self.client.post(
                    "/api/auth/change-password",
                    headers=self.headers(self.resident),
                    json={
                        "currentPassword": "Resident123*",
                        "newPassword": "UpdatedResident123*",
                        "recoveryEmail": recovery_email,
                    },
                )
                self.assertEqual(response.status_code, 400)

        self.assertTrue(
            check_password_hash(self.resident.password_hash, "Resident123*")
        )
        self.assertIsNone(self.resident.recovery_email)
        self.assertEqual(AuditLog.query.filter_by(action="password_changed").count(), 0)

    def test_admin_created_user_must_change_password_and_is_audited(self):
        response = self.client.post(
            "/api/users",
            headers=self.headers(self.admin),
            json={
                "name": "Nuevo",
                "lastName": "Residente",
                "email": "new-resident-actions@test.local",
                "password": "NewUser123*",
                "role": "RESIDENT",
                "apartment": "Torre 3 · Apto 303",
                "occupancyType": "residente",
                "dataProcessingConsent": True,
            },
        )

        self.assertEqual(response.status_code, 201)
        created = User.query.filter_by(
            email="new-resident-actions@test.local"
        ).one()
        self.assertTrue(response.json["user"]["mustChangePassword"])
        self.assertTrue(created.must_change_password)
        audit = AuditLog.query.filter_by(
            entity_type="USER",
            entity_id=created.id,
            action="user_created",
        ).one()
        self.assertEqual(audit.actor_id, self.admin.id)
        self.assertEqual(audit.actor_role, "ADMIN")

    def test_user_creation_and_update_require_a_valid_role(self):
        create_base = {
            "name": "Cuenta",
            "email": "required-role@test.local",
            "password": "RequiredRole123*",
        }
        for role_value in ("missing", "INVALID"):
            with self.subTest(operation="create", role=role_value):
                body = dict(create_base)
                if role_value != "missing":
                    body["role"] = role_value
                response = self.client.post(
                    "/api/admin/users",
                    headers=self.headers(self.admin),
                    json=body,
                )
                self.assertEqual(response.status_code, 400)

        for role_value in ("missing", "INVALID"):
            with self.subTest(operation="update", role=role_value):
                body = {"phone": "3001234567"}
                if role_value != "missing":
                    body["role"] = role_value
                response = self.client.put(
                    f"/api/admin/users/{self.resident.id}",
                    headers=self.headers(self.admin),
                    json=body,
                )
                self.assertEqual(response.status_code, 400)

    def test_admin_can_create_and_edit_an_account_with_admin_role(self):
        created = self.client.post(
            "/api/admin/users",
            headers=self.headers(self.admin),
            json={
                "name": "Segundo",
                "email": "second-admin@test.local",
                "password": "SecondAdmin123*",
                "role": "ADMIN",
            },
        )

        self.assertEqual(created.status_code, 201)
        second_admin_id = created.json["user"]["id"]
        second_admin = db.session.get(User, second_admin_id)
        self.assertEqual(second_admin.role, "ADMIN")
        self.assertIsNone(second_admin.apartment)

        edited = self.client.put(
            f"/api/admin/users/{second_admin_id}",
            headers=self.headers(self.admin),
            json={"role": "GUARD"},
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(second_admin.role, "GUARD")
        self.assertIsNone(second_admin.apartment)

        restored = self.client.put(
            f"/api/admin/users/{second_admin_id}",
            headers=self.headers(self.admin),
            json={"role": "ADMIN"},
        )
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(second_admin.role, "ADMIN")

    def test_admin_cannot_deactivate_or_change_own_role(self):
        for payload in (
            {"role": "ADMIN", "isActive": False},
            {"role": "GUARD"},
        ):
            with self.subTest(payload=payload):
                response = self.client.put(
                    f"/api/admin/users/{self.admin.id}",
                    headers=self.headers(self.admin),
                    json=payload,
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json["error"],
                    "No puedes desactivar ni cambiar el rol de tu propia cuenta.",
                )
                self.assertEqual(self.admin.role, "ADMIN")
                self.assertTrue(self.admin.is_active)

    def test_last_active_admin_cannot_be_deactivated_or_demoted(self):
        last_admin = User(
            name="Último",
            email="last-admin@test.local",
            password_hash=generate_password_hash("LastAdmin123*"),
            role="ADMIN",
            is_active=True,
        )
        db.session.add(last_admin)
        db.session.commit()

        for payload in (
            {"role": "ADMIN", "isActive": False},
            {"role": "GUARD", "isActive": True},
        ):
            with self.subTest(payload=payload):
                with patch.object(User, "query") as user_query:
                    user_query.filter_by.return_value.count.return_value = 1
                    response = self.client.put(
                        f"/api/admin/users/{last_admin.id}",
                        headers=self.headers(self.admin),
                        json=payload,
                    )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json["error"],
                    "Debe existir al menos un administrador activo en el sistema.",
                )
                self.assertEqual(last_admin.role, "ADMIN")
                self.assertTrue(last_admin.is_active)

    def test_admin_password_reset_requires_password_change_and_is_audited(self):
        old_token = generate_token(self.resident)
        response = self.client.post(
            f"/api/users/{self.resident.id}/reset-password",
            headers=self.headers(self.admin),
            json={"password": "Temporary123*"},
        )
        old_session = self.client.get(
            "/api/auth/session",
            headers={"Authorization": f"Bearer {old_token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("token", response.json)
        self.assertEqual(old_session.status_code, 401)
        self.assertTrue(self.resident.must_change_password)
        self.assertEqual(self.resident.token_version, 2)
        self.assertTrue(
            check_password_hash(self.resident.password_hash, "Temporary123*")
        )
        audit = AuditLog.query.filter_by(
            entity_type="USER",
            entity_id=self.resident.id,
            action="password_reset",
        ).one()
        self.assertEqual(audit.actor_id, self.admin.id)
        self.assertEqual(audit.actor_role, "ADMIN")

    def test_admin_can_replace_resident_email_without_duplicates(self):
        updated = self.client.put(
            f"/api/users/{self.resident.id}",
            headers=self.headers(self.admin),
            json={"email": "replacement@test.local", "role": "RESIDENT"},
        )
        duplicate = self.client.put(
            f"/api/users/{self.resident.id}",
            headers=self.headers(self.admin),
            json={"email": self.other_resident.email, "role": "RESIDENT"},
        )

        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json["user"]["email"], "replacement@test.local")
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(self.resident.email, "replacement@test.local")

    def test_password_change_rejects_wrong_current_or_weak_new_password(self):
        original_hash = self.resident.password_hash
        wrong_current = self.client.post(
            "/api/auth/change-password",
            headers=self.headers(self.resident),
            json={
                "currentPassword": "Wrong123*",
                "newPassword": "UpdatedResident123*",
            },
        )
        weak_new = self.client.post(
            "/api/auth/change-password",
            headers=self.headers(self.resident),
            json={
                "currentPassword": "Resident123*",
                "newPassword": "weak",
            },
        )

        self.assertEqual(wrong_current.status_code, 401)
        self.assertEqual(weak_new.status_code, 400)
        self.assertEqual(self.resident.password_hash, original_hash)
        self.assertEqual(AuditLog.query.filter_by(action="password_changed").count(), 0)

    def test_admin_creates_pqrs_for_resident_with_audit_and_notification(self):
        response = self.client.post(
            "/api/pqrs",
            headers=self.headers(self.admin),
            json={
                "residentId": self.resident.id,
                "subject": "Llave del acceso",
                "message": "La residente solicita apoyo con su llave.",
                "category": "Petición",
            },
        )
        self.assertEqual(response.status_code, 201)
        pqrs = Pqrs.query.one()
        self.assertEqual(pqrs.resident_id, self.resident.id)
        self.assertEqual(pqrs.created_by_admin_id, self.admin.id)
        self.assertEqual(pqrs.conversation[0].author_id, self.admin.id)
        self.assertTrue(response.json["pqrs"]["createdByAdministration"])
        self.assertEqual(Notification.query.filter_by(user_id=self.resident.id).count(), 1)

    def test_admin_creates_reservation_for_resident_with_audit_and_notification(self):
        response = self.client.post(
            "/api/reservations",
            headers=self.headers(self.admin),
            json={
                "residentId": self.resident.id,
                "commonAreaId": self.area.id,
                "date": "2099-06-20",
                "timeSlot": "10:00-12:00",
            },
        )
        self.assertEqual(response.status_code, 201)
        reservation = Reservation.query.one()
        self.assertEqual(reservation.resident_id, self.resident.id)
        self.assertEqual(reservation.created_by_admin_id, self.admin.id)
        self.assertTrue(response.json["reservation"]["createdByAdministration"])
        self.assertEqual(Notification.query.filter_by(user_id=self.resident.id).count(), 1)

    def test_resident_cannot_create_requests_for_another_resident(self):
        pqrs_response = self.client.post(
            "/api/pqrs",
            headers=self.headers(self.resident),
            json={
                "residentId": self.other_resident.id,
                "subject": "Solicitud",
                "message": "Solicitud de prueba",
            },
        )
        self.assertEqual(pqrs_response.status_code, 201)
        self.assertEqual(Pqrs.query.one().resident_id, self.resident.id)
        self.assertIsNone(Pqrs.query.one().created_by_admin_id)

        reservation_response = self.client.post(
            "/api/reservations",
            headers=self.headers(self.resident),
            json={
                "residentId": self.other_resident.id,
                "commonAreaId": self.area.id,
                "date": (now_colombia().date() + timedelta(days=5)).isoformat(),
                "timeSlot": "10:00-12:00",
            },
        )
        self.assertEqual(reservation_response.status_code, 201)
        self.assertEqual(Reservation.query.one().resident_id, self.resident.id)
        self.assertIsNone(Reservation.query.one().created_by_admin_id)

    def test_guard_cannot_create_on_behalf_of_a_resident(self):
        pqrs_response = self.client.post(
            "/api/pqrs",
            headers=self.headers(self.guard),
            json={
                "residentId": self.resident.id,
                "subject": "Solicitud",
                "message": "Solicitud de prueba",
            },
        )
        self.assertEqual(pqrs_response.status_code, 403)
        reservation_response = self.client.post(
            "/api/reservations",
            headers=self.headers(self.guard),
            json={
                "residentId": self.resident.id,
                "commonAreaId": self.area.id,
                "date": "2099-06-20",
                "timeSlot": "10:00-12:00",
            },
        )
        self.assertEqual(reservation_response.status_code, 403)
        self.assertEqual(Pqrs.query.count(), 0)
        self.assertEqual(Reservation.query.count(), 0)

    def test_admin_can_respond_to_the_pqrs_created_for_resident(self):
        created = self.client.post(
            "/api/pqrs",
            headers=self.headers(self.admin),
            json={
                "residentId": self.resident.id,
                "subject": "Solicitud",
                "message": "Solicitud de prueba",
            },
        )
        pqrs_id = created.json["pqrs"]["id"]
        response = self.client.put(
            f"/api/pqrs/{pqrs_id}/respond",
            headers=self.headers(self.admin),
            json={"status": "en_proceso", "adminResponse": "Ya estamos revisando."},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Pqrs.query.one().created_by_admin_id, self.admin.id)
        self.assertEqual(len(Pqrs.query.one().conversation), 2)
        self.assertEqual(Notification.query.filter_by(user_id=self.resident.id).count(), 2)

    def test_admin_can_filter_pqrs_by_resident_but_resident_cannot(self):
        first = Pqrs(
            resident_id=self.resident.id,
            subject="Solicitud propia",
            message="Detalle",
        )
        second = Pqrs(
            resident_id=self.other_resident.id,
            subject="Solicitud ajena",
            message="Detalle",
        )
        db.session.add_all([first, second])
        db.session.commit()
        admin_response = self.client.get(
            f"/api/pqrs?residentId={self.resident.id}",
            headers=self.headers(self.admin),
        )
        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual([item["residentId"] for item in admin_response.json["pqrs"]], [self.resident.id])
        resident_response = self.client.get(
            f"/api/pqrs?residentId={self.other_resident.id}",
            headers=self.headers(self.resident),
        )
        self.assertEqual(resident_response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
