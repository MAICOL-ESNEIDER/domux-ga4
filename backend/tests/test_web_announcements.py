"""Pruebas de los comunicados en la web de administración (HU-080): la lista con sus pestañas y filtros, el
comunicado al lado con cuántos apartamentos lo leyeron, publicar con foto, video o audio, retirar sin borrar
y los adjuntos."""

import base64
import html
import io
import re
import unittest
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from extensions import db
from models import Announcement, AnnouncementRead, AuditLog, Notification
from structure_fixtures import apartment_for
from time_utils import colombia_today, utc_now
from web import uploads
from web_testing import WebTestCase

PNG = b"\x89PNG\r\n\x1a\n" + b"imagen-de-prueba"
PHOTO = "data:image/png;base64," + base64.b64encode(PNG).decode()
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"video-de-prueba"
MP3 = b"ID3\x03\x00" + b"audio-de-prueba"


class WebAnnouncementCase(WebTestCase):
    def setUp(self):
        super().setUp()
        self.other = self.make_user(
            "RESIDENT", "carlos-comunicados@test.local", "Carlos", last_name="Pérez",
            apartment_ref=apartment_for("Torre 2 · Apto 202"), occupancy_type="arrendatario",
        )
        db.session.commit()
        self.tower_1 = self.resident.apartment_ref.tower_id
        self.tower_2 = self.other.apartment_ref.tower_id
        self.log_in()

    def day(self, offset):
        return colombia_today() + timedelta(days=offset)

    def add(self, title="Corte de agua", category="mantenimiento", tower=None, expires=None, media=None,
            media_type=None, message="El agua se suspende de 8 a 12.", event=(None, None), minutes_ago=0):
        """Un comunicado guardado directamente; ``expires`` son los días desde hoy (negativo: ya venció)."""
        announcement = Announcement(
            title=title, message=message, category=category, tower_id=tower, author_id=self.admin.id,
            expires_at=self.day(expires) if expires is not None else None,
            event_date=self.day(event[0]).isoformat() if event[0] is not None else None, event_time=event[1],
            media_url=media, media_type=media_type, created_at=utc_now() - timedelta(minutes=minutes_ago),
        )
        db.session.add(announcement)
        db.session.commit()
        return announcement

    def read_by(self, announcement, *residents):
        for resident in residents:
            db.session.add(AnnouncementRead(
                announcement_id=announcement.id, user_id=resident.id, apartment_id=resident.apartment_id,
            ))
        db.session.commit()

    def reload(self, announcement):
        db.session.expire_all()
        return db.session.get(Announcement, announcement.id)

    @staticmethod
    def link_of(body, text):
        """La dirección del enlace que dice ``text``, con sus parámetros ya separados."""
        found = re.search(r'href="([^"]+)"[^>]*>\s*' + re.escape(text), body)
        assert found, f"no hay un enlace «{text}»"
        parts = urlsplit(html.unescape(found.group(1)))
        return parts.path, {key: values[0] for key, values in parse_qs(parts.query).items()}


class WebAnnouncementListTests(WebAnnouncementCase):
    def test_pages_ask_for_login(self):
        anonymous = self.app.test_client()
        for path in ("/web/comunicados", "/web/comunicados/1", "/web/comunicados/nuevo", "/web/comunicados/1/adjunto"):
            with self.subTest(path=path):
                response = anonymous.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/web/login", response.headers["Location"])
        # Sin sesión (y sin el código contra CSRF) los formularios no cambian nada.
        announcement = self.add()
        for path, data in (
            (f"/web/comunicados/{announcement.id}/retirar", {}),
            ("/web/comunicados/nuevo", {"title": "Hola", "message": "Hola", "category": "urgente"}),
        ):
            with self.subTest(path=path):
                self.assertIn(anonymous.post(path, data=data).status_code, (302, 400))
        self.assertIsNone(self.reload(announcement).retired_at)
        self.assertEqual(Announcement.query.count(), 1)

    def test_the_menu_and_the_panel_lead_to_the_list_and_to_the_form(self):
        body = self.page("/web/")
        self.assertIn('href="/web/comunicados"', body)
        self.assertIn('href="/web/comunicados/nuevo"', body)
        page = self.page("/web/comunicados")
        self.assertRegex(
            page, r'<a[^>]*href="/web/comunicados"[^>]*aria-current="page"|<a[^>]*aria-current="page"[^>]*href="/web/comunicados"',
        )

    def test_it_opens_on_the_current_ones_with_the_numbers_of_both_tabs(self):
        current = self.add("Corte de agua", expires=5)
        endless = self.add("Normas de la piscina", category="zonas_comunes", minutes_ago=5)
        old = self.add("Asamblea del año pasado", category="asamblea", expires=-3)

        body = self.page("/web/comunicados")

        self.assertIn("2 comunicados", body)
        self.assertIn("Vigentes (2)", body)
        self.assertIn("Archivados (1)", body)
        self.assertRegex(body, r'aria-current="page">Vigentes \(2\)')
        self.assertIn(f'href="/web/comunicados/{current.id}"', body)
        self.assertIn(f'href="/web/comunicados/{endless.id}"', body)
        self.assertNotIn(f'href="/web/comunicados/{old.id}', body)
        # Sin un comunicado elegido, la lista queda sola y a la derecha se invita a elegir uno.
        self.assertNotIn("inbox-page has-detail", body)
        self.assertIn("Elige un comunicado de la lista", body)

    def test_the_archived_tab_lists_the_ones_past_their_expiry(self):
        self.add("Vigente", expires=5)
        old = self.add("Asamblea del año pasado", category="asamblea", expires=-3)

        body = self.page("/web/comunicados?estado=archivados")

        self.assertRegex(body, r'aria-current="page">Archivados \(1\)')
        self.assertIn(f'href="/web/comunicados/{old.id}?estado=archivados"', body)
        self.assertIn("Asamblea del año pasado", body)
        self.assertNotIn(">Vigente<", body)
        self.assertRegex(body, r"Venció el \d{2}/\d{2}/\d{4}")

    def test_the_newest_comes_first(self):
        old = self.add("Más viejo", minutes_ago=30)
        new = self.add("Más nuevo", minutes_ago=1)

        body = self.page("/web/comunicados")

        self.assertLess(body.index(f"/web/comunicados/{new.id}"), body.index(f"/web/comunicados/{old.id}"))

    def test_each_row_says_who_it_is_for_its_category_how_many_read_it_and_what_it_carries(self):
        read = self.add("Fumigación", category="seguridad", tower=self.tower_1, media=PHOTO, media_type="image",
                        expires=5)
        self.read_by(read, self.resident)
        self.add("Normas de la piscina", category="zonas_comunes")

        body = self.page("/web/comunicados")

        for text in ("Fumigación", "Seguridad", "Torre 1", "Lo leyeron 1 de 1 apartamento", "Con adjunto",
                     "Zonas comunes", "Toda la unidad", "Lo leyeron 0 de 2 apartamentos"):
            self.assertIn(text, body)
        self.assertRegex(body, r"Vence el \d{2}/\d{2}/\d{4}")

    def test_an_old_announcement_without_category_still_shows_up(self):
        old = self.add("Anterior a las categorías", category=None)

        body = self.page("/web/comunicados")

        self.assertIn(f'href="/web/comunicados/{old.id}"', body)
        self.assertIn("Anterior a las categorías", body)

    def test_nothing_heavy_travels_in_the_list(self):
        self.add("Con foto", media=PHOTO, media_type="image")

        body = self.page("/web/comunicados")

        self.assertNotIn("data:image", body)
        self.assertNotIn("base64", body)

    def test_filters_by_text_category_and_audience_change_the_list_and_the_numbers(self):
        water = self.add("Corte de agua", category="mantenimiento", tower=self.tower_1)
        gas = self.add("Fuga de gas", category="urgente")
        assembly = self.add("Citación", category="asamblea", message="Será la asamblea del sábado.")

        by_text = self.page("/web/comunicados?q=ASAMBLEA")
        by_category = self.page("/web/comunicados?categoria=urgente")
        by_tower = self.page(f"/web/comunicados?torre={self.tower_1}")
        by_unit = self.page("/web/comunicados?torre=unit")

        self.assertIn(f"/web/comunicados/{assembly.id}", by_text)
        self.assertNotIn(f"/web/comunicados/{water.id}", by_text)
        self.assertIn("1 comunicado con esos filtros", by_text)
        self.assertIn("Vigentes (1)", by_text)
        self.assertIn(f"/web/comunicados/{gas.id}", by_category)
        self.assertNotIn(f"/web/comunicados/{water.id}", by_category)
        self.assertIn(f"/web/comunicados/{water.id}", by_tower)
        self.assertNotIn(f"/web/comunicados/{gas.id}", by_tower)
        self.assertIn(f"/web/comunicados/{gas.id}", by_unit)
        self.assertIn(f"/web/comunicados/{assembly.id}", by_unit)
        self.assertNotIn(f"/web/comunicados/{water.id}", by_unit)
        # Lo escrito y elegido en el filtro vuelve a verse en el formulario.
        self.assertIn('value="ASAMBLEA"', by_text)
        self.assertRegex(by_category, r'<option value="urgente" selected>Urgente</option>')
        self.assertRegex(by_unit, r'<option value="unit" selected>Toda la unidad</option>')
        self.assertRegex(by_tower, rf'<option value="{self.tower_1}" selected>Torre 1</option>')

    def test_unknown_filter_values_are_ignored(self):
        item = self.add()

        body = self.page("/web/comunicados?estado=inventada&categoria=chisme&torre=abc")

        self.assertIn(f"/web/comunicados/{item.id}", body)
        self.assertRegex(body, r'aria-current="page">Vigentes')
        self.assertNotIn("Quitar filtros", body)

    def test_tab_links_keep_the_filters_and_the_default_tab_stays_out_of_the_address(self):
        self.add()

        body = self.page("/web/comunicados?q=agua&categoria=mantenimiento&torre=unit")

        path, args = self.link_of(body, "Archivados")
        self.assertEqual(path, "/web/comunicados")
        self.assertEqual(args, {"q": "agua", "categoria": "mantenimiento", "torre": "unit", "estado": "archivados"})
        path, args = self.link_of(body, "Vigentes")
        self.assertNotIn("estado", args)
        self.assertEqual(args["q"], "agua")

    def test_quitar_filtros_keeps_the_tab(self):
        body = self.page("/web/comunicados?estado=archivados&q=agua")

        path, args = self.link_of(body, "Quitar filtros")

        self.assertEqual((path, args), ("/web/comunicados", {"estado": "archivados"}))

    def test_each_tab_has_its_own_empty_text_and_filters_have_theirs(self):
        self.assertIn("No hay comunicados vigentes.", self.page("/web/comunicados"))
        self.assertIn("No hay comunicados archivados", self.page("/web/comunicados?estado=archivados"))
        self.add()
        self.assertIn("No hay comunicados que coincidan con esos filtros.", self.page("/web/comunicados?q=nada"))

    def test_long_lists_are_cut_in_pages(self):
        for number in range(17):
            self.add(f"Comunicado {number}", minutes_ago=number)

        first = self.page("/web/comunicados")
        second = self.page("/web/comunicados?page=2")

        self.assertIn("Página 1 de 2", first)
        self.assertIn("Siguiente ›", first)
        self.assertIn("Página 2 de 2", second)
        self.assertIn("‹ Anterior", second)
        # Una página que ya no existe lleva a la última.
        response = self.client.get("/web/comunicados?page=9")
        self.assertEqual(response.status_code, 302)
        self.assertIn("page=2", response.headers["Location"])

    def test_text_written_by_someone_is_never_run(self):
        self.add("<script>alert(1)</script>", message="<img src=x onerror=alert(2)>")

        body = self.page("/web/comunicados")

        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)


class WebAnnouncementDetailTests(WebAnnouncementCase):
    def test_the_detail_shows_the_announcement_next_to_the_list(self):
        item = self.add(
            "Asamblea general", category="asamblea", expires=10, event=(7, "19:00"),
            message="Línea uno\nLínea dos",
        )

        body = self.page(f"/web/comunicados/{item.id}")

        self.assertIn("inbox-page has-detail", body)
        self.assertRegex(body, r'<h2 id="detail-title"[^>]*>Asamblea general</h2>')
        for text in ("Asamblea", "Toda la unidad", "Línea uno\nLínea dos", "a las 19:00", "Lucía Vargas", "Vencimiento"):
            self.assertIn(text, body)
        self.assertRegex(body, r"Evento</dt><dd>\d{2}/\d{2}/\d{4} a las 19:00")
        self.assertIn('aria-current="true"', body)
        path, args = self.link_of(body, "‹ Volver a la lista")
        self.assertEqual((path, args), ("/web/comunicados", {}))

    def test_an_announcement_that_never_expires_says_so(self):
        item = self.add()

        self.assertIn("No vence", self.page(f"/web/comunicados/{item.id}"))

    def test_an_expired_one_says_why_it_is_in_the_archive(self):
        item = self.add("Vieja", expires=-2)

        body = self.page(f"/web/comunicados/{item.id}?estado=archivados")

        self.assertIn("ya venció, por eso está en Archivados", body)
        self.assertIn("Archivado</span>", body)
        path, args = self.link_of(body, "‹ Volver a la lista")
        self.assertEqual(args, {"estado": "archivados"})

    def test_it_shows_how_many_apartments_read_it(self):
        item = self.add("Para todos")
        self.read_by(item, self.resident)

        body = self.page(f"/web/comunicados/{item.id}")

        self.assertRegex(body, r"Lo han leído <strong>1</strong> de 2 apartamentos")
        self.assertIn('<progress class="reading" max="2" value="1"', body)

    def test_a_tower_announcement_counts_only_the_apartments_of_that_tower(self):
        item = self.add("Solo torre 2", tower=self.tower_2)

        body = self.page(f"/web/comunicados/{item.id}")

        self.assertIn("Torre 2", body)
        self.assertRegex(body, r"Lo han leído <strong>0</strong> de 1 apartamento a los que")
        self.assertIn('max="1" value="0"', body)

    def test_with_nobody_to_reach_it_says_so_instead_of_a_bar(self):
        item = self.add("Para todos")
        for resident in (self.resident, self.other):
            resident.is_active = False
        db.session.commit()

        body = self.page(f"/web/comunicados/{item.id}")

        self.assertIn("Todavía no hay apartamentos con residentes", body)
        self.assertNotIn("<progress", body)

    def test_the_attachment_is_requested_apart(self):
        item = self.add("Con foto", media=PHOTO, media_type="image")

        body = self.page(f"/web/comunicados/{item.id}")

        self.assertIn(f'src="/web/comunicados/{item.id}/adjunto"', body)
        self.assertNotIn("data:image", body)
        self.assertNotIn("base64", body)

    def test_video_and_audio_use_their_own_player(self):
        video = self.add("Con video", media="data:video/mp4;base64," + base64.b64encode(MP4).decode(), media_type="video")
        audio = self.add("Con audio", media="data:audio/mpeg;base64," + base64.b64encode(MP3).decode(), media_type="audio")

        self.assertRegex(self.page(f"/web/comunicados/{video.id}"), r"<video controls[^>]*adjunto")
        self.assertRegex(self.page(f"/web/comunicados/{audio.id}"), r"<audio controls[^>]*adjunto")

    def test_the_retire_button_asks_for_confirmation_and_goes_back_to_the_same_list(self):
        item = self.add("Corte de agua")

        body = self.page(f"/web/comunicados/{item.id}?q=agua")

        self.assertIn(f'action="/web/comunicados/{item.id}/retirar"', body)
        self.assertIn('data-confirm="¿Retirar el comunicado «Corte de agua»?', body)
        self.assertRegex(body, r'name="next" value="/web/comunicados\?q=agua"')

    def test_an_unknown_or_retired_announcement_is_a_404(self):
        retired = self.add("Retirado")
        self.post(f"/web/comunicados/{retired.id}/retirar")

        for announcement_id in (retired.id, 99999):
            with self.subTest(announcement_id=announcement_id):
                self.assertEqual(self.client.get(f"/web/comunicados/{announcement_id}").status_code, 404)


class WebAnnouncementPublishTests(WebAnnouncementCase):
    def publish(self, data=None, media=None):
        form = {"title": "Corte de agua", "message": "El agua se suspende de 8 a 12.", "category": "mantenimiento"}
        form.update(data or {})
        if media is not None:
            form["media"] = (io.BytesIO(media[1]), media[0])
        return self.post("/web/comunicados/nuevo", form)

    def test_the_form_has_everything_a_publication_needs(self):
        body = self.page("/web/comunicados/nuevo")

        self.assertIn('enctype="multipart/form-data"', body)
        self.assertIn('name="csrf_token"', body)
        for name in ("title", "message", "category", "towerId", "expiresAt", "eventDate", "eventTime", "media"):
            self.assertIn(f'name="{name}"', body)
        for label in ("Mantenimiento", "Urgente", "Asamblea", "Seguridad", "Zonas comunes"):
            self.assertIn(f">{label}</option>", body)
        for tower in ("Toda la unidad", "Torre 1", "Torre 2"):
            self.assertIn(f">{tower}</option>", body)
        self.assertIn(f'min="{colombia_today().isoformat()}"', body)
        self.assertIn('accept="image/png,image/jpeg,image/webp,video/mp4', body)
        self.assertIn(',application/pdf"', body)
        self.assertIn("Foto, video, audio o PDF (opcional)", body)
        self.assertIn("Publicar comunicado", body)
        self.assertIn('data-confirm="¿Publicar el comunicado?', body)
        self.assertRegex(body, r'<input id="title" name="title"[^>]*required')
        self.assertRegex(body, r'<select id="category" name="category"[^>]*required')

    def test_publishing_tells_the_residents_and_opens_the_announcement(self):
        response = self.publish()

        self.assertEqual(response.status_code, 302)
        announcement = Announcement.query.one()
        self.assertEqual(response.headers["Location"], f"/web/comunicados/{announcement.id}")
        self.assertEqual(announcement.title, "Corte de agua")
        self.assertEqual(announcement.category, "mantenimiento")
        self.assertIsNone(announcement.tower_id)
        self.assertIsNone(announcement.media_url)
        self.assertEqual(announcement.author_id, self.admin.id)
        notified = {item.user_id for item in Notification.query.filter_by(type="announcement")}
        self.assertEqual(notified, {self.resident.id, self.other.id})
        self.assertIn("Comunicado publicado.", self.text(self.client.get(response.headers["Location"])))

    def test_publishing_everything_at_once(self):
        response = self.publish(
            {
                "towerId": str(self.tower_1), "expiresAt": self.day(9).isoformat(),
                "eventDate": self.day(5).isoformat(), "eventTime": "19:30", "category": "urgente",
            },
            media=("aviso.png", PNG),
        )

        self.assertEqual(response.status_code, 302)
        announcement = Announcement.query.one()
        self.assertEqual(announcement.tower_id, self.tower_1)
        self.assertEqual(announcement.category, "urgente")
        self.assertEqual(announcement.expires_at, self.day(9))
        self.assertEqual((announcement.event_date, announcement.event_time), (self.day(5).isoformat(), "19:30"))
        self.assertEqual((announcement.media_type, announcement.media_url), ("image", PHOTO))
        # Solo los residentes de esa torre reciben el aviso.
        notified = {item.user_id for item in Notification.query.filter_by(type="announcement")}
        self.assertEqual(notified, {self.resident.id})

    def test_the_kind_of_attachment_comes_from_the_file_and_not_from_its_name(self):
        for name, content, kind, mime in (
            ("grabacion.bin", MP3, "audio", "audio/mpeg"),
            ("video.txt", MP4, "video", "video/mp4"),
            ("foto.mp3", PNG, "image", "image/png"),
        ):
            with self.subTest(name=name):
                Announcement.query.delete()
                db.session.commit()
                self.assertEqual(self.publish(media=(name, content)).status_code, 302)
                announcement = Announcement.query.one()
                self.assertEqual(announcement.media_type, kind)
                self.assertTrue(announcement.media_url.startswith(f"data:{mime};base64,"))

    def test_without_a_file_the_form_is_sent_as_it_is(self):
        # El navegador manda el campo del archivo vacío, con nombre en blanco.
        response = self.post("/web/comunicados/nuevo", {
            "title": "Sin archivo", "message": "Hola", "category": "urgente", "media": (io.BytesIO(b""), ""),
        })

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(Announcement.query.one().media_url)

    def test_a_file_that_is_not_a_photo_a_video_an_audio_or_a_pdf_is_refused_and_nothing_is_lost(self):
        for name, content in (
            ("foto.png", b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>"),
            ("pagina.png", b"<html><script>alert(1)</script></html>"),
            ("documento.pdf", b"PK\x03\x04 un .docx con nombre de PDF"),
            ("vacio.png", b"x"),
        ):
            with self.subTest(name=name):
                response = self.publish({"title": "No se pierde"}, media=(name, content))
                body = self.text(response)
                self.assertEqual(response.status_code, 400)
                self.assertIn("no es una imagen, un video, un audio ni un PDF", body)
                self.assertIn('value="No se pierde"', body)
                self.assertEqual(Announcement.query.count(), 0)

    def test_a_pdf_is_published_as_a_document(self):
        # Por ejemplo el acta de la asamblea: se reconoce por sus primeros bytes, no por el nombre.
        response = self.publish({"title": "Acta de la asamblea"}, media=("acta.bin", b"%PDF-1.7 acta"))

        self.assertEqual(response.status_code, 302)
        announcement = Announcement.query.one()
        self.assertEqual(announcement.media_type, "document")
        self.assertTrue(announcement.media_url.startswith("data:application/pdf;base64,"))

    def test_a_file_that_weighs_too_much_is_refused(self):
        response = self.publish(media=("enorme.png", PNG + b"0" * uploads.MAX_MEDIA_BYTES))

        self.assertEqual(response.status_code, 400)
        self.assertIn("El archivo pesa demasiado: el máximo es 6 MB.", self.text(response))
        self.assertEqual(Announcement.query.count(), 0)

    def test_the_messages_of_the_api_are_shown_and_what_was_written_is_kept(self):
        past = (colombia_today() - timedelta(days=2)).isoformat()
        for data, message in (
            ({"category": ""}, "El comunicado necesita una categoría"),
            ({"expiresAt": past}, "La fecha de vencimiento no puede ser anterior a hoy."),
            ({"towerId": "99999"}, "Selecciona una torre válida para el comunicado."),
            ({"title": "A" * 151}, "El título no puede pasar de 150 caracteres."),
            ({"message": ""}, "mensaje"),
            ({"eventTime": "tarde"}, "hora"),
        ):
            with self.subTest(message=message):
                response = self.publish({"title": "Se conserva", **data})
                body = self.text(response)
                self.assertEqual(response.status_code, 400)
                self.assertIn(message, html.unescape(body))
                self.assertEqual(Announcement.query.count(), 0)
        # Lo escrito vuelve al formulario.
        response = self.publish({"title": "Se conserva", "message": "Texto largo", "category": "", "towerId": str(self.tower_2)})
        body = self.text(response)
        self.assertIn('value="Se conserva"', body)
        self.assertRegex(body, r">\s*Texto largo</textarea>")
        self.assertRegex(body, rf'<option value="{self.tower_2}" selected>Torre 2</option>')

    def test_when_the_form_is_refused_the_file_has_to_be_chosen_again(self):
        response = self.publish({"category": ""}, media=("aviso.png", PNG))

        self.assertEqual(response.status_code, 400)
        self.assertIn("Vuelve a elegir el archivo", self.text(response))

    def test_forms_without_the_security_code_are_refused(self):
        response = self.client.post("/web/comunicados/nuevo", data={
            "title": "Hola", "message": "Hola", "category": "urgente",
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Announcement.query.count(), 0)


class WebAnnouncementRetireTests(WebAnnouncementCase):
    def test_retiring_hides_it_but_keeps_the_row_and_leaves_a_trace(self):
        item = self.add("Corte de agua")
        keep = self.add("Se queda")

        response = self.post(f"/web/comunicados/{item.id}/retirar")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/web/comunicados")
        row = self.reload(item)
        self.assertIsNotNone(row)
        self.assertIsNotNone(row.retired_at)
        self.assertEqual(row.retired_by_id, self.admin.id)
        self.assertIsNone(self.reload(keep).retired_at)
        self.assertEqual(
            AuditLog.query.filter_by(entity_type="announcement", entity_id=item.id, action="retired").count(), 1,
        )
        page = self.text(self.client.get(response.headers["Location"]))
        self.assertIn("Anuncio retirado.", page)
        self.assertNotIn(f"/web/comunicados/{item.id}", page)
        self.assertIn(f"/web/comunicados/{keep.id}", page)

    def test_it_goes_back_to_the_list_it_came_from(self):
        item = self.add()

        response = self.post(f"/web/comunicados/{item.id}/retirar", {"next": "/web/comunicados?estado=archivados&q=agua"})

        self.assertEqual(response.headers["Location"], "/web/comunicados?estado=archivados&q=agua")

    def test_another_site_is_never_the_next_page(self):
        item = self.add()

        response = self.post(f"/web/comunicados/{item.id}/retirar", {"next": "https://otro-sitio.example/robar"})

        self.assertEqual(response.headers["Location"], "/web/comunicados")

    def test_retiring_twice_shows_the_message_of_the_api(self):
        item = self.add()
        self.post(f"/web/comunicados/{item.id}/retirar")

        response = self.post(f"/web/comunicados/{item.id}/retirar", follow=True)

        self.assertIn("El anuncio ya estaba retirado.", self.text(response))

    def test_an_unknown_announcement_shows_the_message_of_the_api(self):
        response = self.post("/web/comunicados/99999/retirar", follow=True)

        self.assertIn("Anuncio no encontrado", self.text(response))

    def test_forms_without_the_security_code_are_refused(self):
        item = self.add()

        response = self.client.post(f"/web/comunicados/{item.id}/retirar")

        self.assertEqual(response.status_code, 400)
        self.assertIsNone(self.reload(item).retired_at)


class WebAnnouncementAttachmentTests(WebAnnouncementCase):
    def test_a_photo_is_served_with_a_strict_policy(self):
        item = self.add("Con foto", media=PHOTO, media_type="image")

        response = self.client.get(f"/web/comunicados/{item.id}/adjunto")

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
        again = self.client.get(f"/web/comunicados/{item.id}/adjunto", headers={"If-None-Match": response.headers["ETag"]})
        self.assertEqual(again.status_code, 304)

    def test_it_can_be_requested_by_parts(self):
        item = self.add("Con foto", media=PHOTO, media_type="image")

        response = self.client.get(f"/web/comunicados/{item.id}/adjunto", headers={"Range": "bytes=0-3"})

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.data, PNG[:4])

    def test_what_is_not_a_photo_a_video_or_an_audio_is_not_served(self):
        svg = "data:image/svg+xml;base64," + base64.b64encode(b"<svg onload='x()'/>").decode()
        page = "data:text/html;base64," + base64.b64encode(b"<script>x()</script>").decode()
        for media in (svg, page, "https://ejemplo.com/a.png", None):
            with self.subTest(media=media):
                item = self.add("Raro", media=media, media_type="image" if media else None)
                self.assertEqual(self.client.get(f"/web/comunicados/{item.id}/adjunto").status_code, 404)

    def test_a_pdf_is_offered_for_download_and_never_opened_inside_the_web(self):
        pdf = b"%PDF-1.7 acta"
        item = self.add("Acta", media="data:application/pdf;base64," + base64.b64encode(pdf).decode(), media_type="document")

        body = self.page(f"/web/comunicados/{item.id}")
        response = self.client.get(f"/web/comunicados/{item.id}/adjunto")

        self.assertIn("Descargar el documento PDF", body)
        self.assertNotIn(f'src="/web/comunicados/{item.id}/adjunto"', body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertEqual(response.data, pdf)
        self.assertEqual(response.headers["Content-Disposition"], 'attachment; filename="adjunto.pdf"')
        self.assertIn("sandbox", response.headers["Content-Security-Policy"])

    def test_a_pdf_label_on_something_that_is_not_a_pdf_is_not_served(self):
        fake = "data:application/pdf;base64," + base64.b64encode(b"<html><script>x()</script></html>").decode()
        item = self.add("Falso", media=fake, media_type="document")

        self.assertEqual(self.client.get(f"/web/comunicados/{item.id}/adjunto").status_code, 404)

    def test_a_retired_or_unknown_announcement_has_no_attachment(self):
        item = self.add("Con foto", media=PHOTO, media_type="image")
        self.post(f"/web/comunicados/{item.id}/retirar")

        for announcement_id in (item.id, 99999):
            with self.subTest(announcement_id=announcement_id):
                self.assertEqual(self.client.get(f"/web/comunicados/{announcement_id}/adjunto").status_code, 404)


class UploadReadingTests(unittest.TestCase):
    def test_the_kind_of_a_file_comes_from_its_first_bytes(self):
        riff = b"RIFF\x24\x00\x00\x00"
        for content, expected in (
            (PNG, ("image/png", "image")),
            (b"\xff\xd8\xff\xe0" + b"jpeg", ("image/jpeg", "image")),
            (riff + b"WEBPVP8 ", ("image/webp", "image")),
            (MP4, ("video/mp4", "video")),
            (b"\x00\x00\x00\x20ftypM4A " + b"audio", ("audio/mp4", "audio")),
            (b"\x1a\x45\xdf\xa3" + b"webm", ("video/webm", "video")),
            (b"OggS\x00\x02", ("audio/ogg", "audio")),
            (riff + b"WAVEfmt ", ("audio/wav", "audio")),
            (MP3, ("audio/mpeg", "audio")),
            (b"\xff\xfb\x90\x64" + b"mp3", ("audio/mpeg", "audio")),
        ):
            with self.subTest(content=content[:12]):
                self.assertEqual(uploads.sniff_media(content), expected)

    def test_what_looks_like_nothing_known_is_not_media(self):
        for content in (
            b"", b"x", b"<svg onload='x()'/>", b"<html></html>", b"%PDF-1.4", b"GIF89a", b"PK\x03\x04",
            b"\xff\xd9\xff\xff",  # empieza en 0xFF pero no es una trama MPEG
            b"\xff\xe0\x00",  # versión y capa reservadas
        ):
            with self.subTest(content=content):
                self.assertIsNone(uploads.sniff_media(content))

    def test_read_media_builds_the_text_the_app_also_sends(self):
        from werkzeug.datastructures import FileStorage

        upload = FileStorage(stream=io.BytesIO(PNG), filename="foto.png")

        self.assertEqual(uploads.read_media(upload), (PHOTO, "image"))

    def test_a_pdf_is_read_only_where_documents_are_allowed(self):
        from werkzeug.datastructures import FileStorage

        pdf = b"%PDF-1.4 documento"
        allowed = uploads.read_media(FileStorage(stream=io.BytesIO(pdf), filename="a.pdf"), allow_document=True)
        self.assertEqual(allowed, ("data:application/pdf;base64," + base64.b64encode(pdf).decode(), "document"))
        with self.assertRaises(uploads.UploadError):
            uploads.read_media(FileStorage(stream=io.BytesIO(pdf), filename="a.pdf"))

    def test_no_file_chosen_is_not_an_error(self):
        from werkzeug.datastructures import FileStorage

        self.assertIsNone(uploads.read_media(None))
        self.assertIsNone(uploads.read_media(FileStorage(stream=io.BytesIO(b""), filename="")))

    def test_errors_carry_the_message_for_the_person(self):
        from werkzeug.datastructures import FileStorage

        with self.assertRaises(uploads.UploadError) as heavy:
            uploads.read_media(FileStorage(stream=io.BytesIO(PNG + b"0" * uploads.MAX_MEDIA_BYTES), filename="a.png"))
        with self.assertRaises(uploads.UploadError) as strange:
            uploads.read_media(FileStorage(stream=io.BytesIO(b"<svg/>"), filename="a.png"))

        self.assertIn("pesa demasiado", str(heavy.exception))
        self.assertIn("MP4", str(strange.exception))


if __name__ == "__main__":
    unittest.main()
