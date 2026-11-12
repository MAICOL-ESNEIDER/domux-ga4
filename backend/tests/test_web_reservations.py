"""Pruebas de las reservas en la web de administración (HU-079): la lista por estado con filtros, la reserva
al lado, aprobar, rechazar, cancelar, escribirle al residente y los adjuntos de la conversación."""

import base64
import html
import re
import unittest
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from extensions import db
from models import AuditLog, CommonArea, Notification, Reservation, ReservationMessage
from structure_fixtures import apartment_for
from time_utils import colombia_today
from web_testing import WebTestCase

PNG = b"\x89PNG\r\n\x1a\n" + b"imagen-de-prueba"
PHOTO = "data:image/png;base64," + base64.b64encode(PNG).decode()


class WebReservationCase(WebTestCase):
    def setUp(self):
        super().setUp()
        self.other = self.make_user(
            "RESIDENT", "carlos-web@test.local", "Carlos", last_name="Pérez",
            apartment_ref=apartment_for("Torre 2 · Apto 202"), occupancy_type="arrendatario",
        )
        self.hall = CommonArea(name="Salón social")
        self.pool = CommonArea(name="Piscina")
        db.session.add_all([self.hall, self.pool])
        db.session.commit()
        self.log_in()

    def day(self, offset):
        return (colombia_today() + timedelta(days=offset)).isoformat()

    def add(self, offset=3, slot="10:00-12:00", status="pendiente", area=None, resident=None, attendees=None,
            archived=False, by_admin=False, messages=()):
        """Una reserva guardada directamente; ``messages`` son pares (texto, adjunto) escritos por el residente."""
        resident = resident or self.resident
        reservation = Reservation(
            resident_id=resident.id, common_area_id=(area or self.hall).id, date=self.day(offset),
            time_slot=slot, attendees=attendees, status=status, is_archived=archived,
            created_by_admin_id=self.admin.id if by_admin else None,
        )
        db.session.add(reservation)
        db.session.flush()
        for text, media in messages:
            self.say(reservation, "RESIDENT", text, media=media, author=resident)
        db.session.commit()
        return reservation

    def say(self, reservation, role, text, media=None, author=None):
        message = ReservationMessage(
            reservation_id=reservation.id, author_id=(author or self.admin).id, author_role=role,
            message=text, media_url=media, media_type="image" if media else None,
        )
        db.session.add(message)
        db.session.commit()
        return message

    def reload(self, reservation):
        db.session.expire_all()
        return db.session.get(Reservation, reservation.id)

    @staticmethod
    def link_of(body, text):
        """La dirección del enlace que dice ``text``, con sus parámetros ya separados."""
        found = re.search(r'href="([^"]+)"[^>]*>\s*' + re.escape(text), body)
        assert found, f"no hay un enlace «{text}»"
        parts = urlsplit(html.unescape(found.group(1)))
        return parts.path, {key: values[0] for key, values in parse_qs(parts.query).items()}


class WebReservationListTests(WebReservationCase):
    def test_pages_ask_for_login(self):
        anonymous = self.app.test_client()
        for path in ("/web/reservas", "/web/reservas/1", "/web/reservas/1/mensajes/1/adjunto"):
            with self.subTest(path=path):
                response = anonymous.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/web/login", response.headers["Location"])
        # Sin sesión (y sin el código contra CSRF) los formularios no cambian nada.
        reservation = self.add(status="aprobada")
        for path, data in (
            (f"/web/reservas/{reservation.id}/decision", {"decision": "rechazada"}),
            (f"/web/reservas/{reservation.id}/cancelar", {}),
            (f"/web/reservas/{reservation.id}/mensaje", {"message": "Hola"}),
        ):
            with self.subTest(path=path):
                response = anonymous.post(path, data=data)
                self.assertIn(response.status_code, (302, 400))
        self.assertEqual(self.reload(reservation).status, "aprobada")
        self.assertEqual(ReservationMessage.query.count(), 0)

    def test_the_menu_and_the_panel_lead_to_the_list(self):
        self.add()
        body = self.page("/web/")
        self.assertIn('href="/web/reservas"', body)
        self.assertRegex(body, r'href="/web/reservas"[^>]*>\s*(?:<svg.*?</svg>\s*)?<span[^>]*>Reservas|Reservas por aprobar')
        self.assertIn("Ver todas las reservas", body)
        # El menú marca la página en la que se está.
        page = self.page("/web/reservas")
        self.assertRegex(page, r'<a[^>]*href="/web/reservas"[^>]*aria-current="page"|<a[^>]*aria-current="page"[^>]*href="/web/reservas"')

    def test_the_panel_links_each_pending_reservation_to_its_detail(self):
        reservation = self.add(attendees=12)
        body = self.page("/web/")
        self.assertRegex(
            body, rf'<a href="/web/reservas/{reservation.id}">Salón social<span class="sr-only"> del [^<]*Marta Ríos</span></a>',
        )

    def test_it_opens_on_what_waits_for_a_decision_with_the_numbers_of_every_tab(self):
        waiting = self.add(offset=5, attendees=40)
        legacy = self.add(offset=2, slot="14:00-16:00", status="activa", resident=self.other)
        self.add(offset=7, slot="08:00-10:00", status="aprobada")
        self.add(offset=8, slot="08:00-10:00", status="rechazada")
        self.add(offset=9, slot="08:00-10:00", status="cancelada")

        body = self.page("/web/reservas")

        self.assertIn("2 reservas", body)
        for tab in ("Por aprobar (2)", "Aprobadas (1)", "Rechazadas (1)", "Canceladas (1)", "Todas (5)"):
            self.assertIn(tab, body)
        self.assertRegex(body, r'aria-current="page">Por aprobar \(2\)')
        # Solo las que esperan decisión, la de fecha más próxima primero.
        self.assertIn(f'href="/web/reservas/{waiting.id}"', body)
        self.assertIn(f'href="/web/reservas/{legacy.id}"', body)
        self.assertLess(body.index(f"/web/reservas/{legacy.id}"), body.index(f"/web/reservas/{waiting.id}"))
        self.assertNotIn("Aprobada</span>", body)
        for text in ("Salón social", "Torre 1 · Apto 101", "Marta Ríos", "Torre 2 · Apto 202", "Carlos Pérez",
                     "10:00-12:00", "40 personas", "Pendiente", "Activa"):
            self.assertIn(text, body)
        self.assertIn(self.day(5)[8:] + "/" + self.day(5)[5:7] + "/" + self.day(5)[:4], body)
        # Sin una reserva elegida, la lista queda sola y a la derecha se invita a elegir una.
        self.assertNotIn("inbox-page has-detail", body)
        self.assertIn("Elige una reserva de la lista", body)

    def test_each_tab_shows_its_own_reservations(self):
        waiting = self.add(offset=2)
        approved = self.add(offset=3, status="aprobada")
        rejected = self.add(offset=4, status="rechazada")
        cancelled = self.add(offset=5, status="cancelada")

        for tab, expected in (
            ("por_aprobar", {waiting}), ("aprobada", {approved}), ("rechazada", {rejected}),
            ("cancelada", {cancelled}), ("todas", {waiting, approved, rejected, cancelled}),
        ):
            with self.subTest(tab=tab):
                body = self.page(f"/web/reservas?estado={tab}")
                shown = {item for item in (waiting, approved, rejected, cancelled)
                         if f'href="/web/reservas/{item.id}' in body}
                self.assertEqual(shown, expected)

    def test_an_unknown_tab_opens_the_default_one(self):
        waiting = self.add()
        self.add(offset=4, status="aprobada")
        body = self.page("/web/reservas?estado=inventada")
        self.assertIn(f'href="/web/reservas/{waiting.id}', body)
        self.assertRegex(body, r'aria-current="page">Por aprobar')

    def test_tab_links_keep_the_other_filters_and_the_default_tab_stays_out_of_the_address(self):
        self.add()
        body = self.page(f"/web/reservas?q=Marta&zona={self.hall.id}&desde={self.day(1)}")

        path, args = self.link_of(body, "Aprobadas")
        self.assertEqual(path, "/web/reservas")
        self.assertEqual(args, {"q": "Marta", "zona": str(self.hall.id), "desde": self.day(1), "estado": "aprobada"})
        path, args = self.link_of(body, "Por aprobar")
        self.assertNotIn("estado", args)
        self.assertEqual(args["q"], "Marta")

    def test_the_rows_say_how_many_messages_and_attachments_they_have(self):
        self.add(messages=[("Hola", None), ("Adjunto el recibo", PHOTO)], by_admin=True)
        body = self.page("/web/reservas")
        for text in ("2 mensajes", "1 adjunto", "Registrada por la administración"):
            self.assertIn(text, body)
        # Las fotos no viajan dentro de la página.
        self.assertNotIn("data:image", body)
        self.assertNotIn("base64", body)

    def test_filters_by_zone_search_and_dates_change_the_list_and_the_numbers(self):
        in_hall = self.add(offset=2)
        in_pool = self.add(offset=6, area=self.pool, resident=self.other)

        by_zone = self.page(f"/web/reservas?zona={self.pool.id}")
        self.assertIn(f"/web/reservas/{in_pool.id}", by_zone)
        self.assertNotIn(f"/web/reservas/{in_hall.id}", by_zone)
        self.assertIn("1 reserva con esos filtros", by_zone)
        self.assertIn("Por aprobar (1)", by_zone)
        self.assertIn("Quitar filtros", by_zone)

        by_text = self.page("/web/reservas?q=marta")
        self.assertIn(f"/web/reservas/{in_hall.id}", by_text)
        self.assertNotIn(f"/web/reservas/{in_pool.id}", by_text)
        self.assertIn(f"/web/reservas/{in_pool.id}", self.page("/web/reservas?q=202"))

        by_dates = self.page(f"/web/reservas?desde={self.day(5)}&hasta={self.day(7)}")
        self.assertIn(f"/web/reservas/{in_pool.id}", by_dates)
        self.assertNotIn(f"/web/reservas/{in_hall.id}", by_dates)

        nothing = self.page("/web/reservas?q=nadie")
        self.assertIn("No hay reservas que coincidan con esos filtros.", nothing)

    def test_quitar_filtros_keeps_the_tab_and_the_filters_keep_it_too(self):
        self.add(offset=4, status="aprobada")
        body = self.page("/web/reservas?estado=aprobada&q=nadie")
        path, args = self.link_of(body, "Quitar filtros")
        self.assertEqual((path, args), ("/web/reservas", {"estado": "aprobada"}))
        self.assertIn('<input type="hidden" name="estado" value="aprobada">', body)
        # En la pestaña que se abre sola no hace falta escribirla.
        self.assertNotIn('name="estado"', self.page("/web/reservas?q=nadie"))

    def test_archived_reservations_are_hidden_unless_asked(self):
        archived = self.add(archived=True)
        self.assertNotIn(f"/web/reservas/{archived.id}", self.page("/web/reservas"))
        body = self.page("/web/reservas?archivadas=1")
        self.assertIn(f"/web/reservas/{archived.id}", body)
        self.assertIn(">Archivada<", body)

    def test_a_date_that_is_not_a_date_is_ignored(self):
        reservation = self.add()
        body = self.page("/web/reservas?desde=basura&hasta=2026-02-30")
        self.assertIn(f"/web/reservas/{reservation.id}", body)
        self.assertNotIn("Quitar filtros", body)

    def test_dates_in_the_wrong_order_show_the_message_of_the_api(self):
        self.add()
        response = self.client.get(f"/web/reservas?desde={self.day(5)}&hasta={self.day(2)}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("La fecha &#39;dateFrom&#39; no puede ser posterior a &#39;dateTo&#39;.", self.text(response))
        self.assertIn("No hay reservas que coincidan con esos filtros.", self.text(response))

    def test_each_tab_has_its_own_empty_text(self):
        for tab, text in (
            ("por_aprobar", "No hay reservas esperando decisión."), ("aprobada", "No hay reservas aprobadas."),
            ("rechazada", "No hay reservas rechazadas."), ("cancelada", "No hay reservas canceladas."),
            ("todas", "Todavía no hay reservas."),
        ):
            with self.subTest(tab=tab):
                self.assertIn(text, self.page(f"/web/reservas?estado={tab}"))

    def test_long_lists_are_cut_in_pages(self):
        for number in range(17):
            self.add(offset=1 + number, slot="10:00-12:00")

        first = self.page("/web/reservas")
        second = self.page("/web/reservas?page=2")

        self.assertIn("Página 1 de 2", first)
        self.assertIn("Siguiente ›", first)
        self.assertIn("Página 2 de 2", second)
        self.assertIn("‹ Anterior", second)
        # Una página que ya no existe lleva a la última.
        response = self.client.get("/web/reservas?page=9")
        self.assertEqual(response.status_code, 302)
        self.assertIn("page=2", response.headers["Location"])


class WebReservationDetailTests(WebReservationCase):
    def test_the_detail_shows_the_reservation_next_to_the_list(self):
        reservation = self.add(offset=4, attendees=30, messages=[("¿Me confirman la hora?", None)])
        self.say(reservation, "ADMIN", "Claro, la confirmo hoy.")

        body = self.page(f"/web/reservas/{reservation.id}")

        self.assertIn("inbox-page has-detail", body)
        self.assertRegex(body, r'<h2 id="detail-title" tabindex="-1" data-focus-on-load>Salón social</h2>')
        for text in ("Marta Ríos", "Torre 1 · Apto 101", "10:00-12:00", "30", "Pendiente", "Decisión",
                     "¿Me confirman la hora?", "Claro, la confirmo hoy.", "Escribirle al residente",
                     "‹ Volver a la lista"):
            self.assertIn(text, body)
        self.assertIn(f'href="/web/reservas/{reservation.id}" aria-current="true"', body)
        self.assertIn('class="msg from-admin"', body)
        self.assertIn("El residente puede cancelar hasta el", body)

    def test_a_pending_reservation_offers_to_approve_or_reject_and_nothing_else(self):
        reservation = self.add()
        body = self.page(f"/web/reservas/{reservation.id}")
        self.assertIn(f'action="/web/reservas/{reservation.id}/decision"', body)
        self.assertRegex(body, r'<button[^>]*name="decision" value="aprobada">Aprobar</button>')
        self.assertRegex(body, r'<button[^>]*name="decision" value="rechazada"[^>]*>Rechazar</button>')
        self.assertNotIn("Cancelar reserva", body)
        self.assertIn("antes el motivo en la conversación", body)
        # Rechazar pide confirmación; aprobar, no.
        self.assertRegex(body, r'name="decision" value="rechazada"\s+data-confirm="[^"]*Rechazar la reserva de Marta Ríos')

    def test_an_approved_reservation_can_only_be_cancelled(self):
        reservation = self.add(status="aprobada")
        body = self.page(f"/web/reservas/{reservation.id}")
        self.assertIn(f'action="/web/reservas/{reservation.id}/cancelar"', body)
        self.assertIn("Sí, cancelar la reserva", body)
        self.assertNotIn('value="aprobada"', body)
        self.assertNotIn("Decisión", body)
        self.assertIn("Escribirle al residente", body)

    def test_a_finished_reservation_has_no_actions_and_a_closed_conversation(self):
        for status, word in (("rechazada", "rechazada"), ("cancelada", "cancelada")):
            with self.subTest(status=status):
                reservation = self.add(status=status, offset=10, slot="14:00-16:00", messages=[("Hola", None)])
                body = self.page(f"/web/reservas/{reservation.id}")
                self.assertIn("Esta reserva ya terminó: no se puede cambiar.", body)
                self.assertIn(f"Esta reserva está {word}: la conversación quedó cerrada", body)
                for absent in ('name="decision"', "/cancelar", "Escribirle al residente", 'name="message"'):
                    self.assertNotIn(absent, body)
                self.assertIn("Hola", body)

    def test_it_warns_when_another_approved_reservation_already_holds_the_slot(self):
        self.add(status="aprobada", resident=self.other)
        clash = self.add()

        body = self.page(f"/web/reservas/{clash.id}")

        self.assertIn("Esa franja ya la ocupa otra reserva aprobada", body)
        self.assertRegex(body, r'name="decision" value="aprobada" disabled aria-describedby="slot-taken"')
        self.assertIn('id="slot-taken"', body)
        # Rechazarla sigue siendo posible.
        self.assertNotRegex(body, r'name="decision" value="rechazada" disabled')

    def test_no_warning_when_the_slot_is_free(self):
        reservation = self.add()
        body = self.page(f"/web/reservas/{reservation.id}")
        self.assertNotIn("slot-taken", body)
        self.assertNotRegex(body, r'name="decision" value="aprobada"[^>]*disabled')

    def test_the_cancellation_deadline_of_the_resident_is_shown(self):
        late = self.add(offset=1)
        early = self.add(offset=10, slot="14:00-16:00")
        self.assertIn("ese plazo ya venció", self.page(f"/web/reservas/{late.id}"))
        body = self.page(f"/web/reservas/{early.id}")
        self.assertIn("El residente puede cancelar hasta el", body)
        self.assertNotIn("ya venció", body)

    def test_it_says_when_the_resident_is_a_minor(self):
        self.resident.birth_date = (colombia_today() - timedelta(days=365 * 12)).isoformat()
        db.session.commit()
        reservation = self.add()
        self.assertIn("Menor de edad", self.page(f"/web/reservas/{reservation.id}"))
        adult = self.add(resident=self.other, offset=6)
        self.assertNotIn("Menor de edad", self.page(f"/web/reservas/{adult.id}"))

    def test_a_reservation_made_by_the_administration_says_so(self):
        reservation = self.add(by_admin=True)
        self.assertIn("la registró la administración a nombre del residente", self.page(f"/web/reservas/{reservation.id}"))

    def test_a_reservation_without_messages_says_so(self):
        reservation = self.add()
        self.assertIn("Todavía no hay mensajes en esta reserva.", self.page(f"/web/reservas/{reservation.id}"))

    def test_an_unknown_reservation_is_a_404(self):
        self.assertEqual(self.client.get("/web/reservas/99999").status_code, 404)

    def test_the_detail_keeps_the_filters_of_the_list(self):
        reservation = self.add(offset=4, status="aprobada")
        body = self.page(f"/web/reservas/{reservation.id}?estado=aprobada&q=Marta")

        path, args = self.link_of(body, "‹ Volver a la lista")
        self.assertEqual((path, args), ("/web/reservas", {"estado": "aprobada", "q": "Marta"}))
        self.assertRegex(body, r'name="next" value="/web/reservas/%d\?q=Marta&amp;estado=aprobada"' % reservation.id)
        self.assertIn(f'action="/web/reservas/{reservation.id}/mensaje?q=Marta&amp;estado=aprobada"', body)

    def test_the_photos_of_the_conversation_are_requested_apart(self):
        reservation = self.add(messages=[("Con foto", PHOTO)])
        message = reservation.messages[0]

        body = self.page(f"/web/reservas/{reservation.id}")

        self.assertIn(f'src="/web/reservas/{reservation.id}/mensajes/{message.id}/adjunto"', body)
        self.assertNotIn("data:image", body)
        self.assertNotIn("base64", body)


class WebReservationDecisionTests(WebReservationCase):
    def test_approving_tells_the_resident_and_leaves_a_trace(self):
        reservation = self.add()
        detail = f"/web/reservas/{reservation.id}?q=Marta"

        response = self.post(f"/web/reservas/{reservation.id}/decision", {"decision": "aprobada", "next": detail})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], detail)
        self.assertEqual(self.reload(reservation).status, "aprobada")
        body = self.page(detail)
        self.assertIn("Reserva aprobada. Se le avisó al residente.", body)
        self.assertEqual(
            Notification.query.filter_by(user_id=self.resident.id, type="reservation", title="Reserva actualizada").count(), 1,
        )
        self.assertEqual(
            AuditLog.query.filter_by(entity_type="RESERVATION", entity_id=reservation.id, action="status_changed").count(), 1,
        )

    def test_rejecting_closes_the_reservation(self):
        reservation = self.add()
        self.post(f"/web/reservas/{reservation.id}/decision", {
            "decision": "rechazada", "next": f"/web/reservas/{reservation.id}",
        })
        self.assertEqual(self.reload(reservation).status, "rechazada")
        body = self.page(f"/web/reservas/{reservation.id}")
        self.assertIn("Esta reserva está rechazada", body)

    def test_approving_a_clash_keeps_it_pending_and_shows_the_rule(self):
        self.add(status="aprobada", resident=self.other)
        clash = self.add()

        response = self.post(f"/web/reservas/{clash.id}/decision", {
            "decision": "aprobada", "next": f"/web/reservas/{clash.id}",
        }, follow=True)

        self.assertEqual(self.reload(clash).status, "pendiente")
        self.assertIn("Ese horario ya no está disponible", self.text(response))

    def test_a_reservation_already_decided_cannot_be_decided_again(self):
        reservation = self.add(status="aprobada")
        response = self.post(f"/web/reservas/{reservation.id}/decision", {
            "decision": "rechazada", "next": f"/web/reservas/{reservation.id}",
        }, follow=True)
        self.assertEqual(self.reload(reservation).status, "aprobada")
        self.assertIn("Solo puedes aprobar o rechazar reservas pendientes.", self.text(response))

    def test_a_missing_or_strange_decision_changes_nothing(self):
        reservation = self.add()
        for decision in ("", "cancelada", "pendiente"):
            with self.subTest(decision=decision):
                response = self.post(f"/web/reservas/{reservation.id}/decision", {"decision": decision}, follow=True)
                self.assertIn("Elige si quieres aprobar o rechazar la reserva.", self.text(response))
                self.assertEqual(self.reload(reservation).status, "pendiente")

    def test_without_a_next_page_it_goes_back_to_the_panel(self):
        reservation = self.add()
        response = self.post(f"/web/reservas/{reservation.id}/decision", {"decision": "aprobada"})
        self.assertEqual(response.headers["Location"], "/web/")

    def test_another_site_is_never_the_next_page(self):
        reservation = self.add()
        response = self.post(f"/web/reservas/{reservation.id}/decision", {
            "decision": "aprobada", "next": "https://otro-sitio.example/robar",
        })
        self.assertEqual(response.headers["Location"], "/web/")

    def test_an_unknown_reservation_shows_the_message_of_the_api(self):
        response = self.post("/web/reservas/99999/decision", {"decision": "aprobada"}, follow=True)
        self.assertIn("Reserva no encontrada", self.text(response))

    def test_cancelling_an_approved_reservation_frees_the_slot_and_tells_the_resident(self):
        reservation = self.add(status="aprobada")
        detail = f"/web/reservas/{reservation.id}"

        response = self.post(f"/web/reservas/{reservation.id}/cancelar", {"next": detail})

        self.assertEqual(response.headers["Location"], detail)
        self.assertEqual(self.reload(reservation).status, "cancelada")
        self.assertIn("Reserva cancelada. Se le avisó al residente.", self.page(detail))
        self.assertEqual(
            Notification.query.filter_by(user_id=self.resident.id, type="reservation", title="Reserva cancelada").count(), 1,
        )
        # La franja quedó libre: otra reserva ya se puede aprobar.
        other = self.add(resident=self.other)
        self.post(f"/web/reservas/{other.id}/decision", {"decision": "aprobada"})
        self.assertEqual(self.reload(other).status, "aprobada")

    def test_cancelling_without_a_next_page_goes_back_to_the_reservation(self):
        reservation = self.add(status="aprobada")
        response = self.post(f"/web/reservas/{reservation.id}/cancelar")
        self.assertEqual(response.headers["Location"], f"/web/reservas/{reservation.id}")

    def test_a_finished_reservation_cannot_be_cancelled(self):
        reservation = self.add(status="rechazada")
        response = self.post(f"/web/reservas/{reservation.id}/cancelar", follow=True)
        self.assertEqual(self.reload(reservation).status, "rechazada")
        self.assertIn("Solo se pueden cancelar reservas pendientes o aprobadas.", self.text(response))

    def test_forms_without_the_security_code_are_refused(self):
        reservation = self.add()
        for path, data in (
            (f"/web/reservas/{reservation.id}/decision", {"decision": "aprobada"}),
            (f"/web/reservas/{reservation.id}/cancelar", {}),
            (f"/web/reservas/{reservation.id}/mensaje", {"message": "Hola"}),
        ):
            with self.subTest(path=path):
                response = self.client.post(path, data=data)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.reload(reservation).status, "pendiente")
        self.assertEqual(ReservationMessage.query.count(), 0)


class WebReservationMessageTests(WebReservationCase):
    def test_a_message_reaches_the_conversation_and_the_resident(self):
        reservation = self.add(messages=[("¿Qué necesitan?", None)])
        detail = f"/web/reservas/{reservation.id}?estado=aprobada"

        response = self.post(f"/web/reservas/{reservation.id}/mensaje?estado=aprobada", {"message": "  Falta el recibo del depósito.  "})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], detail)
        messages = self.reload(reservation).messages
        self.assertEqual([m.author_role for m in messages], ["RESIDENT", "ADMIN"])
        self.assertEqual(messages[-1].message, "Falta el recibo del depósito.")
        self.assertEqual(messages[-1].author_id, self.admin.id)
        body = self.page(detail)
        self.assertIn("Mensaje enviado. El residente recibió un aviso en la app.", body)
        self.assertIn("Falta el recibo del depósito.", body)
        self.assertEqual(
            Notification.query.filter_by(user_id=self.resident.id, type="reservation", title="Respuesta sobre tu reserva").count(), 1,
        )

    def test_an_empty_message_is_refused_with_the_message_of_the_api(self):
        reservation = self.add()
        response = self.post(f"/web/reservas/{reservation.id}/mensaje", {"message": "   "})
        self.assertEqual(response.status_code, 400)
        body = self.text(response)
        self.assertIn("Escribe un mensaje o adjunta un archivo.", body)
        # Se queda en la reserva, con el formulario a la mano.
        self.assertIn('data-focus-on-load>Salón social</h2>', body)
        self.assertIn('name="message"', body)
        self.assertEqual(ReservationMessage.query.count(), 0)

    def test_a_finished_conversation_does_not_take_more_messages(self):
        reservation = self.add(status="rechazada")
        response = self.post(f"/web/reservas/{reservation.id}/mensaje", {"message": "¿Sigues ahí?"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("No se puede continuar una conversación de una reserva finalizada.", self.text(response))
        self.assertEqual(ReservationMessage.query.count(), 0)

    def test_opening_the_message_address_goes_back_to_the_reservation(self):
        reservation = self.add()
        response = self.client.get(f"/web/reservas/{reservation.id}/mensaje?estado=aprobada&page=2")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], f"/web/reservas/{reservation.id}?estado=aprobada&page=2")

    def test_an_unknown_reservation_is_a_404(self):
        response = self.post("/web/reservas/99999/mensaje", {"message": "Hola"})
        self.assertEqual(response.status_code, 404)


class WebReservationAttachmentTests(WebReservationCase):
    def test_a_photo_is_served_with_a_strict_policy(self):
        reservation = self.add(messages=[("Con foto", PHOTO)])
        message = reservation.messages[0]

        response = self.client.get(f"/web/reservas/{reservation.id}/mensajes/{message.id}/adjunto")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        self.assertEqual(response.data, PNG)
        policy = response.headers["Content-Security-Policy"]
        for directive in ("default-src 'none'", "sandbox"):
            self.assertIn(directive, policy)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertEqual(response.headers["Accept-Ranges"], "bytes")
        # Con el ETag que ya tiene, el navegador no vuelve a bajarla.
        again = self.client.get(
            f"/web/reservas/{reservation.id}/mensajes/{message.id}/adjunto",
            headers={"If-None-Match": response.headers["ETag"]},
        )
        self.assertEqual(again.status_code, 304)

    def test_it_can_be_requested_by_parts(self):
        reservation = self.add(messages=[("Con foto", PHOTO)])
        message = reservation.messages[0]
        response = self.client.get(
            f"/web/reservas/{reservation.id}/mensajes/{message.id}/adjunto", headers={"Range": "bytes=0-3"},
        )
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.data, PNG[:4])

    def test_what_is_not_a_photo_a_video_or_an_audio_is_not_served(self):
        svg = "data:image/svg+xml;base64," + base64.b64encode(b"<svg onload='x()'/>").decode()
        page = "data:text/html;base64," + base64.b64encode(b"<script>x()</script>").decode()
        reservation = self.add(messages=[("a", svg), ("b", page), ("c", "https://ejemplo.com/a.png"), ("d", None)])
        for message in reservation.messages:
            with self.subTest(message=message.message):
                response = self.client.get(f"/web/reservas/{reservation.id}/mensajes/{message.id}/adjunto")
                self.assertEqual(response.status_code, 404)

    def test_a_message_of_another_reservation_is_not_found(self):
        mine = self.add()
        other = self.add(resident=self.other, offset=6, messages=[("Con foto", PHOTO)])
        response = self.client.get(f"/web/reservas/{mine.id}/mensajes/{other.messages[0].id}/adjunto")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
