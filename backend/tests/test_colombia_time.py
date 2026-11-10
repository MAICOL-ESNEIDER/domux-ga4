"""Pruebas de la hora de Colombia (ADR-011, TT-031 y DEF-002).

La base guarda UTC, pero la app muestra la hora de Colombia y «hoy» es el día
de Colombia, aunque el servidor (Render) corra en UTC. Antes, después de las
7 de la noche las horas salían 5 horas adelante y los QR del día dejaban de
servir.
"""

import unittest
from datetime import date, datetime
from unittest import mock

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import generate_password_hash

import time_utils
from app import create_app
from auth import generate_token
from extensions import db
from models import User, VisitQrPass, _fmt

#: 10 de noviembre de 2026 a las 10 de la noche en Colombia (ya es 11 en UTC).
NIGHT_IN_COLOMBIA = datetime(2026, 11, 10, 22, 0, tzinfo=time_utils.COLOMBIA)


class ColombiaTimeTests(unittest.TestCase):
    def test_saved_utc_time_is_shown_in_colombia_time(self):
        self.assertEqual(_fmt(datetime(2026, 11, 11, 2, 30)), "2026-11-10 21:30")
        self.assertIsNone(_fmt(None))

    def test_today_is_colombias_date_even_when_utc_is_already_tomorrow(self):
        with mock.patch.object(time_utils, "colombia_now", return_value=NIGHT_IN_COLOMBIA):
            self.assertEqual(time_utils.colombia_today(), date(2026, 11, 10))

    def test_utc_now_has_no_time_zone_like_the_database(self):
        self.assertIsNone(time_utils.utc_now().tzinfo)


class QrAtNightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.guard = User(
            name="Guardia", email="guardia-noche@test.local", role="GUARD", is_active=True,
            password_hash=generate_password_hash("Clave-de-prueba-1*"),
        )
        resident = User(
            name="Residente", email="residente-noche@test.local", role="RESIDENT",
            apartment="Apto 101", is_active=True,
            password_hash=generate_password_hash("Clave-de-prueba-1*"),
        )
        db.session.add_all([self.guard, resident])
        db.session.flush()
        db.session.add(VisitQrPass(
            resident_id=resident.id, token="qr-de-hoy",
            valid_from="2026-11-10", valid_until="2026-11-10", max_people=1,
        ))
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def test_qr_valid_today_still_works_at_night(self):
        with mock.patch.object(time_utils, "colombia_now", return_value=NIGHT_IN_COLOMBIA):
            response = self.client.get(
                "/api/visits/qr/qr-de-hoy",
                headers={"Authorization": f"Bearer {generate_token(self.guard)}"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["canRegister"])


if __name__ == "__main__":
    unittest.main()
