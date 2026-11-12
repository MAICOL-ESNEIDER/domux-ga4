"""Pruebas del inicio de la web: el panel de pendientes (HU-081) y las notificaciones (HU-064)."""

import unittest
from datetime import timedelta

from extensions import db
from models import CommonArea, Notification, PackageItem, Pqrs, Reservation
from time_utils import colombia_day_to_utc, colombia_today, utc_now
from web_testing import WebTestCase


class WebPanelTests(WebTestCase):
    def setUp(self):
        super().setUp()
        self.area = CommonArea(name="Salón social", capacity=30)
        db.session.add(self.area)
        db.session.commit()
        self.log_in()

    def pqrs(self, subject="Ascensor dañado", status="abierta", days_ago=0):
        item = Pqrs(
            resident_id=self.resident.id, category="Daño", subject=subject, message="Detalle", status=status,
            created_at=colombia_day_to_utc(colombia_today() - timedelta(days=days_ago)) + timedelta(hours=14),
        )
        db.session.add(item)
        db.session.commit()
        return item

    def reservation(self, status="pendiente", day_offset=3, slot="08:00 - 10:00"):
        item = Reservation(
            resident_id=self.resident.id, common_area_id=self.area.id, status=status, attendees=10,
            date=(colombia_today() + timedelta(days=day_offset)).isoformat(), time_slot=slot,
        )
        db.session.add(item)
        db.session.commit()
        return item

    # --- El panel ---------------------------------------------------------------------------------

    def test_empty_panel_says_everything_is_up_to_date(self):
        body = self.page("/web/")
        self.assertIn("Hola, Lucía", body)
        self.assertIn("Todo al día", body)
        self.assertIn("No hay PQRS en trámite", body)
        self.assertIn("No hay reservas esperando decisión", body)

    def test_panel_shows_counters_and_urgent_rows(self):
        self.pqrs("Ascensor dañado", days_ago=40)       # vencida
        self.pqrs("Fuga en el parqueadero", status="en_proceso")
        self.pqrs("Ya resuelta", status="resuelta", days_ago=40)
        self.reservation()
        db.session.add(PackageItem(
            resident_id=self.resident.id, registered_by=self.guard.id, description="Caja", status="pendiente",
            arrived_at=utc_now() - timedelta(hours=80),
        ))
        db.session.commit()

        body = self.page("/web/")
        self.assertIn("PQRS abiertas", body)
        self.assertIn("1 vencida", body)
        self.assertIn("Reservas por aprobar", body)
        self.assertIn("Paquetes con más de 48 horas", body)
        self.assertIn("1 lleva más de 72 horas", body)
        self.assertIn("Ascensor dañado", body)
        self.assertIn("Fuga en el parqueadero", body)
        self.assertNotIn("Ya resuelta", body)
        self.assertIn("Vencida hace", body)           # el plazo se dice con palabras, no solo con color
        self.assertIn("Torre 1 · Apto 101", body)
        self.assertIn("Marta", body)
        self.assertIn("Salón social", body)
        self.assertIn("PQRS-", body)

    def test_text_written_by_residents_is_escaped(self):
        self.pqrs("<script>alert(1)</script>")
        body = self.page("/web/")
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)

    # --- Aprobar y rechazar desde el panel ---------------------------------------------------------

    def test_approving_from_the_panel_updates_the_reservation_and_tells_the_resident(self):
        item = self.reservation()
        response = self.post(f"/web/reservas/{item.id}/decision", {"decision": "aprobada", "next": "/web/"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/web/"))

        self.assertEqual(db.session.get(Reservation, item.id).status, "aprobada")
        notice = Notification.query.filter_by(user_id=self.resident.id).one()
        self.assertIn("aprobada", notice.message)

        body = self.page("/web/")
        self.assertIn("Reserva aprobada. Se le avisó al residente.", body)
        self.assertIn("No hay reservas esperando decisión", body)

    def test_rejecting_from_the_panel(self):
        item = self.reservation()
        self.post(f"/web/reservas/{item.id}/decision", {"decision": "rechazada"})
        self.assertEqual(db.session.get(Reservation, item.id).status, "rechazada")
        self.assertIn("Reserva rechazada", self.page("/web/"))

    def test_approving_a_taken_slot_shows_the_servers_message_and_changes_nothing(self):
        self.reservation(status="aprobada")
        waiting = self.reservation(status="pendiente")  # mismo horario
        self.post(f"/web/reservas/{waiting.id}/decision", {"decision": "aprobada"})
        self.assertEqual(db.session.get(Reservation, waiting.id).status, "pendiente")
        self.assertIn("Ese horario ya no está disponible", self.page("/web/"))

    def test_an_unknown_decision_or_reservation_is_refused_politely(self):
        item = self.reservation()
        self.post(f"/web/reservas/{item.id}/decision", {"decision": "borrar"})
        self.assertEqual(db.session.get(Reservation, item.id).status, "pendiente")
        self.assertIn("Elige si quieres aprobar o rechazar", self.page("/web/"))

        self.post("/web/reservas/9999/decision", {"decision": "aprobada"})
        self.assertIn("Reserva no encontrada", self.page("/web/"))

    def test_decision_needs_the_csrf_code_and_a_session(self):
        item = self.reservation()
        self.assertEqual(self.client.post(f"/web/reservas/{item.id}/decision", data={"decision": "aprobada"}).status_code, 400)
        self.assertEqual(db.session.get(Reservation, item.id).status, "pendiente")

        anonymous = self.app.test_client()
        response = anonymous.post(f"/web/reservas/{item.id}/decision", data={"decision": "aprobada"})
        self.assertEqual(response.status_code, 400)  # sin sesión tampoco hay código válido

    def test_the_return_page_never_leaves_the_web(self):
        item = self.reservation()
        response = self.post(f"/web/reservas/{item.id}/decision", {"decision": "rechazada", "next": "https://malo.example/"})
        self.assertTrue(response.headers["Location"].endswith("/web/"))

    # --- Notificaciones ---------------------------------------------------------------------------

    def notify(self, user, title, read=False, kind="general"):
        item = Notification(user_id=user.id, title=title, message=f"Texto de {title}", type=kind, is_read=read)
        db.session.add(item)
        db.session.commit()
        return item

    def test_notifications_show_the_administrators_own_and_count_unread_in_the_menu(self):
        self.notify(self.admin, "Nueva PQRS", kind="pqrs")
        self.notify(self.admin, "Reserva pedida", kind="reservation")
        self.notify(self.admin, "Aviso viejo", read=True)
        self.notify(self.resident, "Solo de la residente")

        body = self.page("/web/notificaciones")
        self.assertIn("2 avisos sin leer", body)
        self.assertIn("Nueva PQRS", body)
        self.assertIn("Aviso viejo", body)
        self.assertNotIn("Solo de la residente", body)
        self.assertIn("PQRS", body)
        self.assertIn('class="nav-badge"', body)

    def test_unread_filter_and_marking_one_as_read(self):
        first = self.notify(self.admin, "Primero")
        self.notify(self.admin, "Segundo", read=True)

        only_unread = self.page("/web/notificaciones?filtro=sin-leer")
        self.assertIn("Primero", only_unread)
        self.assertNotIn("Segundo", only_unread)

        response = self.post(f"/web/notificaciones/{first.id}/leida", {"filtro": "sin-leer"})
        self.assertTrue(response.headers["Location"].endswith("?filtro=sin-leer"))
        self.assertTrue(db.session.get(Notification, first.id).is_read)
        self.assertIn("Estás al día", self.page("/web/notificaciones"))

    def test_marking_all_as_read_leaves_other_peoples_notifications_alone(self):
        self.notify(self.admin, "Uno")
        self.notify(self.admin, "Dos")
        other = self.notify(self.resident, "De la residente")
        self.post("/web/notificaciones/leidas")
        self.assertEqual(Notification.query.filter_by(user_id=self.admin.id, is_read=False).count(), 0)
        self.assertFalse(db.session.get(Notification, other.id).is_read)

    def test_notifications_are_paginated(self):
        for number in range(25):
            self.notify(self.admin, f"Aviso {number:02d}")
        first = self.page("/web/notificaciones")
        self.assertIn("Página 1 de 2", first)
        second = self.page("/web/notificaciones?page=2")
        self.assertIn("Página 2 de 2", second)
        self.assertEqual(self.client.get("/web/notificaciones?page=99").status_code, 200)  # se lleva a la última

    def test_notification_pages_need_a_session(self):
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.get("/web/notificaciones").status_code, 302)


if __name__ == "__main__":
    unittest.main()
