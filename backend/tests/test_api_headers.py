"""La API manda cabeceras de seguridad: nada de sus respuestas se guarda en cachés y el navegador no adivina tipos."""

import unittest

import env_setup  # noqa: F401  (va antes de importar la app)

from app import create_app


class ApiHeadersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.addClassCleanup(env_setup.release_app, cls.app)
        cls.client = cls.app.test_client()

    def test_las_respuestas_de_la_api_no_se_guardan_ni_se_adivinan(self):
        for path in ("/api/legal", "/api/auth/me"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
                self.assertEqual(response.headers.get("Cache-Control"), "no-store")

    def test_la_web_conserva_sus_cabeceras(self):
        response = self.client.get("/web/login")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertIn("Content-Security-Policy", response.headers)


if __name__ == "__main__":
    unittest.main()
