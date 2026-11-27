"""La página web «Esperados por la administración»: técnicos y paquetes de la unidad (decisión del 26/11/2026)."""

import unittest
from datetime import timedelta

from extensions import db
from models import PackageItem, Visit
from time_utils import colombia_today
from web_testing import WebTestCase


class WebExpectedTests(WebTestCase):
    def setUp(self):
        super().setUp()
        self.log_in()

    def test_anunciar_y_cancelar_un_tecnico(self):
        day = (colombia_today() + timedelta(days=2)).isoformat()
        self.page("/web/esperados")
        response = self.post("/web/esperados/tecnico", {
            "visitorName": "Jardines del Valle", "description": "Poda de la zona verde", "expectedDate": day,
        }, follow=True)
        self.assertIn("Jardines del Valle", self.text(response))
        visit = Visit.query.filter_by(visitor_name="Jardines del Valle").one()
        self.assertTrue(visit.for_unit)
        self.post(f"/web/esperados/tecnico/{visit.id}/cancelar", follow=True)
        db.session.expire_all()
        self.assertEqual(db.session.get(Visit, visit.id).approval_status, "rechazada")

    def test_anunciar_un_paquete_de_la_unidad(self):
        self.page("/web/esperados")
        self.post("/web/esperados/paquete", {"description": "Plantas para el jardín"}, follow=True)
        item = PackageItem.query.filter_by(description="Plantas para el jardín").one()
        self.assertTrue(item.for_unit)
        self.assertEqual(item.status, "por_llegar")

    def test_un_dia_que_ya_paso_muestra_el_error(self):
        self.page("/web/esperados")
        response = self.post("/web/esperados/tecnico", {
            "visitorName": "X", "description": "Y", "expectedDate": "2020-01-01",
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("ya pasó", self.text(response))


if __name__ == "__main__":
    unittest.main()
