"""Pruebas de los mensajes de error y de los registros (DEF-012, SEC-012 y DT-011).

Los errores que responde Flask por su cuenta salen en español, y el token del QR
nunca queda escrito en los registros del servidor.
"""

import unittest

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import generate_password_hash

from app import create_app
from auth import generate_token
from extensions import db
from models import User


class ErrorMessageTests(unittest.TestCase):
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
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def test_flask_errors_answer_in_spanish(self):
        cases = [
            (self.client.get("/api/ruta-que-no-existe"), 404, "Recurso no encontrado"),
            (self.client.delete("/api/health"), 405, "Método no permitido para esta ruta"),
            (
                self.client.post(
                    "/api/auth/login", data=b"x" * (13 * 1024 * 1024),
                    content_type="application/json",
                ),
                413,
                "La solicitud supera el tamaño máximo permitido (12 MB)",
            ),
        ]
        for response, status, message in cases:
            with self.subTest(status=status):
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.get_json(), {"error": message, "status": status})

    def test_qr_token_is_hidden_in_the_request_log(self):
        guard = User(
            name="Guardia", email="guardia-registros@test.local", role="GUARD", is_active=True,
            password_hash=generate_password_hash("Clave-de-prueba-1*"),
        )
        db.session.add(guard)
        db.session.commit()

        with self.assertLogs(level="INFO") as logs:
            self.client.get(
                "/api/visits/qr/token-secreto-del-qr",
                headers={"Authorization": f"Bearer {generate_token(guard)}"},
            )

        written = "\n".join(logs.output)
        self.assertNotIn("token-secreto-del-qr", written)
        self.assertIn("/api/visits/qr/***", written)


if __name__ == "__main__":
    unittest.main()
