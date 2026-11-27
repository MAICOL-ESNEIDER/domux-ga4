"""La descarga directa de la app en /descargar (la dirección del QR del póster)."""

import os
import unittest
from unittest import mock

import env_setup  # noqa: F401  (va antes de importar la app)

from app import create_app
from services import app_download

FAKE_APK = b"PK" + b"0" * 1_500_000


class AppDownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.addClassCleanup(env_setup.release_app, cls.app)

    def setUp(self):
        self.client = self.app.test_client()
        if os.path.exists(app_download._cache_path):
            os.remove(app_download._cache_path)

    def test_entrega_la_apk_como_app_android(self):
        with mock.patch.object(app_download, "_download", return_value=FAKE_APK):
            response = self.client.get("/descargar")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/vnd.android.package-archive")
        self.assertIn("domux.apk", response.headers["Content-Disposition"])
        self.assertEqual(int(response.headers["Content-Length"]), len(FAKE_APK))
        response.close()

    def test_si_github_falla_y_no_hay_copia_manda_a_github(self):
        with mock.patch.object(app_download, "_download", side_effect=OSError("sin red")):
            with self.assertLogs("services.app_download", level="ERROR"):
                response = self.client.get("/descargar")
        self.assertEqual(response.status_code, 302)
        self.assertIn("github.com", response.headers["Location"])

    def test_algo_que_no_es_una_apk_no_se_guarda(self):
        with mock.patch.object(app_download, "_download", return_value=b"<html>error</html>"):
            with self.assertLogs("services.app_download", level="ERROR"):
                self.assertIsNone(app_download.cached_apk())


if __name__ == "__main__":
    unittest.main()
