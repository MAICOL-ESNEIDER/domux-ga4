"""Pruebas del resumen de pendientes de la administración (HU-081) y de «marcar todas como leídas» (HU-064)."""

import unittest
from datetime import timedelta

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import generate_password_hash

from app import create_app
from auth import generate_token
from business_days import is_business_day
from extensions import db
from models import CommonArea, Notification, PackageItem, Pqrs, Reservation, User
from structure_fixtures import apartment_for
from time_utils import colombia_day_to_utc, colombia_today, utc_now


class AdminSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.admin = self.person("ADMIN", "admin-resumen@test.local", "Lucía")
        self.guard = self.person("GUARD", "guardia-resumen@test.local", "Guardia")
        self.resident = self.person(
            "RESIDENT", "residente-resumen@test.local", "Marta",
            apartment_ref=apartment_for("Torre 1 · 101"), phone="3000000000", occupancy_type="propietario",
        )
        self.area = CommonArea(name="Salón social", capacity=30)
        db.session.add(self.area)
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def person(self, role, email, name, **fields):
        user = User(
            name=name, email=email, role=role, is_active=True,
            password_hash=generate_password_hash("Clave-de-prueba-1*"), **fields,
        )
        db.session.add(user)
        db.session.flush()
        return user

    def get_summary(self, user=None):
        user = user or self.admin
        return self.client.get("/api/admin/summary", headers={"Authorization": f"Bearer {generate_token(user)}"})

    def business_days_ago(self, count):
        """El día de Colombia que quedó hace ese número de días hábiles."""
        day = colombia_today()
        passed = 0
        while passed < count:
            day -= timedelta(days=1)
            if is_business_day(day):
                passed += 1
        return day

    def pqrs(self, created_day, status="abierta", subject="Ascensor", **fields):
        item = Pqrs(
            resident_id=self.resident.id, category="Daño", subject=subject, message="Mensaje largo",
            status=status, created_at=colombia_day_to_utc(created_day) + timedelta(hours=14), **fields,
        )
        db.session.add(item)
        db.session.flush()
        return item

    # --- Permisos ---------------------------------------------------------------------------------

    def test_only_the_administration_can_see_the_summary(self):
        self.assertEqual(self.client.get("/api/admin/summary").status_code, 401)
        self.assertEqual(self.get_summary(self.guard).status_code, 403)
        self.assertEqual(self.get_summary(self.resident).status_code, 403)
        self.assertEqual(self.get_summary().status_code, 200)

    def test_summary_of_an_empty_building_is_all_zeros(self):
        body = self.get_summary().get_json()
        self.assertEqual(set(body["counts"].values()), {0})
        self.assertEqual(body["urgentPqrs"], [])
        self.assertEqual(body["pendingReservations"], [])

    # --- PQRS -------------------------------------------------------------------------------------

    def test_pqrs_counts_and_the_most_urgent_go_first(self):
        green = self.pqrs(colombia_today(), subject="Verde")
        yellow = self.pqrs(self.business_days_ago(12), subject="Amarilla")
        red = self.pqrs(self.business_days_ago(20), subject="Roja", status="en_proceso")
        self.pqrs(self.business_days_ago(30), subject="Resuelta", status="resuelta")
        self.pqrs(self.business_days_ago(30), subject="Archivada", is_archived=True)
        db.session.commit()

        body = self.get_summary().get_json()
        counts = body["counts"]
        self.assertEqual((counts["pqrsOpen"], counts["pqrsOverdue"], counts["pqrsDueSoon"]), (3, 1, 1))

        rows = body["urgentPqrs"]
        self.assertEqual([row["id"] for row in rows], [red.id, yellow.id, green.id])
        self.assertEqual([row["semaphore"] for row in rows], ["rojo", "amarillo", "verde"])
        self.assertLess(rows[0]["daysRemaining"], 0)
        first = rows[0]
        self.assertTrue(first["radicado"].startswith("PQRS-"))
        self.assertEqual(first["residentName"], "Marta")
        self.assertEqual(first["apartment"], "Torre 1 · Apto 101")
        self.assertEqual(first["status"], "en_proceso")

    def test_pqrs_rows_are_light_and_limited(self):
        for number in range(10):
            self.pqrs(colombia_today(), subject=f"Caso {number}", media_url="data:image/png;base64,AAAA")
        db.session.commit()
        body = self.get_summary().get_json()
        self.assertEqual(body["counts"]["pqrsOpen"], 10)
        self.assertEqual(len(body["urgentPqrs"]), 8)
        for row in body["urgentPqrs"]:
            self.assertNotIn("message", row)
            self.assertNotIn("mediaUrl", row)
            self.assertNotIn("messages", row)

    # --- Reservas ---------------------------------------------------------------------------------

    def reservation(self, day_offset, status, archived=False, slot="08:00 - 10:00"):
        item = Reservation(
            resident_id=self.resident.id, common_area_id=self.area.id,
            date=(colombia_today() + timedelta(days=day_offset)).isoformat(), time_slot=slot,
            status=status, is_archived=archived, attendees=12,
        )
        db.session.add(item)
        db.session.flush()
        return item

    def test_reservations_waiting_for_a_decision_are_counted_by_date(self):
        later = self.reservation(9, "pendiente")
        sooner = self.reservation(2, "activa")
        self.reservation(3, "aprobada")
        self.reservation(4, "rechazada")
        self.reservation(5, "cancelada")
        self.reservation(6, "pendiente", archived=True)
        db.session.commit()

        body = self.get_summary().get_json()
        self.assertEqual(body["counts"]["reservationsPending"], 2)
        rows = body["pendingReservations"]
        self.assertEqual([row["id"] for row in rows], [sooner.id, later.id])
        self.assertEqual(rows[0]["commonAreaName"], "Salón social")
        self.assertEqual(rows[0]["residentName"], "Marta")
        self.assertEqual(rows[0]["attendees"], 12)

    # --- Paquetes ---------------------------------------------------------------------------------

    def package(self, hours, status="pendiente", deleted=False):
        item = PackageItem(
            resident_id=self.resident.id, registered_by=self.guard.id, description="Caja",
            status=status, is_deleted=deleted, arrived_at=utc_now() - timedelta(hours=hours),
        )
        db.session.add(item)
        return item

    def test_packages_over_48_and_72_hours_are_counted(self):
        self.package(10)              # reciente: no cuenta
        self.package(49)              # más de 48 horas
        self.package(80)              # más de 72 horas: cuenta en las dos
        self.package(100, status="entregado")
        self.package(100, deleted=True)
        db.session.commit()
        counts = self.get_summary().get_json()["counts"]
        self.assertEqual(counts["packagesOver48"], 2)
        self.assertEqual(counts["packagesOver72"], 1)

    # --- Notificaciones ---------------------------------------------------------------------------

    def notify(self, user, read=False, title="Aviso"):
        db.session.add(Notification(user_id=user.id, title=title, message="Texto", type="general", is_read=read))

    def test_unread_notifications_are_only_the_administrators(self):
        self.notify(self.admin)
        self.notify(self.admin)
        self.notify(self.admin, read=True)
        self.notify(self.resident)
        db.session.commit()
        self.assertEqual(self.get_summary().get_json()["counts"]["unreadNotifications"], 2)

    def test_mark_all_read_only_touches_the_users_own_notifications(self):
        self.notify(self.admin)
        self.notify(self.admin)
        self.notify(self.resident)
        db.session.commit()
        headers = {"Authorization": f"Bearer {generate_token(self.admin)}"}

        response = self.client.put("/api/notifications/read-all", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["updatedCount"], 2)
        self.assertEqual(self.get_summary().get_json()["counts"]["unreadNotifications"], 0)
        self.assertEqual(Notification.query.filter_by(user_id=self.resident.id, is_read=False).count(), 1)

        again = self.client.put("/api/notifications/read-all", headers=headers)
        self.assertEqual(again.get_json()["updatedCount"], 0)
        self.assertEqual(self.client.put("/api/notifications/read-all").status_code, 401)


if __name__ == "__main__":
    unittest.main()
