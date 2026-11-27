"""Pruebas de lo que la administración espera para la unidad: técnicos y paquetes (decisión del 26/11/2026).

La administración no registra visitas ni paquetes de los residentes. Solo anuncia con anticipación a los
técnicos o contratistas que vienen a trabajar en las zonas comunes y los paquetes de la unidad
(repuestos, materiales, plantas, herramientas). El guardia los ve como esperados y registra la llegada.
"""

import unittest
from datetime import timedelta

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import generate_password_hash

from app import create_app
from auth import generate_token
from extensions import db
from models import Notification, User, UNIT_PLACE_LABEL
from structure_fixtures import apartment_for
from time_utils import colombia_today


class UnitExpectedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.addClassCleanup(env_setup.release_app, cls.app)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        apartment = apartment_for("Torre 1 · Apto 101")
        self.admin = self.user("Admin", "admin", "ADMIN")
        self.guard = self.user("Guardia", "guard", "GUARD")
        self.resident = self.user("Residente", "resident", "RESIDENT", apartment)
        db.session.add_all([self.admin, self.guard, self.resident])
        db.session.commit()
        self.client = self.app.test_client()
        self.tomorrow = (colombia_today() + timedelta(days=1)).isoformat()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def user(self, name, key, role, apartment=None):
        return User(
            name=name, email=f"{key}@esperados.test", role=role, is_active=True,
            password_hash=generate_password_hash("Prueba123*"), apartment_ref=apartment,
        )

    def auth(self, user):
        return {"Authorization": f"Bearer {generate_token(user)}"}

    def expect_technician(self, **extra):
        body = {"visitorName": "Ascensores Andinos", "description": "Mantenimiento del ascensor de la Torre 1",
                "expectedDate": self.tomorrow, "expectedTime": "08:30", **extra}
        return self.client.post("/api/visits/expected", json=body, headers=self.auth(self.admin))

    def test_el_tecnico_esperado_aparece_al_guardia_y_entra_sin_autorizacion(self):
        response = self.expect_technician()
        self.assertEqual(response.status_code, 201, response.get_json())
        visit = response.get_json()["visit"]
        self.assertTrue(visit["forUnit"])
        self.assertEqual(visit["apartment"], UNIT_PLACE_LABEL)
        self.assertEqual(visit["approvalStatus"], "aprobada")
        self.assertTrue(Notification.query.filter_by(user_id=self.guard.id, title="Técnico esperado").first())

        listed = self.client.get("/api/visits/expected", headers=self.auth(self.guard)).get_json()["visits"]
        self.assertEqual([item["id"] for item in listed], [visit["id"]])

        entry = self.client.post(f"/api/visits/{visit['id']}/entry", json={}, headers=self.auth(self.guard))
        self.assertEqual(entry.status_code, 200, entry.get_json())
        listed = self.client.get("/api/visits/expected", headers=self.auth(self.guard)).get_json()["visits"]
        self.assertEqual(listed, [])

    def test_validaciones_del_tecnico_esperado(self):
        self.assertEqual(self.expect_technician(expectedDate="2020-01-01").status_code, 400)
        self.assertEqual(self.expect_technician(expectedTime="25:00").status_code, 400)
        self.assertEqual(self.expect_technician(description="").status_code, 400)
        guard_try = self.client.post("/api/visits/expected", json={}, headers=self.auth(self.guard))
        self.assertEqual(guard_try.status_code, 403)

    def test_el_residente_no_ve_los_tecnicos_de_la_unidad(self):
        self.expect_technician()
        visits = self.client.get("/api/visits", headers=self.auth(self.resident)).get_json()["visits"]
        self.assertEqual(visits, [])

    def test_la_administracion_cancela_un_tecnico_esperado(self):
        visit_id = self.expect_technician().get_json()["visit"]["id"]
        response = self.client.put(f"/api/visits/expected/{visit_id}/cancel", headers=self.auth(self.admin))
        self.assertEqual(response.status_code, 200)
        listed = self.client.get("/api/visits/expected", headers=self.auth(self.guard)).get_json()["visits"]
        self.assertEqual(listed, [])

    def test_la_administracion_solo_registra_paquetes_de_la_unidad(self):
        refused = self.client.post(
            "/api/packages", json={"description": "Caja", "residentId": self.resident.id}, headers=self.auth(self.admin)
        )
        self.assertEqual(refused.status_code, 403)

        response = self.client.post(
            "/api/packages", json={"description": "Repuestos de la bomba de agua", "carrier": "Servientrega"},
            headers=self.auth(self.admin),
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        item = response.get_json()["packageItem"]
        self.assertTrue(item["forUnit"])
        self.assertEqual(item["status"], "por_llegar")
        self.assertEqual(item["apartment"], UNIT_PLACE_LABEL)
        self.assertTrue(Notification.query.filter_by(user_id=self.guard.id, title="Paquete esperado para la unidad").first())

        # La portería lo recibe y luego lo entrega a la administración.
        arrived = self.client.put(f"/api/packages/{item['id']}/status", json={"status": "pendiente"}, headers=self.auth(self.guard))
        self.assertEqual(arrived.status_code, 200, arrived.get_json())
        delivered = self.client.put(
            f"/api/packages/{item['id']}/deliver", json={"receivedBy": "Administración"}, headers=self.auth(self.guard)
        )
        self.assertEqual(delivered.status_code, 200, delivered.get_json())
