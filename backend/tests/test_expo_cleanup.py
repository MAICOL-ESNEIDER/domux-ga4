"""Pruebas de la limpieza única de la exposición (expo_cleanup.py)."""

import os
import unittest
from datetime import datetime, timedelta
from unittest import mock

import env_setup  # noqa: F401  (va antes de importar la app)

import demo_data
import expo_cleanup
import expo_data
import seed
from app import create_app
from extensions import db
from models import (
    Announcement,
    AuditLog,
    CommonArea,
    LoginAttempt,
    PackageItem,
    Pqrs,
    Reservation,
    User,
    Visit,
)


class ExpoCleanupTests(unittest.TestCase):
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
        self.admin = User.query.filter_by(email="admin@domux.com").first()
        self.maria = User.query.filter_by(email="maria@domux.com").first()
        self.guard = User.query.filter_by(email="guardia@domux.com").first()
        self.long_ago = datetime(2026, 11, 10, 15, 0)
        self.sala = CommonArea.query.filter_by(name="Salón social").first()
        self.cancha = CommonArea.query.filter_by(name="Cancha múltiple").first()
        db.session.add_all([
            Announcement(title="hi", message="hi", category="general", author_id=self.admin.id),
            Announcement(title="Se nos infiltró un dragón", message="x", category="general", author_id=self.admin.id),
            Pqrs(resident_id=self.maria.id, category="Queja", subject="basura", message="x", created_at=self.long_ago),
            PackageItem(resident_id=self.maria.id, registered_by=self.guard.id, description="Paquete de prueba pendiente",
                        status="pendiente", created_at=self.long_ago),
            Reservation(resident_id=self.maria.id, common_area_id=self.cancha.id, date="2026-11-17",
                        time_slot=self.cancha.slots[0], attendees=10, status="pendiente"),
            Reservation(resident_id=self.maria.id, common_area_id=self.sala.id, date="2026-11-11",
                        time_slot=self.sala.full_day_slot, attendees=10, status="pendiente"),
            Visit(resident_id=self.maria.id, registered_by=self.guard.id, visitor_name="Andres", type="visitante",
                  approval_status="pendiente"),
            LoginAttempt(kind="email", subject="alguien@correo.com", failed_count=2),
        ])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def test_borra_las_pruebas_y_renueva_lo_vencido(self):
        with self.assertLogs("expo_cleanup", level="WARNING") as logs:
            self.assertTrue(expo_cleanup.clean_for_expo())

        self.assertIsNone(Announcement.query.filter_by(title="hi").first())
        self.assertIsNone(Announcement.query.filter_by(title="Se nos infiltró un dragón").first())
        self.assertIsNone(Pqrs.query.filter_by(subject="basura").first())
        self.assertIsNone(Visit.query.filter_by(visitor_name="Andres").first())
        self.assertEqual(LoginAttempt.query.count(), 0)
        self.assertIsNone(PackageItem.query.filter_by(description="Paquete de prueba pendiente").first())

        # Lo vencido que se renueva: queda una copia nueva y reciente, con su radicado.
        renewed = Pqrs.query.filter_by(subject="Ruido en el apartamento de arriba").all()
        self.assertEqual(len(renewed), 1)
        self.assertGreater(renewed[0].created_at, datetime.utcnow() - timedelta(days=2))
        self.assertTrue(renewed[0].radicado.startswith("PQRS-2026-"))
        self.assertEqual(len(renewed[0].conversation), 1)
        self.assertEqual(PackageItem.query.filter_by(description="Caja de Amazon").count(), 1)
        self.assertGreater(PackageItem.query.filter_by(description="Caja de Amazon").first().arrived_at, datetime.utcnow() - timedelta(days=2))

        # Los ejemplos que se dejan vencidos siguen igual.
        self.assertEqual(Pqrs.query.filter_by(subject="El ascensor se detiene entre pisos").count(), 1)
        self.assertEqual(PackageItem.query.filter_by(description="Caja de Mercado Libre").count(), 1)
        self.assertIsNotNone(Reservation.query.filter_by(date="2026-11-11").first())
        self.assertIsNone(Reservation.query.filter_by(date="2026-11-17").first())
        self.assertIsNotNone(Reservation.query.filter_by(date="2026-12-02", status="pendiente").first())

        # Antes de borrar queda escrito en el registro.
        backup = [record.getMessage() for record in logs.records if "[EXPO-RESPALDO]" in record.getMessage()]
        self.assertTrue(any("basura" in line for line in backup))
        self.assertTrue(any("Andres" in line for line in backup))

    def test_se_hace_una_sola_vez(self):
        self.assertTrue(expo_cleanup.clean_for_expo())
        self.assertTrue(AuditLog.query.filter_by(entity_type=expo_cleanup.MARKER_ENTITY).first())
        before = Pqrs.query.count()
        self.assertFalse(expo_cleanup.clean_for_expo())
        self.assertEqual(Pqrs.query.count(), before)

    def test_la_variable_limpiar_la_ejecuta(self):
        with mock.patch.dict(os.environ, {expo_data.ACTION_VAR: "limpiar"}):
            self.assertTrue(expo_data.run_requested_action())
        self.assertIsNone(Pqrs.query.filter_by(subject="basura").first())
