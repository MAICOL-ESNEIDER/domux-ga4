import os
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from google.auth.exceptions import DefaultCredentialsError

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "unit-test-only-secret-with-enough-bytes"

from app import create_app
from auth import generate_token
from extensions import db
from models import DevicePushToken, Notification, PackageItem, User, Visit, VisitQrPass
from services import notification_service
from werkzeug.security import generate_password_hash


class SecurityWorkflowTests(unittest.TestCase):
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
            email="security-admin@test.local",
            password_hash=generate_password_hash("Admin123*"),
            role="ADMIN",
            is_active=True,
        )
        self.resident = User(
            name="Resident",
            email="security-resident@test.local",
            password_hash=generate_password_hash("Resident123*"),
            role="RESIDENT",
            apartment="Torre 1 · Apto 101",
            document_id="123456",
            is_active=True,
        )
        self.other_resident = User(
            name="Other Resident",
            email="security-other@test.local",
            password_hash=generate_password_hash("Other123*"),
            role="RESIDENT",
            apartment="Torre 2 · Apto 202",
            is_active=True,
        )
        self.guard = User(
            name="Guard",
            email="security-guard@test.local",
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

    def register_visit(self, **fields):
        data = {
            "residentId": self.resident.id,
            "visitorName": "Visita de prueba",
            "type": "visitante",
        }
        data.update(fields)
        return self.client.post("/api/visits", headers=self.auth(self.guard), json=data)

    def make_qr(self, max_people=1):
        start = date.today()
        end = start + timedelta(days=29)
        response = self.client.post(
            "/api/visits/qr-passes",
            headers=self.auth(self.resident),
            json={
                "validFrom": start.isoformat(),
                "validUntil": end.isoformat(),
                "maxPeople": max_people,
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()["qrPass"]

    def test_visit_needs_consent_for_document_and_notifies_resident(self):
        response = self.register_visit(visitorDocument="1234")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Visit.query.count(), 0)

        response = self.register_visit(
            visitorDocument="1234",
            mediaConsent=True,
            mediaUrl="data:image/jpeg;base64,AA==",
            mediaType="image",
        )
        self.assertEqual(response.status_code, 201)
        visit = Visit.query.one()
        self.assertEqual(visit.visitor_document, "1234")
        self.assertTrue(visit.media_consent)
        self.assertEqual(Notification.query.filter_by(user_id=self.resident.id).count(), 1)

    def test_resident_decision_call_authorization_entry_and_exit_are_audited(self):
        visit_response = self.register_visit()
        visit_id = visit_response.get_json()["visit"]["id"]

        rejected = self.client.put(
            f"/api/visits/{visit_id}/decision",
            headers=self.auth(self.other_resident),
            json={"decision": "aprobada"},
        )
        self.assertEqual(rejected.status_code, 403)
        approved = self.client.put(
            f"/api/visits/{visit_id}/decision",
            headers=self.auth(self.resident),
            json={"decision": "aprobada"},
        )
        self.assertEqual(approved.status_code, 200)

        entry = self.client.post(
            f"/api/visits/{visit_id}/entry",
            headers=self.auth(self.guard),
            json={},
        )
        self.assertEqual(entry.status_code, 200)
        exit_response = self.client.post(
            f"/api/visits/{visit_id}/exit",
            headers=self.auth(self.guard),
            json={"returningToday": True},
        )
        self.assertEqual(exit_response.status_code, 200)
        visit = db.session.get(Visit, visit_id)
        self.assertEqual([event.event_type for event in visit.events], [
            "solicitud", "aprobada", "entrada", "salida",
        ])
        self.assertTrue(visit.exit_returning)
        self.assertEqual(Notification.query.filter_by(user_id=self.resident.id).count(), 3)

    def test_manual_visitor_cannot_return_after_definitive_exit(self):
        visit_id = self.register_visit().get_json()["visit"]["id"]
        approval = self.client.put(
            f"/api/visits/{visit_id}/authorize-call",
            headers=self.auth(self.guard),
        )
        self.assertEqual(approval.status_code, 200)
        entry = self.client.post(
            f"/api/visits/{visit_id}/entry",
            headers=self.auth(self.guard),
            json={},
        )
        self.assertEqual(entry.status_code, 200)
        exit_response = self.client.post(
            f"/api/visits/{visit_id}/exit",
            headers=self.auth(self.guard),
            json={"returningToday": False},
        )
        self.assertEqual(exit_response.status_code, 200)
        reentry = self.client.post(
            f"/api/visits/{visit_id}/entry",
            headers=self.auth(self.guard),
            json={},
        )
        self.assertEqual(reentry.status_code, 400)

    def test_call_authorization_is_guard_only_and_guard_can_record_resident_search(self):
        visit_id = self.register_visit().get_json()["visit"]["id"]
        response = self.client.put(
            f"/api/visits/{visit_id}/authorize-call",
            headers=self.auth(self.resident),
        )
        self.assertEqual(response.status_code, 403)

        search = self.client.get(
            "/api/residents?search=123456",
            headers=self.auth(self.guard),
        )
        self.assertEqual(search.status_code, 200)
        self.assertEqual([item["id"] for item in search.get_json()["residents"]], [self.resident.id])
        missing_search = self.client.get("/api/residents", headers=self.auth(self.guard))
        self.assertEqual(missing_search.status_code, 200)
        self.assertEqual(len(missing_search.get_json()["residents"]), 2)
        admin_list = self.client.get("/api/residents", headers=self.auth(self.admin))
        self.assertEqual(admin_list.status_code, 200)
        self.assertEqual(len(admin_list.get_json()["residents"]), 2)

    def test_package_registration_status_trash_restore_and_purge(self):
        registration = self.client.post(
            "/api/packages",
            headers=self.auth(self.admin),
            json={
                "residentId": self.resident.id,
                "description": "Caja especial",
                "status": "por_llegar",
            },
        )
        self.assertEqual(registration.status_code, 201)
        package_id = registration.get_json()["packageItem"]["id"]

        invalid_registration = self.client.post(
            "/api/packages",
            headers=self.auth(self.guard),
            json={
                "residentId": self.resident.id,
                "description": "Estado inválido",
                "status": "entregado",
            },
        )
        self.assertEqual(invalid_registration.status_code, 400)

        status_response = self.client.put(
            f"/api/packages/{package_id}/status",
            headers=self.auth(self.guard),
            json={"status": "pendiente"},
        )
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.get_json()["packageItem"]["status"], "pendiente")
        self.assertEqual(
            Notification.query.filter_by(user_id=self.resident.id).count(),
            2,
        )

        deleted = self.client.delete(
            f"/api/packages/{package_id}",
            headers=self.auth(self.guard),
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.get_json()["packageItem"]["isDeleted"])
        trash = self.client.get(
            "/api/packages?status=papelera",
            headers=self.auth(self.guard),
        )
        self.assertEqual([item["id"] for item in trash.get_json()["packages"]], [package_id])

        restored = self.client.put(
            f"/api/packages/{package_id}/restore",
            headers=self.auth(self.admin),
        )
        self.assertEqual(restored.status_code, 200)
        self.assertFalse(restored.get_json()["packageItem"]["isDeleted"])

        forced_delete = self.client.delete(
            f"/api/packages/{package_id}?force=true",
            headers=self.auth(self.admin),
        )
        self.assertEqual(forced_delete.status_code, 200)
        self.assertIsNone(db.session.get(PackageItem, package_id))

    def test_package_listing_automatically_trashes_and_purges_expired_items(self):
        expired_delivery = PackageItem(
            resident_id=self.resident.id,
            registered_by=self.guard.id,
            description="Entrega antigua",
            status="entregado",
            delivered_at=datetime.utcnow() - timedelta(days=8),
        )
        expired_trash = PackageItem(
            resident_id=self.other_resident.id,
            registered_by=self.guard.id,
            description="Papelera antigua",
            is_deleted=True,
            deleted_at=datetime.utcnow() - timedelta(days=31),
        )
        db.session.add_all([expired_delivery, expired_trash])
        db.session.commit()
        expired_delivery_id = expired_delivery.id
        expired_trash_id = expired_trash.id

        response = self.client.get(
            "/api/packages?status=papelera",
            headers=self.auth(self.guard),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.get_json()["packages"]],
            [expired_delivery_id],
        )
        self.assertTrue(db.session.get(PackageItem, expired_delivery_id).is_deleted)
        self.assertIsNone(db.session.get(PackageItem, expired_trash_id))


    def test_qr_limits_new_people_allows_same_day_reentry_and_revokes(self):
        qr = self.make_qr()
        token = qr["token"]
        first = self.client.post(
            f"/api/visits/qr/{token}/entry",
            headers=self.auth(self.guard),
            json={"visitorName": "Visitante Uno"},
        )
        self.assertEqual(first.status_code, 201)
        visit_id = first.get_json()["visit"]["id"]
        exit_response = self.client.post(
            f"/api/visits/qr/{token}/exit",
            headers=self.auth(self.guard),
            json={"visitId": visit_id, "returningToday": True},
        )
        self.assertEqual(exit_response.status_code, 200)
        reentry = self.client.post(
            f"/api/visits/qr/{token}/entry",
            headers=self.auth(self.guard),
            json={"visitId": visit_id},
        )
        self.assertEqual(reentry.status_code, 201)
        self.assertEqual(Visit.query.count(), 1)
        full = self.client.post(
            f"/api/visits/qr/{token}/entry",
            headers=self.auth(self.guard),
            json={"visitorName": "Otra Persona"},
        )
        self.assertEqual(full.status_code, 409)

        revoke = self.client.put(
            f"/api/visits/qr-passes/{qr['id']}/revoke",
            headers=self.auth(self.resident),
        )
        self.assertEqual(revoke.status_code, 200)
        self.assertIsNotNone(VisitQrPass.query.one().revoked_at)
        revoked_entry = self.client.post(
            f"/api/visits/qr/{token}/entry",
            headers=self.auth(self.guard),
            json={"visitorName": "Visitante Uno"},
        )
        self.assertEqual(revoked_entry.status_code, 404)
        exit_after_revoke = self.client.post(
            f"/api/visits/qr/{token}/exit",
            headers=self.auth(self.guard),
            json={"visitId": visit_id, "returningToday": False},
        )
        self.assertEqual(exit_after_revoke.status_code, 200)

    def test_manual_visit_can_be_linked_to_qr_without_duplicating_history(self):
        visit_response = self.register_visit(visitorName="Visitante Manual")
        visit_id = visit_response.get_json()["visit"]["id"]
        qr = self.make_qr()
        linked = self.client.post(
            f"/api/visits/qr/{qr['token']}/entry",
            headers=self.auth(self.guard),
            json={"visitId": visit_id},
        )
        self.assertEqual(linked.status_code, 201)
        visit = db.session.get(Visit, visit_id)
        self.assertEqual(visit.qr_pass_id, qr["id"])
        self.assertEqual(visit.authorization_method, "qr")
        self.assertEqual(Visit.query.count(), 1)
        self.assertEqual(VisitQrPass.query.one().to_dict()["registeredPeople"], 1)

    def test_qr_rejects_invalid_duration_and_foreign_resident_cannot_revoke(self):
        today = date.today().isoformat()
        too_long = self.client.post(
            "/api/visits/qr-passes",
            headers=self.auth(self.resident),
            json={
                "validFrom": today,
                "validUntil": (date.today() + timedelta(days=30)).isoformat(),
                "maxPeople": 2,
            },
        )
        self.assertEqual(too_long.status_code, 400)
        qr = self.make_qr()
        forbidden = self.client.put(
            f"/api/visits/qr-passes/{qr['id']}/revoke",
            headers=self.auth(self.other_resident),
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_admin_cannot_create_a_resident_owned_qr_pass(self):
        today = date.today().isoformat()
        response = self.client.post(
            "/api/visits/qr-passes",
            headers=self.auth(self.admin),
            json={"validFrom": today, "validUntil": today, "maxPeople": 1},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(VisitQrPass.query.count(), 0)

    def test_push_tokens_are_scoped_to_authenticated_user(self):
        current = self.client.get("/api/auth/session", headers=self.auth(self.resident))
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.get_json()["user"]["id"], self.resident.id)
        expired_session = self.client.get("/api/auth/session")
        self.assertEqual(expired_session.status_code, 401)

        unauthenticated = self.client.post(
            "/api/push-tokens",
            json={"token": "fcm-token"},
        )
        self.assertEqual(unauthenticated.status_code, 401)
        registered = self.client.post(
            "/api/push-tokens",
            headers=self.auth(self.resident),
            json={"token": "fcm-token", "deviceId": "device-1"},
        )
        self.assertEqual(registered.status_code, 201)
        token = DevicePushToken.query.one()
        self.assertEqual(token.user_id, self.resident.id)

        rotated = self.client.post(
            "/api/push-tokens",
            headers=self.auth(self.resident),
            json={"token": "fcm-token-rotated", "deviceId": "device-1"},
        )
        self.assertEqual(rotated.status_code, 201)
        self.assertEqual(DevicePushToken.query.count(), 1)
        self.assertEqual(DevicePushToken.query.one().token, "fcm-token-rotated")

        removed_foreign = self.client.delete(
            "/api/push-tokens",
            headers=self.auth(self.other_resident),
            json={"token": "fcm-token-rotated"},
        )
        self.assertEqual(removed_foreign.status_code, 200)
        self.assertEqual(DevicePushToken.query.count(), 1)

        removed = self.client.delete(
            "/api/push-tokens",
            headers=self.auth(self.resident),
            json={"token": "fcm-token-rotated"},
        )
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(DevicePushToken.query.count(), 0)

    def test_push_is_sent_after_commit_with_route_and_high_priority_for_visitors(self):
        self.client.post(
            "/api/push-tokens",
            headers=self.auth(self.resident),
            json={"token": "fcm-token", "deviceId": "device-1"},
        )
        with (
            patch.object(notification_service, "_get_firebase_app", return_value=object()),
            patch.object(notification_service.messaging, "send_each_for_multicast") as send,
        ):
            send.return_value.failure_count = 0
            notification_service.notify_user(
                self.resident.id,
                "Visitante esperando",
                "Autoriza su ingreso.",
                "visit",
            )
            db.session.commit()

        self.assertEqual(send.call_count, 1)
        fcm_message = send.call_args.args[0]
        self.assertEqual(
            {key: fcm_message.data[key] for key in ("type", "route")},
            {"type": "visit", "route": "registry"},
        )
        self.assertEqual(fcm_message.data["notificationId"], str(Notification.query.one().id))
        self.assertEqual(fcm_message.android.priority, "high")
        self.assertEqual(Notification.query.count(), 1)

    def test_push_from_rolled_back_notification_is_not_sent_later(self):
        self.client.post(
            "/api/push-tokens",
            headers=self.auth(self.resident),
            json={"token": "fcm-token", "deviceId": "device-1"},
        )
        with (
            patch.object(notification_service, "_get_firebase_app", return_value=object()),
            patch.object(notification_service.messaging, "send_each_for_multicast") as send,
        ):
            notification_service.notify_user(
                self.resident.id, "No committed", "This must not send.", "pqrs"
            )
            db.session.flush()
            db.session.rollback()
            self.assertEqual(send.call_count, 0)
            notification_service.notify_user(
                self.resident.id, "Committed", "This can send.", "pqrs"
            )
            db.session.commit()
        self.assertEqual(send.call_count, 1)

    def test_invalid_default_firebase_credentials_do_not_fail_committed_notification(self):
        self.client.post(
            "/api/push-tokens",
            headers=self.auth(self.resident),
            json={"token": "fcm-token", "deviceId": "device-1"},
        )
        with (
            patch.dict(
                os.environ,
                {
                    "FIREBASE_SERVICE_ACCOUNT_JSON": "",
                    "GOOGLE_APPLICATION_CREDENTIALS": "missing-service-account.json",
                },
            ),
            patch.object(
                notification_service,
                "initialize_app",
                side_effect=DefaultCredentialsError("Invalid application credentials."),
            ),
        ):
            notification_service._firebase_app = None
            notification_service.notify_user(
                self.resident.id,
                "Visitante esperando",
                "Autoriza su ingreso.",
                "visit",
            )
            db.session.commit()

        self.assertEqual(Notification.query.count(), 1)

    def test_package_delivery_requires_receiver_and_notifies_resident(self):
        package = PackageItem(
            resident_id=self.resident.id,
            registered_by=self.guard.id,
            description="Caja",
        )
        db.session.add(package)
        db.session.commit()
        response = self.client.put(
            f"/api/packages/{package.id}/deliver",
            headers=self.auth(self.guard),
            json={"receivedBy": "  "},
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.put(
            f"/api/packages/{package.id}/deliver",
            headers=self.auth(self.guard),
            json={"receivedBy": "María Pérez"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["packageItem"]["deliveredTo"], "María Pérez")
        self.assertEqual(response.get_json()["packageItem"]["deliveredByName"], "Guard")
        self.assertEqual(Notification.query.filter_by(user_id=self.resident.id).count(), 1)


if __name__ == "__main__":
    unittest.main()
