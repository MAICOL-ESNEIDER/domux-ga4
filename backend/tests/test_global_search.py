"""Pruebas del buscador general con el filtro «Buscar en» (HU-089).

Usan los datos de prueba (demo_data.py): 17 usuarios, cuatro hogares, PQRS, paquetes, visitas y
vehículos. Revisan qué encuentra cada rol, que la portería siga las reglas de su buscador de
residentes (sin correos, sin PQRS, máximo 5) y que los resultados lleguen agrupados.
"""

import os
import unittest
from unittest import mock

import env_setup  # noqa: F401  (va antes de importar la app)

import demo_data
import seed
from app import create_app
from auth import generate_token
from extensions import db
from models import PackageItem, User, VisitorVehicleEntry
from services import global_search
from time_utils import utc_now


class GlobalSearchTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.addClassCleanup(env_setup.release_app, cls.app)
        cls.client = cls.app.test_client()

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        seed.seed_if_empty()
        with mock.patch.dict(os.environ, {"DOMUX_DEMO_DATA": "1"}):
            self.assertTrue(demo_data.add_demo_data())
        self.admin = User.query.filter_by(email="admin@domux.com").one()
        self.guard = User.query.filter_by(email="guardia2@domux.com").one()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def search(self, who, q, place=None, expect=200):
        query = {"q": q}
        if place:
            query["in"] = place
        response = self.client.get(
            "/api/search", query_string=query, headers={"Authorization": f"Bearer {generate_token(who)}"}
        )
        self.assertEqual(response.status_code, expect, response.get_json())
        return response.get_json()

    @staticmethod
    def titles(result, kind):
        return [item["title"] for group in result["groups"] if group["type"] == kind for item in group["items"]]


class WhoCanSearchTests(GlobalSearchTestCase):
    def test_los_residentes_no_usan_el_buscador_general(self):
        resident = User.query.filter_by(email="jorge@domux.com").one()
        self.search(resident, "Natalia", expect=403)

    def test_la_porteria_no_busca_pqrs(self):
        body = self.search(self.guard, "ascensor", "pqrs", expect=403)
        self.assertIn("PQRS", body["error"])
        self.assertEqual(self.titles(self.search(self.guard, "ascensor"), "pqrs"), [])

    def test_cada_rol_recibe_sus_opciones_del_filtro(self):
        admin_places = [place["value"] for place in self.search(self.admin, "xx")["places"]]
        guard_places = [place["value"] for place in self.search(self.guard, "xx")["places"]]
        self.assertEqual(admin_places, ["todo", "personas", "apartamentos", "vehiculos", "pqrs", "paquetes", "visitas"])
        self.assertEqual(guard_places, ["todo", "personas", "apartamentos", "vehiculos", "paquetes", "visitas"])

    def test_un_lugar_que_no_existe(self):
        self.search(self.admin, "Natalia", "cuentas", expect=400)

    def test_con_menos_de_dos_letras_no_busca(self):
        body = self.search(self.admin, " n ")
        self.assertTrue(body["tooShort"])
        self.assertEqual(body["groups"], [])


class PeopleTests(GlobalSearchTestCase):
    def test_la_administracion_encuentra_por_correo_y_por_telefono(self):
        self.assertEqual(self.titles(self.search(self.admin, "marta@domux", "personas"), "personas"),
                         ["Marta Lucía Henao Arango"])
        self.assertEqual(self.titles(self.search(self.admin, "3000000309", "personas"), "personas"),
                         ["Gustavo Restrepo Arango"])

    def test_la_porteria_no_busca_por_correo_ni_ve_al_personal(self):
        self.assertEqual(self.titles(self.search(self.guard, "marta@domux", "personas"), "personas"), [])
        self.assertEqual(self.titles(self.search(self.guard, "Edwin", "personas"), "personas"), [])
        found = self.search(self.guard, "Natalia", "personas")["groups"][0]["items"][0]
        self.assertEqual(found["subtitle"], "Torre 2 · Apto 101")

    def test_la_porteria_no_ve_cuentas_desactivadas(self):
        natalia = User.query.filter_by(email="natalia@domux.com").one()
        natalia.is_active = False
        db.session.commit()
        self.assertEqual(self.titles(self.search(self.guard, "Natalia", "personas"), "personas"), [])
        admin_item = self.search(self.admin, "Natalia", "personas")["groups"][0]["items"][0]
        self.assertIn("Cuenta desactivada", admin_item["subtitle"])

    def test_la_porteria_ve_maximo_cinco(self):
        group = self.search(self.guard, "Torre", "personas")["groups"][0]
        self.assertEqual(len(group["items"]), 5)
        self.assertTrue(group["more"])


class PlacesTests(GlobalSearchTestCase):
    def test_apartamentos_por_torre_y_codigo(self):
        self.assertEqual(self.titles(self.search(self.admin, "Torre 2 101", "apartamentos"), "apartamentos"),
                         ["Torre 2 · Apto 101"])
        item = self.search(self.admin, "Torre 1 · Apto 201", "apartamentos")["groups"][0]["items"][0]
        self.assertEqual(item["subtitle"], "2 residentes")

    def test_vehiculos_de_residentes_y_de_visitantes_adentro(self):
        found = self.search(self.guard, "dmx-101", "vehiculos")["groups"][0]["items"]
        self.assertEqual([(item["title"], item["kind"]) for item in found], [("DMX101", "residente")])
        visitor = self.search(self.guard, "VIS123", "vehiculos")["groups"][0]["items"][0]
        self.assertEqual(visitor["kind"], "visitante")
        self.assertIn("V-06", visitor["subtitle"])
        entry = VisitorVehicleEntry.query.filter_by(plate="VIS123").one()
        entry.exited_at = utc_now()
        db.session.commit()
        self.assertEqual(self.search(self.guard, "VIS123", "vehiculos")["groups"], [])

    def test_una_placa_muy_corta_no_busca_vehiculos(self):
        self.assertEqual(self.titles(self.search(self.admin, "DM", "vehiculos"), "vehiculos"), [])

    def test_pqrs_por_radicado_y_por_asunto(self):
        by_subject = self.search(self.admin, "ascensor", "pqrs")["groups"][0]["items"][0]
        self.assertIn("En proceso", by_subject["subtitle"])
        radicado = by_subject["title"].split(" · ")[0]
        self.assertEqual(self.search(self.admin, radicado, "pqrs")["groups"][0]["items"][0]["id"], by_subject["id"])

    def test_paquetes_con_su_alerta_y_sin_los_de_la_papelera(self):
        item = self.search(self.guard, "Mercado Libre", "paquetes")["groups"][0]["items"][0]
        self.assertIn("Más de 48 h sin reclamar", item["subtitle"])
        package = PackageItem.query.filter_by(description="Caja de Mercado Libre").one()
        package.is_deleted = True
        db.session.commit()
        self.assertEqual(self.titles(self.search(self.guard, "Mercado Libre", "paquetes"), "paquetes"), [])

    def test_visitas_con_su_estado(self):
        found = {item["title"]: item["subtitle"] for item in self.search(self.guard, "Torre", "visitas")["groups"][0]["items"]}
        self.assertIn("Adentro", found["Ana María Vélez"])
        self.assertIn("Esperando autorización", found["Domiciliario de Rappi"])
        self.assertIn("Ya salió", found["Lucía Restrepo Patiño"])


class EverywhereTests(GlobalSearchTestCase):
    def test_en_todo_salen_los_grupos_en_orden(self):
        body = self.search(self.admin, "Natalia")
        self.assertEqual([group["type"] for group in body["groups"]], ["personas", "pqrs", "paquetes", "visitas"])
        self.assertTrue(all(len(group["items"]) <= global_search.LIMIT_EVERYWHERE for group in body["groups"]))

    def test_los_comodines_se_buscan_como_texto(self):
        self.assertEqual(self.search(self.admin, "%%")["groups"], [])
        self.assertEqual(self.search(self.admin, "__")["groups"], [])

    def test_cada_resultado_dice_su_apartamento(self):
        item = self.search(self.admin, "Rappi", "visitas")["groups"][0]["items"][0]
        diana = User.query.filter_by(email="diana@domux.com").one()
        self.assertEqual(item["apartmentId"], diana.apartment_id)


if __name__ == "__main__":
    unittest.main()
