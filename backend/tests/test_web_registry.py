"""Pruebas de «Paquetería y visitas» en la web de administración (HU-088): la consulta del historial de
paquetes, visitas y vehículos de visitantes, con sus pestañas, búsqueda, fechas, detalle, fotos y permisos.
Es solo de consulta: ninguna de estas páginas registra ni cambia nada."""

import base64
import html
import re
import unittest
from datetime import timedelta
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from extensions import db
from models import PackageItem, PackagePickupCode, ParkingSpot, Visit, VisitEvent, VisitorVehicleEntry
from structure_fixtures import apartment_for
from time_utils import colombia_today, utc_now
from web import texts
from web.api import ApiResult
from web_testing import WebTestCase

JPEG = b"\xff\xd8\xff" + b"foto-de-prueba" * 40
PHOTO = "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()
SVG = "data:image/svg+xml;base64," + base64.b64encode(b"<svg xmlns='http://www.w3.org/2000/svg'/>").decode()


class RegistryWebCase(WebTestCase):
    def setUp(self):
        super().setUp()
        self.other = self.make_user(
            "RESIDENT", "carlos-web@test.local", "Carlos", last_name="Pérez",
            apartment_ref=apartment_for("Torre 2 · Apto 202"), occupancy_type="arrendatario",
        )
        db.session.commit()
        self.log_in()

    # --- Datos de ejemplo -----------------------------------------------------------------------

    def package(self, resident=None, status="pendiente", hours=0, created_minutes_ago=None, **fields):
        """Un paquete guardado directamente; ``hours`` son las horas que lleva en la portería."""
        now = utc_now()
        item = PackageItem(
            resident_id=(resident or self.resident).id, registered_by=self.guard.id, status=status,
            arrived_at=now - timedelta(hours=hours) if status in ("pendiente", "entregado") else None,
            **{"description": "Caja", **fields},
        )
        if created_minutes_ago is not None:
            item.created_at = now - timedelta(minutes=created_minutes_ago)
        db.session.add(item)
        db.session.commit()
        return item

    def trash(self, package, by=None):
        package.is_deleted = True
        package.deleted_at = utc_now()
        package.deleted_by_id = by.id if by else None
        db.session.commit()
        return package

    def visit(
        self, resident=None, name="Visitante", status="aprobada", method="app", entered_minutes_ago=None,
        exited_minutes_ago=None, created_minutes_ago=None, stay=None, **fields,
    ):
        """Una visita guardada directamente; los minutos cuentan desde ahora hacia atrás."""
        now = utc_now()
        item = Visit(
            resident_id=(resident or self.resident).id, registered_by=self.guard.id, visitor_name=name,
            type=fields.pop("type", "visitante"), approval_status=status,
            authorization_method=method if status != "pendiente" else None, expected_stay_minutes=stay,
            entered_at=now - timedelta(minutes=entered_minutes_ago) if entered_minutes_ago is not None else None,
            exited_at=now - timedelta(minutes=exited_minutes_ago) if exited_minutes_ago is not None else None,
            **fields,
        )
        if created_minutes_ago is not None:
            item.created_at = now - timedelta(minutes=created_minutes_ago)
        db.session.add(item)
        db.session.commit()
        return item

    def step(self, visit, kind, actor=None, method="app", returning=False):
        visit.events.append(VisitEvent(
            event_type=kind, method=method, actor_id=(actor or self.guard).id, returning_today=returning,
        ))
        db.session.commit()

    def entry(self, plate, days_ago=1, exited=False, resident=None, name="Visitante", spot=None):
        """Una entrada de vehículo de visitante, con la visita a la que pertenece."""
        resident = resident or self.resident
        now = utc_now()
        visit = self.visit(resident, name=name, entered_minutes_ago=days_ago * 24 * 60)
        record = VisitorVehicleEntry(
            plate=plate, visit_id=visit.id, apartment_id=resident.apartment_id, spot_id=spot.id if spot else None,
            entered_at=now - timedelta(days=days_ago), registered_by=self.guard.id,
            exited_at=now - timedelta(days=days_ago, hours=-3) if exited else None,
            exited_by_id=self.guard.id if exited else None,
        )
        db.session.add(record)
        db.session.commit()
        return record

    # --- Lectura de las páginas -----------------------------------------------------------------

    @staticmethod
    def links(body, prefix):
        """Los enlaces de la página que empiezan por ``prefix``: lista de (ruta, parámetros)."""
        found = []
        for href in re.findall(r'href="(' + re.escape(prefix) + r'[^"]*)"', body):
            parts = urlsplit(html.unescape(href))
            found.append((parts.path, {key: values[0] for key, values in parse_qs(parts.query).items()}))
        return found

    def assertInOrder(self, body, *fragments):
        positions = [body.find(fragment) for fragment in fragments]
        for fragment, position in zip(fragments, positions):
            self.assertGreaterEqual(position, 0, f"No aparece «{fragment}»")
        self.assertEqual(positions, sorted(positions), f"Salen en otro orden: {fragments}")

    def main_of(self, body):
        """Solo el contenido de la página (sin el menú), para no confundir lo que dice la barra lateral."""
        return body.split('<main id="contenido"', 1)[1]


# ---------------------------------------------------------------------------
# Lo común: permisos, solo consulta, menú
# ---------------------------------------------------------------------------

class RegistryAccessTests(RegistryWebCase):
    PATHS = (
        "/web/paqueteria", "/web/paqueteria/1", "/web/paqueteria/1/foto",
        "/web/visitas", "/web/visitas/1", "/web/visitas/1/foto", "/web/vehiculos",
    )

    def test_every_page_asks_for_login(self):
        anonymous = self.app.test_client()
        for path in self.PATHS:
            with self.subTest(path=path):
                response = anonymous.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/web/login", response.headers["Location"])

    def test_a_guard_or_a_resident_does_not_get_in(self):
        for email in ("guardia-web@test.local", "residente-web@test.local"):
            with self.subTest(email=email):
                client = self.app.test_client()
                self.client = client
                self.log_in(email)
                for path in ("/web/paqueteria", "/web/visitas", "/web/vehiculos"):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 302)
                    self.assertIn("/web/login", response.headers["Location"])

    def test_nothing_can_be_changed_from_here(self):
        package = self.package()
        visit = self.visit()
        for path in ("/web/paqueteria", f"/web/paqueteria/{package.id}", "/web/visitas", f"/web/visitas/{visit.id}",
                     "/web/vehiculos"):
            with self.subTest(path=path):
                self.assertEqual(self.post(path, {"description": "Otra cosa", "visitorName": "Otro"}).status_code, 405)
        db.session.expire_all()
        self.assertEqual(db.session.get(PackageItem, package.id).description, "Caja")
        self.assertEqual(db.session.get(Visit, visit.id).visitor_name, "Visitante")

    def test_the_pages_only_carry_the_logout_form(self):
        package = self.package()
        visit = self.visit()
        for path in ("/web/paqueteria", f"/web/paqueteria/{package.id}", "/web/visitas", f"/web/visitas/{visit.id}",
                     "/web/vehiculos"):
            with self.subTest(path=path):
                forms = re.findall(r'<form[^>]*method="post"[^>]*action="([^"]*)"', self.page(path))
                self.assertEqual(forms, ["/web/logout"])

    def test_the_pages_are_not_kept_in_the_browser(self):
        package = self.package(media_url=PHOTO, media_type="image")
        for path in ("/web/paqueteria", f"/web/paqueteria/{package.id}", f"/web/paqueteria/{package.id}/foto",
                     "/web/visitas", "/web/vehiculos"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.headers.get("Cache-Control"), "no-store")
                self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")

    def test_the_menu_leads_to_the_section_and_marks_where_you_are(self):
        for path in ("/web/paqueteria", "/web/visitas", "/web/vehiculos"):
            with self.subTest(path=path):
                body = self.page(path)
                self.assertRegex(
                    body, r'<a href="/web/paqueteria" aria-current="page">\s*<span class="nav-icon">.*?Paquetería y visitas',
                )

    def test_the_three_sections_are_linked_from_each_other(self):
        for path, current in (("/web/paqueteria", "Paquetes"), ("/web/visitas", "Visitas"),
                              ("/web/vehiculos", "Vehículos de visitantes")):
            with self.subTest(path=path):
                body = self.page(path)
                self.assertIn('aria-label="Secciones de paquetería y visitas"', body)
                self.assertRegex(body, rf'<a href="{path}" aria-current="page">{current}</a>')
                for other in ("/web/paqueteria", "/web/visitas", "/web/vehiculos"):
                    self.assertIn(f'href="{other}"', body)

    def test_the_panel_counter_leads_to_the_packages_waiting(self):
        self.assertIn('href="/web/paqueteria?estado=pendiente"', self.page("/web/"))


# ---------------------------------------------------------------------------
# Paquetes
# ---------------------------------------------------------------------------

class WebPackageListTests(RegistryWebCase):
    def test_it_opens_on_everything_with_the_numbers_of_every_tab(self):
        self.package(hours=80, description="Caja grande", created_minutes_ago=50)
        self.package(self.other, hours=2, description="Sobre", created_minutes_ago=40)
        self.package(status="por_llegar", description="Televisor", created_minutes_ago=30)
        self.package(status="entregado", description="Libros", delivered_at=utc_now() - timedelta(days=1),
                     delivered_to="Tercero Pérez", created_minutes_ago=20)
        self.trash(self.package(status="entregado", description="Perdido", delivered_at=utc_now() - timedelta(days=9),
                                created_minutes_ago=10))

        body = self.page("/web/paqueteria")

        self.assertIn("<h1>Paquetes</h1>", body)
        self.assertIn("5 paquetes", body)
        self.assertIn("Es solo de consulta", body)
        for label in ("Todos (5)", "En portería (2)", "Por llegar (1)", "Entregados (1)", "Papelera (1)"):
            self.assertIn(label, body)
        self.assertRegex(body, r'aria-current="page">Todos \(5\)')
        # Del más reciente al más antiguo, también la papelera.
        self.assertInOrder(body, "Perdido", "Libros", "Televisor", "Sobre", "Caja grande")
        self.assertIn("También los de la papelera".lower(), body.lower())

    def test_each_row_says_who_where_and_how_long_it_has_been_waiting(self):
        self.package(hours=80, description="Caja grande", carrier="Servientrega", tracking_number="SV-100")

        body = self.main_of(self.page("/web/paqueteria"))

        self.assertIn("Caja grande", body)
        self.assertIn(f"{self.resident.apartment} · Marta Ríos", body)
        self.assertIn("Servientrega · guía SV-100", body)
        self.assertIn("En portería", body)
        self.assertIn("Más de 72 h sin reclamar", body)
        self.assertIn("Lleva 3 días 8 h en portería", body)

    def test_the_orange_alert_says_it_in_words(self):
        self.package(hours=50, description="Naranja")
        self.package(hours=5, description="Reciente")

        body = self.main_of(self.page("/web/paqueteria?estado=pendiente"))

        self.assertEqual(body.count("Más de 48 h sin reclamar"), 1)
        self.assertNotIn("Más de 72 h sin reclamar", body)
        self.assertIn("Lleva 2 días 2 h en portería", body)
        self.assertIn("Lleva 5 h en portería", body)

    def test_a_package_that_just_arrived_says_so(self):
        self.package(hours=0, description="Nuevo")

        body = self.main_of(self.page("/web/paqueteria?estado=pendiente"))

        self.assertIn("Llegó hace menos de 1 hora", body)

    def test_those_waiting_come_first_the_longest_waiting_on_top(self):
        self.package(hours=3, description="Reciente")
        self.package(hours=60, description="Antiguo")
        self.package(hours=20, description="Medio")

        body = self.page("/web/paqueteria?estado=pendiente")

        self.assertInOrder(body, "Antiguo", "Medio", "Reciente")
        self.assertIn("Los que llevan más tiempo esperando van primero.", body)

    def test_the_tabs_show_only_their_own(self):
        self.package(hours=3, description="En la portería")
        self.package(status="por_llegar", description="Anunciado")
        self.package(status="entregado", description="Entregado ayer", delivered_at=utc_now() - timedelta(days=1),
                     delivered_to="Tercero Pérez")
        self.trash(self.package(status="entregado", description="De la papelera",
                                delivered_at=utc_now() - timedelta(days=9)))
        expected = {
            "pendiente": ("En la portería", ("Anunciado", "Entregado ayer", "De la papelera")),
            "por_llegar": ("Anunciado", ("En la portería", "Entregado ayer", "De la papelera")),
            "entregado": ("Entregado ayer", ("En la portería", "Anunciado", "De la papelera")),
            "papelera": ("De la papelera", ("En la portería", "Anunciado", "Entregado ayer")),
        }
        for tab, (present, absent) in expected.items():
            with self.subTest(tab=tab):
                body = self.main_of(self.page(f"/web/paqueteria?estado={tab}"))
                self.assertIn(present, body)
                for text in absent:
                    self.assertNotIn(text, body)

    def test_a_delivered_package_says_when_and_to_whom(self):
        self.package(status="entregado", description="Libros", delivered_at=utc_now() - timedelta(hours=5),
                     delivered_to="Tercero Pérez")

        body = self.main_of(self.page("/web/paqueteria?estado=entregado"))

        self.assertRegex(body, r"Entregado el \d{2}/\d{2}/\d{4} \d{2}:\d{2} a Tercero Pérez")
        self.assertIn("pasan a la papelera", body)

    def test_the_trash_explains_what_it_is_and_marks_each_package(self):
        self.trash(self.package(status="entregado", description="Vieja", delivered_at=utc_now() - timedelta(days=9)))

        body = self.main_of(self.page("/web/paqueteria?estado=papelera"))

        self.assertIn("la portería ya no ve en su lista", body)
        self.assertIn("En la papelera", body)

    def test_the_search_finds_in_the_whole_history_and_keeps_the_tab(self):
        self.package(hours=60, description="Caja grande", carrier="Servientrega", tracking_number="SV-100")
        self.package(self.other, hours=2, description="Sobre", carrier="Coordinadora")
        self.trash(self.package(self.other, status="entregado", description="Antigua", carrier="Coordinadora",
                                delivered_at=utc_now() - timedelta(days=9)))
        searches = {
            "Marta": ("Caja grande",), "Ríos": ("Caja grande",), "Torre 2": ("Sobre", "Antigua"),
            "Coordinadora": ("Sobre", "Antigua"), "SV-100": ("Caja grande",), "Sobre": ("Sobre",),
        }
        for text, found in searches.items():
            with self.subTest(text=text):
                body = self.main_of(self.page(f"/web/paqueteria?q={text}"))
                for description in ("Caja grande", "Sobre", "Antigua"):
                    self.assertEqual(description in body, description in found, description)
        # Dentro de una pestaña, la búsqueda se queda en ella, y los números de las pestañas cuentan la búsqueda.
        body = self.main_of(self.page("/web/paqueteria?estado=pendiente&q=Coordinadora"))
        self.assertIn("Sobre", body)
        self.assertNotIn("Antigua", body)
        self.assertIn("Todos (2)", body)
        self.assertIn("En portería (1)", body)
        self.assertIn("Papelera (1)", body)

    def test_a_search_without_results_says_so_and_can_be_cleared(self):
        self.package()

        body = self.page("/web/paqueteria?estado=entregado&q=Nadie")

        self.assertIn("No hay paquetes que coincidan con esa búsqueda.", body)
        self.assertIn("Quitar búsqueda", body)
        self.assertIn('href="/web/paqueteria?estado=entregado"', body)
        self.assertIn('<input type="hidden" name="estado" value="entregado">', body)
        self.assertIn('value="Nadie"', body)

    def test_each_empty_tab_says_what_it_would_have(self):
        expected = {
            "todos": "Todavía no hay paquetes registrados.",
            "pendiente": "No hay paquetes esperando en la portería.",
            "por_llegar": "No hay paquetes anunciados que estén por llegar.",
            "entregado": "No hay paquetes entregados en los últimos 7 días.",
            "papelera": "La papelera de paquetes está vacía.",
        }
        for tab, text in expected.items():
            with self.subTest(tab=tab):
                self.assertIn(text, self.page(f"/web/paqueteria?estado={tab}"))

    def test_an_unknown_tab_opens_everything(self):
        self.package(description="Caja única")

        body = self.page("/web/paqueteria?estado=inventado")

        self.assertRegex(body, r'aria-current="page">Todos \(1\)')
        self.assertIn("Caja única", body)

    def test_the_list_is_paginated_and_keeps_the_filters(self):
        for number in range(17):
            self.package(status="por_llegar", description=f"Paquete {number:02d}", created_minutes_ago=number)

        first = self.page("/web/paqueteria?estado=por_llegar")
        second = self.page("/web/paqueteria?estado=por_llegar&page=2")

        self.assertIn("Página 1 de 2", first)
        self.assertEqual(len(self.links(first, "/web/paqueteria/")), 15)
        self.assertInOrder(first, "Paquete 00", "Paquete 14")
        self.assertNotIn("Paquete 15", first)
        self.assertIn("Página 2 de 2", second)
        self.assertIn("Paquete 16", second)
        self.assertIn("‹ Anterior", second)
        self.assertIn("estado=por_llegar", html.unescape(re.search(r'href="([^"]*)"[^>]*>‹ Anterior', second).group(1)))

    def test_a_page_that_no_longer_exists_leads_to_the_last_one(self):
        for number in range(17):
            self.package(status="por_llegar", description=f"Paquete {number:02d}", created_minutes_ago=number)

        response = self.client.get("/web/paqueteria?estado=por_llegar&page=9")

        self.assertEqual(response.status_code, 302)
        path, params = urlsplit(response.headers["Location"]).path, parse_qs(urlsplit(response.headers["Location"]).query)
        self.assertEqual(path, "/web/paqueteria")
        self.assertEqual(params, {"estado": ["por_llegar"], "page": ["2"]})

    def test_a_failure_of_the_api_is_told_and_the_page_still_opens(self):
        with mock.patch("web.views_registry.Api.get", return_value=ApiResult(500, {"error": "No pudimos leer los paquetes."})):
            response = self.client.get("/web/paqueteria")

        self.assertEqual(response.status_code, 200)
        body = self.text(response)
        self.assertIn("No pudimos leer los paquetes.", body)
        self.assertIn("Todavía no hay paquetes registrados.", body)

    def test_texts_written_by_people_are_escaped(self):
        self.package(description="<script>alert(1)</script>", carrier='<b>"X"</b>', tracking_number="<i>1</i>")

        body = self.page("/web/paqueteria")

        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)
        self.assertNotIn("<b>", self.main_of(body))
        self.assertNotIn("<i>1</i>", body)


class WebPackageDetailTests(RegistryWebCase):
    def test_the_package_opens_next_to_the_list_with_its_data(self):
        item = self.package(
            hours=80, description="Caja grande", carrier="Servientrega", tracking_number="SV-100",
        )

        body = self.page(f"/web/paqueteria/{item.id}")

        self.assertIn('class="inbox-page has-detail"', body)
        self.assertRegex(body, rf'<a class="inbox-link" href="/web/paqueteria/{item.id}"[^>]*aria-current="true"')
        article = body.split('<article class="card" aria-labelledby="detail-title">', 1)[1]
        self.assertIn("‹ Volver a la lista", article)
        self.assertIn('id="detail-title" tabindex="-1" data-focus-on-load>Caja grande</h2>', article)
        for text in ("Marta Ríos", str(self.resident.apartment), "Servientrega", "SV-100", "Más de 72 h sin reclamar",
                     "3 días 8 h", "Registrado", "por Guardia", "Llegó a la portería"):
            self.assertIn(text, article)

    def test_without_choosing_one_the_page_invites_to_choose(self):
        self.package()

        body = self.page("/web/paqueteria")

        self.assertIn("Elige un paquete de la lista", body)
        self.assertNotIn("has-detail", body)

    def test_the_links_of_the_list_keep_the_filters_and_the_page(self):
        for number in range(17):
            self.package(status="por_llegar", description=f"Paquete {number:02d}", created_minutes_ago=number)

        body = self.page("/web/paqueteria?estado=por_llegar&q=Paquete&page=2")

        for path, params in self.links(body, "/web/paqueteria/"):
            self.assertEqual(params, {"estado": "por_llegar", "q": "Paquete", "page": "2"}, path)
        back = self.page("/web/paqueteria/1?estado=por_llegar&q=Paquete&page=1")
        self.assertIn(
            ("/web/paqueteria", {"estado": "por_llegar", "q": "Paquete"}),
            self.links(back, "/web/paqueteria?"),
        )

    def test_a_delivered_package_says_who_delivered_it_and_who_received_it(self):
        item = self.package(
            status="entregado", description="Libros", delivered_at=utc_now() - timedelta(hours=3),
            delivered_to="Tercero Pérez", delivered_by_id=self.admin.id,
        )

        article = self.page(f"/web/paqueteria/{item.id}").split('<article class="card"', 1)[1]

        self.assertIn("Entregado", article)
        self.assertIn("lo entregó Lucía Vargas", article)
        self.assertIn("Lo recibió", article)
        self.assertIn("Tercero Pérez", article)
        self.assertNotIn("Tiempo en portería", article)

    def test_a_package_in_the_trash_says_who_sent_it_there(self):
        item = self.trash(self.package(status="entregado", description="Vieja"), by=self.guard)

        article = self.page(f"/web/paqueteria/{item.id}").split('<article class="card"', 1)[1]

        self.assertIn("Este paquete está en la papelera", article)
        self.assertIn("lo quitó Guardia", article)
        self.assertNotIn("pasó solo", article)

    def test_a_package_that_went_to_the_trash_by_itself_says_so(self):
        item = self.trash(self.package(status="entregado", description="Vieja"))

        article = self.page(f"/web/paqueteria/{item.id}").split('<article class="card"', 1)[1]

        self.assertIn("pasó solo, por llevar más de 7 días entregado", article)

    def test_it_says_when_the_resident_made_a_pickup_code_but_never_shows_it(self):
        item = self.package(hours=3)
        db.session.add(PackagePickupCode(
            package_id=item.id, token="TOKEN-SECRETO-DE-PRUEBA", pin_hash="HASH-SECRETO-DE-PRUEBA",
            created_by_id=self.resident.id,
        ))
        db.session.commit()

        body = self.page(f"/web/paqueteria/{item.id}")

        self.assertIn("El residente generó un código para que otra persona recoja este paquete.", body)
        self.assertNotIn("TOKEN-SECRETO-DE-PRUEBA", body)
        self.assertNotIn("HASH-SECRETO-DE-PRUEBA", body)

    def test_a_package_that_does_not_exist_is_a_404(self):
        response = self.client.get("/web/paqueteria/9999")

        self.assertEqual(response.status_code, 404)
        self.assertIn("No encontramos esa página", self.text(response))


class WebPackagePhotoTests(RegistryWebCase):
    def test_the_photo_is_asked_for_apart_and_never_travels_inside_the_page(self):
        item = self.package(media_url=PHOTO, media_type="image", description="Con foto")

        body = self.page(f"/web/paqueteria/{item.id}")

        self.assertIn(f'<img src="/web/paqueteria/{item.id}/foto" alt="Foto del paquete"', body)
        self.assertNotIn("base64", body)
        self.assertNotIn(PHOTO[40:120], body)

    def test_the_photo_is_delivered_as_an_image_that_cannot_run_anything(self):
        item = self.package(media_url=PHOTO, media_type="image")

        response = self.client.get(f"/web/paqueteria/{item.id}/foto")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/jpeg")
        self.assertEqual(response.data, JPEG)
        self.assertEqual(response.headers["Content-Security-Policy"], "default-src 'none'; style-src 'unsafe-inline'; sandbox")
        self.assertEqual(response.headers["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        again = self.client.get(f"/web/paqueteria/{item.id}/foto", headers={"If-None-Match": response.headers["ETag"]})
        self.assertEqual(again.status_code, 304)

    def test_a_package_without_photo_has_no_picture_and_no_photo_page(self):
        item = self.package()

        body = self.page(f"/web/paqueteria/{item.id}")

        self.assertNotIn("Foto del paquete", body)
        self.assertEqual(self.client.get(f"/web/paqueteria/{item.id}/foto").status_code, 404)
        self.assertEqual(self.client.get("/web/paqueteria/9999/foto").status_code, 404)

    def test_something_that_is_not_an_image_is_never_delivered(self):
        item = self.package(media_url=SVG, media_type="image")

        self.assertEqual(self.client.get(f"/web/paqueteria/{item.id}/foto").status_code, 404)

    def test_a_package_in_the_trash_keeps_its_photo(self):
        item = self.trash(self.package(status="entregado", media_url=PHOTO, media_type="image"))

        self.assertEqual(self.client.get(f"/web/paqueteria/{item.id}/foto").status_code, 200)


# ---------------------------------------------------------------------------
# Visitas
# ---------------------------------------------------------------------------

class WebVisitListTests(RegistryWebCase):
    def test_it_opens_on_everything_with_the_numbers_of_every_tab(self):
        self.visit(name="Ana Dentro", entered_minutes_ago=180, created_minutes_ago=180)
        self.visit(name="Beto Salió", entered_minutes_ago=600, exited_minutes_ago=500, created_minutes_ago=600)
        self.visit(self.other, name="Carla Pendiente", status="pendiente", created_minutes_ago=30)
        self.visit(name="Dani Rechazado", status="rechazada", created_minutes_ago=20)

        body = self.page("/web/visitas")

        self.assertIn("<h1>Visitas</h1>", body)
        self.assertIn("4 visitas", body)
        self.assertIn("Es solo de consulta", body)
        for label in ("Todas (4)", "Dentro ahora (1)", "Esperando autorización (1)", "Aprobadas (2)", "Rechazadas (1)"):
            self.assertIn(label, body)
        self.assertRegex(body, r'aria-current="page">Todas \(4\)')
        self.assertInOrder(body, "Dani Rechazado", "Carla Pendiente", "Ana Dentro", "Beto Salió")

    def test_each_row_says_who_comes_for_whom_and_how_it_stands(self):
        self.visit(
            name="Carlos Ruiz", type="domiciliario", entered_minutes_ago=180, stay=60, created_minutes_ago=181,
        )

        body = self.main_of(self.page("/web/visitas"))

        self.assertIn("Carlos Ruiz", body)
        self.assertIn(f"Domiciliario · {self.resident.apartment} · Marta Ríos", body)
        self.assertIn("Aprobada", body)
        self.assertRegex(body, r"Llegó a la portería el \d{2}/\d{2}/\d{4} \d{2}:\d{2}")
        self.assertRegex(body, r"Dentro · 3 h( 1 min)?")
        self.assertIn("Pasó el tiempo previsto", body)

    def test_a_visit_that_left_shows_when_it_came_in_and_out(self):
        self.visit(name="Beto Salió", entered_minutes_ago=600, exited_minutes_ago=500)

        body = self.main_of(self.page("/web/visitas"))

        self.assertRegex(body, r"Entró el \d{2}/\d{2}/\d{4} \d{2}:\d{2} · salió el \d{2}/\d{2}/\d{4} \d{2}:\d{2}")
        self.assertNotIn("Dentro ·", body)
        self.assertNotIn("Pasó el tiempo previsto", body)

    def test_a_visit_waiting_for_authorization_says_so(self):
        self.visit(name="Carla Pendiente", status="pendiente")

        body = self.main_of(self.page("/web/visitas?estado=pendiente"))

        self.assertIn("Esperando autorización", body)
        self.assertNotIn("Dentro ·", body)

    def test_the_tabs_show_only_their_own(self):
        self.visit(name="Ana Dentro", entered_minutes_ago=60)
        self.visit(name="Beto Salió", entered_minutes_ago=600, exited_minutes_ago=500)
        self.visit(name="Carla Pendiente", status="pendiente")
        self.visit(name="Dani Rechazado", status="rechazada")
        expected = {
            "dentro": ("Ana Dentro", ("Beto Salió", "Carla Pendiente", "Dani Rechazado")),
            "pendiente": ("Carla Pendiente", ("Ana Dentro", "Beto Salió", "Dani Rechazado")),
            "aprobada": ("Ana Dentro", ("Carla Pendiente", "Dani Rechazado")),
            "rechazada": ("Dani Rechazado", ("Ana Dentro", "Beto Salió", "Carla Pendiente")),
        }
        for tab, (present, absent) in expected.items():
            with self.subTest(tab=tab):
                body = self.main_of(self.page(f"/web/visitas?estado={tab}"))
                self.assertIn(present, body)
                for text in absent:
                    self.assertNotIn(text, body)

    def test_those_inside_come_with_the_longest_inside_first(self):
        self.visit(name="Reciente", entered_minutes_ago=10)
        self.visit(name="Antigua", entered_minutes_ago=300)
        self.visit(name="Media", entered_minutes_ago=100)

        body = self.page("/web/visitas?estado=dentro")

        self.assertInOrder(body, "Antigua", "Media", "Reciente")
        self.assertIn("Los que llevan más tiempo dentro van primero.", body)

    def test_the_search_finds_by_visitor_resident_and_apartment(self):
        self.visit(name="Ana Dentro")
        self.visit(self.other, name="Carla Pendiente", status="pendiente")
        searches = {"ana": "Ana Dentro", "Carla": "Carla Pendiente", "Pérez": "Carla Pendiente", "Torre 2": "Carla Pendiente",
                    "Marta": "Ana Dentro"}
        for text, found in searches.items():
            with self.subTest(text=text):
                body = self.main_of(self.page(f"/web/visitas?q={text}"))
                for name in ("Ana Dentro", "Carla Pendiente"):
                    self.assertEqual(name in body, name == found, name)

    def test_the_dates_narrow_the_list_and_the_numbers(self):
        self.visit(name="De hoy", created_minutes_ago=0)
        self.visit(name="De hace dos días", created_minutes_ago=2 * 24 * 60)
        self.visit(name="De hace diez días", created_minutes_ago=10 * 24 * 60)
        day = lambda offset: (colombia_today() + timedelta(days=offset)).isoformat()  # noqa: E731

        old = self.main_of(self.page(f"/web/visitas?hasta={day(-5)}"))
        recent = self.main_of(self.page(f"/web/visitas?desde={day(-3)}"))

        self.assertIn("De hace diez días", old)
        self.assertNotIn("De hoy", old)
        self.assertIn("Todas (1)", old)
        self.assertIn("1 visita con esos filtros", old)
        self.assertIn("De hoy", recent)
        self.assertIn("De hace dos días", recent)
        self.assertNotIn("De hace diez días", recent)
        self.assertIn("Todas (2)", recent)
        self.assertIn(f'value="{day(-3)}"', recent)

    def test_a_date_that_is_not_a_date_is_ignored(self):
        self.visit(name="Ana Dentro")

        body = self.main_of(self.page("/web/visitas?desde=ayer&hasta=99-99-99"))

        self.assertIn("Ana Dentro", body)
        self.assertNotIn("Quitar filtros", body)

    def test_the_filters_can_be_cleared_and_keep_the_tab(self):
        self.visit(name="Ana Dentro", entered_minutes_ago=60)

        body = self.page("/web/visitas?estado=dentro&q=Nadie")

        self.assertIn("No hay visitas que coincidan con esos filtros.", body)
        self.assertIn('href="/web/visitas?estado=dentro"', body)
        self.assertIn('<input type="hidden" name="estado" value="dentro">', body)

    def test_each_empty_tab_says_what_it_would_have(self):
        expected = {
            "todas": "Todavía no hay visitas registradas.",
            "dentro": "No hay visitantes dentro de la unidad en este momento.",
            "pendiente": "No hay visitas esperando autorización.",
            "aprobada": "No hay visitas aprobadas.",
            "rechazada": "No hay visitas rechazadas.",
        }
        for tab, text in expected.items():
            with self.subTest(tab=tab):
                self.assertIn(text, self.page(f"/web/visitas?estado={tab}"))

    def test_the_list_is_paginated(self):
        for number in range(17):
            self.visit(name=f"Visitante {number:02d}", created_minutes_ago=number)

        first = self.page("/web/visitas")
        second = self.page("/web/visitas?page=2")
        moved = self.client.get("/web/visitas?page=9")

        self.assertIn("Página 1 de 2", first)
        self.assertEqual(len(self.links(first, "/web/visitas/")), 15)
        self.assertIn("Visitante 16", second)
        self.assertEqual(moved.status_code, 302)
        self.assertEqual(urlsplit(moved.headers["Location"]).query, "page=2")

    def test_a_photo_is_never_inside_the_list(self):
        self.visit(name="Con foto", visitor_photo_url=PHOTO, visitor_photo_type="image", media_consent=True)

        body = self.page("/web/visitas")

        self.assertIn("Con foto", body)
        self.assertNotIn("base64", body)
        self.assertNotIn("<img", self.main_of(body))

    def test_texts_written_by_people_are_escaped(self):
        self.visit(name="<script>alert(1)</script>", description="<b>pedido</b>")

        body = self.page("/web/visitas")

        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)

    def test_a_failure_of_the_api_is_told_and_the_page_still_opens(self):
        with mock.patch("web.views_registry.Api.get", return_value=ApiResult(500, {"error": "No pudimos leer las visitas."})):
            response = self.client.get("/web/visitas")

        self.assertEqual(response.status_code, 200)
        self.assertIn("No pudimos leer las visitas.", self.text(response))


class WebVisitDetailTests(RegistryWebCase):
    def make_complete_visit(self):
        visit = self.visit(
            name="Carlos Ruiz", type="domiciliario", entered_minutes_ago=135, stay=240, created_minutes_ago=140,
            visitor_document="1234567", description="Pedido de pizza", visitor_photo_url=PHOTO,
            visitor_photo_type="image", media_consent=True,
        )
        self.step(visit, "solicitud")
        self.step(visit, "aprobada", actor=self.resident)
        self.step(visit, "entrada")
        return visit

    def article(self, visit):
        return self.page(f"/web/visitas/{visit.id}").split('<article class="card" aria-labelledby="detail-title">', 1)[1]

    def test_the_visit_opens_next_to_the_list_with_its_data(self):
        visit = self.make_complete_visit()

        body = self.page(f"/web/visitas/{visit.id}")
        article = body.split('<article class="card" aria-labelledby="detail-title">', 1)[1]

        self.assertIn('class="inbox-page has-detail"', body)
        self.assertRegex(body, rf'<a class="inbox-link" href="/web/visitas/{visit.id}"[^>]*aria-current="true"')
        self.assertIn("‹ Volver a la lista", article)
        self.assertIn('data-focus-on-load>Carlos Ruiz</h2>', article)
        for text in ("Domiciliario", "Marta Ríos", str(self.resident.apartment), "Pedido de pizza", "1234567",
                     "Desde la app", "lo registró Guardia", "Dentro de la unidad", "Aprobada", "2 h 15 min",
                     "4 h"):
            self.assertIn(text, article)
        self.assertIn("Lleva dentro", article)
        self.assertIn("Estadía prevista", article)

    def test_without_choosing_one_the_page_invites_to_choose(self):
        self.visit()

        body = self.page("/web/visitas")

        self.assertIn("Elige una visita de la lista", body)
        self.assertNotIn("has-detail", body)

    def test_the_history_tells_each_step_with_who_did_it(self):
        visit = self.make_complete_visit()

        article = self.article(visit)

        self.assertInOrder(
            article, "Llegó a la portería y se pidió la autorización", "Se aprobó el ingreso", "Entró a la unidad",
        )
        history = article.split("Historial de la visita", 1)[1]
        self.assertIn("Marta Ríos · desde la app", history)
        self.assertEqual(history.count("Guardia"), 2)
        self.assertNotIn("visita autorizada", history)

    def test_a_visit_authorized_by_phone_says_so(self):
        visit = self.visit(name="Por teléfono", method="llamada", entered_minutes_ago=30)
        self.step(visit, "solicitud")
        self.step(visit, "aprobada", method="llamada")
        self.step(visit, "entrada", method="llamada")

        article = self.article(visit)

        self.assertIn("Por llamada a la portería", article)
        self.assertIn("Guardia · por llamada a la portería", article)
        self.assertIn("Guardia · visita autorizada por llamada a la portería", article)

    def test_a_visit_that_came_in_with_a_qr_says_so(self):
        visit = self.visit(name="Con QR", method="qr", entered_minutes_ago=600, exited_minutes_ago=500)
        self.step(visit, "entrada", method="qr")
        self.step(visit, "salida", method="qr", returning=True)
        visit.exit_returning = True
        db.session.commit()

        article = self.article(visit)

        self.assertIn("Con el código QR del residente", article)
        self.assertIn("visita autorizada con el código QR del residente", article)
        self.assertEqual(article.count("dijo que vuelve hoy"), 2)
        self.assertIn("Ya salió", article)
        self.assertNotIn("Lleva dentro", article)

    def test_a_rejected_visit_has_no_entry(self):
        visit = self.visit(name="Dani Rechazado", status="rechazada")
        self.step(visit, "solicitud")
        self.step(visit, "rechazada", actor=self.resident)

        article = self.article(visit)

        self.assertIn("Se rechazó el ingreso", article)
        self.assertNotIn("<dt>Entró</dt>", article)
        self.assertNotIn("Dentro de la unidad", article)

    def test_a_visit_without_steps_says_so(self):
        visit = self.visit()

        self.assertIn("Esta visita no tiene pasos registrados.", self.article(visit))

    def test_a_visit_that_does_not_exist_is_a_404(self):
        response = self.client.get("/web/visitas/9999")

        self.assertEqual(response.status_code, 404)
        self.assertIn("No encontramos esa página", self.text(response))

    def test_the_links_of_the_list_keep_the_filters(self):
        self.visit(name="Ana Dentro", entered_minutes_ago=60)

        body = self.page("/web/visitas?estado=dentro&q=Ana")

        self.assertEqual(
            [params for _path, params in self.links(body, "/web/visitas/")], [{"estado": "dentro", "q": "Ana"}],
        )


class WebVisitPhotoTests(RegistryWebCase):
    def test_the_photo_is_asked_for_apart_and_never_travels_inside_the_page(self):
        visit = self.visit(visitor_photo_url=PHOTO, visitor_photo_type="image", media_consent=True)

        body = self.page(f"/web/visitas/{visit.id}")

        self.assertIn(f'<img src="/web/visitas/{visit.id}/foto" alt="Foto del visitante"', body)
        self.assertIn("Se guardó con el consentimiento del visitante.", body)
        self.assertNotIn("base64", body)
        self.assertNotIn(PHOTO[40:120], body)

    def test_the_photo_is_delivered_as_an_image_that_cannot_run_anything(self):
        visit = self.visit(visitor_photo_url=PHOTO, visitor_photo_type="image", media_consent=True)

        response = self.client.get(f"/web/visitas/{visit.id}/foto")

        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.mimetype, response.data), ("image/jpeg", JPEG))
        self.assertEqual(response.headers["Content-Security-Policy"], "default-src 'none'; style-src 'unsafe-inline'; sandbox")
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_without_the_consent_of_the_visitor_the_photo_is_neither_shown_nor_delivered(self):
        visit = self.visit(visitor_photo_url=PHOTO, visitor_photo_type="image", media_consent=False)

        body = self.page(f"/web/visitas/{visit.id}")

        self.assertNotIn("Foto del visitante", body)
        self.assertEqual(self.client.get(f"/web/visitas/{visit.id}/foto").status_code, 404)

    def test_a_visit_without_photo_has_no_picture_and_no_photo_page(self):
        visit = self.visit()

        self.assertNotIn("Foto del visitante", self.page(f"/web/visitas/{visit.id}"))
        self.assertEqual(self.client.get(f"/web/visitas/{visit.id}/foto").status_code, 404)
        self.assertEqual(self.client.get("/web/visitas/9999/foto").status_code, 404)

    def test_something_that_is_not_an_image_is_never_delivered(self):
        visit = self.visit(visitor_photo_url=SVG, visitor_photo_type="image", media_consent=True)

        self.assertEqual(self.client.get(f"/web/visitas/{visit.id}/foto").status_code, 404)


# ---------------------------------------------------------------------------
# Vehículos de visitantes
# ---------------------------------------------------------------------------

class WebVehicleTests(RegistryWebCase):
    def setUp(self):
        super().setUp()
        self.spot = ParkingSpot(code="V-01", kind="visitante", location="Sótano 1")
        db.session.add(self.spot)
        db.session.commit()

    def test_it_opens_on_everything_with_the_numbers_of_every_tab(self):
        self.entry("ABC123", days_ago=1)
        self.entry("XYZ789", days_ago=5)
        self.entry("DEF456", days_ago=8, exited=True)
        self.entry("GHI111", days_ago=2, exited=True, resident=self.other)

        body = self.page("/web/vehiculos")

        self.assertIn("<h1>Vehículos de visitantes</h1>", body)
        self.assertIn("4 entradas", body)
        self.assertIn("Es solo de consulta", body)
        for label in ("Todos (4)", "Adentro (2)", "Vencidos (1)", "Ya salieron (2)"):
            self.assertIn(label, body)
        self.assertRegex(body, r'aria-current="page">Todos \(4\)')
        self.assertInOrder(body, "ABC123", "GHI111", "XYZ789", "DEF456")

    def test_each_row_says_who_where_and_for_how_long(self):
        record = self.entry("XYZ789", days_ago=4, name="Carlos Ruiz", spot=self.spot)

        body = self.main_of(self.page("/web/vehiculos"))

        self.assertIn("XYZ789", body)
        self.assertIn("Carlos Ruiz", body)
        self.assertIn(f"{self.resident.apartment}", body)
        self.assertIn("Marta Ríos", body)
        self.assertIn("V-01", body)
        self.assertIn("Sótano 1", body)
        self.assertIn("Sigue adentro", body)
        self.assertIn("Pasó el máximo de 3 días", body)
        self.assertIn("4 días", body)
        self.assertIn("Guardia", body)
        self.assertIn(f'<a href="/web/visitas/{record.visit_id}">Ver la visita</a>', body)

    def test_a_vehicle_that_left_says_when_and_who_let_it_out(self):
        self.entry("DEF456", days_ago=8, exited=True)

        body = self.main_of(self.page("/web/vehiculos"))

        self.assertRegex(body, r"<td data-label=\"Salió\">\s*\d{2}/\d{2}/\d{4} \d{2}:\d{2}<br><small class=\"muted\">Guardia</small>")
        self.assertNotIn("Sigue adentro", body)
        self.assertIn("Sin parqueadero", body)

    def test_the_tabs_show_only_their_own(self):
        self.entry("KLM123", days_ago=1)
        self.entry("XYZ789", days_ago=5)
        self.entry("DEF456", days_ago=8, exited=True)
        expected = {
            "adentro": (("KLM123", "XYZ789"), ("DEF456",)),
            "vencidos": (("XYZ789",), ("KLM123", "DEF456")),
            "salieron": (("DEF456",), ("KLM123", "XYZ789")),
        }
        for tab, (present, absent) in expected.items():
            with self.subTest(tab=tab):
                body = self.main_of(self.page(f"/web/vehiculos?estado={tab}"))
                for plate in present:
                    self.assertIn(plate, body)
                for plate in absent:
                    self.assertNotIn(plate, body)
        self.assertIn("pasaron el tiempo máximo", self.page("/web/vehiculos?estado=vencidos"))

    def test_the_search_by_plate_ignores_case_and_keeps_the_tab(self):
        self.entry("ABC123", days_ago=1)
        self.entry("ABC123", days_ago=9, exited=True)
        self.entry("XYZ789", days_ago=5)

        body = self.main_of(self.page("/web/vehiculos?placa=abc"))
        inside = self.main_of(self.page("/web/vehiculos?estado=adentro&placa=abc"))

        self.assertEqual(body.count("ABC123</strong>"), 2)
        self.assertNotIn("XYZ789", body)
        self.assertIn("Todos (2)", body)
        self.assertIn("2 entradas con esa placa", body)
        self.assertEqual(inside.count("ABC123</strong>"), 1)
        self.assertIn("Ya salieron (1)", inside)
        self.assertIn('<input type="hidden" name="estado" value="adentro">', inside)
        self.assertIn('href="/web/vehiculos?estado=adentro"', inside)

    def test_each_empty_tab_says_what_it_would_have(self):
        expected = {
            "todos": "Todavía no hay entradas de vehículos de visitantes.",
            "adentro": "No hay vehículos de visitantes adentro en este momento.",
            "vencidos": "Ningún vehículo de visitante ha pasado el tiempo máximo.",
            "salieron": "Todavía no hay vehículos de visitantes que hayan salido.",
        }
        for tab, text in expected.items():
            with self.subTest(tab=tab):
                self.assertIn(text, self.page(f"/web/vehiculos?estado={tab}"))

    def test_a_search_without_results_says_so(self):
        self.entry("ABC123")

        body = self.page("/web/vehiculos?placa=ZZZ")

        self.assertIn("No hay entradas con esa placa en esta lista.", body)

    def test_the_list_is_paginated(self):
        for number in range(17):
            self.entry(f"AAA{number:03d}", days_ago=1)

        first = self.page("/web/vehiculos")
        moved = self.client.get("/web/vehiculos?page=9")

        self.assertIn("Página 1 de 2", first)
        self.assertEqual(first.count("<tr>"), 16)  # el encabezado y 15 filas
        self.assertEqual(moved.status_code, 302)
        self.assertEqual(urlsplit(moved.headers["Location"]).query, "page=2")

    def test_the_link_to_the_visit_opens_it(self):
        record = self.entry("ABC123", name="Carlos Ruiz")

        self.assertIn("Carlos Ruiz", self.page(f"/web/visitas/{record.visit_id}"))

    def test_a_failure_of_the_api_is_told_and_the_page_still_opens(self):
        with mock.patch("web.views_registry.Api.get", return_value=ApiResult(500, {"error": "No pudimos leer los vehículos."})):
            response = self.client.get("/web/vehiculos")

        self.assertEqual(response.status_code, 200)
        self.assertIn("No pudimos leer los vehículos.", self.text(response))


# ---------------------------------------------------------------------------
# Textos
# ---------------------------------------------------------------------------

class RegistryTextsTests(unittest.TestCase):
    def test_durations_are_written_with_words(self):
        cases = {
            None: "", 0: "0 min", 45: "45 min", 60: "1 h", 135: "2 h 15 min", 180: "3 h", 1440: "1 día",
            1500: "1 día 1 h", 2 * 1440 + 3 * 60: "2 días 3 h", 5 * 1440: "5 días", -5: "0 min",
        }
        for minutes, expected in cases.items():
            with self.subTest(minutes=minutes):
                self.assertEqual(texts.duration_text(minutes), expected)

    def test_package_and_visit_badges_have_words_and_tones(self):
        self.assertEqual(texts.badge_info("package", "pendiente"), {"label": "En portería", "tone": "progress"})
        self.assertEqual(texts.badge_info("package", "entregado"), {"label": "Entregado", "tone": "success"})
        self.assertEqual(texts.badge_info("package", "por_llegar"), {"label": "Por llegar", "tone": "neutral"})
        self.assertEqual(texts.badge_info("package_alert", "naranja"), {"label": "Más de 48 h sin reclamar", "tone": "progress"})
        self.assertEqual(texts.badge_info("package_alert", "rojo"), {"label": "Más de 72 h sin reclamar", "tone": "alert"})
        self.assertEqual(texts.badge_info("visit", "pendiente"), {"label": "Esperando autorización", "tone": "progress"})
        self.assertEqual(texts.badge_info("visit", "aprobada"), {"label": "Aprobada", "tone": "success"})
        self.assertEqual(texts.badge_info("visit", "rechazada"), {"label": "Rechazada", "tone": "alert"})

    def test_visit_texts(self):
        self.assertEqual(texts.visit_type_text("domiciliario"), "Domiciliario")
        self.assertEqual(texts.visit_type_text("otro_tipo"), "Otro tipo")
        self.assertEqual(texts.visit_event_text("entrada"), "Entró a la unidad")
        self.assertEqual(texts.visit_event_text("desconocido"), "Desconocido")
        self.assertEqual(texts.authorization_method_text("qr"), "con el código QR del residente")
        self.assertEqual(texts.authorization_method_text("qr", True), "Con el código QR del residente")
        self.assertEqual(texts.authorization_method_text(None), "")


if __name__ == "__main__":
    unittest.main()
