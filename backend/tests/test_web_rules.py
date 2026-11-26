"""Pruebas de las reglas de la unidad en la web de administración (DEC-032): la página, guardar solo lo que
cambió, los mensajes de la API y volver a los valores de DOMUX."""

import re
import unittest
from datetime import timedelta

from extensions import db
from models import AuditLog, PackageItem, Pqrs, UnitSettings
from services.unit_rules import current_rules
from time_utils import colombia_day_to_utc, colombia_today, utc_now
from web_testing import WebTestCase

#: Lo que manda el formulario sin tocar nada (los valores de DOMUX).
UNTOUCHED = {
    "pqrsTermDays": "15", "pqrsWarningDays": "5", "packageOrangeHours": "48", "packageRedHours": "72",
    "visitorParkingMaxDays": "3", "visitMaxStayDays": "30", "qrMaxPeople": "5", "qrMaxValidDays": "30",
    "autoQrMinStayDays": "2", "deliveredArchiveDays": "7", "motosPerCarSpot": "6", "term_0": "", "term_1": "", "term_2": "", "term_3": "", "term_4": "",
}


class WebRulesTests(WebTestCase):
    def setUp(self):
        super().setUp()
        self.log_in()

    def send(self, **changes):
        """Manda el formulario con los valores de DOMUX y los cambios indicados."""
        return self.post("/web/reglas", {**UNTOUCHED, **changes})

    def settings(self):
        return db.session.get(UnitSettings, UnitSettings.SINGLE_ID)

    def logs(self):
        return AuditLog.query.filter_by(entity_type="unit_settings").all()

    def flashes(self, response):
        """Los avisos que dejó la respuesta, leídos en la página siguiente."""
        return self.text(self.client.get(response.headers["Location"]))

    # --- La página ----------------------------------------------------------------------------------

    def test_the_page_explains_every_rule_and_shows_the_values_of_domux(self):
        body = self.page("/web/reglas")

        for text in (
            "Reglas de la unidad", "Plazo general para responder (días hábiles)",
            "El semáforo pasa a amarillo cuando faltan", "Plazo propio de cada tipo (opcional)",
            "Petición (días hábiles)", "Queja (días hábiles)", "Reclamo (días hábiles)",
            "Sugerencia (días hábiles)", "Daño (días hábiles)",
            "Aviso naranja a las (horas)", "Aviso rojo a las (horas)", "Días máximos de un vehículo visitante",
            "Valor de DOMUX: 15 días hábiles", "Valor de DOMUX: 48 horas", "Valor de DOMUX: 72 horas",
            "Valor de DOMUX: 3 días", "Guardar las reglas", "Volver a los valores de DOMUX",
        ):
            self.assertIn(text, body)
        for name, value in (("pqrsTermDays", "15"), ("pqrsWarningDays", "5"), ("packageOrangeHours", "48"),
                            ("packageRedHours", "72"), ("visitorParkingMaxDays", "3")):
            self.assertRegex(body, rf'name="{name}" type="number" value="{value}"')
        self.assertNotIn("Esta regla ya la cambiaste", body)
        self.assertNotIn("Última actualización", body)

    def test_the_inputs_carry_the_limits_so_the_browser_helps_too(self):
        body = self.page("/web/reglas")

        self.assertIn('min="1"', body)
        self.assertIn('max="90"', body)
        self.assertIn('max="720"', body)
        self.assertIn('max="1440"', body)
        self.assertIn('max="30"', body)

    def test_the_menu_links_to_the_page_and_marks_it_as_the_current_one(self):
        self.assertIn('href="/web/reglas" aria-current="page"', self.page("/web/reglas"))
        self.assertIn("Reglas de la unidad", self.page("/web/"))

    def test_without_a_session_the_page_sends_to_the_login(self):
        response = self.app.test_client().get("/web/reglas")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/web/login", response.headers["Location"])

    def test_a_guard_or_a_resident_cannot_open_the_page(self):
        for email in ("guardia-web@test.local", "residente-web@test.local"):
            client = self.app.test_client()
            token = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/web/login").get_data(as_text=True))
            client.post("/web/login", data={"csrf_token": token.group(1), "email": email, "password": "Clave-de-prueba-1*"})
            self.assertNotEqual(client.get("/web/reglas").status_code, 200, email)

    # --- Guardar --------------------------------------------------------------------------------------

    def test_saving_a_change_shows_it_again_and_tells_that_it_worked(self):
        response = self.send(pqrsTermDays="20", packageRedHours="96")

        self.assertEqual(response.status_code, 302)
        self.assertIn("Reglas de la unidad guardadas", self.flashes(response))
        body = self.page("/web/reglas")
        self.assertRegex(body, r'name="pqrsTermDays" type="number" value="20"')
        self.assertRegex(body, r'name="packageRedHours" type="number" value="96"')
        self.assertIn("Esta regla ya la cambiaste", body)
        self.assertIn("Última actualización", body)
        self.assertIn("por Lucía", body)
        self.assertEqual(current_rules().pqrs_term_days, 20)

    def test_only_what_changed_is_saved_so_the_rest_keeps_following_domux(self):
        self.send(pqrsTermDays="20")

        row = self.settings()
        self.assertEqual(row.pqrs_term_days, 20)
        self.assertIsNone(row.pqrs_warning_days)
        self.assertIsNone(row.package_orange_hours)
        self.assertIsNone(row.package_red_hours)
        self.assertIsNone(row.visitor_parking_max_days)
        self.assertIsNone(row.pqrs_terms_by_category)

    def test_sending_the_form_without_changes_says_so_and_saves_nothing(self):
        response = self.send()

        self.assertEqual(response.status_code, 200)
        self.assertIn("No cambiaste ninguna regla", self.text(response))
        self.assertIsNone(self.settings())
        self.assertEqual(self.logs(), [])

    def test_a_term_of_one_type_is_saved_and_shown_in_its_own_box(self):
        self.send(term_4="5", term_1="10")

        body = self.page("/web/reglas")
        self.assertRegex(body, r'name="term_4" type="number" value="5"')
        self.assertRegex(body, r'name="term_1" type="number" value="10"')
        self.assertRegex(body, r'name="term_0" type="number" value=""')
        self.assertIn("Ya hay plazos propios guardados", body)
        self.assertEqual(current_rules().pqrs_terms_by_category, {"Queja": 10, "Daño": 5})

    def test_emptying_the_box_of_a_type_removes_its_own_term(self):
        self.send(term_4="5")

        self.send(term_4="")

        self.assertEqual(current_rules().pqrs_terms_by_category, {})
        self.assertNotIn("Ya hay plazos propios guardados", self.page("/web/reglas"))

    def test_emptying_a_box_brings_that_rule_back_to_the_value_of_domux(self):
        self.send(pqrsTermDays="20")

        self.send(pqrsTermDays="")

        self.assertEqual(current_rules().pqrs_term_days, 15)
        self.assertIsNone(self.settings().pqrs_term_days)
        self.assertNotIn("Esta regla ya la cambiaste", self.page("/web/reglas"))

    def test_a_refused_value_shows_the_message_of_the_api_and_keeps_what_was_typed(self):
        response = self.send(pqrsTermDays="500")

        self.assertEqual(response.status_code, 400)
        body = self.text(response)
        self.assertIn("El plazo para responder una PQRS debe estar entre 1 y 90 días hábiles.", body)
        self.assertRegex(body, r'name="pqrsTermDays" type="number" value="500"')
        self.assertIsNone(self.settings())

    def test_text_that_is_not_a_number_is_refused_with_a_clear_message(self):
        response = self.send(packageOrangeHours="muchas")

        self.assertEqual(response.status_code, 400)
        self.assertIn("El aviso naranja de un paquete sin reclamar debe ser un número entero de horas", self.text(response))

    def test_rules_that_do_not_make_sense_together_are_explained(self):
        response = self.send(packageOrangeHours="100")

        self.assertEqual(response.status_code, 400)
        self.assertIn("debe llegar después del naranja", self.text(response))

        response = self.send(pqrsTermDays="3")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Baja los días del aviso amarillo (máximo 3)", self.text(response))
        self.assertIsNone(self.settings())

    def test_a_change_without_the_security_code_is_refused(self):
        response = self.client.post("/web/reglas", data={**UNTOUCHED, "pqrsTermDays": "20"})

        self.assertIn(response.status_code, (400, 403))
        self.assertIsNone(self.settings())

    # --- Volver a los valores de DOMUX ----------------------------------------------------------------

    def test_going_back_to_the_values_of_domux_clears_every_change(self):
        self.send(pqrsTermDays="20", pqrsWarningDays="7", packageOrangeHours="24", packageRedHours="48",
                  visitorParkingMaxDays="5", term_4="5")

        response = self.post("/web/reglas/restablecer")

        self.assertEqual(response.status_code, 302)
        self.assertIn("volvieron a los valores de DOMUX", self.flashes(response))
        rules = current_rules()
        self.assertEqual(
            (rules.pqrs_term_days, rules.pqrs_warning_days, rules.package_orange_hours, rules.package_red_hours,
             rules.visitor_parking_max_days, dict(rules.pqrs_terms_by_category)),
            (15, 5, 48, 72, 3, {}),
        )
        self.assertNotIn("Esta regla ya la cambiaste", self.page("/web/reglas"))
        self.assertEqual(len(self.logs()), 2)  # el cambio y la vuelta atrás

    def test_going_back_when_nothing_was_changed_does_no_harm(self):
        response = self.post("/web/reglas/restablecer")

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.settings())

    def test_the_reset_button_asks_for_confirmation(self):
        body = self.page("/web/reglas")

        self.assertRegex(body, r'data-confirm="¿Volver todas las reglas a los valores de DOMUX\?')

    # --- Lo que se ve en otras páginas ---------------------------------------------------------------

    def test_the_package_registry_writes_the_hours_of_the_unit(self):
        package = PackageItem(
            resident_id=self.resident.id, registered_by=self.guard.id, description="Caja grande",
            status="pendiente", arrived_at=utc_now() - timedelta(hours=60),
        )
        db.session.add(package)
        db.session.commit()
        self.assertIn("Más de 48 h sin reclamar", self.page("/web/paqueteria"))

        self.send(packageOrangeHours="24", packageRedHours="200")

        body = self.page("/web/paqueteria")
        self.assertIn("Más de 24 h sin reclamar", body)
        self.assertNotIn("Más de 48 h sin reclamar", body)

    def test_the_panel_counts_and_names_the_hours_of_the_unit(self):
        db.session.add(PackageItem(
            resident_id=self.resident.id, registered_by=self.guard.id, description="Caja",
            status="pendiente", arrived_at=utc_now() - timedelta(hours=30),
        ))
        db.session.commit()
        body = self.page("/web/")
        self.assertIn("Paquetes con más de 48 horas", body)

        self.send(packageOrangeHours="24", packageRedHours="60")

        body = self.page("/web/")
        self.assertIn("Paquetes con más de 24 horas", body)

    def test_the_inbox_uses_the_new_term_for_the_open_pqrs(self):
        created = colombia_day_to_utc(colombia_today() - timedelta(days=10)) + timedelta(hours=15)
        db.session.add(Pqrs(
            resident_id=self.resident.id, category="Daño", subject="Ascensor sin servicio", message="No sirve",
            status="abierta", created_at=created, updated_at=created,
        ))
        db.session.commit()
        before = self.page("/web/pqrs")
        self.assertIn("En plazo</span>", before)
        self.assertNotIn("Vencida</span>", before)

        self.send(term_4="3")

        after = self.page("/web/pqrs")
        self.assertIn("Vencida</span>", after)
        self.assertNotIn("En plazo</span>", after)


if __name__ == "__main__":
    unittest.main()
