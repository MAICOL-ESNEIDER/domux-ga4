"""La documentación interactiva (/docs): se abre sin sesión, sirve el contrato y la copia del servidor es igual
al contrato oficial de docs/api."""

import unittest
from pathlib import Path

import env_setup  # noqa: F401  (prepara el entorno de pruebas)
from app import create_app
from routes.docs import THIS_SERVER

OFFICIAL = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.yaml"


class ApiDocsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.addClassCleanup(env_setup.release_app, cls.app)
        cls.client = cls.app.test_client()

    def test_the_page_opens_without_a_session_and_loads_the_contract(self):
        response = self.client.get("/docs")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/html")
        body = response.get_data(as_text=True)
        self.assertIn("swagger-ui-bundle.js", body)
        self.assertIn('url: "/docs/openapi.yaml"', body)

    def test_the_contract_is_served_as_yaml(self):
        response = self.client.get("/docs/openapi.yaml")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_data(as_text=True).startswith("openapi: 3.0.3"))

    def test_the_copy_of_the_server_is_the_official_contract(self):
        served = self.client.get("/docs/openapi.yaml").get_data(as_text=True)
        official = OFFICIAL.read_text(encoding="utf-8")
        # Lo único que se agrega al servirlo es «este servidor» al inicio de la lista de servidores.
        self.assertEqual(
            served.replace(THIS_SERVER, "servers:\n", 1), official,
            "Corre «python scripts/sync_openapi.py» para copiar el contrato a backend/openapi.",
        )

    def test_this_server_is_the_first_option_so_try_it_out_uses_the_server_that_serves_the_page(self):
        served = self.client.get("/docs/openapi.yaml").get_data(as_text=True)
        self.assertIn(THIS_SERVER, served)
        self.assertLess(served.index(THIS_SERVER), served.index("http://localhost:5000"))


if __name__ == "__main__":
    unittest.main()
