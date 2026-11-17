"""Pruebas del buscador general de la web (HU-089): la caja de arriba con «Buscar en» y la página de
resultados. La búsqueda en sí la hace ``GET /api/search`` (ver test_global_search.py); aquí se revisa
lo que ve la administración: la caja en cada página, los grupos, los enlaces y los permisos."""

import html
import re
import unittest
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from extensions import db
from models import PackageItem, Pqrs, Vehicle, Visit, VisitorVehicleEntry
from structure_fixtures import apartment_for
from time_utils import utc_now
from web_testing import WebTestCase


class WebSearchTests(WebTestCase):
    def setUp(self):
        super().setUp()
        apartment = apartment_for("Torre 1 · Apto 101")
        db.session.add(Vehicle(
            unit_id=apartment.unit.id, plate="QWE123", vehicle_type="carro", make_model="Mazda 3", year=2020,
            registered_owner="Marta Ríos", color="Rojo",
        ))
        self.pqrs = Pqrs(
            resident_id=self.resident.id, category="Daño", subject="Ascensor dañado", message="Detalle",
            status="abierta",
        )
        self.package = PackageItem(
            resident_id=self.resident.id, registered_by=self.guard.id, description="Caja de libros",
            status="pendiente", arrived_at=utc_now() - timedelta(hours=2),
        )
        self.visit = Visit(
            resident_id=self.resident.id, registered_by=self.guard.id, visitor_name="Jorge Visitante",
            type="visitante", approval_status="aprobada", authorization_method="app",
            entered_at=utc_now() - timedelta(minutes=30),
        )
        db.session.add_all([self.pqrs, self.package, self.visit])
        db.session.flush()
        db.session.add(VisitorVehicleEntry(
            plate="ZZZ999", visit_id=self.visit.id, apartment_id=self.resident.apartment_id,
            entered_at=utc_now() - timedelta(minutes=30), registered_by=self.guard.id,
        ))
        db.session.commit()
        self.log_in()

    def links(self, body):
        """Las direcciones de los resultados (se ignoran las del menú y las de las pestañas)."""
        main = body.split('<main id="contenido"', 1)[1]
        return [html.unescape(link) for link in re.findall(r'<a href="([^"]+)"><strong>', main)]

    # --- La caja de la barra de arriba -----------------------------------------------------------

    def test_every_page_has_the_search_box_with_the_place_filter(self):
        for path in ("/web/", "/web/pqrs", "/web/notificaciones"):
            body = self.page(path)
            self.assertIn('role="search"', body, path)
            self.assertIn('action="/web/buscar"', body, path)
            self.assertIn('for="buscar-en"', body, path)
            for place in ("Todo", "Personas", "Apartamentos", "Vehículos", "PQRS", "Paquetes", "Visitas"):
                self.assertIn(f">{place}</option>", body, f"{path} no ofrece «{place}»")

    def test_login_page_has_no_search_box(self):
        self.client.post("/web/logout", data={"csrf_token": self.token_of("/web/")})
        self.assertNotIn('role="search"', self.page("/web/login"))

    def test_search_page_keeps_what_was_searched(self):
        body = self.page("/web/buscar?q=Marta&en=personas")
        self.assertIn('value="Marta"', body)
        self.assertRegex(body, r'<option value="personas" selected>')

    def test_other_pages_start_with_an_empty_box(self):
        body = self.page("/web/pqrs?q=ascensor")
        self.assertIn('id="buscar-texto" name="q" value=""', body)

    # --- Los resultados ---------------------------------------------------------------------------

    def test_without_text_it_explains_how_to_search(self):
        body = self.page("/web/buscar")
        self.assertIn("Escribe al menos 2 letras o números para buscar", body)

    def test_one_letter_is_too_short(self):
        self.assertIn("Escribe al menos 2 letras", self.page("/web/buscar?q=M"))

    def test_everywhere_groups_results_by_type(self):
        body = self.page("/web/buscar?q=Marta")
        self.assertIn("Resultados para «Marta»", body)
        self.assertIn(">Personas <", body)
        self.assertIn("Marta Ríos", body)
        # Sus paquetes, visitas y PQRS aparecen porque llevan su nombre en el apartamento o el residente.
        self.assertIn(">Paquetes <", body)
        self.assertIn("Caja de libros", body)

    def test_each_result_links_to_its_page(self):
        pqrs = self.page("/web/buscar?q=Ascensor&en=pqrs")
        self.assertIn(f'href="/web/pqrs/{self.pqrs.id}"', pqrs)
        packages = self.page("/web/buscar?q=Caja&en=paquetes")
        self.assertIn(f'href="/web/paqueteria/{self.package.id}"', packages)
        visits = self.page("/web/buscar?q=Jorge&en=visitas")
        self.assertIn(f'href="/web/visitas/{self.visit.id}"', visits)

    def test_a_person_opens_the_users_list_filtered_by_name(self):
        links = self.links(self.page("/web/buscar?q=Marta&en=personas"))
        self.assertEqual(len(links), 1)
        parts = urlsplit(links[0])
        self.assertEqual(parts.path, "/web/usuarios")
        self.assertEqual(parse_qs(parts.query)["q"], ["Marta Ríos"])
        # Y esa lista sí la encuentra.
        self.assertIn("Marta Ríos", self.page(links[0]))

    def test_an_apartment_opens_the_apartments_list_filtered_by_its_label(self):
        links = self.links(self.page("/web/buscar?q=101&en=apartamentos"))
        self.assertEqual(len(links), 1)
        parts = urlsplit(links[0])
        self.assertEqual(parts.path, "/web/estructura/apartamentos")
        self.assertEqual(parse_qs(parts.query)["q"], ["Torre 1 · Apto 101"])
        self.assertIn("101", self.page(links[0]))

    def test_vehicles_find_residents_and_visitors_by_plate(self):
        resident = self.page("/web/buscar?q=QWE&en=vehiculos")
        self.assertIn("QWE123", resident)
        # El vehículo de un residente se ve en su apartamento.
        self.assertEqual(urlsplit(self.links(resident)[0]).path, "/web/estructura/apartamentos")
        visitor = self.page("/web/buscar?q=ZZZ&en=vehiculos")
        self.assertIn("ZZZ999", visitor)
        self.assertIn("De visitante", visitor)
        link = urlsplit(self.links(visitor)[0])
        self.assertEqual(link.path, "/web/vehiculos")
        self.assertEqual(parse_qs(link.query)["placa"], ["ZZZ999"])

    def test_a_plate_needs_three_characters(self):
        body = self.page("/web/buscar?q=QW&en=vehiculos")
        self.assertIn("No encontramos nada con «QW» en Vehículos", body)

    def test_no_results_says_so_and_suggests_everything(self):
        body = self.page("/web/buscar?q=zzzxxyy&en=personas")
        self.assertIn("No encontramos nada con «zzzxxyy» en Personas", body)
        self.assertIn("prueba con «Todo»", body)

    def test_search_text_is_escaped_in_the_page(self):
        body = self.page("/web/buscar?q=%3Cscript%3Ealert(1)%3C/script%3E")
        self.assertNotIn("<script>alert(1)", body)
        self.assertIn("&lt;script&gt;", body)

    def test_percent_and_underscore_are_searched_as_text(self):
        body = self.page("/web/buscar?q=%25%25")
        self.assertIn("No encontramos nada", body)

    def test_unknown_place_shows_a_notice_instead_of_breaking(self):
        response = self.client.get("/web/buscar?q=Marta&en=cualquiera")
        self.assertEqual(response.status_code, 200)
        self.assertIn("No se puede buscar ahí", self.text(response))

    def test_more_results_offers_to_see_them_all_in_one_place(self):
        for number in range(7):
            self.make_user("RESIDENT", f"extra{number}@test.local", f"Extra{number}", last_name="Prueba")
        db.session.commit()
        everywhere = self.page("/web/buscar?q=Extra")
        self.assertIn("Hay más resultados de los que se muestran", everywhere)
        self.assertIn("Ver todos en Personas", everywhere)
        one_place = self.page("/web/buscar?q=Extra&en=personas")
        self.assertNotIn("Hay más resultados", one_place)
        self.assertEqual(len(self.links(one_place)), 7)

    # --- Permisos ---------------------------------------------------------------------------------

    def test_it_asks_for_a_session(self):
        self.client.post("/web/logout", data={"csrf_token": self.token_of("/web/")})
        response = self.client.get("/web/buscar?q=Marta")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/web/login", response.headers["Location"])

    def test_a_guard_cannot_use_the_web(self):
        self.client.post("/web/logout", data={"csrf_token": self.token_of("/web/")})
        self.log_in("guardia-web@test.local")
        self.assertNotEqual(self.client.get("/web/buscar?q=Marta").status_code, 200)


if __name__ == "__main__":
    unittest.main()
