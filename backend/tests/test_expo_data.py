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
from models import Announcement, Pqrs, Reservation, PackageItem, User, Visit


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


class ExpoActivityTests(ExpoReportTests):
    # Hereda solo la preparación de la base; las pruebas de arriba no se repiten.
    test_sin_la_variable_no_hace_nada = test_el_resumen_separa_los_usuarios_que_no_son_de_prueba = test_revisar_no_cambia_la_base = None

    def load(self):
        with mock.patch.dict(os.environ, {expo_data.ACTION_VAR: "cargar"}):
            return expo_data.run_requested_action()

    def test_agrega_actividad_con_adjuntos_y_solo_una_vez(self):
        before = {"u": User.query.count()}
        self.assertTrue(self.load())
        self.assertEqual(User.query.count(), before["u"])
        self.assertGreaterEqual(Announcement.query.count(), 9 + 5)
        self.assertGreaterEqual(Pqrs.query.count(), 8 + 5)
        self.assertGreaterEqual(Reservation.query.count(), 6)
        self.assertGreaterEqual(PackageItem.query.count(), 8)
        self.assertGreaterEqual(Visit.query.count(), 11)
        kinds = {a.media_type for a in Announcement.query if a.media_url}
        self.assertEqual(kinds, {"image", "video", "audio", "document"})
        self.assertFalse(self.load())  # no se repite

    def test_todos_los_adjuntos_pasan_la_revision_del_servidor(self):
        from services.media import check_attachment
        self.load()
        rows = [(a.media_url, a.media_type) for a in Announcement.query if a.media_url]
        rows += [(p.media_url, p.media_type) for p in Pqrs.query if p.media_url]
        self.assertTrue(rows)
        for url, kind in rows:
            checked, error = check_attachment(url, kind, allow_document=True)
            self.assertIsNone(error, kind)
            self.assertEqual(checked, url)

    def test_la_api_los_entrega_como_cualquier_dato(self):
        self.load()
        client = self.app.test_client()
        login = client.post("/api/auth/login", json={"email": "jorge@domux.com", "password": os.environ["SEED_RESIDENT_PASSWORD"]})
        self.assertEqual(login.status_code, 200, login.get_json())
        headers = {"Authorization": f"Bearer {login.get_json()['token']}"}
        for path in ("/api/announcements", "/api/pqrs", "/api/reservations", "/api/packages"):
            response = client.get(path, headers=headers)
            self.assertEqual(response.status_code, 200, path)


if __name__ == "__main__":
    unittest.main()
