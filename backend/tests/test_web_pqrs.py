"""Pruebas de las PQRS en la web de administración (HU-078): la bandeja con filtros, la solicitud al
lado, responder, responder varias a la vez, registrar a nombre de un residente y los adjuntos."""

import base64
import html
import re
import unittest
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from extensions import db
from models import AuditLog, Notification, Pqrs, PqrsMessage, PqrsSatisfaction
from services.pqrs_rules import pqrs_semaphore
from structure_fixtures import apartment_for
from time_utils import colombia_day_to_utc, colombia_today
from web_testing import WebTestCase

PNG = b"\x89PNG\r\n\x1a\n" + b"imagen-de-prueba"
PHOTO = "data:image/png;base64," + base64.b64encode(PNG).decode()
AUDIO = "data:audio/mpeg;base64," + base64.b64encode(b"audio-de-prueba").decode()


def days_old_with_color(color):
    """Cuántos días atrás se radicó una PQRS para que hoy tenga ese color de semáforo."""
    today = colombia_today()
    for days in range(60):
        if pqrs_semaphore(today - timedelta(days=days), today, "Daño")["color"] == color:
            return days
    raise AssertionError(color)


class WebPqrsCase(WebTestCase):
    def setUp(self):
        super().setUp()
        self.other = self.make_user(
            "RESIDENT", "carlos-web@test.local", "Carlos", last_name="Pérez",
            apartment_ref=apartment_for("Torre 2 · Apto 202"), occupancy_type="arrendatario",
        )
        db.session.commit()
        self.log_in()

    def add(self, subject="Ascensor dañado", status="abierta", category="Daño", days_ago=0, resident=None,
            media=None, message="Detalle largo del problema", archived=False, first_message=True):
        resident = resident or self.resident
        created = colombia_day_to_utc(colombia_today() - timedelta(days=days_ago)) + timedelta(hours=14)
        pqrs = Pqrs(
            resident_id=resident.id, category=category, subject=subject, message=message, status=status,
            created_at=created, updated_at=created, is_archived=archived,
            media_url=media, media_type="image" if media else None,
        )
        db.session.add(pqrs)
        db.session.flush()
        if first_message:
            self.say(pqrs, "RESIDENT", message, media=media, media_type="image" if media else None, author=resident)
        db.session.commit()
        return pqrs

    def say(self, pqrs, role, text, media=None, media_type=None, author=None):
        message = PqrsMessage(
            pqrs_id=pqrs.id, author_id=(author or self.admin).id, author_role=role, message=text,
            media_url=media, media_type=media_type,
        )
        db.session.add(message)
        db.session.commit()
        return message

    def reload(self, pqrs):
        db.session.expire_all()
        return db.session.get(Pqrs, pqrs.id)

    @staticmethod
    def link_of(body, text):
        """La dirección del enlace que dice ``text``, con sus parámetros ya separados."""
        found = re.search(r'href="([^"]+)"[^>]*>\s*' + re.escape(text), body)
        assert found, f"no hay un enlace «{text}»"
        parts = urlsplit(html.unescape(found.group(1)))
        return parts.path, {key: values[0] for key, values in parse_qs(parts.query).items()}


class WebPqrsInboxTests(WebPqrsCase):
    def test_pages_ask_for_login(self):
        anonymous = self.app.test_client()
        for path in ("/web/pqrs", "/web/pqrs/1", "/web/pqrs/nueva", "/web/pqrs/1/adjunto", "/web/pqrs/1/mensajes/1/adjunto"):
            with self.subTest(path=path):
                response = anonymous.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/web/login", response.headers["Location"])

    def test_the_menu_and_the_panel_lead_to_the_inbox(self):
        pqrs = self.add()
        body = self.page("/web/")
        self.assertIn('href="/web/pqrs"', body)
        self.assertIn(f'href="/web/pqrs/{pqrs.id}"', body)

    def test_the_inbox_shows_what_each_pqrs_needs(self):
        overdue = self.add("Ascensor dañado", days_ago=days_old_with_color("rojo"), media=PHOTO)
        self.add("Fuga en el parqueadero", status="en_proceso", category="Queja", resident=self.other)
        self.add("Ya resuelta", status="resuelta", days_ago=40)

        body = self.page("/web/pqrs")

        self.assertIn("3 PQRS", body)
        for text in (overdue.radicado, "Ascensor dañado", "Torre 1 · Apto 101", "Marta Ríos", "Torre 2 · Apto 202",
                     "Carlos Pérez", "Vencida hace", "En proceso", "1 adjunto"):
            self.assertIn(text, body)
        # Lo que sigue sin resolverse va primero (la más antigua antes) y lo resuelto, al final.
        self.assertLess(body.index("Ascensor dañado"), body.index("Fuga en el parqueadero"))
        self.assertLess(body.index("Fuga en el parqueadero"), body.index("Ya resuelta"))
        # Sin solicitud elegida, la bandeja queda sola y a la derecha se invita a elegir una.
        self.assertNotIn("inbox-page has-detail", body)
        self.assertIn("Elige una PQRS de la bandeja", body)

    def test_a_resolved_pqrs_shows_no_deadline(self):
        self.add("Ya resuelta", status="resuelta", days_ago=days_old_with_color("rojo"))
        body = self.page("/web/pqrs")
        self.assertNotIn("Vencida hace", body)

    def test_filters_by_state_type_deadline_and_text(self):
        self.add("Ascensor dañado", days_ago=days_old_with_color("rojo"))
        self.add("Fuga en el parqueadero", status="en_proceso", category="Queja", resident=self.other)
        self.add("Ya resuelta", status="resuelta", category="Sugerencia")

        by_state = self.page("/web/pqrs?estado=resuelta")
        self.assertIn("Ya resuelta", by_state)
        self.assertNotIn("Ascensor dañado", by_state)
        self.assertIn("1 PQRS con esos filtros", by_state)

        by_type = self.page("/web/pqrs?tipo=Queja")
        self.assertIn("Fuga en el parqueadero", by_type)
        self.assertNotIn("Ya resuelta", by_type)

        by_deadline = self.page("/web/pqrs?plazo=rojo")
        self.assertIn("Ascensor dañado", by_deadline)
        self.assertNotIn("Fuga en el parqueadero", by_deadline)

        by_text = self.page("/web/pqrs?q=Carlos")
        self.assertIn("Fuga en el parqueadero", by_text)
        self.assertNotIn("Ascensor dañado", by_text)

        by_apartment = self.page("/web/pqrs?q=Apto 101")
        self.assertIn("Ascensor dañado", by_apartment)
        self.assertNotIn("Fuga en el parqueadero", by_apartment)

    def test_filters_keep_their_selection_in_the_form(self):
        body = self.page("/web/pqrs?estado=en_proceso&tipo=Queja&plazo=amarillo&q=ruido&archivadas=1")
        self.assertRegex(body, r'<option value="en_proceso" selected>')
        self.assertRegex(body, r'<option value="Queja" selected>')
        self.assertRegex(body, r'<option value="amarillo" selected>')
        self.assertIn('value="ruido"', body)
        self.assertRegex(body, r'id="archivadas" name="archivadas" value="1" checked')

    def test_no_match_and_empty_inbox_have_their_own_text(self):
        self.assertIn("Todavía no hay PQRS.", self.page("/web/pqrs"))
        self.add()
        body = self.page("/web/pqrs?q=zzzz")
        self.assertIn("No hay PQRS que coincidan con esos filtros.", body)
        self.assertIn("Quitar filtros", body)

    def test_unknown_filter_values_are_ignored(self):
        self.add()
        body = self.page("/web/pqrs?estado=rara&tipo=Otra&plazo=azul")
        self.assertIn("Ascensor dañado", body)
        self.assertNotIn("con esos filtros", body)

    def test_archived_pqrs_appear_only_when_asked(self):
        self.add("Vigente")
        self.add("Archivada vieja", archived=True)
        self.assertNotIn("Archivada vieja", self.page("/web/pqrs"))
        body = self.page("/web/pqrs?archivadas=1")
        self.assertIn("Archivada vieja", body)
        self.assertIn('<span class="inbox-meta">Archivada</span>', body)

    def test_pagination_and_a_page_past_the_end(self):
        for number in range(17):
            self.add(f"Asunto {number:02d}", days_ago=number)
        first = self.page("/web/pqrs")
        self.assertIn("Página 1 de 2", first)
        self.assertEqual(first.count('name="ids"'), 15)
        second = self.page("/web/pqrs?page=2")
        self.assertEqual(second.count('name="ids"'), 2)
        response = self.client.get("/web/pqrs?page=99")
        self.assertEqual(response.status_code, 302)
        self.assertIn("page=2", response.headers["Location"])

    def test_texts_written_by_people_are_escaped(self):
        pqrs = self.add("<script>alert(1)</script>", message="<img src=x onerror=alert(2)>")
        self.say(pqrs, "ADMIN", "<b>negrita</b>")
        for path in ("/web/pqrs", f"/web/pqrs/{pqrs.id}"):
            body = self.page(path)
            self.assertNotIn("<script>alert(1)</script>", body)
            self.assertNotIn("<img src=x", body)
            self.assertNotIn("<b>negrita</b>", body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", self.page("/web/pqrs"))

    def test_pages_keep_the_page_security_policy_and_use_no_inline_code(self):
        pqrs = self.add(media=PHOTO)
        for path in ("/web/pqrs", f"/web/pqrs/{pqrs.id}", "/web/pqrs/nueva"):
            response = self.client.get(path)
            self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            body = self.text(response)
            self.assertNotRegex(body, r'\sstyle\s*=')
            self.assertNotRegex(body, r'\son[a-z]+\s*=')

    def test_every_row_has_a_label_for_its_checkbox(self):
        pqrs = self.add()
        body = self.page("/web/pqrs")
        self.assertIn(f'<label class="inbox-check" for="sel-{pqrs.id}">', body)
        self.assertIn(f'<span class="sr-only">Seleccionar {pqrs.radicado}', body)


class WebPqrsDetailTests(WebPqrsCase):
    def test_the_request_opens_beside_the_inbox(self):
        pqrs = self.add(days_ago=3, message="Detalle largo del problema")
        self.say(pqrs, "ADMIN", "Ya enviamos al técnico")
        self.say(pqrs, "RESIDENT", "Gracias, quedo atenta", author=self.resident)

        body = self.page(f"/web/pqrs/{pqrs.id}")

        self.assertIn("inbox-page has-detail", body)
        for text in (pqrs.radicado, "Ascensor dañado", "Marta Ríos", "Torre 1 · Apto 101", "Daño",
                     "Ya enviamos al técnico", "Gracias, quedo atenta", "Quedan", "Enviar respuesta"):
            self.assertIn(text, body)
        # El primer mensaje solo repite la descripción: se muestra una vez.
        self.assertEqual(body.count("Detalle largo del problema"), 1)
        # El título recibe el foco y la fila abierta queda marcada en la bandeja.
        self.assertIn('id="detail-title" tabindex="-1" data-focus-on-load', body)
        self.assertEqual(body.count('aria-current="true"'), 1)

    def test_the_way_back_keeps_the_filters_and_the_page(self):
        pqrs = self.add()
        body = self.page(f"/web/pqrs/{pqrs.id}?estado=abierta&q=Ascensor")
        path, query = self.link_of(body, "‹ Volver a la bandeja")
        self.assertEqual(path, "/web/pqrs")
        self.assertEqual(query, {"q": "Ascensor", "estado": "abierta"})
        # Los enlaces de la bandeja conservan los mismos filtros.
        self.assertIn(f'href="/web/pqrs/{pqrs.id}?q=Ascensor&amp;estado=abierta"', body)

    def test_the_conversation_says_who_wrote_each_message(self):
        pqrs = self.add()
        self.say(pqrs, "ADMIN", "Ya enviamos al técnico")
        body = self.page(f"/web/pqrs/{pqrs.id}")
        self.assertIn("Lucía Vargas", body)
        self.assertIn("Administración", body)
        self.assertIn('class="msg from-admin"', body)

    def test_a_pqrs_without_messages_says_so(self):
        pqrs = self.add(first_message=False)
        self.assertIn("Todavía no hay mensajes en esta conversación.", self.page(f"/web/pqrs/{pqrs.id}"))

    def test_a_first_message_that_differs_from_the_request_is_kept(self):
        pqrs = self.add(first_message=False, message="Texto de la solicitud")
        self.say(pqrs, "RESIDENT", "Otro texto distinto", author=self.resident)
        self.assertIn("Otro texto distinto", self.page(f"/web/pqrs/{pqrs.id}"))

    def test_the_detail_shows_the_deadline_the_creation_and_the_rating(self):
        pqrs = self.add(days_ago=days_old_with_color("rojo"))
        pqrs.created_by_admin_id = self.admin.id
        pqrs.incident_date = "2026-11-02"
        pqrs.incident_time = "18:30"
        db.session.commit()
        body = self.page(f"/web/pqrs/{pqrs.id}")
        self.assertIn("Vencida hace", body)
        self.assertIn("la registró la administración a nombre del residente", body)
        self.assertIn("02/11/2026 18:30", body)

        done = self.add("Resuelta", status="resuelta")
        db.session.add(PqrsSatisfaction(pqrs_id=done.id, rating=4, comment="Muy bien atendido"))
        db.session.commit()
        resolved = self.page(f"/web/pqrs/{done.id}")
        self.assertIn("Ya no corre: la PQRS está resuelta.", resolved)
        self.assertIn("4 de 5", resolved)
        self.assertIn("Muy bien atendido", resolved)

    def test_an_open_pqrs_proposes_moving_to_in_progress(self):
        pqrs = self.add()
        body = self.page(f"/web/pqrs/{pqrs.id}")
        self.assertRegex(body, r'<option value="en_proceso" selected>')
        resolved = self.add("Resuelta", status="resuelta")
        self.assertRegex(self.page(f"/web/pqrs/{resolved.id}"), r'<option value="resuelta" selected>')

    def test_an_unknown_pqrs_gives_the_not_found_page(self):
        response = self.client.get("/web/pqrs/99999")
        self.assertEqual(response.status_code, 404)
        self.assertIn("No encontramos esa página", self.text(response))

    def test_attachments_are_requested_apart_and_never_embedded(self):
        pqrs = self.add(media=PHOTO)
        audio = self.say(pqrs, "ADMIN", "Te dejo un audio", media=AUDIO, media_type="audio")
        video = self.say(
            pqrs, "RESIDENT", "Y un video", media="data:video/mp4;base64," + base64.b64encode(b"video").decode(),
            media_type="video", author=self.resident,
        )

        body = self.page(f"/web/pqrs/{pqrs.id}")

        self.assertIn(f'<img src="/web/pqrs/{pqrs.id}/adjunto"', body)
        self.assertIn(f'<audio controls preload="none" src="/web/pqrs/{pqrs.id}/mensajes/{audio.id}/adjunto"', body)
        self.assertIn(f'<video controls preload="metadata" src="/web/pqrs/{pqrs.id}/mensajes/{video.id}/adjunto"', body)
        self.assertIn('rel="noopener"', body)
        self.assertNotIn("base64", body)
        self.assertEqual(body.count(f"/web/pqrs/{pqrs.id}/adjunto"), 2)  # la foto y el enlace para abrirla


class WebPqrsAttachmentTests(WebPqrsCase):
    def test_a_photo_is_served_with_its_own_strict_policy(self):
        pqrs = self.add(media=PHOTO)

        response = self.client.get(f"/web/pqrs/{pqrs.id}/adjunto")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "image/png")
        self.assertEqual(response.get_data(), PNG)
        self.assertEqual(response.headers["Content-Security-Policy"], "default-src 'none'; style-src 'unsafe-inline'; sandbox")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertTrue(response.headers["ETag"])

    def test_it_answers_not_modified_and_partial_requests(self):
        pqrs = self.add(media=PHOTO)
        first = self.client.get(f"/web/pqrs/{pqrs.id}/adjunto")
        again = self.client.get(f"/web/pqrs/{pqrs.id}/adjunto", headers={"If-None-Match": first.headers["ETag"]})
        self.assertEqual(again.status_code, 304)
        part = self.client.get(f"/web/pqrs/{pqrs.id}/adjunto", headers={"Range": "bytes=0-3"})
        self.assertEqual(part.status_code, 206)
        self.assertEqual(part.get_data(), PNG[:4])
        self.assertEqual(part.headers["Content-Range"], f"bytes 0-3/{len(PNG)}")

    def test_the_attachment_of_a_message(self):
        pqrs = self.add()
        message = self.say(pqrs, "ADMIN", "Audio", media=AUDIO, media_type="audio")
        response = self.client.get(f"/web/pqrs/{pqrs.id}/mensajes/{message.id}/adjunto")
        self.assertEqual((response.status_code, response.content_type), (200, "audio/mpeg"))
        self.assertEqual(response.get_data(), b"audio-de-prueba")

    def test_what_is_not_an_image_video_or_audio_is_never_served(self):
        svg = "data:image/svg+xml;base64," + base64.b64encode(b"<svg onload=alert(1)/>").decode()
        page = "data:text/html;base64," + base64.b64encode(b"<script>alert(1)</script>").decode()
        for stored in (svg, page, "https://otro-sitio.test/foto.png", "javascript:alert(1)", "data:image/png;base64,###"):
            pqrs = self.add(media=stored)
            with self.subTest(stored=stored[:30]):
                self.assertEqual(self.client.get(f"/web/pqrs/{pqrs.id}/adjunto").status_code, 404)

    def test_missing_attachments_and_foreign_messages_are_not_found(self):
        pqrs = self.add()
        other = self.add("Otra", media=PHOTO)
        message = self.say(other, "ADMIN", "Audio", media=AUDIO, media_type="audio")
        self.assertEqual(self.client.get(f"/web/pqrs/{pqrs.id}/adjunto").status_code, 404)
        self.assertEqual(self.client.get("/web/pqrs/99999/adjunto").status_code, 404)
        # Un mensaje de otra PQRS no se entrega pidiéndolo por esta.
        self.assertEqual(self.client.get(f"/web/pqrs/{pqrs.id}/mensajes/{message.id}/adjunto").status_code, 404)
        self.assertEqual(self.client.get(f"/web/pqrs/{other.id}/mensajes/{message.id}/adjunto").status_code, 200)


class WebPqrsRespondTests(WebPqrsCase):
    def respond(self, pqrs, data=None, query="", follow=False):
        form = {"status": "en_proceso", "adminResponse": "Ya lo estamos revisando"}
        form.update(data or {})
        return self.post(f"/web/pqrs/{pqrs.id}/responder{query}", form, follow=follow)

    def test_responding_changes_the_state_tells_the_resident_and_keeps_the_view(self):
        pqrs = self.add()

        response = self.respond(pqrs, query="?estado=abierta&q=Ascensor")

        self.assertEqual(response.status_code, 302)
        path, query = urlsplit(response.headers["Location"]).path, parse_qs(urlsplit(response.headers["Location"]).query)
        self.assertEqual(path, f"/web/pqrs/{pqrs.id}")
        self.assertEqual(query, {"q": ["Ascensor"], "estado": ["abierta"]})
        pqrs = self.reload(pqrs)
        self.assertEqual(pqrs.status, "en_proceso")
        self.assertEqual(pqrs.admin_response, "Ya lo estamos revisando")
        self.assertEqual(pqrs.conversation[-1].author_role, "ADMIN")
        self.assertEqual(pqrs.conversation[-1].message, "Ya lo estamos revisando")
        self.assertEqual(Notification.query.filter_by(user_id=self.resident.id).count(), 1)
        self.assertEqual(
            AuditLog.query.filter_by(entity_type="PQRS", entity_id=pqrs.id, action="status_changed").count(), 1,
        )
        body = self.page(response.headers["Location"])
        self.assertIn("PQRS actualizada.", body)
        self.assertIn("Ya lo estamos revisando", body)

    def test_resolving_ends_the_deadline(self):
        pqrs = self.add(days_ago=days_old_with_color("rojo"))
        self.respond(pqrs, {"status": "resuelta", "adminResponse": "Quedó solucionado"})
        pqrs = self.reload(pqrs)
        self.assertEqual(pqrs.status, "resuelta")
        self.assertIsNone(pqrs.semaphore)

    def test_an_empty_response_is_refused_and_what_was_chosen_is_kept(self):
        pqrs = self.add()

        response = self.respond(pqrs, {"status": "resuelta", "adminResponse": ""})

        self.assertEqual(response.status_code, 400)
        body = self.text(response)
        self.assertIn("Escribe una respuesta antes de actualizar la PQRS.", body)
        self.assertRegex(body, r'<option value="resuelta" selected>')
        self.assertIn("inbox-page has-detail", body)
        self.assertEqual(self.reload(pqrs).status, "abierta")
        self.assertEqual(Notification.query.count(), 0)

    def test_what_was_typed_is_kept_when_the_state_is_invalid(self):
        pqrs = self.add()
        response = self.respond(pqrs, {"status": "rara", "adminResponse": "Mi respuesta a medias"})
        self.assertEqual(response.status_code, 400)
        body = self.text(response)
        self.assertIn("Estado de PQRS inválido", body)
        self.assertIn("Mi respuesta a medias", body)
        self.assertEqual(self.reload(pqrs).status, "abierta")

    def test_responding_to_a_missing_pqrs_gives_the_not_found_page(self):
        pqrs = self.add()
        gone = pqrs.id + 100
        response = self.post(f"/web/pqrs/{gone}/responder", {"status": "resuelta", "adminResponse": "Hola"})
        self.assertEqual(response.status_code, 404)

    def test_a_get_to_the_response_address_goes_back_to_the_request(self):
        pqrs = self.add()
        response = self.client.get(f"/web/pqrs/{pqrs.id}/responder?estado=abierta&pqrs_id=7")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(urlsplit(response.headers["Location"]).path, f"/web/pqrs/{pqrs.id}")

    def test_pager_links_after_a_rejected_response_still_work(self):
        for number in range(17):
            self.add(f"Asunto {number:02d}", days_ago=number)
        target = Pqrs.query.first()
        response = self.respond(target, {"adminResponse": ""})
        self.assertEqual(response.status_code, 400)
        path, _query = self.link_of(self.text(response), "Siguiente ›")
        followed = self.client.get(path + "?page=2")
        self.assertEqual(followed.status_code, 302)

    def test_forms_without_the_csrf_code_are_refused(self):
        pqrs = self.add()
        for path in (f"/web/pqrs/{pqrs.id}/responder", "/web/pqrs/lote", "/web/pqrs/nueva"):
            with self.subTest(path=path):
                response = self.client.post(path, data={"status": "resuelta", "adminResponse": "Hola"})
                self.assertEqual(response.status_code, 400)
                self.assertIn("El formulario venció", self.text(response))
        self.assertEqual(self.reload(pqrs).status, "abierta")


class WebPqrsBatchTests(WebPqrsCase):
    def setUp(self):
        super().setUp()
        self.first = self.add("Uno", category="Queja")
        self.second = self.add("Dos", category="Queja", resident=self.other)
        self.third = self.add("Tres", category="Daño")

    def batch(self, ids, status="resuelta", message="Quedó solucionado", query=""):
        data = {"ids": [str(value) for value in ids], "batchStatus": status, "batchMessage": message}
        return self.post(f"/web/pqrs/lote{query}", data)

    def test_one_answer_for_several_pqrs(self):
        response = self.batch([self.first.id, self.second.id], query="?estado=abierta")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(urlsplit(response.headers["Location"]).path, "/web/pqrs")
        self.assertEqual(parse_qs(urlsplit(response.headers["Location"]).query), {"estado": ["abierta"]})
        self.assertIn("2 PQRS actualizadas.", self.page(response.headers["Location"]))
        for pqrs in (self.first, self.second):
            pqrs = self.reload(pqrs)
            self.assertEqual(pqrs.status, "resuelta")
            self.assertEqual(pqrs.admin_response, "Quedó solucionado")
            self.assertEqual(pqrs.conversation[-1].author_role, "ADMIN")
        self.assertEqual(self.reload(self.third).status, "abierta")
        # Cada residente recibe su aviso.
        self.assertEqual(Notification.query.filter_by(user_id=self.resident.id).count(), 1)
        self.assertEqual(Notification.query.filter_by(user_id=self.other.id).count(), 1)

    def test_a_single_one_is_singular(self):
        response = self.batch([self.first.id], status="en_proceso")
        self.assertIn("1 PQRS actualizada.", self.page(response.headers["Location"]))

    def test_different_types_are_refused_and_nothing_changes(self):
        response = self.batch([self.first.id, self.third.id], message="Un mensaje para dos tipos")

        self.assertEqual(response.status_code, 400)
        body = self.text(response)
        self.assertIn("La respuesta por lotes solo permite PQRS de la misma categoría.", body)
        # La selección y lo escrito se conservan para corregir sin empezar de nuevo.
        self.assertRegex(body, rf'value="{self.first.id}" id="sel-{self.first.id}"[^>]*checked')
        self.assertRegex(body, rf'value="{self.third.id}" id="sel-{self.third.id}"[^>]*checked')
        self.assertNotRegex(body, rf'value="{self.second.id}" id="sel-{self.second.id}"[^>]*checked')
        self.assertIn('<details class="batch" open>', body)
        self.assertIn("Un mensaje para dos tipos", body)
        self.assertEqual({self.reload(item).status for item in (self.first, self.third)}, {"abierta"})

    def test_nothing_selected_a_wrong_state_or_no_message_are_refused(self):
        cases = (
            (self.batch([]), "Selecciona una o más PQRS válidas."),
            (self.batch([self.first.id], status="abierta"), "El estado debe ser"),
            (self.batch([self.first.id], message=""), "Escribe una respuesta para todas las PQRS seleccionadas."),
            (self.batch(["abc"]), "Selecciona una o más PQRS válidas."),
            (self.batch([self.first.id, self.first.id]), "La selección contiene PQRS repetidas."),
        )
        for response, message in cases:
            with self.subTest(message=message):
                self.assertEqual(response.status_code, 400)
                self.assertIn(message, self.text(response))
        self.assertEqual(self.reload(self.first).status, "abierta")

    def test_a_pqrs_that_no_longer_exists_stops_the_whole_batch(self):
        response = self.batch([self.first.id, self.third.id + 100], status="en_proceso")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Algunas PQRS ya no existen", self.text(response))
        self.assertEqual(self.reload(self.first).status, "abierta")

    def test_a_get_to_the_batch_address_goes_back_to_the_inbox(self):
        response = self.client.get("/web/pqrs/lote?estado=abierta")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(urlsplit(response.headers["Location"]).path, "/web/pqrs")

    def test_the_batch_button_asks_for_confirmation(self):
        body = self.page("/web/pqrs")
        self.assertIn("data-confirm=", body)
        self.assertIn('data-needs-selection="pqrs"', body)
        self.assertIn('data-select-all="pqrs"', body)


class WebPqrsNewTests(WebPqrsCase):
    def form(self, **changes):
        form = {"residentId": str(self.resident.id), "category": "Queja", "subject": "Ruido nocturno",
                "message": "Hay ruido todas las noches en el piso de arriba."}
        form.update(changes)
        return form

    def test_the_form_offers_only_active_residents(self):
        inactive = self.make_user("RESIDENT", "zoe-web@test.local", "Zoe", last_name="Inactiva")
        inactive.is_active = False
        db.session.commit()

        body = self.page("/web/pqrs/nueva")

        options = re.search(r'<select id="residentId".*?</select>', body, re.S).group(0)
        self.assertIn("Marta Ríos · Torre 1 · Apto 101", options)
        self.assertIn("Carlos Pérez · Torre 2 · Apto 202", options)
        self.assertNotIn("Zoe", options)
        self.assertNotIn("Guardia", options)
        self.assertNotIn("Lucía", options)
        for category in ("Petición", "Queja", "Reclamo", "Sugerencia", "Daño"):
            self.assertIn(f'<option value="{category}"', body)

    def test_it_registers_the_pqrs_in_the_name_of_the_resident(self):
        response = self.post("/web/pqrs/nueva", self.form())

        self.assertEqual(response.status_code, 302)
        pqrs = Pqrs.query.one()
        self.assertEqual(response.headers["Location"], f"/web/pqrs/{pqrs.id}")
        self.assertEqual(pqrs.resident_id, self.resident.id)
        self.assertEqual(pqrs.created_by_admin_id, self.admin.id)
        self.assertEqual((pqrs.category, pqrs.subject), ("Queja", "Ruido nocturno"))
        self.assertEqual(pqrs.conversation[0].author_role, "ADMIN")
        self.assertEqual(Notification.query.filter_by(user_id=self.resident.id).count(), 1)
        body = self.page(response.headers["Location"])
        self.assertIn("PQRS registrada a nombre del residente. Se le avisó en la app.", body)
        self.assertIn("la registró la administración a nombre del residente", body)

    def test_mistakes_are_explained_and_what_was_typed_is_kept(self):
        for changes, message in (
            ({"residentId": ""}, "Selecciona un residente válido"),
            ({"subject": ""}, "asunto"),
            ({"message": ""}, "mensaje"),
        ):
            with self.subTest(changes=changes):
                response = self.post("/web/pqrs/nueva", self.form(**changes))
                self.assertEqual(response.status_code, 400)
                body = self.text(response)
                self.assertIn(message, body)
        self.assertEqual(Pqrs.query.count(), 0)

    def test_what_was_typed_survives_a_rejected_form(self):
        response = self.post("/web/pqrs/nueva", self.form(subject="", message="Texto que no quiero perder"))
        body = self.text(response)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Texto que no quiero perder", body)
        self.assertRegex(body, r'<option value="Queja" selected>')
        self.assertRegex(body, rf'<option value="{self.resident.id}" selected>')

    def test_without_active_residents_it_says_so(self):
        for resident in (self.resident, self.other):
            resident.is_active = False
        db.session.commit()
        body = self.page("/web/pqrs/nueva")
        self.assertIn("No hay residentes con la cuenta activa", body)
        self.assertNotIn("<form method=\"post\" action=\"/web/pqrs/nueva\"", body)

    def test_the_tabs_switch_between_the_inbox_and_the_new_pqrs(self):
        inbox = self.page("/web/pqrs")
        self.assertRegex(inbox, r'<a href="/web/pqrs" aria-current="page">Bandeja</a>')
        new = self.page("/web/pqrs/nueva")
        self.assertRegex(new, r'<a href="/web/pqrs/nueva" aria-current="page">Nueva PQRS</a>')


if __name__ == "__main__":
    unittest.main()
