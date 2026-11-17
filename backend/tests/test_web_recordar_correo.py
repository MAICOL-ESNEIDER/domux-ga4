"""«Recordar mi correo en este equipo» en el inicio de sesión de la web (HU-074, SCRUM-183).

El servidor no guarda ninguna lista de cuentas: solo avisa una vez a la página que sigue al
ingreso, y es el navegador el que guarda el correo y el nombre. La contraseña nunca sale.
"""
import re
import unittest

from web_testing import PASSWORD, WebTestCase

MARKER = "data-recordar-cuenta"


class RememberEmailTests(WebTestCase):
    def log_in_remembering(self, email="admin-web@test.local", password=PASSWORD, remember=True):
        data = {"csrf_token": self.token_of("/web/login"), "email": email, "password": password}
        if remember:
            data["recordar"] = "1"
        response = self.client.post("/web/login", data=data)
        self._token = None
        return response

    def test_login_page_offers_the_box_unchecked_and_hidden_until_the_script_shows_it(self):
        body = self.page("/web/login")
        box = re.search(r'<input[^>]*name="recordar"[^>]*>', body)
        self.assertIsNotNone(box, "falta la casilla «Recordar mi correo»")
        self.assertNotIn("checked", box.group(0))
        self.assertIn("Recordar mi correo en este equipo", body)
        self.assertIn("nunca la contraseña", body)
        # Sin JavaScript no se ve: sin él no hay dónde guardar el correo.
        self.assertRegex(body, r'class="remember" data-campo-recordar hidden')
        self.assertRegex(body, r'class="accounts" data-cuentas hidden')

    def test_remembering_marks_only_the_first_page_after_logging_in(self):
        response = self.log_in_remembering()
        self.assertEqual(response.status_code, 302)

        first = self.page("/web/")
        marker = re.search(r'<div hidden data-recordar-cuenta [^>]*></div>', first)
        self.assertIsNotNone(marker, "la primera página no trae la cuenta para guardar")
        self.assertIn('data-correo="admin-web@test.local"', marker.group(0))
        self.assertIn('data-nombre="Lucía Vargas"', marker.group(0))
        self.assertNotIn(PASSWORD, first)

        self.assertNotIn(MARKER, self.page("/web/"), "el aviso se repitió en la página siguiente")

    def test_without_the_box_nothing_is_marked(self):
        self.log_in_remembering(remember=False)
        self.assertNotIn(MARKER, self.page("/web/"))

    def test_any_other_value_of_the_box_is_ignored(self):
        data = {
            "csrf_token": self.token_of("/web/login"), "email": "admin-web@test.local",
            "password": PASSWORD, "recordar": "si",
        }
        self.client.post("/web/login", data=data)
        self.assertNotIn(MARKER, self.page("/web/"))

    def test_a_failed_login_marks_nothing(self):
        failed = self.log_in_remembering(password="otra-clave-cualquiera")
        self.assertEqual(failed.status_code, 401)
        self.assertNotIn(MARKER, self.text(failed))

        self.log_in_remembering(remember=False)
        self.assertNotIn(MARKER, self.page("/web/"))

    def test_residents_and_guards_are_never_marked(self):
        for email in ("residente-web@test.local", "guardia-web@test.local"):
            with self.subTest(email=email):
                denied = self.log_in_remembering(email=email)
                self.assertEqual(denied.status_code, 403)
                self.assertNotIn(MARKER, self.text(denied))
        # La administradora entra después sin la casilla: no hereda nada de esos intentos.
        self.log_in_remembering(remember=False)
        self.assertNotIn(MARKER, self.page("/web/"))

    def test_the_name_is_escaped_in_the_page(self):
        self.admin.name = 'Ana"><script>alert(1)</script>'
        self.admin.last_name = None
        from extensions import db
        db.session.commit()

        self.log_in_remembering()
        first = self.page("/web/")
        self.assertNotIn("<script>alert(1)</script>", first)
        self.assertIn("&lt;script&gt;", first)

    def test_logging_out_keeps_nothing_on_the_server(self):
        self.log_in_remembering()
        self.post("/web/logout")
        login_page = self.page("/web/login")
        self.assertNotIn(MARKER, login_page)
        self.assertNotIn("admin-web@test.local", login_page)


if __name__ == "__main__":
    unittest.main()
