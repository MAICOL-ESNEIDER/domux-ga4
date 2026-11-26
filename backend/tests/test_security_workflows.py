import os
import unittest
from datetime import timedelta
from unittest.mock import patch

from google.auth.exceptions import DefaultCredentialsError
from sqlalchemy import inspect

os.environ["DATABASE_URL"] = "sqlite://"

from app import (
    create_app,
    migrate_legacy_package_statuses,
    migrate_sqlite_schema,
)
from auth import generate_token
from extensions import db
from models import (
    AuditLog,
    Announcement,
    DevicePushToken,
    Notification,
    PackageItem,
    User,
    Visit,
    VisitQrPass,
)
from routes.auth import limiter
from services import notification_service
from werkzeug.security import generate_password_hash
from time_utils import now_colombia
from validators import validate_media_url


class SecurityWorkflowTests(unittest.TestCase):
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
            phone="3001234567",
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
            "documentRefused": True,
        }
        data.update(fields)
        return self.client.post("/api/visits", headers=self.auth(self.guard), json=data)

    def make_qr(self, max_people=1, **fields):
        start = now_colombia().date()
        end = start + timedelta(days=1)
        data = {
            "visitorName": "Visita de prueba",
            "visitorDocument": "QR-123456",
            "validFrom": start.isoformat(),
            "validUntil": end.isoformat(),
            "maxGuests": max_people,
        }
        data.update(fields)
        response = self.client.post(
            "/api/visits/qr-passes",
            headers=self.auth(self.resident),
            json=data,
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()["qrPass"]

    def test_visit_needs_consent_for_document_and_notifies_resident(self):
        response = self.register_visit(
            visitorDocument="1234",
            documentRefused=False,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Visit.query.count(), 0)

    def test_inactive_accounts_are_blocked_from_old_tokens_and_login(self):
        headers = self.auth(self.resident)
        self.resident.is_active = False
        db.session.commit()

        old_token = self.client.get("/api/auth/session", headers=headers)
        login = self.client.post(
            "/api/auth/login",
            json={"email": self.resident.email, "password": "Resident123*"},
        )

        self.assertEqual(old_token.status_code, 403)
        self.assertEqual(login.status_code, 403)
        expected = "Tu cuenta se encuentra desactivada. Contacta a administración."
        self.assertEqual(old_token.json["error"], expected)
        self.assertEqual(login.json["error"], expected)

    def test_password_change_invalidates_the_previous_token(self):
        old_token = self.auth(self.resident)["Authorization"]
        response = self.client.post(
            "/api/auth/change-password",
            headers={"Authorization": old_token},
            json={
                "currentPassword": "Resident123*",
                "newPassword": "UpdatedResident123*",
            },
        )
        old_session = self.client.get(
            "/api/auth/session",
            headers={"Authorization": old_token},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(old_session.status_code, 401)
        self.assertEqual(self.resident.token_version, 2)

    def test_deactivation_invalidates_the_previous_token(self):
        old_token = self.auth(self.resident)["Authorization"]
        response = self.client.put(
            f"/api/users/{self.resident.id}",
            headers=self.auth(self.admin),
            json={"isActive": False},
        )
        old_session = self.client.get(
            "/api/auth/session",
            headers={"Authorization": old_token},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(old_session.status_code, 401)

    def test_visit_photo_is_saved_when_consent_is_given(self):
        response = self.register_visit(
            visitorDocument="1234",
            documentRefused=False,
            mediaConsent=True,
            mediaUrl="data:image/jpeg;base64,AA==",
            mediaType="image",
        )
        self.assertEqual(response.status_code, 201)
        visit = Visit.query.one()
        self.assertEqual(visit.visitor_document, "1234")
        self.assertTrue(visit.media_consent)
        self.assertFalse(visit.document_refused)
        self.assertFalse(response.json["visit"]["documentRefused"])
        self.assertEqual(Notification.query.filter_by(user_id=self.resident.id).count(), 1)

    def test_visit_requires_document_or_explicit_refusal(self):
        response = self.register_visit(
            visitorDocument="",
            documentRefused=False,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json["error"],
            "El documento de identidad del visitante es obligatorio, o debes marcar que se negó a suministrarlo.",
        )
        self.assertEqual(Visit.query.count(), 0)

    def test_refused_document_is_recorded_without_document_consent(self):
        response = self.register_visit(
            visitorDocument="",
            documentRefused=True,
        )

        self.assertEqual(response.status_code, 201)
        visit = Visit.query.one()
        self.assertEqual(visit.visitor_document, "NO SUMINISTRADO")
        self.assertTrue(visit.document_refused)
        self.assertFalse(visit.media_consent)
        self.assertTrue(response.json["visit"]["documentRefused"])

    def test_announcement_and_package_reject_past_event_dates(self):
        yesterday = (now_colombia().date() - timedelta(days=1)).isoformat()
        announcement = self.client.post(
            "/api/announcements",
            headers=self.auth(self.admin),
            json={
                "title": "Evento vencido",
                "message": "No se debe publicar.",
                "eventDate": yesterday,
            },
        )
        package = self.client.post(
            "/api/packages",
            headers=self.auth(self.guard),
            json={
                "residentId": self.resident.id,
                "description": "Evento vencido",
                "eventDate": yesterday,
            },
        )

        self.assertEqual(announcement.status_code, 400)
        self.assertEqual(package.status_code, 400)
        self.assertEqual(Announcement.query.count(), 0)
        self.assertEqual(PackageItem.query.count(), 0)

    def test_package_arrival_rejects_future_dates(self):
        tomorrow = (now_colombia().date() + timedelta(days=1)).isoformat()
        response = self.client.post(
            "/api/packages",
            headers=self.auth(self.guard),
            json={
                "residentId": self.resident.id,
                "description": "Llegada futura",
                "eventDate": tomorrow,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(PackageItem.query.count(), 0)

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
        self.assertTrue(exit_response.json["visit"]["referenceCode"].startswith(
            f"VIS-{now_colombia().year}-"
        ))

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

    def test_notifications_only_list_for_the_authenticated_user(self):
        resident_notification = Notification(
            user_id=self.resident.id,
            title="Aviso propio",
            message="Notificación para el residente.",
        )
        other_notification = Notification(
            user_id=self.other_resident.id,
            title="Aviso ajeno",
            message="Notificación para otro residente.",
        )
        db.session.add_all([resident_notification, other_notification])
        db.session.commit()

        response = self.client.get(
            "/api/notifications",
            headers=self.auth(self.resident),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.get_json()["notifications"]],
            [resident_notification.id],
        )

    def test_read_notification_cleanup_is_scoped_to_user_and_read_state(self):
        read_notification = Notification(
            user_id=self.resident.id,
            title="Leída",
            message="Se puede limpiar",
            is_read=True,
        )
        unread_notification = Notification(
            user_id=self.resident.id,
            title="No leída",
            message="Debe conservarse",
            is_read=False,
        )
        foreign_notification = Notification(
            user_id=self.other_resident.id,
            title="Leída ajena",
            message="No se debe eliminar",
            is_read=True,
        )
        db.session.add_all([read_notification, unread_notification, foreign_notification])
        db.session.commit()
        read_id = read_notification.id
        unread_id = unread_notification.id
        foreign_id = foreign_notification.id

        deleted = self.client.delete(
            "/api/notifications/read",
            headers=self.auth(self.resident),
        )

        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json["deletedCount"], 1)
        self.assertEqual(Notification.query.filter_by(id=read_id).count(), 0)
        self.assertEqual(Notification.query.filter_by(id=unread_id).count(), 1)
        self.assertEqual(Notification.query.filter_by(id=foreign_id).count(), 1)

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
        response_package = registration.get_json()["packageItem"]
        self.assertEqual(registration.get_json()["packageItem"]["status"], "pendiente")
        self.assertEqual(
            response_package["referenceCode"],
            f"PAQ-{now_colombia().year}-{package_id:04d}",
        )
        self.assertEqual(response_package["eventDate"], now_colombia().date().isoformat())
        self.assertRegex(response_package["eventTime"], r"^\d{2}:\d{2}$")
        self.assertIn(
            "Resident (Torre 1 · Apto 101)",
            Notification.query.filter_by(user_id=self.resident.id).one().message,
        )
        legacy_filter = self.client.get(
            "/api/packages?status=por_llegar",
            headers=self.auth(self.guard),
        )
        self.assertEqual(
            [item["id"] for item in legacy_filter.get_json()["packages"]],
            [package_id],
        )

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
            json={"status": "por_llegar"},
        )
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.get_json()["packageItem"]["status"], "pendiente")
        self.assertEqual(
            Notification.query.filter_by(user_id=self.resident.id).count(),
            1,
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
        self.assertEqual(forced_delete.status_code, 403)
        self.assertIn("no pueden eliminarse definitivamente", forced_delete.json["error"])
        self.assertIsNotNone(db.session.get(PackageItem, package_id))

    def test_visit_serializer_includes_resident_phone(self):
        visit = Visit(
            resident_id=self.resident.id,
            registered_by=self.guard.id,
            visitor_name="Visitante",
            type="visitante",
            resident=self.resident,
        )

        self.assertEqual(visit.to_dict()["residentPhone"], "3001234567")

    def test_login_rate_limit_is_scoped_by_ip_and_normalized_email(self):
        self.app.config["RATELIMIT_ENABLED"] = True
        limiter.enabled = True
        try:
            responses = [
                self.client.post(
                    "/api/auth/login",
                    json={
                        "email": (
                            "LOCKOUT@test.local"
                            if attempt % 2
                            else " lockout@test.local "
                        ),
                        "password": "WrongPassword123*",
                    },
                )
                for attempt in range(6)
            ]
        finally:
            limiter.enabled = False
            self.app.config["RATELIMIT_ENABLED"] = False

        self.assertEqual([response.status_code for response in responses[:5]], [401] * 5)
        self.assertEqual(responses[5].status_code, 429)
        self.assertEqual(
            responses[5].json["error"],
            "Demasiados intentos de inicio de sesión. Intenta nuevamente en un minuto.",
        )
        self.assertEqual(
            AuditLog.query.filter_by(action="login_rate_limited").count(),
            1,
        )

    def test_media_url_validation_and_rejection_of_external_hosts(self):
        valid_image = "data:image/png;base64,AA=="
        valid_pdf = "data:application/pdf;base64,JVBERiQ="
        self.assertIsNone(validate_media_url(valid_image))
        self.assertIsNone(validate_media_url(valid_pdf))

        accepted = self.client.post(
            "/api/announcements",
            headers=self.auth(self.admin),
            json={
                "title": "Anuncio con imagen",
                "message": "Contenido válido",
                "mediaUrl": valid_image,
                "mediaType": "image",
            },
        )
        rejected = self.client.post(
            "/api/announcements",
            headers=self.auth(self.admin),
            json={
                "title": "Anuncio externo",
                "message": "URL no permitida",
                "mediaUrl": "https://arbitrary.example/image.png",
                "mediaType": "image",
            },
        )

        self.assertEqual(accepted.status_code, 201)
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(Announcement.query.count(), 1)

    def test_qr_pass_and_announcement_notify_active_guards(self):
        inactive_guard = User(
            name="Inactive Guard",
            email="inactive-guard@test.local",
            password_hash=generate_password_hash("Guard123*"),
            role="GUARD",
            is_active=False,
        )
        db.session.add(inactive_guard)
        db.session.commit()
        start = now_colombia().date().isoformat()
        qr_payload = {
            "visitorName": "Invitado",
            "visitorDocument": "QR-123",
            "validFrom": start,
        }

        resident_qr = self.client.post(
            "/api/visits/qr-passes",
            headers=self.auth(self.resident),
            json=qr_payload,
        )
        admin_qr = self.client.post(
            "/api/visits/qr-passes",
            headers=self.auth(self.admin),
            json={**qr_payload, "residentId": self.resident.id},
        )
        announcement = self.client.post(
            "/api/announcements",
            headers=self.auth(self.admin),
            json={"title": "Aviso", "message": "Nuevo anuncio"},
        )

        self.assertEqual(resident_qr.status_code, 201)
        self.assertEqual(admin_qr.status_code, 201)
        self.assertEqual(announcement.status_code, 201)
        self.assertEqual(Notification.query.filter_by(user_id=self.guard.id).count(), 3)
        self.assertEqual(
            Notification.query.filter_by(user_id=inactive_guard.id).count(),
            0,
        )

    def test_app_migrates_legacy_package_statuses(self):
        package = PackageItem(
            resident_id=self.resident.id,
            registered_by=self.guard.id,
            description="Paquete legado",
            status="por_llegar",
        )
        db.session.add(package)
        db.session.commit()

        migrate_legacy_package_statuses()
        db.session.refresh(package)

        self.assertEqual(package.status, "pendiente")

    def test_sqlite_migration_adds_delivery_media_and_qr_guests_columns(self):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                'ALTER TABLE "packages" DROP COLUMN "delivery_media_url"'
            )
            connection.exec_driver_sql(
                'ALTER TABLE "visit_qr_passes" DROP COLUMN "guests_json"'
            )

        migrate_sqlite_schema()

        inspector = inspect(db.engine)
        package_columns = {column["name"] for column in inspector.get_columns("packages")}
        qr_columns = {
            column["name"] for column in inspector.get_columns("visit_qr_passes")
        }
        self.assertIn("delivery_media_url", package_columns)
        self.assertIn("guests_json", qr_columns)

    def test_package_listing_archives_expired_items_without_purging_history(self):
        expired_delivery = PackageItem(
            resident_id=self.resident.id,
            registered_by=self.guard.id,
            description="Entrega antigua",
            status="entregado",
            delivered_at=now_colombia() - timedelta(days=8),
        )
        expired_trash = PackageItem(
            resident_id=self.other_resident.id,
            registered_by=self.guard.id,
            description="Papelera antigua",
            is_deleted=True,
            deleted_at=now_colombia() - timedelta(days=31),
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
            {item["id"] for item in response.get_json()["packages"]},
            {expired_delivery_id, expired_trash_id},
        )
        self.assertTrue(db.session.get(PackageItem, expired_delivery_id).is_deleted)
        self.assertIsNotNone(db.session.get(PackageItem, expired_trash_id))


    def test_qr_limits_new_people_allows_same_day_reentry_and_revokes(self):
        qr = self.make_qr(max_people=2)
        token = qr["token"]
        first = self.client.post(
            f"/api/visits/qr/{token}/entry",
            headers=self.auth(self.guard),
            json={},
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
            json={},
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

    def test_qr_rejects_more_than_five_guests(self):
        response = self.client.post(
            "/api/visits/qr",
            headers=self.auth(self.resident),
            json={
                "visitorName": "Visita",
                "visitorDocument": "123456",
                "validFrom": now_colombia().date().isoformat(),
                "maxGuests": 6,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(VisitQrPass.query.count(), 0)

    def test_qr_accepts_pre_registered_guests_and_uses_each_identity(self):
        qr = self.make_qr(
            max_people=2,
            guests=[
                {"fullName": "Ana Invitada", "document": "DOC-1"},
                {"fullName": "Luis Invitado", "document": "DOC-2"},
            ],
        )
        created = VisitQrPass.query.one()
        self.assertEqual(
            created.to_dict()["guests"],
            [
                {"fullName": "Ana Invitada", "document": "DOC-1"},
                {"fullName": "Luis Invitado", "document": "DOC-2"},
            ],
        )
        for expected_name, expected_document in (
            ("Ana Invitada", "DOC-1"),
            ("Luis Invitado", "DOC-2"),
        ):
            response = self.client.post(
                f"/api/visits/qr/{qr['token']}/entry",
                headers=self.auth(self.guard),
                json={},
            )
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json["visit"]["visitorName"], expected_name)
            self.assertEqual(response.json["visit"]["visitorDocument"], expected_document)

        inspected = self.client.get(
            f"/api/visits/qr/{qr['token']}",
            headers=self.auth(self.guard),
        )
        self.assertEqual(inspected.json["qrPass"]["guests"], created.to_dict()["guests"])

    def test_qr_rejects_more_guests_than_max_guests(self):
        response = self.client.post(
            "/api/visits/qr",
            headers=self.auth(self.resident),
            json={
                "validFrom": now_colombia().date().isoformat(),
                "maxGuests": 1,
                "guests": [
                    {"fullName": "Ana", "document": "DOC-1"},
                    {"fullName": "Luis", "document": "DOC-2"},
                ],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(VisitQrPass.query.count(), 0)

    def test_qr_defaults_to_one_guest_and_24_hour_validity(self):
        start = now_colombia().date()
        response = self.client.post(
            "/api/visits/qr",
            headers=self.auth(self.resident),
            json={
                "visitorName": "Visita",
                "visitorDocument": "123456",
                "validFrom": start.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 201)
        qr = response.json["qrPass"]
        self.assertEqual(qr["validUntil"], (start + timedelta(days=1)).isoformat())
        self.assertEqual(qr["maxGuests"], 1)
        self.assertEqual(qr["usedEntries"], 0)
        self.assertEqual(qr["remainingEntries"], 1)

    def test_qr_rejects_validity_longer_than_72_hours_and_foreign_revoke(self):
        today = now_colombia().date().isoformat()
        too_long = self.client.post(
            "/api/visits/qr-passes",
            headers=self.auth(self.resident),
            json={
                "visitorName": "Visita",
                "visitorDocument": "123456",
                "validFrom": today,
                "validUntil": (now_colombia().date() + timedelta(days=4)).isoformat(),
                "maxGuests": 2,
            },
        )
        self.assertEqual(too_long.status_code, 400)
        qr = self.make_qr()
        forbidden = self.client.put(
            f"/api/visits/qr-passes/{qr['id']}/revoke",
            headers=self.auth(self.other_resident),
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_qr_consumes_entry_slots_and_prefills_visitor_identity(self):
        qr = self.make_qr(max_people=2)
        token = qr["token"]

        first = self.client.post(
            f"/api/visits/qr/{token}/entry",
            headers=self.auth(self.guard),
            json={},
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json["visit"]["visitorName"], "Visita de prueba")
        self.assertEqual(first.json["visit"]["visitorDocument"], "QR-123456")

        second = self.client.post(
            f"/api/visits/qr/{token}/entry",
            headers=self.auth(self.guard),
            json={},
        )
        self.assertEqual(second.status_code, 201)
        full = self.client.post(
            f"/api/visits/qr/{token}/entry",
            headers=self.auth(self.guard),
            json={},
        )
        self.assertEqual(full.status_code, 409)

        qr_response = self.client.get(
            f"/api/visits/qr/{token}",
            headers=self.auth(self.guard),
        )
        qr_data = qr_response.json["qrPass"]
        self.assertEqual(qr_data["visitorName"], "Visita de prueba")
        self.assertEqual(qr_data["visitorDocument"], "QR-123456")
        self.assertEqual(qr_data["maxGuests"], 2)
        self.assertEqual(qr_data["usedEntries"], 2)
        self.assertEqual(qr_data["remainingEntries"], 0)
        self.assertFalse(qr_response.json["canRegister"])
        self.assertEqual(
            Notification.query.filter_by(user_id=self.resident.id).count(),
            2,
        )

    def test_visit_to_dict_reports_overstay_limits_by_visitor_type(self):
        stay_limits = {
            "domiciliario": 2,
            "contratista": 10,
            "visitante": 24,
        }
        visits = [
            Visit(
                resident_id=self.resident.id,
                registered_by=self.guard.id,
                visitor_name=f"Visita {visitor_type}",
                type=visitor_type,
                entered_at=now_colombia() - timedelta(hours=hours, minutes=1),
            )
            for visitor_type, hours in stay_limits.items()
        ]
        db.session.add_all(visits)
        db.session.commit()

        for visit in visits:
            result = visit.to_dict()
            self.assertEqual(result["maxStayHours"], stay_limits[visit.type])
            self.assertTrue(result["overstayWarning"])

        visits[0].exited_at = now_colombia()
        self.assertFalse(visits[0].to_dict()["overstayWarning"])

    def test_admin_must_select_a_resident_before_creating_a_qr_pass(self):
        today = now_colombia().date().isoformat()
        response = self.client.post(
            "/api/visits/qr-passes",
            headers=self.auth(self.admin),
            json={"validFrom": today, "validUntil": today, "maxPeople": 1},
        )
        self.assertEqual(response.status_code, 400)
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
            "/api/notifications/device-token",
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
        self.assertIsNone(fcm_message.notification)
        self.assertEqual(fcm_message.data["title"], "Visitante esperando")
        self.assertEqual(fcm_message.data["message"], "Autoriza su ingreso.")
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
            json={
                "receivedBy": "María Pérez",
                "deliveryMediaUrl": "data:image/jpeg;base64,AA==",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["packageItem"]["deliveredTo"], "María Pérez")
        self.assertEqual(response.get_json()["packageItem"]["deliveredByName"], "Guard")
        self.assertEqual(
            response.get_json()["packageItem"]["deliveryMediaUrl"],
            "data:image/jpeg;base64,AA==",
        )
        self.assertEqual(Notification.query.filter_by(user_id=self.resident.id).count(), 1)


if __name__ == "__main__":
    unittest.main()
