"""Pruebas del buscador con el botón «Filtros» de la web y de lo que la web tomó del rediseño de la app.

Los filtros ya no ocupan la página: van en un panel que se abre con el botón «Filtros»; los que están
puestos salen como etiquetas que se quitan con un clic. Además, los avisos y las insignias llevan su
ícono, y al responder una PQRS, crearla o escribir en una reserva se puede adjuntar un archivo.
"""

import html
import io
import re
import unittest
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from extensions import db
from models import CommonArea, Pqrs, PqrsMessage, Reservation, ReservationMessage
from time_utils import colombia_today
from web_testing import WebTestCase

PNG = b"\x89PNG\r\n\x1a\n" + b"imagen-de-prueba"
PDF = b"%PDF-1.4\n%prueba\n"


class WebFilterCase(WebTestCase):
    def setUp(self):
        super().setUp()
        self.log_in()

    def pqrs(self, subject="Ascensor dañado", status="abierta", category="Daño"):
        item = Pqrs(resident_id=self.resident.id, category=category, subject=subject, message="Detalle", status=status)
        db.session.add(item)
        db.session.commit()
        return item

    @staticmethod
    def chips(body):
        """Las etiquetas de los filtros puestos: lista de (texto, ruta, parámetros)."""
        found = []
        for href, text in re.findall(r'<a class="chip" href="([^"]+)">([^<]+)<', body):
            parts = urlsplit(html.unescape(href))
            found.append((html.unescape(text), parts.path, {k: v[0] for k, v in parse_qs(parts.query).items()}))
        return found

    @staticmethod
    def panel(body):
        """La etiqueta que abre el panel de filtros (con o sin «hidden») y el botón que lo abre."""
        return re.search(r'<div class="filters-panel" id="panel-filtros"( hidden)?>', body), re.search(
            r'<button type="submit" name="filtros" value="1" class="btn btn-quiet filters-toggle( is-on)?"\s+'
            r'data-filters-toggle aria-expanded="(true|false)" aria-controls="panel-filtros">', body)


class WebFilterButtonTests(WebFilterCase):
    def test_the_filters_are_closed_and_the_button_sits_next_to_the_search(self):
        self.pqrs()

        body = self.page("/web/pqrs")

        panel, button = self.panel(body)
        self.assertEqual(panel.group(1), " hidden")
        self.assertEqual((button.group(1), button.group(2)), (None, "false"))
        # Primero «Buscar», después «Filtros»: Enter en el buscador busca, no abre el panel.
        self.assertLess(body.index('<button type="submit" class="btn">Buscar</button>'), button.start())
        self.assertIn("Aplicar filtros", body)
        self.assertEqual(self.chips(body), [])
        self.assertNotIn("data-autosubmit", body)

    def test_without_javascript_the_button_opens_the_panel(self):
        self.pqrs()

        body = self.page("/web/pqrs?filtros=1")

        panel, button = self.panel(body)
        self.assertIsNone(panel.group(1))
        self.assertEqual(button.group(2), "true")

    def test_the_filters_in_use_show_as_removable_chips_and_the_button_counts_them(self):
        self.pqrs()
        self.pqrs("Ruido", status="resuelta", category="Queja")

        body = self.page("/web/pqrs?estado=abierta&tipo=Da%C3%B1o&q=Ascensor")

        self.assertIn("Filtros · 2", body)
        self.assertEqual(self.panel(body)[1].group(1), " is-on")
        chips = self.chips(body)
        self.assertEqual([text for text, _path, _args in chips], ["Estado: Abierta", "Tipo: Daño"])
        # Quitar un filtro conserva los demás y lo que está escrito en el buscador.
        self.assertEqual(chips[0][1:], ("/web/pqrs", {"tipo": "Daño", "q": "Ascensor"}))
        self.assertEqual(chips[1][1:], ("/web/pqrs", {"estado": "abierta", "q": "Ascensor"}))
        self.assertIn("(quitar este filtro)", body)
        self.assertIn("Ascensor dañado", body)
        self.assertNotIn("Ruido", body)

    def test_a_search_alone_is_not_a_chip_but_can_be_cleared(self):
        self.pqrs()

        body = self.page("/web/pqrs?q=Ascensor")

        self.assertEqual(self.chips(body), [])
        self.assertIn('<a class="btn btn-quiet" href="/web/pqrs">Quitar filtros</a>', body)

    def test_chips_keep_the_tab_of_the_list(self):
        hall = CommonArea(name="Salón social")
        db.session.add(hall)
        db.session.flush()
        day = (colombia_today() + timedelta(days=3)).isoformat()
        db.session.add(Reservation(
            resident_id=self.resident.id, common_area_id=hall.id, date=day, time_slot="10:00-12:00", status="aprobada",
        ))
        db.session.commit()

        body = self.page(f"/web/reservas?estado=aprobada&zona={hall.id}&archivadas=1")

        chips = self.chips(body)
        self.assertEqual([text for text, _path, _args in chips], ["Zona: Salón social", "Con archivadas"])
        self.assertEqual(chips[0][1:], ("/web/reservas", {"estado": "aprobada", "archivadas": "1"}))
        self.assertIn('<input type="hidden" name="estado" value="aprobada">', body)

    def test_every_list_with_filters_has_the_button_and_the_search_only_lists_do_not(self):
        with_filters = ("/web/pqrs", "/web/reservas", "/web/visitas", "/web/usuarios", "/web/comunicados",
                        "/web/estructura/apartamentos", "/web/estructura/parqueaderos", "/web/estructura/cuartos")
        for path in with_filters:
            with self.subTest(path=path):
                body = self.page(path)
                panel, button = self.panel(body)
                self.assertIsNotNone(button, "falta el botón «Filtros»")
                self.assertEqual(panel.group(1), " hidden")
        for path in ("/web/paqueteria", "/web/vehiculos"):
            with self.subTest(path=path):
                body = self.page(path)
                self.assertNotIn("data-filters-toggle", body)
                self.assertIn('<button type="submit" class="btn">Buscar</button>', body)

    def test_user_and_date_filters_have_their_chips(self):
        users = self.chips(self.page("/web/usuarios?rol=GUARD&estado=activos"))
        self.assertEqual([text for text, _path, _args in users], ["Rol: Portería", "Estado: Activos"])
        self.assertEqual(users[0][1:], ("/web/usuarios", {"estado": "activos"}))

        visits = self.chips(self.page("/web/visitas?estado=dentro&desde=2026-11-01&hasta=2026-11-30"))
        self.assertEqual([text for text, _path, _args in visits], ["Desde: 01/11/2026", "Hasta: 30/11/2026"])
        self.assertEqual(visits[0][1:], ("/web/visitas", {"estado": "dentro", "hasta": "2026-11-30"}))


class WebRedesignParityTests(WebFilterCase):
    def test_result_notices_have_their_icon_and_a_close_button(self):
        pqrs = self.pqrs()

        done = self.text(self.post(
            f"/web/pqrs/{pqrs.id}/responder", {"status": "en_proceso", "adminResponse": "La estamos revisando"}, follow=True,
        ))
        self.assertRegex(done, r'<div class="notice notice-flash notice-success" role="status">\s*<svg class="icon"')
        self.assertIn("PQRS actualizada.", done)
        self.assertIn("data-dismiss-notice", done)
        self.assertIn("Cerrar el aviso", done)

        failed = self.text(self.post(f"/web/pqrs/{pqrs.id}/responder", {"status": "resuelta", "adminResponse": ""}))
        self.assertRegex(failed, r'<div class="notice notice-flash notice-error" role="alert">\s*<svg class="icon"')

    def test_status_badges_have_an_icon_besides_the_colour(self):
        self.pqrs()

        body = self.page("/web/pqrs")

        self.assertRegex(body, r'<span class="badge badge-alert"><svg class="icon"[^>]*>.*?</svg>Abierta</span>')

    def test_a_reply_to_a_pqrs_can_carry_an_attachment(self):
        pqrs = self.pqrs()
        self.assertIn('name="media"', self.page(f"/web/pqrs/{pqrs.id}"))

        response = self.post(f"/web/pqrs/{pqrs.id}/responder", {
            "status": "en_proceso", "adminResponse": "Mira la foto", "media": (io.BytesIO(PNG), "foto.png"),
        })

        self.assertEqual(response.status_code, 302)
        message = PqrsMessage.query.filter_by(pqrs_id=pqrs.id, author_role="ADMIN").one()
        self.assertEqual(message.media_type, "image")
        self.assertTrue(message.media_url.startswith("data:image/png;base64,"))

    def test_a_reply_with_a_file_that_is_not_allowed_is_refused_and_keeps_the_text(self):
        pqrs = self.pqrs()

        response = self.post(f"/web/pqrs/{pqrs.id}/responder", {
            "status": "en_proceso", "adminResponse": "Mi respuesta", "media": (io.BytesIO(b"<html>"), "pagina.html"),
        })

        body = self.text(response)
        self.assertEqual(response.status_code, 400)
        self.assertIn("El archivo no es una imagen, un video, un audio ni un PDF", body)
        self.assertIn("Mi respuesta", body)
        self.assertEqual(PqrsMessage.query.filter_by(pqrs_id=pqrs.id, author_role="ADMIN").count(), 0)

    def test_a_new_pqrs_can_carry_a_pdf(self):
        self.assertIn('name="media"', self.page("/web/pqrs/nueva"))

        response = self.post("/web/pqrs/nueva", {
            "residentId": str(self.resident.id), "category": "Petición", "subject": "Carta del residente",
            "message": "Trajo una carta", "media": (io.BytesIO(PDF), "carta.pdf"),
        })

        self.assertEqual(response.status_code, 302)
        created = Pqrs.query.filter_by(subject="Carta del residente").one()
        self.assertEqual(created.media_type, "document")
        self.assertTrue(created.media_url.startswith("data:application/pdf;base64,"))

    def test_a_message_in_a_reservation_can_carry_an_attachment(self):
        hall = CommonArea(name="Salón social")
        db.session.add(hall)
        db.session.flush()
        day = (colombia_today() + timedelta(days=3)).isoformat()
        reservation = Reservation(
            resident_id=self.resident.id, common_area_id=hall.id, date=day, time_slot="10:00-12:00", status="pendiente",
        )
        db.session.add(reservation)
        db.session.commit()
        self.assertIn('name="media"', self.page(f"/web/reservas/{reservation.id}"))

        response = self.post(f"/web/reservas/{reservation.id}/mensaje", {
            "message": "Te mando el reglamento", "media": (io.BytesIO(PDF), "reglamento.pdf"),
        })

        self.assertEqual(response.status_code, 302)
        message = ReservationMessage.query.filter_by(reservation_id=reservation.id).one()
        self.assertEqual(message.media_type, "document")


if __name__ == "__main__":
    unittest.main()
