"""Pruebas de la estructura de la unidad en la web (HU-076): torres, apartamentos, parqueaderos y cuartos útiles."""

import unittest

from extensions import db
from models import Apartment, ParkingSpot, StorageRoom, Tower
from structure_fixtures import apartment_for, apartment_in, parking_spot, storage_room, tower_named
from web_testing import WebTestCase


class WebStructureTests(WebTestCase):
    def setUp(self):
        super().setUp()
        # El residente de la clase base vive en la Torre 1, apartamento 101.
        self.tower = Tower.query.filter_by(name="Torre 1").one()
        self.apartment = apartment_for("Torre 1 · Apto 101")
        self.empty_apartment = apartment_in("Torre 1", "102")
        parking_spot("P-101", apartment=self.apartment, location="Sótano 1")
        parking_spot("V-01", kind="visitante", location="Entrada")
        storage_room("CU-01", apartment=self.apartment)
        storage_room("CU-02")
        db.session.commit()
        self.log_in()

    # --- Torres -------------------------------------------------------------------------------------

    def test_the_towers_page_lists_each_tower_with_its_floors_and_apartments(self):
        tower_named("Torre 2", floors=4)
        db.session.commit()
        body = self.page("/web/estructura")
        self.assertIn("Torre 1", body)
        self.assertIn("Torre 2", body)
        self.assertIn("4 pisos", body)
        self.assertIn("2 apartamentos", body)
        for tab in ("Torres", "Apartamentos", "Parqueaderos", "Cuartos útiles"):
            self.assertIn(tab, body)

    def test_creating_a_tower(self):
        response = self.post("/web/estructura/torres/nueva", {"name": "  Torre 3 ", "floors": "12"})
        self.assertEqual(response.status_code, 302)
        tower = Tower.query.filter_by(name="Torre 3").one()
        self.assertEqual(tower.floors, 12)
        self.assertIn("Torre creada.", self.page("/web/estructura"))

    def test_a_repeated_tower_name_and_a_bad_number_of_floors_are_refused_with_the_servers_message(self):
        repeated = self.post("/web/estructura/torres/nueva", {"name": "torre 1", "floors": "5"})
        self.assertEqual(repeated.status_code, 409)
        self.assertIn("Ya existe una torre llamada", self.text(repeated))

        bad = self.post("/web/estructura/torres/nueva", {"name": "Torre 9", "floors": "0"})
        self.assertEqual(bad.status_code, 400)
        body = self.text(bad)
        self.assertIn("debe ser un número entero entre 1 y 100", body)
        self.assertIn('value="Torre 9"', body)           # lo escrito no se pierde
        self.assertIsNone(Tower.query.filter_by(name="Torre 9").first())

        words = self.post("/web/estructura/torres/nueva", {"name": "Torre 9", "floors": "muchos"})
        self.assertEqual(words.status_code, 400)

    def test_editing_a_tower_and_its_floors_rule(self):
        page = self.page(f"/web/estructura/torres/{self.tower.id}")
        self.assertIn('value="Torre 1"', page)
        self.assertIn("Retirar torre", page)

        self.post(f"/web/estructura/torres/{self.tower.id}", {"name": "Torre Norte", "floors": "20"})
        saved = db.session.get(Tower, self.tower.id)
        db.session.refresh(saved)
        self.assertEqual((saved.name, saved.floors), ("Torre Norte", 20))

        apartment_in("Torre Norte", "1505", floor=15)
        db.session.commit()
        refused = self.post(f"/web/estructura/torres/{self.tower.id}", {"name": "Torre Norte", "floors": "10"})
        self.assertEqual(refused.status_code, 409)
        self.assertIn("no puede quedar con menos pisos", self.text(refused))

    def test_a_tower_with_apartments_is_not_retired_but_an_empty_one_is(self):
        self.post(f"/web/estructura/torres/{self.tower.id}/retirar")
        self.assertIsNone(db.session.get(Tower, self.tower.id).retired_at)
        self.assertIn("apartamentos", self.page("/web/estructura").lower())

        spare = tower_named("Torre Libre")
        db.session.commit()
        self.post(f"/web/estructura/torres/{spare.id}/retirar")
        kept = db.session.get(Tower, spare.id)
        db.session.refresh(kept)
        self.assertIsNotNone(kept.retired_at)           # no se borra: queda retirada
        self.assertNotIn("Torre Libre", self.page("/web/estructura"))
        self.assertEqual(self.client.get(f"/web/estructura/torres/{spare.id}").status_code, 404)

    # --- Apartamentos -------------------------------------------------------------------------------

    def test_the_apartments_page_shows_residents_parking_and_storage(self):
        body = self.page("/web/estructura/apartamentos")
        self.assertIn("Torre 1 · Apto 101", body)
        self.assertIn("Torre 1 · Apto 102", body)
        self.assertIn("P-101", body)
        self.assertIn("CU-01", body)
        self.assertIn("Crear un piso completo", body)

    def test_apartments_can_be_filtered_by_tower_and_text(self):
        tower_two = tower_named("Torre 2")
        apartment_in("Torre 2", "201")
        db.session.commit()
        only_two = self.page(f"/web/estructura/apartamentos?torre={tower_two.id}")
        self.assertIn("Torre 2 · Apto 201", only_two)
        self.assertNotIn("Apto 101", only_two)
        by_code = self.page("/web/estructura/apartamentos?q=102")
        self.assertIn("Apto 102", by_code)
        self.assertNotIn("Apto 101", by_code)
        self.assertIn("No hay apartamentos con esos filtros", self.page("/web/estructura/apartamentos?q=zzz"))

    def test_creating_an_apartment_takes_the_floor_from_the_code(self):
        form = self.page(f"/web/estructura/apartamentos/nuevo?torre={self.tower.id}")
        self.assertIn(f'<option value="{self.tower.id}" selected>', form)
        response = self.post("/web/estructura/apartamentos/nuevo", {"towerId": str(self.tower.id), "code": "305"})
        self.assertEqual(response.status_code, 302)
        created = Apartment.query.filter_by(tower_id=self.tower.id, code="305").one()
        self.assertEqual(created.floor, 3)
        self.assertIsNotNone(created.unit)               # nace con la ficha del hogar

    def test_an_apartment_that_already_exists_or_without_a_tower_is_refused(self):
        repeated = self.post("/web/estructura/apartamentos/nuevo", {"towerId": str(self.tower.id), "code": "101"})
        self.assertEqual(repeated.status_code, 409)
        self.assertIn("ya existe", self.text(repeated).lower())
        no_tower = self.post("/web/estructura/apartamentos/nuevo", {"code": "999"})
        self.assertEqual(no_tower.status_code, 400)
        self.assertIn("Elige la torre del apartamento", self.text(no_tower))
        too_high = self.post(
            "/web/estructura/apartamentos/nuevo", {"towerId": str(self.tower.id), "code": "9901", "floor": "99"},
        )
        self.assertEqual(too_high.status_code, 400)

    def test_creating_a_whole_floor_at_once(self):
        form = {"towerId": str(self.tower.id), "floor": "3", "count": "4"}
        response = self.post("/web/estructura/apartamentos/piso", form)
        self.assertEqual(response.status_code, 302)
        codes = sorted(item.code for item in Apartment.query.filter(Apartment.code.like("3%")))
        self.assertEqual(codes, ["301", "302", "303", "304"])
        self.assertIn("Se crearon 4 apartamentos en el piso 3 de Torre 1", self.page("/web/estructura/apartamentos?torre=%d" % self.tower.id))

    def test_a_floor_with_an_existing_apartment_creates_none(self):
        form = {"towerId": str(self.tower.id), "floor": "1", "count": "3"}      # 101, 102 y 103: ya existen 101 y 102
        response = self.post("/web/estructura/apartamentos/piso", form)
        self.assertEqual(response.status_code, 409)
        self.assertIn("No se creó ninguno", self.text(response))
        self.assertIsNone(Apartment.query.filter_by(tower_id=self.tower.id, code="103").first())

    def test_a_floor_beyond_the_tower_is_refused(self):
        response = self.post(
            "/web/estructura/apartamentos/piso", {"towerId": str(self.tower.id), "floor": "50", "count": "2"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(Apartment.query.filter_by(code="5001").first())

    def test_editing_an_apartment(self):
        page = self.page(f"/web/estructura/apartamentos/{self.empty_apartment.id}")
        self.assertIn('value="102"', page)
        self.assertNotIn('name="towerId"', page)          # un apartamento no cambia de torre
        self.post(f"/web/estructura/apartamentos/{self.empty_apartment.id}", {"code": "202", "floor": "2"})
        saved = db.session.get(Apartment, self.empty_apartment.id)
        db.session.refresh(saved)
        self.assertEqual((saved.code, saved.floor), ("202", 2))

        repeated = self.post(f"/web/estructura/apartamentos/{self.empty_apartment.id}", {"code": "101", "floor": "1"})
        self.assertEqual(repeated.status_code, 409)

    def test_an_apartment_with_residents_is_not_retired_and_an_empty_one_frees_its_parking(self):
        refused = self.post(f"/web/estructura/apartamentos/{self.apartment.id}/retirar", follow=True)
        self.assertIn("residente", self.text(refused))
        self.assertIsNone(db.session.get(Apartment, self.apartment.id).retired_at)

        spot = ParkingSpot.query.filter_by(code="P-102").first() or parking_spot("P-102", apartment=self.empty_apartment)
        db.session.commit()
        self.post(f"/web/estructura/apartamentos/{self.empty_apartment.id}/retirar")
        retired = db.session.get(Apartment, self.empty_apartment.id)
        db.session.refresh(retired)
        self.assertIsNotNone(retired.retired_at)
        db.session.refresh(spot)
        self.assertIsNone(spot.apartment_id)              # el parqueadero queda libre para otro
        self.assertNotIn("Apto 102", self.page("/web/estructura/apartamentos"))

    def test_the_retire_button_asks_for_confirmation(self):
        page = self.page(f"/web/estructura/apartamentos/{self.empty_apartment.id}")
        self.assertIn("data-confirm=", page)
        self.assertIn("Retirar apartamento", page)

    # --- Parqueaderos -------------------------------------------------------------------------------

    def test_the_parking_page_shows_kind_location_and_assignment(self):
        body = self.page("/web/estructura/parqueaderos")
        self.assertIn("P-101", body)
        self.assertIn("Sótano 1", body)
        self.assertIn("Torre 1 · Apto 101", body)
        self.assertIn("De visitantes", body)
        self.assertIn("Libre", body)

    def test_parking_filters(self):
        visitors = self.page("/web/estructura/parqueaderos?tipo=visitante")
        self.assertIn("V-01", visitors)
        self.assertNotIn("P-101", visitors)
        free = self.page("/web/estructura/parqueaderos?asignado=no")
        self.assertIn("V-01", free)
        self.assertNotIn("P-101", free)
        self.assertIn("P-101", self.page("/web/estructura/parqueaderos?q=sótano"))
        ignored = self.page("/web/estructura/parqueaderos?tipo=raro&asignado=raro")
        self.assertIn("P-101", ignored)             # un filtro desconocido se ignora
        self.assertIn("V-01", ignored)

    def test_creating_a_resident_and_a_visitor_parking_spot(self):
        self.post("/web/estructura/parqueaderos/nuevo", {
            "code": "p-202", "type": "residente", "location": "Sótano 2", "apartmentId": str(self.empty_apartment.id),
        })
        resident_spot = ParkingSpot.query.filter_by(code="P-202").one()
        self.assertEqual(resident_spot.apartment_id, self.empty_apartment.id)
        self.post("/web/estructura/parqueaderos/nuevo", {"code": "V-02", "type": "visitante", "location": "Entrada"})
        self.assertIsNone(ParkingSpot.query.filter_by(code="V-02").one().apartment_id)

    def test_a_visitor_spot_cannot_be_assigned_and_codes_cannot_repeat(self):
        assigned = self.post("/web/estructura/parqueaderos/nuevo", {
            "code": "V-09", "type": "visitante", "location": "Entrada", "apartmentId": str(self.apartment.id),
        })
        self.assertEqual(assigned.status_code, 400)
        self.assertIn("no se asigna a un apartamento", self.text(assigned))
        repeated = self.post("/web/estructura/parqueaderos/nuevo", {"code": "P-101", "type": "residente", "location": "Otro"})
        self.assertEqual(repeated.status_code, 409)
        self.assertIn("ya existe", self.text(repeated))
        self.assertIsNone(ParkingSpot.query.filter_by(code="V-09").first())

    def test_editing_a_parking_spot_and_leaving_it_without_an_apartment(self):
        spot = ParkingSpot.query.filter_by(code="P-101").one()
        page = self.page(f"/web/estructura/parqueaderos/{spot.id}")
        self.assertIn('value="Sótano 1"', page)
        self.assertIn(f'<option value="{self.apartment.id}" selected>', page)

        self.post(f"/web/estructura/parqueaderos/{spot.id}", {
            "code": "P-101", "type": "residente", "location": "Sótano 3", "apartmentId": "",
        })
        db.session.refresh(spot)
        self.assertEqual(spot.location, "Sótano 3")
        self.assertIsNone(spot.apartment_id)              # «Sin asignar» lo deja libre

    def test_an_occupied_parking_spot_is_not_retired_but_a_free_one_is(self):
        visitor = ParkingSpot.query.filter_by(code="V-01").one()
        visitor.occupied = True
        db.session.commit()
        refused = self.post(f"/web/estructura/parqueaderos/{visitor.id}/retirar", follow=True)
        self.assertIn("está ocupado", self.text(refused))
        db.session.refresh(visitor)
        self.assertIsNone(visitor.retired_at)

        visitor.occupied = False
        db.session.commit()
        self.post(f"/web/estructura/parqueaderos/{visitor.id}/retirar")
        db.session.refresh(visitor)
        self.assertIsNotNone(visitor.retired_at)
        self.assertEqual(self.client.get(f"/web/estructura/parqueaderos/{visitor.id}").status_code, 404)

    # --- Cuartos útiles -----------------------------------------------------------------------------

    def test_the_storage_page_and_its_filters(self):
        body = self.page("/web/estructura/cuartos")
        self.assertIn("CU-01", body)
        self.assertIn("CU-02", body)
        self.assertIn("Sin asignar", body)
        free = self.page("/web/estructura/cuartos?asignado=no")
        self.assertIn("CU-02", free)
        self.assertNotIn("CU-01", free)
        self.assertIn("CU-01", self.page("/web/estructura/cuartos?q=cu-01"))

    def test_creating_editing_and_retiring_a_storage_room(self):
        self.post("/web/estructura/cuartos/nuevo", {"code": "cu-10", "apartmentId": str(self.empty_apartment.id)})
        room = StorageRoom.query.filter_by(code="CU-10").one()
        self.assertEqual(room.apartment_id, self.empty_apartment.id)

        repeated = self.post("/web/estructura/cuartos/nuevo", {"code": "CU-10"})
        self.assertEqual(repeated.status_code, 409)

        self.post(f"/web/estructura/cuartos/{room.id}", {"code": "CU-11", "apartmentId": ""})
        db.session.refresh(room)
        self.assertEqual(room.code, "CU-11")
        self.assertIsNone(room.apartment_id)

        self.post(f"/web/estructura/cuartos/{room.id}/retirar")
        db.session.refresh(room)
        self.assertIsNotNone(room.retired_at)

    # --- Seguridad ----------------------------------------------------------------------------------

    def test_every_structure_page_needs_a_session(self):
        anonymous = self.app.test_client()
        for path in (
            "/web/estructura", "/web/estructura/torres/nueva", f"/web/estructura/torres/{self.tower.id}",
            "/web/estructura/apartamentos", "/web/estructura/apartamentos/nuevo", "/web/estructura/apartamentos/piso",
            "/web/estructura/parqueaderos", "/web/estructura/parqueaderos/nuevo",
            "/web/estructura/cuartos", "/web/estructura/cuartos/nuevo",
        ):
            self.assertEqual(anonymous.get(path).status_code, 302, path)

    def test_every_change_needs_the_csrf_code(self):
        spot = ParkingSpot.query.filter_by(code="V-01").one()
        for path in (
            "/web/estructura/torres/nueva", f"/web/estructura/torres/{self.tower.id}/retirar",
            "/web/estructura/apartamentos/nuevo", "/web/estructura/apartamentos/piso",
            f"/web/estructura/apartamentos/{self.empty_apartment.id}/retirar",
            "/web/estructura/parqueaderos/nuevo", f"/web/estructura/parqueaderos/{spot.id}/retirar",
            "/web/estructura/cuartos/nuevo",
        ):
            self.assertEqual(self.client.post(path, data={"code": "X"}).status_code, 400, path)
        self.assertIsNone(db.session.get(Apartment, self.empty_apartment.id).retired_at)
        self.assertIsNone(db.session.get(ParkingSpot, spot.id).retired_at)

    def test_names_written_by_the_administration_are_escaped(self):
        self.post("/web/estructura/torres/nueva", {"name": "<b>Torre</b>", "floors": "3"})
        body = self.page("/web/estructura")
        self.assertNotIn("<b>Torre</b>", body)
        self.assertIn("&lt;b&gt;Torre&lt;/b&gt;", body)


if __name__ == "__main__":
    unittest.main()
