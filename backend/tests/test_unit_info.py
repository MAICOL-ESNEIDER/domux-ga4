"""Pruebas de los datos de la unidad: nombre, NIT, dirección, teléfono de portería y logo (HU-077)."""

import json
import unittest

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import generate_password_hash

from app import create_app
from auth import generate_token
from extensions import db
from models import AuditLog, ComplexProfile, User
from services import unit_service
from unit_fixtures import JPEG, PNG, WEBP, data_url


def with_check_digit(number):
    """Un NIT bien escrito: el número seguido de su dígito de verificación."""
    return f"{number}-{unit_service.nit_check_digit(number)}"


class UnitInfoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.admin = self.person("ADMIN", "admin-unidad@test.local", "Lucía")
        self.guard = self.person("GUARD", "guardia-unidad@test.local", "Pedro")
        self.resident = self.person("RESIDENT", "residente-unidad@test.local", "Marta")
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def person(self, role, email, name):
        user = User(
            name=name, email=email, role=role, is_active=True,
            password_hash=generate_password_hash("Clave-de-prueba-1*"),
        )
        db.session.add(user)
        db.session.flush()
        return user

    def headers(self, user):
        return {"Authorization": f"Bearer {generate_token(user)}"}

    def read(self, user=None, path="/api/unit-info", **kwargs):
        return self.client.get(path, headers={**self.headers(user or self.resident), **kwargs.pop("headers", {})})

    def save(self, body, user=None):
        return self.client.put("/api/admin/unit-info", json=body, headers=self.headers(user or self.admin))

    def logs(self):
        return AuditLog.query.filter_by(entity_type="complex_profile").order_by(AuditLog.id).all()

    # --- Lectura -------------------------------------------------------------------------------

    def test_before_saving_anything_every_data_comes_empty(self):
        for user in (self.admin, self.guard, self.resident):
            response = self.read(user)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["unit"], unit_service.BLANK_UNIT)

    def test_reading_needs_a_session_but_not_a_particular_role(self):
        self.assertEqual(self.client.get("/api/unit-info").status_code, 401)
        self.assertEqual(self.client.get("/api/unit-info/logo").status_code, 401)

    def test_only_the_administrator_can_change_the_data(self):
        for user in (self.guard, self.resident):
            response = self.save({"name": "Altos de DOMUX"}, user)
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.put("/api/admin/unit-info", json={"name": "X"}).status_code, 401)
        self.assertIsNone(unit_service.get_profile())

    # --- Guardar -------------------------------------------------------------------------------

    def test_the_administrator_saves_everything_and_every_role_sees_it(self):
        nit = with_check_digit("900123456")
        response = self.save({
            "name": "  Altos   de DOMUX ",
            "nit": nit,
            "address": "Calle 10 # 20-30, Medellín",
            "portalPhone": "+57 (604) 234-5678",
            "logo": data_url(PNG),
        })
        self.assertEqual(response.status_code, 200)
        saved = response.get_json()
        self.assertEqual(saved["message"], "Datos de la unidad guardados")
        self.assertEqual(saved["unit"]["name"], "Altos de DOMUX")
        self.assertTrue(saved["unit"]["hasLogo"])
        for user in (self.admin, self.guard, self.resident):
            unit = self.read(user).get_json()["unit"]
            self.assertEqual(unit["name"], "Altos de DOMUX")
            self.assertEqual(unit["nit"], nit)
            self.assertEqual(unit["address"], "Calle 10 # 20-30, Medellín")
            self.assertEqual(unit["portalPhone"], "+57 (604) 234-5678")
            self.assertTrue(unit["hasLogo"])
            self.assertEqual(len(unit["logoVersion"]), 12)
            self.assertRegex(unit["updatedAt"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")

    def test_the_first_time_the_name_is_required(self):
        for body in ({"nit": "900123456"}, {"address": "Calle 1"}, {"portalPhone": "3001234567"}):
            response = self.save(body)
            self.assertEqual(response.status_code, 400, body)
            self.assertIn("nombre de la unidad", response.get_json()["error"])
        self.assertIsNone(unit_service.get_profile())

    def test_a_rejected_first_save_leaves_nothing_half_saved(self):
        response = self.save({"name": "Altos de DOMUX", "nit": "900123456-0"})
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(unit_service.get_profile())
        self.assertEqual(self.logs(), [])
        # Y el siguiente guardado, ya bien hecho, funciona.
        self.assertEqual(self.save({"name": "Altos de DOMUX"}).status_code, 200)

    def test_changing_one_data_keeps_the_others(self):
        self.save({"name": "Altos de DOMUX", "nit": "900123456", "address": "Calle 1", "logo": data_url(PNG)})
        response = self.save({"address": "Carrera 5 # 6-7"})
        self.assertEqual(response.status_code, 200)
        unit = response.get_json()["unit"]
        self.assertEqual(unit["name"], "Altos de DOMUX")
        self.assertEqual(unit["nit"], "900123456")
        self.assertEqual(unit["address"], "Carrera 5 # 6-7")
        self.assertTrue(unit["hasLogo"])

    def test_an_optional_data_sent_as_null_is_erased_but_the_name_cannot_be(self):
        self.save({"name": "Altos de DOMUX", "nit": "900123456", "address": "Calle 1", "portalPhone": "3001234567"})
        unit = self.save({"nit": None, "address": None, "portalPhone": None}).get_json()["unit"]
        self.assertEqual((unit["nit"], unit["address"], unit["portalPhone"]), (None, None, None))
        self.assertEqual(unit["name"], "Altos de DOMUX")
        response = self.save({"name": None})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.read().get_json()["unit"]["name"], "Altos de DOMUX")

    def test_blank_texts_are_rejected_like_in_every_write(self):
        self.assertEqual(self.save({"name": "   "}).status_code, 400)
        self.assertEqual(self.save({"name": "Altos de DOMUX", "address": " "}).status_code, 400)

    def test_an_empty_request_asks_for_at_least_one_data(self):
        response = self.save({})
        self.assertEqual(response.status_code, 400)
        self.assertIn("al menos un dato", response.get_json()["error"])

    def test_saving_the_same_data_again_does_not_fill_the_audit_log(self):
        body = {"name": "Altos de DOMUX", "nit": "900123456", "logo": data_url(PNG)}
        self.save(body)
        self.save(body)
        self.assertEqual(len(self.logs()), 1)

    # --- Reglas de cada dato ----------------------------------------------------------------------

    def test_name_and_address_have_a_maximum_length(self):
        long_name = self.save({"name": "N" * 121})
        self.assertEqual(long_name.status_code, 400)
        self.assertIn("120 caracteres", long_name.get_json()["error"])
        self.save({"name": "N" * 120})
        long_address = self.save({"address": "D" * 201})
        self.assertEqual(long_address.status_code, 400)
        self.assertIn("200 caracteres", long_address.get_json()["error"])
        self.assertEqual(self.save({"address": "D" * 200}).status_code, 200)

    def test_nit_accepts_the_usual_ways_of_writing_it(self):
        for nit in ("900123456", "900.123.456", "900123456-8", "900.123.456-8", " 900 123 456 - 8 "):
            response = self.save({"name": "Altos de DOMUX", "nit": nit})
            self.assertEqual(response.status_code, 200, nit)
        # Se guarda sin espacios.
        self.assertEqual(self.read().get_json()["unit"]["nit"], "900123456-8")

    def test_nit_with_a_wrong_shape_or_a_wrong_check_digit_is_rejected(self):
        self.save({"name": "Altos de DOMUX"})
        for nit in ("ABC", "900.12.3456", "900123456-", "900123456-88", "1234", "1234567890123", "-5"):
            response = self.save({"nit": nit})
            self.assertEqual(response.status_code, 400, nit)
        wrong = self.save({"nit": "900123456-7"})
        self.assertIn("dígito de verificación", wrong.get_json()["error"])
        self.assertIsNone(self.read().get_json()["unit"]["nit"])

    def test_the_check_digit_follows_the_dian_rule(self):
        # El NIT de un banco conocido: 890903938-8.
        self.assertEqual(unit_service.nit_check_digit("890903938"), 8)
        self.assertEqual(unit_service.nit_check_digit("900123456"), 8)
        self.assertEqual(self.save({"name": "Altos de DOMUX", "nit": "890.903.938-8"}).status_code, 200)

    def test_phone_accepts_landlines_and_mobiles_and_rejects_the_rest(self):
        self.save({"name": "Altos de DOMUX"})
        for phone in ("3001234567", "300 123 4567", "604-234-5678", "+57 (604) 234-5678", "2345678"):
            self.assertEqual(self.save({"portalPhone": phone}).status_code, 200, phone)
        for phone in ("123456", "abcdefghij", "300 123 45x7", "1234567890123456", "300+1234567"):
            self.assertEqual(self.save({"portalPhone": phone}).status_code, 400, phone)
        self.assertEqual(self.read().get_json()["unit"]["portalPhone"], "2345678")

    # --- Logo -----------------------------------------------------------------------------------

    def test_the_logo_is_served_as_an_image_with_its_version(self):
        self.save({"name": "Altos de DOMUX", "logo": data_url(PNG)})
        for user in (self.admin, self.guard, self.resident):
            response = self.read(user, "/api/unit-info/logo")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, "image/png")
            self.assertEqual(response.data, PNG)
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(response.headers["Cache-Control"], "private, no-cache")
            self.assertTrue(response.headers["ETag"])

    def test_asking_again_for_an_unchanged_logo_answers_304_without_sending_it(self):
        self.save({"name": "Altos de DOMUX", "logo": data_url(PNG)})
        etag = self.read(path="/api/unit-info/logo").headers["ETag"]
        again = self.read(path="/api/unit-info/logo", headers={"If-None-Match": etag})
        self.assertEqual(again.status_code, 304)
        self.assertEqual(again.data, b"")
        # Con otro logo, el ETag viejo ya no sirve y se envía el nuevo.
        self.save({"logo": data_url(JPEG, "image/jpeg")})
        changed = self.read(path="/api/unit-info/logo", headers={"If-None-Match": etag})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.mimetype, "image/jpeg")

    def test_the_version_changes_only_when_the_logo_changes(self):
        self.save({"name": "Altos de DOMUX", "logo": data_url(PNG)})
        first = self.read().get_json()["unit"]["logoVersion"]
        self.save({"address": "Calle 1"})
        self.assertEqual(self.read().get_json()["unit"]["logoVersion"], first)
        self.save({"logo": data_url(JPEG, "image/jpeg")})
        self.assertNotEqual(self.read().get_json()["unit"]["logoVersion"], first)

    def test_without_a_logo_there_is_nothing_to_serve(self):
        self.assertEqual(self.read(path="/api/unit-info/logo").status_code, 404)
        self.save({"name": "Altos de DOMUX"})
        response = self.read(path="/api/unit-info/logo")
        self.assertEqual(response.status_code, 404)
        self.assertIn("logo", response.get_json()["error"])

    def test_the_logo_can_be_removed_with_null(self):
        self.save({"name": "Altos de DOMUX", "logo": data_url(PNG)})
        unit = self.save({"logo": None}).get_json()["unit"]
        self.assertFalse(unit["hasLogo"])
        self.assertIsNone(unit["logoVersion"])
        self.assertEqual(self.read(path="/api/unit-info/logo").status_code, 404)

    def test_png_jpg_and_webp_are_accepted(self):
        self.save({"name": "Altos de DOMUX"})
        for raw, mime in ((PNG, "image/png"), (JPEG, "image/jpeg"), (WEBP, "image/webp")):
            self.assertEqual(self.save({"logo": data_url(raw, mime)}).status_code, 200, mime)
            self.assertEqual(self.read(path="/api/unit-info/logo").mimetype, mime)

    def test_the_type_comes_from_the_bytes_not_from_what_the_file_declares(self):
        self.save({"name": "Altos de DOMUX"})
        # Un JPG que llega declarado como PNG se guarda y se sirve como lo que es.
        self.assertEqual(self.save({"logo": data_url(JPEG, "image/png")}).status_code, 200)
        self.assertEqual(self.read(path="/api/unit-info/logo").mimetype, "image/jpeg")

    def test_anything_that_is_not_one_of_those_images_is_rejected(self):
        self.save({"name": "Altos de DOMUX"})
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        cases = {
            "un SVG": data_url(svg, "image/svg+xml"),
            "texto disfrazado de PNG": data_url(b"esto no es una imagen", "image/png"),
            "un GIF": data_url(b"GIF89a" + b"\x00" * 20, "image/gif"),
            "sin base64": "data:image/png,hola",
            "base64 dañado": "data:image/png;base64,@@@@",
            "un enlace": "https://ejemplo.test/logo.png",
            "un número": 123,
        }
        for label, value in cases.items():
            response = self.save({"logo": value})
            self.assertEqual(response.status_code, 400, label)
        self.assertFalse(self.read().get_json()["unit"]["hasLogo"])

    def test_a_logo_over_the_limit_is_rejected_with_a_clear_message(self):
        self.save({"name": "Altos de DOMUX"})
        # Pasa el encabezado de PNG, pero pesa más de lo permitido.
        heavy = PNG + b"\x00" * unit_service.MAX_LOGO_BYTES
        huge = b"\x00" * (3 * unit_service.MAX_LOGO_BYTES)
        for raw in (heavy, huge):
            response = self.save({"logo": data_url(raw)})
            self.assertEqual(response.status_code, 400)
            self.assertIn("muy pesado", response.get_json()["error"])
            self.assertIn("512 KB", response.get_json()["error"])
        # Justo en el límite sí entra.
        edge = PNG + b"\x00" * (unit_service.MAX_LOGO_BYTES - len(PNG))
        self.assertEqual(self.save({"logo": data_url(edge)}).status_code, 200)

    # --- Auditoría -----------------------------------------------------------------------------

    def test_every_change_is_written_in_the_audit_log_without_the_image(self):
        self.save({"name": "Altos de DOMUX", "nit": "900123456", "logo": data_url(PNG)})
        self.save({"address": "Calle 1", "logo": data_url(JPEG, "image/jpeg")})
        self.save({"logo": None})
        created, changed, removed = self.logs()
        self.assertEqual((created.action, changed.action, removed.action), ("created", "updated", "updated"))
        self.assertEqual(created.actor_id, self.admin.id)
        first = json.loads(created.details)
        self.assertEqual(first["after"]["name"], "Altos de DOMUX")
        self.assertEqual(first["logo"], "changed")
        second = json.loads(changed.details)
        self.assertEqual(second["before"]["address"], None)
        self.assertEqual(second["after"]["address"], "Calle 1")
        self.assertEqual(json.loads(removed.details)["logo"], "removed")
        for log in self.logs():
            self.assertNotIn("base64", log.details)
            self.assertNotIn("PNG", log.details)

    def test_the_row_remembers_who_changed_it_last(self):
        self.save({"name": "Altos de DOMUX"})
        profile = ComplexProfile.query.one()
        self.assertEqual(profile.updated_by_id, self.admin.id)
        self.assertEqual(profile.id, ComplexProfile.SINGLE_ID)


if __name__ == "__main__":
    unittest.main()
