import os
import unittest

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "unit-test-only-secret-with-enough-bytes"

from app import create_app


class SwaggerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.client = cls.app.test_client()

    def test_docs_route_serves_swagger_ui(self):
        with self.client.get("/docs") as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"swagger-ui-bundle.js", response.data)
            self.assertIn(b"/api/openapi.json", response.data)

    def test_openapi_route_serves_specification(self):
        with self.client.get("/api/openapi.json") as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, "application/json")
            self.assertEqual(response.get_json()["openapi"], "3.0.3")


if __name__ == "__main__":
    unittest.main()
