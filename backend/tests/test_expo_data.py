"""Pruebas de la revisión de la base para la exposición (expo_data.py): solo lee, nunca cambia nada."""

import os
import unittest
from unittest import mock

import env_setup  # noqa: F401  (va antes de importar la app)

import demo_data
import expo_data
import seed
from app import create_app
from extensions import db
from models import User


class ExpoReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.addClassCleanup(env_setup.release_app, cls.app)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        seed.seed_if_empty()
        with mock.patch.dict(os.environ, {"DOMUX_DEMO_DATA": "1"}):
            demo_data.add_demo_data()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def test_sin_la_variable_no_hace_nada(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(expo_data.ACTION_VAR, None)
            self.assertIsNone(expo_data.requested_action())
            self.assertFalse(expo_data.run_requested_action())

    def test_el_resumen_separa_los_usuarios_que_no_son_de_prueba(self):
        db.session.add(User(
            email="prueba.propia@gmail.com", password_hash="x", role="RESIDENT", name="Prueba", last_name="Propia",
        ))
        db.session.commit()
        lines = expo_data.report()
        self.assertIn("== Filas por tabla ==", lines)
        extra = [line for line in lines if "prueba.propia@gmail.com" in line]
        self.assertEqual(len(extra), 1)
        self.assertFalse([line for line in lines if "maria@domux.com" in line])
        self.assertIn("Total: 1 de 18 usuarios", lines)

    def test_revisar_no_cambia_la_base(self):
        before = expo_data.table_counts()
        with mock.patch.dict(os.environ, {expo_data.ACTION_VAR: "inspeccionar"}):
            with self.assertLogs("expo_data", level="WARNING") as logs:
                self.assertTrue(expo_data.run_requested_action())
        self.assertTrue(logs.records)
        self.assertTrue(all(record.getMessage().startswith("[EXPO]") for record in logs.records))
        self.assertEqual(expo_data.table_counts(), before)


if __name__ == "__main__":
    unittest.main()
