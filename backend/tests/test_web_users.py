"""Pruebas de los usuarios en la web de administración (HU-075): lista con filtros, crear, editar,
desactivar, restablecer la contraseña y asignar el PIN de un guardia."""

import unittest

from werkzeug.security import check_password_hash

from extensions import db
from models import AuditLog, User
from structure_fixtures import apartment_for
from web_testing import PASSWORD, WebTestCase

NEW_PASSWORD = "Nueva-clave-2*"
WEAK_PASSWORD = "corta"


class WebUsersTests(WebTestCase):
    def setUp(self):
        super().setUp()
        self.apartment_202 = apartment_for("Torre 2 · Apto 202")
        self.other = self.make_user(
            "RESIDENT", "carlos-web@test.local", "Carlos", last_name="Pérez",
            apartment_ref=self.apartment_202, phone="3111111111", occupancy_type="arrendatario",
        )
        self.inactive = self.make_user("GUARD", "inactivo-web@test.local", "Inés", last_name="Inactiva")
        self.inactive.is_active = False
        db.session.commit()
        self.log_in()

    def new_resident_form(self, **changes):
        form = {
            "role": "RESIDENT", "name": "Laura", "lastName": "Gómez", "email": "laura-web@test.local",
            "phone": "3222222222", "password": NEW_PASSWORD, "apartmentId": str(self.apartment_202.id),
            "occupancyType": "propietario", "dataProcessingConsent": "1",
        }
        form.update(changes)
        return {key: value for key, value in form.items() if value is not None}

    # --- La lista -----------------------------------------------------------------------------------

    def test_the_list_shows_everyone_with_role_apartment_and_state(self):
        body = self.page("/web/usuarios")
        for text in ("Marta Ríos", "Carlos Pérez", "Lucía Vargas", "Inés Inactiva", "Torre 1 · Apto 101", "Torre 2 · Apto 202"):
            self.assertIn(text, body)
        self.assertIn("Portería", body)
        self.assertIn("Inactivo", body)
        self.assertIn("5 usuarios", body)
        self.assertIn("Crear usuario", body)

    def test_search_and_role_and_state_filters(self):
        by_name = self.page("/web/usuarios?q=Carlos")
        self.assertIn("Carlos Pérez", by_name)
        self.assertNotIn("Marta Ríos", by_name)
        self.assertIn("1 usuario con esos filtros", by_name)

        guards = self.page("/web/usuarios?rol=GUARD")
        self.assertIn("Inés Inactiva", guards)
        self.assertNotIn("Marta Ríos", guards)

        inactive = self.page("/web/usuarios?estado=inactivos")
        self.assertIn("Inés Inactiva", inactive)
        self.assertNotIn("Carlos Pérez", inactive)

        nothing = self.page("/web/usuarios?q=zzzz")
        self.assertIn("No hay usuarios con esos filtros", nothing)
        self.assertIn("Quitar filtros", nothing)

    def test_an_unknown_role_or_state_is_ignored(self):
        body = self.page("/web/usuarios?rol=DIOS&estado=raro")
        self.assertIn("5 usuarios", body)

    def test_names_written_by_people_are_escaped(self):
        self.other.name = "<script>alert(1)</script>"
        db.session.commit()
        body = self.page("/web/usuarios")
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)

    def test_a_page_past_the_end_goes_to_the_last_one(self):
        response = self.client.get("/web/usuarios?page=99")
        self.assertEqual(response.status_code, 302)
        self.assertIn("page=1", response.headers["Location"])

    # --- Crear --------------------------------------------------------------------------------------

    def test_the_new_user_form_lists_the_apartments_and_asks_for_the_consent(self):
        body = self.page("/web/usuarios/nuevo")
        self.assertIn("Contraseña temporal", body)
        self.assertIn("Torre 1 · Apto 101", body)
        self.assertIn("Torre 2 · Apto 202", body)
        self.assertIn("autorizó el tratamiento de sus datos", body)
        self.assertNotIn('name="pin"', body)

    def test_creating_a_resident_saves_it_and_opens_its_page(self):
        response = self.post("/web/usuarios/nuevo", self.new_resident_form())
        self.assertEqual(response.status_code, 302)
        created = User.query.filter_by(email="laura-web@test.local").one()
        self.assertTrue(response.headers["Location"].endswith(f"/web/usuarios/{created.id}"))
        self.assertEqual(created.role, "RESIDENT")
        self.assertEqual(created.apartment_id, self.apartment_202.id)
        self.assertEqual(created.occupancy_type, "propietario")
        self.assertTrue(created.data_processing_consent)
        self.assertTrue(check_password_hash(created.password_hash, NEW_PASSWORD))
        self.assertIn("Usuario creado.", self.page(f"/web/usuarios/{created.id}"))

    def test_creating_a_guard_needs_no_apartment_and_offers_the_pin(self):
        form = self.new_resident_form(
            role="GUARD", email="portero-web@test.local", name="Pedro", apartmentId=None,
            occupancyType=None, dataProcessingConsent=None,
        )
        response = self.post("/web/usuarios/nuevo", form)
        self.assertEqual(response.status_code, 302)
        guard = User.query.filter_by(email="portero-web@test.local").one()
        self.assertEqual(guard.role, "GUARD")
        self.assertIsNone(guard.apartment_id)
        page = self.page(f"/web/usuarios/{guard.id}")
        self.assertIn("PIN de turno", page)
        self.assertIn("todavía no tiene PIN", page)

    def test_a_rejected_form_keeps_what_was_typed_and_shows_the_servers_message(self):
        response = self.post("/web/usuarios/nuevo", self.new_resident_form(password=WEAK_PASSWORD))
        body = self.text(response)
        self.assertEqual(response.status_code, 400)
        self.assertIn("La contraseña debe tener mínimo 8 caracteres", body)
        self.assertIn('value="Laura"', body)
        self.assertIn('value="laura-web@test.local"', body)
        self.assertNotIn(WEAK_PASSWORD, body)           # la contraseña nunca vuelve a la página
        self.assertIsNone(User.query.filter_by(email="laura-web@test.local").first())

    def test_the_phone_is_saved_with_only_its_ten_digits(self):
        self.assertIn("10 números: un celular empieza por 3", self.page("/web/usuarios/nuevo"))
        response = self.post("/web/usuarios/nuevo", self.new_resident_form(phone="+57 322 333 4444"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.query.filter_by(email="laura-web@test.local").one().phone, "3223334444")

    def test_a_wrong_phone_is_refused_with_the_servers_message(self):
        response = self.post("/web/usuarios/nuevo", self.new_resident_form(phone="322 333"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("El teléfono debe tener 10 números", self.text(response))
        self.assertIn('value="322 333"', self.text(response))
        self.assertIsNone(User.query.filter_by(email="laura-web@test.local").first())

    def test_a_repeated_email_is_refused(self):
        response = self.post("/web/usuarios/nuevo", self.new_resident_form(email="CARLOS-web@test.local"))
        self.assertEqual(response.status_code, 409)
        self.assertIn("Ese correo ya está registrado", self.text(response))

    def test_a_resident_needs_an_apartment_and_the_data_consent(self):
        no_apartment = self.post("/web/usuarios/nuevo", self.new_resident_form(apartmentId=None))
        self.assertIn("El residente necesita un apartamento", self.text(no_apartment))
        no_consent = self.post("/web/usuarios/nuevo", self.new_resident_form(dataProcessingConsent=None))
        self.assertIn("Debes registrar la autorización de tratamiento de datos", self.text(no_consent))
        self.assertIsNone(User.query.filter_by(email="laura-web@test.local").first())

    def test_a_missing_name_is_refused_by_the_server(self):
        response = self.post("/web/usuarios/nuevo", self.new_resident_form(name=""))
        self.assertEqual(response.status_code, 400)
        self.assertIn("nombre", self.text(response).lower())

    # --- Editar -------------------------------------------------------------------------------------

    def test_the_edit_page_shows_the_current_data(self):
        body = self.page(f"/web/usuarios/{self.other.id}")
        self.assertIn('value="Carlos"', body)
        self.assertIn('value="Pérez"', body)
        self.assertIn('value="3111111111"', body)
        self.assertIn("Estado de la cuenta", body)
        self.assertIn("Restablecer la contraseña", body)
        self.assertNotIn("PIN de turno", body)          # solo los guardias tienen PIN

    def test_editing_saves_the_changes(self):
        form = {
            "role": "RESIDENT", "name": "Carlos", "lastName": "Pérez Ruiz", "email": "carlos-web@test.local",
            "phone": "3999999999", "apartmentId": str(self.apartment_202.id), "occupancyType": "propietario",
        }
        response = self.post(f"/web/usuarios/{self.other.id}", form)
        self.assertEqual(response.status_code, 302)
        saved = db.session.get(User, self.other.id)
        db.session.refresh(saved)
        self.assertEqual(saved.last_name, "Pérez Ruiz")
        self.assertEqual(saved.phone, "3999999999")
        self.assertEqual(saved.occupancy_type, "propietario")
        self.assertIn("Cambios guardados.", self.page(f"/web/usuarios/{self.other.id}"))

    def test_moving_a_resident_to_another_apartment(self):
        form = {
            "role": "RESIDENT", "name": "Marta", "email": "residente-web@test.local",
            "apartmentId": str(self.apartment_202.id), "occupancyType": "propietario",
        }
        self.post(f"/web/usuarios/{self.resident.id}", form)
        moved = db.session.get(User, self.resident.id)
        db.session.refresh(moved)
        self.assertEqual(moved.apartment_id, self.apartment_202.id)

    def test_editing_with_a_repeated_email_shows_the_message_and_keeps_the_form(self):
        form = {"role": "RESIDENT", "name": "Carlos", "email": "residente-web@test.local",
                "apartmentId": str(self.apartment_202.id), "occupancyType": "arrendatario"}
        response = self.post(f"/web/usuarios/{self.other.id}", form)
        self.assertEqual(response.status_code, 409)
        self.assertIn("Ese correo ya está registrado", self.text(response))
        self.assertEqual(db.session.get(User, self.other.id).email, "carlos-web@test.local")

    def test_turning_a_guard_into_a_resident_asks_for_the_consent(self):
        guard_page = self.page(f"/web/usuarios/{self.guard.id}")
        self.assertIn("autorizó el tratamiento de sus datos", guard_page)
        form = {"role": "RESIDENT", "name": "Guardia", "email": "guardia-web@test.local",
                "apartmentId": str(self.apartment_202.id), "occupancyType": "residente"}
        refused = self.post(f"/web/usuarios/{self.guard.id}", form)
        self.assertIn("Debes registrar la autorización", self.text(refused))
        self.post(f"/web/usuarios/{self.guard.id}", {**form, "dataProcessingConsent": "1"})
        changed = db.session.get(User, self.guard.id)
        db.session.refresh(changed)
        self.assertEqual(changed.role, "RESIDENT")

    def test_an_unknown_user_gives_the_not_found_page(self):
        self.assertEqual(self.client.get("/web/usuarios/9999").status_code, 404)

    # --- Desactivar y reactivar ---------------------------------------------------------------------

    def test_deactivating_closes_the_account_and_keeps_the_history(self):
        page = self.page(f"/web/usuarios/{self.other.id}")
        self.assertIn("Desactivar cuenta", page)
        self.assertIn("data-confirm=", page)             # pide confirmación antes de desactivar

        response = self.post(f"/web/usuarios/{self.other.id}/estado", {"activo": "0"})
        self.assertEqual(response.status_code, 302)
        saved = db.session.get(User, self.other.id)
        db.session.refresh(saved)
        self.assertFalse(saved.is_active)
        self.assertIn("Usuario desactivado", self.page(f"/web/usuarios/{self.other.id}"))
        self.assertIn("Reactivar cuenta", self.page(f"/web/usuarios/{self.other.id}"))
        self.assertTrue(AuditLog.query.filter_by(entity_type="user", entity_id=self.other.id, action="deactivated").count())

    def test_a_deactivated_account_can_be_reactivated(self):
        self.post(f"/web/usuarios/{self.inactive.id}/estado", {"activo": "1"})
        saved = db.session.get(User, self.inactive.id)
        db.session.refresh(saved)
        self.assertTrue(saved.is_active)
        self.assertIn("Usuario reactivado", self.page(f"/web/usuarios/{self.inactive.id}"))

    def test_the_administrator_cannot_deactivate_their_own_account_from_the_web(self):
        self.post(f"/web/usuarios/{self.admin.id}/estado", {"activo": "0"})
        self.assertTrue(db.session.get(User, self.admin.id).is_active)
        self.assertIn("No puedes desactivar tu propia cuenta", self.page(f"/web/usuarios/{self.admin.id}"))

    def test_an_unknown_user_in_a_state_change_is_refused_politely(self):
        self.post("/web/usuarios/9999/estado", {"activo": "0"})
        self.assertIn("Usuario no encontrado", self.page("/web/usuarios/%d" % self.other.id))

    # --- Contraseña ---------------------------------------------------------------------------------

    def test_resetting_a_password_lets_the_person_log_in_with_the_new_one(self):
        response = self.post(
            f"/web/usuarios/{self.other.id}/clave", {"password": NEW_PASSWORD, "password2": NEW_PASSWORD}, follow=True,
        )
        body = self.text(response)
        self.assertIn("Contraseña restablecida", body)
        self.assertNotIn(NEW_PASSWORD, body)
        saved = db.session.get(User, self.other.id)
        db.session.refresh(saved)
        self.assertTrue(check_password_hash(saved.password_hash, NEW_PASSWORD))
        self.assertFalse(check_password_hash(saved.password_hash, PASSWORD))

    def test_two_different_passwords_change_nothing(self):
        response = self.post(
            f"/web/usuarios/{self.other.id}/clave", {"password": NEW_PASSWORD, "password2": "Otra-clave-3*"}, follow=True,
        )
        self.assertIn("Las dos contraseñas no coinciden", self.text(response))
        saved = db.session.get(User, self.other.id)
        self.assertTrue(check_password_hash(saved.password_hash, PASSWORD))

    def test_a_weak_password_is_refused_with_the_servers_message(self):
        response = self.post(
            f"/web/usuarios/{self.other.id}/clave", {"password": WEAK_PASSWORD, "password2": WEAK_PASSWORD}, follow=True,
        )
        body = self.text(response)
        self.assertIn("La contraseña debe tener mínimo 8 caracteres", body)
        self.assertNotIn(WEAK_PASSWORD, body)
        self.assertTrue(check_password_hash(db.session.get(User, self.other.id).password_hash, PASSWORD))

    # --- PIN del guardia ----------------------------------------------------------------------------

    def test_assigning_a_pin_to_a_guard(self):
        response = self.post(f"/web/usuarios/{self.guard.id}/pin", {"pin": "4821"}, follow=True)
        body = self.text(response)
        self.assertIn("PIN asignado", body)
        self.assertNotIn("4821", body)
        guard = db.session.get(User, self.guard.id)
        db.session.refresh(guard)
        self.assertTrue(check_password_hash(guard.pin_hash, "4821"))
        self.assertIn("Este guardia ya tiene PIN", self.page(f"/web/usuarios/{self.guard.id}"))

    def test_a_pin_must_be_four_digits_and_only_for_guards(self):
        short = self.post(f"/web/usuarios/{self.guard.id}/pin", {"pin": "123"}, follow=True)
        self.assertIn("exactamente 4 dígitos", self.text(short))
        resident = self.post(f"/web/usuarios/{self.resident.id}/pin", {"pin": "1234"}, follow=True)
        self.assertIn("Solo los guardias tienen PIN", self.text(resident))
        self.assertIsNone(db.session.get(User, self.guard.id).pin_hash)

    # --- Seguridad ----------------------------------------------------------------------------------

    def test_every_user_page_needs_a_session(self):
        anonymous = self.app.test_client()
        for path in ("/web/usuarios", "/web/usuarios/nuevo", f"/web/usuarios/{self.other.id}"):
            self.assertEqual(anonymous.get(path).status_code, 302, path)

    def test_every_change_needs_the_csrf_code(self):
        for path, form in (
            ("/web/usuarios/nuevo", self.new_resident_form()),
            (f"/web/usuarios/{self.other.id}", {"role": "RESIDENT", "name": "X"}),
            (f"/web/usuarios/{self.other.id}/estado", {"activo": "0"}),
            (f"/web/usuarios/{self.other.id}/clave", {"password": NEW_PASSWORD, "password2": NEW_PASSWORD}),
            (f"/web/usuarios/{self.guard.id}/pin", {"pin": "4821"}),
        ):
            self.assertEqual(self.client.post(path, data=form).status_code, 400, path)
        self.assertTrue(db.session.get(User, self.other.id).is_active)
        self.assertIsNone(User.query.filter_by(email="laura-web@test.local").first())


if __name__ == "__main__":
    unittest.main()
