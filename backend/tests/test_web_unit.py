"""Pruebas de los datos de la unidad en la web de administración (HU-077): el formulario, el logo
y el nombre en el encabezado y en el inicio de sesión."""

import io
import unittest

from models import AuditLog
from services import unit_service
from unit_fixtures import JPEG, PNG
from web_testing import WebTestCase

NIT = "900.123.456-8"


class WebUnitTests(WebTestCase):
    def setUp(self):
        super().setUp()
        self.log_in()

    def send(self, data=None, logo=None, name="logo.png"):
        """Manda el formulario de datos de la unidad, con o sin archivo de logo."""
        if self._token is None:
            self._token = self.token_of("/web/")
        form = {"csrf_token": self._token, **(data or {})}
        if logo is not None:
            form["logo"] = (io.BytesIO(logo), name)
        return self.client.post("/web/unidad", data=form, content_type="multipart/form-data")

    def saved(self):
        return unit_service.get_profile()

    # --- La página ----------------------------------------------------------------------------------

    def test_the_empty_form_explains_what_each_data_is_for(self):
        body = self.page("/web/unidad")
        for text in ("Datos de la unidad", "Nombre de la unidad", "NIT", "Dirección", "Teléfono de portería",
                     "Todavía no hay un logo", "Subir un logo", "Guardar los datos", "multipart/form-data"):
            self.assertIn(text, body)
        self.assertNotIn("Quitar el logo actual", body)
        self.assertNotIn("Última actualización", body)

    def test_the_menu_links_to_the_page_and_marks_it_as_the_current_one(self):
        body = self.page("/web/unidad")
        self.assertIn('href="/web/unidad" aria-current="page"', body)
        self.assertIn("Datos de la unidad", self.page("/web/"))

    def test_without_a_session_the_page_sends_to_the_login(self):
        anonymous = self.app.test_client()
        response = anonymous.get("/web/unidad")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/web/login", response.headers["Location"])

    # --- Guardar --------------------------------------------------------------------------------------

    def test_saving_the_data_shows_them_again_and_tells_that_it_worked(self):
        response = self.send({
            "name": "Altos de DOMUX", "nit": NIT, "address": "Calle 10 # 20-30", "portalPhone": "604 234 5678",
        })
        self.assertEqual(response.status_code, 302)
        body = self.page("/web/unidad")
        self.assertIn("Datos de la unidad guardados.", body)
        for value in ("Altos de DOMUX", NIT, "Calle 10 # 20-30", "604 234 5678"):
            self.assertIn(f'value="{value}"', body)
        self.assertIn("Última actualización", body)
        profile = self.saved()
        self.assertEqual((profile.name, profile.nit), ("Altos de DOMUX", NIT))
        log = AuditLog.query.filter_by(entity_type="complex_profile").one()
        self.assertEqual((log.action, log.actor_id), ("created", self.admin.id))

    def test_a_blank_optional_field_erases_that_data(self):
        self.send({"name": "Altos de DOMUX", "nit": NIT, "address": "Calle 1", "portalPhone": "3001234567"})
        self.send({"name": "Altos de DOMUX", "nit": "", "address": "", "portalPhone": ""})
        profile = self.saved()
        self.assertEqual(profile.name, "Altos de DOMUX")
        self.assertEqual((profile.nit, profile.address, profile.portal_phone), (None, None, None))

    def test_the_name_cannot_be_left_blank(self):
        response = self.send({"name": "  ", "nit": NIT})
        self.assertEqual(response.status_code, 400)
        self.assertIn("El nombre de la unidad es obligatorio.", self.text(response))
        self.assertIsNone(self.saved())

    def test_a_rejected_form_keeps_what_was_written_and_shows_the_reason(self):
        response = self.send({"name": "Altos de DOMUX", "nit": "900123456-0", "address": "Calle 1"})
        self.assertEqual(response.status_code, 400)
        body = self.text(response)
        self.assertIn("El dígito de verificación del NIT no coincide", body)
        for value in ("Altos de DOMUX", "900123456-0", "Calle 1"):
            self.assertIn(f'value="{value}"', body)
        self.assertIsNone(self.saved())

    def test_a_form_without_the_csrf_code_is_refused(self):
        response = self.client.post("/web/unidad", data={"name": "Altos de DOMUX"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("El formulario venció", self.text(response))
        self.assertIsNone(self.saved())

    # --- Logo -----------------------------------------------------------------------------------------

    def test_uploading_a_logo_saves_it_and_shows_a_preview(self):
        self.send({"name": "Altos de DOMUX"}, logo=PNG)
        profile = self.saved()
        self.assertTrue(profile.has_logo)
        body = self.page("/web/unidad")
        self.assertIn("Logo actual de la unidad", body)
        self.assertIn(f"/web/unidad/logo?v={profile.logo_version}", body)
        self.assertIn("Quitar el logo actual", body)
        self.assertIn("Cambiar el logo", body)

    def test_saving_again_without_choosing_a_file_keeps_the_logo(self):
        self.send({"name": "Altos de DOMUX"}, logo=PNG)
        version = self.saved().logo_version
        self.send({"name": "Altos de DOMUX", "address": "Calle 1"})
        self.assertEqual(self.saved().logo_version, version)
        # Un archivo vacío (el navegador lo manda así cuando no se eligió ninguno) tampoco lo toca.
        self.send({"name": "Altos de DOMUX"}, logo=b"", name="")
        self.assertEqual(self.saved().logo_version, version)

    def test_a_new_file_replaces_the_logo_and_the_checkbox_removes_it(self):
        self.send({"name": "Altos de DOMUX"}, logo=PNG)
        first = self.saved().logo_version
        self.send({"name": "Altos de DOMUX"}, logo=JPEG, name="logo.jpg")
        self.assertNotEqual(self.saved().logo_version, first)
        self.assertEqual(self.saved().logo_type, "image/jpeg")
        self.send({"name": "Altos de DOMUX", "removeLogo": "1"})
        self.assertFalse(self.saved().has_logo)
        self.assertIn("Todavía no hay un logo", self.page("/web/unidad"))

    def test_a_file_that_is_not_an_allowed_image_is_rejected(self):
        for label, raw, name in (
            ("un SVG", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "logo.svg"),
            ("un texto con nombre de imagen", b"esto no es una imagen", "logo.png"),
        ):
            response = self.send({"name": "Altos de DOMUX", "address": "Calle 1"}, logo=raw, name=name)
            self.assertEqual(response.status_code, 400, label)
            body = self.text(response)
            self.assertIn("El logo debe ser una imagen PNG, JPG o WebP", body, label)
            # Lo escrito se conserva, y se avisa que el archivo hay que elegirlo de nuevo.
            self.assertIn('value="Calle 1"', body, label)
            self.assertIn("Vuelve a elegir el logo", body, label)
        self.assertIsNone(self.saved())

    def test_a_heavy_file_is_rejected_with_the_limit(self):
        heavy = PNG + b"\x00" * unit_service.MAX_LOGO_BYTES
        response = self.send({"name": "Altos de DOMUX"}, logo=heavy)
        self.assertEqual(response.status_code, 400)
        self.assertIn("El logo es muy pesado: el máximo es 512 KB", self.text(response))
        self.assertIsNone(self.saved())

    def test_the_logo_is_public_but_revalidated_and_not_stored_as_a_page(self):
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.get("/web/unidad/logo").status_code, 404)
        self.send({"name": "Altos de DOMUX"}, logo=PNG)
        response = anonymous.get("/web/unidad/logo")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        self.assertEqual(response.data, PNG)
        self.assertEqual(response.headers["Cache-Control"], "private, no-cache")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("img-src 'self' data:", response.headers["Content-Security-Policy"])
        again = anonymous.get("/web/unidad/logo", headers={"If-None-Match": response.headers["ETag"]})
        self.assertEqual(again.status_code, 304)

    # --- Nombre y logo en todas las páginas ---------------------------------------------------------

    def test_without_data_the_header_is_the_one_of_domux(self):
        body = self.page("/web/")
        self.assertIn("<strong>DOMUX</strong><small>Administración</small>", body)
        self.assertIn("img/domux-logo.svg", body)
        self.assertNotIn("/web/unidad/logo", body)

    def test_with_data_the_menu_and_the_login_show_the_name_and_the_logo(self):
        self.send({"name": "Altos de DOMUX", "address": "Calle 10"}, logo=PNG)
        version = self.saved().logo_version
        for path in ("/web/", "/web/usuarios", "/web/unidad"):
            body = self.page(path)
            self.assertIn('<strong class="unit-name">Altos de DOMUX</strong><small>DOMUX · Administración</small>', body, path)
            self.assertIn(f"/web/unidad/logo?v={version}", body, path)
        # La pantalla de inicio de sesión (sin sesión) muestra solo el nombre y el logo.
        login = self.app.test_client().get("/web/login").get_data(as_text=True)
        self.assertIn('<strong class="unit-name">Altos de DOMUX</strong>', login)
        self.assertIn(f"/web/unidad/logo?v={version}", login)
        self.assertNotIn("Calle 10", login)

    def test_the_name_written_by_a_person_is_escaped_in_the_header(self):
        self.send({"name": "<script>alert(1)</script>"})
        for body in (self.page("/web/"), self.app.test_client().get("/web/login").get_data(as_text=True)):
            self.assertNotIn("<script>alert(1)</script>", body)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)

    def test_the_error_pages_also_show_the_name(self):
        self.send({"name": "Altos de DOMUX"})
        body = self.text(self.client.get("/web/no-existe"))
        self.assertIn('<strong class="unit-name">Altos de DOMUX</strong>', body)


if __name__ == "__main__":
    unittest.main()
