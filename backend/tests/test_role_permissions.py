"""Pruebas de permisos por rol (ADR-015, SEC-002 y SEC-015).

Cada ruta deja pasar solo a los roles que nombra: la administración ya no hace
lo de portería (salvo paquetes) ni entra a las rutas del residente, y portería
no ve PQRS, reservas ni datos de residentes que no necesita.
"""

import unittest

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import generate_password_hash

from app import create_app
from auth import generate_token
from extensions import db
from models import User, Visit, VisitQrPass


class RolePermissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.admin = self.user("ADMIN", "admin-permisos@test.local")
        self.guard = self.user("GUARD", "guardia-permisos@test.local")
        self.resident = self.user(
            "RESIDENT", "residente-permisos@test.local",
            apartment="Apto 101", phone="3000000000", occupancy_type="propietario",
        )
        db.session.flush()
        self.visit = Visit(
            resident_id=self.resident.id, registered_by=self.guard.id,
            visitor_name="Visitante", type="visita",
        )
        db.session.add(VisitQrPass(
            resident_id=self.resident.id, token="qr-permisos",
            valid_from="2000-01-01", valid_until="2999-12-31", max_people=2,
        ))
        db.session.add(self.visit)
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def user(self, role, email, **fields):
        person = User(
            name=role.title(), email=email, role=role, is_active=True,
            password_hash=generate_password_hash("Clave-de-prueba-1*"), **fields,
        )
        db.session.add(person)
        return person

    def call(self, user, method, path, body=None):
        return self.client.open(
            path, method=method, json=body,
            headers={"Authorization": f"Bearer {generate_token(user)}"},
        )

    def test_administration_cannot_do_guard_or_resident_actions(self):
        forbidden = [
            ("POST", "/api/visits", {"residentId": self.resident.id, "visitorName": "X", "type": "visita"}),
            ("PUT", f"/api/visits/{self.visit.id}/authorize-call", None),
            ("POST", f"/api/visits/{self.visit.id}/entry", None),
            ("PUT", f"/api/visits/{self.visit.id}/decision", {"decision": "aprobada"}),
            ("GET", "/api/visits/qr/qr-permisos", None),
            ("POST", "/api/visits/qr/qr-permisos/entry", {"visitorName": "X"}),
            ("POST", "/api/visits/qr-passes", {"days": 1, "maxPeople": 1}),
            ("GET", "/api/profile", None),
            ("GET", "/api/profile/unit", None),
        ]
        for method, path, body in forbidden:
            with self.subTest(method=method, path=path):
                self.assertEqual(self.call(self.admin, method, path, body).status_code, 403)

    def test_administration_keeps_packages_and_visit_history(self):
        registered = self.call(self.admin, "POST", "/api/packages", {
            "residentId": self.resident.id, "description": "Caja", "status": "pendiente",
        })
        self.assertEqual(registered.status_code, 201)
        package_id = registered.get_json()["packageItem"]["id"]

        delivered = self.call(
            self.admin, "PUT", f"/api/packages/{package_id}/deliver", {"receivedBy": "María Pérez"}
        )
        history = self.call(self.admin, "GET", "/api/visits")

        self.assertEqual(delivered.status_code, 200)
        self.assertEqual(history.status_code, 200)

    def test_guard_cannot_see_pqrs_reservations_or_users(self):
        for method, path, body in [
            ("GET", "/api/pqrs", None),
            ("POST", "/api/pqrs", {"residentId": self.resident.id, "type": "peticion",
                                   "subject": "Asunto", "message": "Mensaje"}),
            ("GET", "/api/reservations", None),
            ("GET", "/api/users", None),
            ("POST", "/api/announcements", {"title": "T", "message": "M"}),
        ]:
            with self.subTest(method=method, path=path):
                self.assertEqual(self.call(self.guard, method, path, body).status_code, 403)

    def test_guard_only_gets_name_phone_and_apartment_of_residents(self):
        response = self.call(self.guard, "GET", "/api/residents")
        by_email = self.call(self.guard, "GET", "/api/residents?search=residente-permisos")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.get_json()["residents"][0]),
            {"id", "name", "phone", "apartment", "apartmentNumber"},
        )
        self.assertEqual(by_email.get_json()["residents"], [])
        admin_view = self.call(self.admin, "GET", "/api/residents").get_json()["residents"][0]
        self.assertIn("email", admin_view)

    def test_resident_cannot_use_staff_routes(self):
        for method, path, body in [
            ("GET", "/api/residents", None),
            ("POST", "/api/packages", {"residentId": self.resident.id, "description": "Caja"}),
            ("GET", "/api/admin/units?apartment=Apto%20101", None),
        ]:
            with self.subTest(method=method, path=path):
                self.assertEqual(self.call(self.resident, method, path, body).status_code, 403)


if __name__ == "__main__":
    unittest.main()
