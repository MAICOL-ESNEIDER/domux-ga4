"""Pruebas de las zonas comunes y sus reglas de reserva en la web de administración (HU-055): la lista con las
reglas en palabras, el formulario de cada zona, guardar solo lo que cambió y los mensajes de la API."""

import unittest

from extensions import db
from models import ANNOUNCEMENT_CATEGORIES, AuditLog, CommonArea, Reservation
from time_utils import colombia_today
from web import texts
from web_testing import WebTestCase


class WebZoneCase(WebTestCase):
    def setUp(self):
        super().setUp()
        self.hall = CommonArea(name="Salón social", capacity=40, maintenance_weekday=0)
        self.pool = CommonArea(
            name="Piscina", open_time="06:00", close_time="20:00", slot_minutes=60, min_advance_days=1,
            max_advance_days=30, cancel_deadline_days=1, weekly_limit=1,
        )
        db.session.add_all([self.hall, self.pool])
        db.session.commit()
        self.log_in()

    def reload(self, area):
        db.session.expire_all()
        return db.session.get(CommonArea, area.id)

    def rules(self, area, **changes):
        """Lo que manda el formulario: las reglas de la zona tal como están, con los cambios encima."""
        form = {
            "openTime": area.open_time, "closeTime": area.close_time, "slotMinutes": str(area.slot_minutes),
            "capacity": "" if area.capacity is None else str(area.capacity),
            "minAdvanceDays": str(area.min_advance_days), "maxAdvanceDays": str(area.max_advance_days),
            "cancelDeadlineDays": str(area.cancel_deadline_days), "weeklyLimit": str(area.weekly_limit),
            "maintenanceWeekday": "" if area.maintenance_weekday is None else str(area.maintenance_weekday),
        }
        form.update({key: str(value) for key, value in changes.items()})
        return form

    def save(self, area, **changes):
        return self.post(f"/web/zonas/{area.id}", self.rules(area, **changes))


class WebZoneListTests(WebZoneCase):
    def test_pages_ask_for_login(self):
        anonymous = self.app.test_client()
        for path in ("/web/zonas", f"/web/zonas/{self.hall.id}"):
            with self.subTest(path=path):
                response = anonymous.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/web/login", response.headers["Location"])
        # Sin sesión (y sin el código contra CSRF) el formulario no cambia nada.
        response = anonymous.post(f"/web/zonas/{self.hall.id}", data=self.rules(self.hall, capacity=99))
        self.assertIn(response.status_code, (302, 400))
        self.assertEqual(self.reload(self.hall).capacity, 40)

    def test_the_menu_leads_to_the_list_and_marks_it(self):
        self.assertIn('href="/web/zonas"', self.page("/web/"))
        page = self.page("/web/zonas")
        self.assertRegex(
            page, r'<a[^>]*href="/web/zonas"[^>]*aria-current="page"|<a[^>]*aria-current="page"[^>]*href="/web/zonas"',
        )

    def test_the_rules_of_each_zone_are_written_in_words(self):
        body = self.page("/web/zonas")

        for text in (
            "Salón social", "De 08:00 a 22:00", "2 horas cada una · 7 franjas al día", "40 personas",
            "Desde el mismo día y hasta 60 días antes", "El residente cancela hasta 3 días antes",
            "2 reservas por semana por residente", "Cierra los lunes (si ese día es festivo, pasa al día siguiente)",
            "Piscina", "De 06:00 a 20:00", "1 hora cada una · 14 franjas al día", "Sin límite definido",
            "Desde 1 día antes y hasta 30 días antes", "El residente cancela hasta 1 día antes",
            "1 reserva por semana por residente", "Sin día de mantenimiento",
        ):
            self.assertIn(text, body)

    def test_the_weekend_days_are_written_in_plural(self):
        self.hall.maintenance_weekday = 5
        self.pool.maintenance_weekday = 2
        db.session.commit()

        body = self.page("/web/zonas")

        self.assertIn("Cierra los sábados", body)
        self.assertIn("Cierra los miércoles", body)

    def test_each_zone_has_its_own_edit_link_with_a_name_for_screen_readers(self):
        body = self.page("/web/zonas")

        for area in (self.hall, self.pool):
            self.assertIn(
                f'href="/web/zonas/{area.id}">Editar las reglas<span class="sr-only"> de {area.name}</span>', body,
            )

    def test_without_zones_it_says_so(self):
        CommonArea.query.delete()
        db.session.commit()

        self.assertIn("Todavía no hay zonas comunes.", self.page("/web/zonas"))


class WebZoneFormTests(WebZoneCase):
    def test_the_form_shows_the_current_rules(self):
        body = self.page(f"/web/zonas/{self.hall.id}")

        self.assertIn("Reglas de Salón social", body)
        self.assertIn('name="csrf_token"', body)
        self.assertRegex(body, r'name="openTime" type="time" value="08:00" required')
        self.assertRegex(body, r'name="closeTime" type="time" value="22:00" required')
        self.assertRegex(body, r'<option value="120" selected>2 horas</option>')
        for option in ("30 minutos", "1 hora", "1 hora y media", "3 horas", "4 horas"):
            self.assertIn(f">{option}</option>", body)
        self.assertRegex(body, r'name="capacity" type="number" value="40"')
        self.assertRegex(body, r'name="minAdvanceDays" type="number" value="0" required')
        self.assertRegex(body, r'name="maxAdvanceDays" type="number" value="60" required')
        self.assertRegex(body, r'name="weeklyLimit" type="number" value="2" required')
        self.assertRegex(body, r'name="cancelDeadlineDays" type="number" value="3" required')
        self.assertRegex(body, r'<option value="0" selected>Lunes</option>')
        self.assertIn(">Sin día de mantenimiento</option>", body)
        self.assertIn("Las reservas que ya existen no cambian", body)

    def test_an_empty_capacity_and_no_maintenance_day_show_empty(self):
        body = self.page(f"/web/zonas/{self.pool.id}")

        self.assertRegex(body, r'name="capacity" type="number" value=""|name="capacity" type="number"(?! value)')
        self.assertNotRegex(body, r'<option value="\d" selected>')

    def test_an_unknown_zone_is_a_404(self):
        self.assertEqual(self.client.get("/web/zonas/99999").status_code, 404)
        self.assertEqual(self.post("/web/zonas/99999", {"capacity": "10"}).status_code, 404)


class WebZoneSaveTests(WebZoneCase):
    def test_saving_sends_only_what_changed_and_leaves_a_trace(self):
        response = self.save(self.hall, capacity=60, openTime="07:00")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/web/zonas")
        zone = self.reload(self.hall)
        self.assertEqual((zone.capacity, zone.open_time), (60, "07:00"))
        self.assertEqual(
            (zone.close_time, zone.slot_minutes, zone.min_advance_days, zone.max_advance_days,
             zone.cancel_deadline_days, zone.weekly_limit, zone.maintenance_weekday),
            ("22:00", 120, 0, 60, 3, 2, 0),
        )
        log = AuditLog.query.filter_by(entity_type="common_area", entity_id=self.hall.id, action="rules_changed").one()
        self.assertEqual(log.actor_id, self.admin.id)
        self.assertIn('"capacity": 60', log.details)
        self.assertIn('"open_time": "07:00"', log.details)
        self.assertNotIn("close_time", log.details)
        self.assertNotIn("slot_minutes", log.details)
        page = self.text(self.client.get("/web/zonas"))
        self.assertIn("Reglas de Salón social guardadas.", page)
        self.assertIn("60 personas", page)
        self.assertIn("De 07:00 a 22:00", page)

    def test_every_rule_can_be_changed(self):
        response = self.save(
            self.pool, openTime="07:00", closeTime="19:00", slotMinutes=90, capacity=25, minAdvanceDays=2,
            maxAdvanceDays=45, cancelDeadlineDays=2, weeklyLimit=3, maintenanceWeekday=4,
        )

        self.assertEqual(response.status_code, 302)
        zone = self.reload(self.pool)
        self.assertEqual(
            (zone.open_time, zone.close_time, zone.slot_minutes, zone.capacity, zone.min_advance_days,
             zone.max_advance_days, zone.cancel_deadline_days, zone.weekly_limit, zone.maintenance_weekday),
            ("07:00", "19:00", 90, 25, 2, 45, 2, 3, 4),
        )

    def test_the_other_zone_is_left_alone(self):
        self.save(self.hall, capacity=60)

        other = self.reload(self.pool)

        self.assertEqual((other.capacity, other.open_time, other.weekly_limit), (None, "06:00", 1))

    def test_nothing_changed_says_so_and_changes_nothing(self):
        response = self.save(self.hall)

        self.assertEqual(response.status_code, 200)
        self.assertIn("No cambiaste ninguna regla.", self.text(response))
        self.assertEqual(AuditLog.query.filter_by(action="rules_changed").count(), 0)

    def test_an_empty_capacity_and_no_maintenance_day_clear_them(self):
        response = self.save(self.hall, capacity="", maintenanceWeekday="")

        self.assertEqual(response.status_code, 302)
        zone = self.reload(self.hall)
        self.assertIsNone(zone.capacity)
        self.assertIsNone(zone.maintenance_weekday)

    def test_an_empty_weekly_limit_and_cancel_deadline_go_back_to_the_usual_values(self):
        response = self.save(self.pool, weeklyLimit="", cancelDeadlineDays="")

        self.assertEqual(response.status_code, 302)
        zone = self.reload(self.pool)
        self.assertEqual((zone.weekly_limit, zone.cancel_deadline_days), (2, 3))

    def test_the_messages_of_the_api_are_shown_and_what_was_written_is_kept(self):
        for changes, message in (
            ({"closeTime": "07:00"}, "La hora de cierre debe ser después de la hora de apertura."),
            ({"closeTime": "10:00", "slotMinutes": 240}, "debe caber al menos una franja de 240 minutos."),
            ({"minAdvanceDays": 10, "maxAdvanceDays": 5}, "La anticipación máxima no puede ser menor que la mínima."),
            ({"cancelDeadlineDays": 4}, "El plazo de cancelación debe ser un número entero entre 1 y 3."),
            ({"slotMinutes": 45}, "La duración de cada franja debe ser de 30, 60, 90, 120, 180, 240 minutos."),
            ({"capacity": "muchas"}, "El aforo debe ser un número entero entre 1 y 2000."),
            ({"capacity": 0}, "El aforo debe ser un número entero entre 1 y 2000."),
            ({"maintenanceWeekday": 7}, "El día de mantenimiento debe ser un número entero entre 0 y 6."),
            ({"weeklyLimit": 15}, "El límite semanal debe ser un número entero entre 1 y 14."),
            ({"openTime": "25:99"}, "La hora de apertura"),
        ):
            with self.subTest(changes=changes):
                response = self.save(self.hall, **changes)
                body = self.text(response)
                self.assertEqual(response.status_code, 400)
                self.assertIn(message, body)
                # La zona sigue como estaba y el formulario conserva lo que se escribió.
                zone = self.reload(self.hall)
                self.assertEqual((zone.open_time, zone.close_time, zone.slot_minutes, zone.capacity), ("08:00", "22:00", 120, 40))
                first_key, first_value = next(iter(changes.items()))
                if first_key not in ("slotMinutes", "maintenanceWeekday"):
                    # (Las listas desplegables solo tienen valores válidos: el navegador no manda otros.)
                    self.assertRegex(body, rf'name="{first_key}"[^>]*value="{first_value}"')
        self.assertEqual(AuditLog.query.filter_by(action="rules_changed").count(), 0)

    def test_reservations_that_already_exist_are_not_touched(self):
        reservation = Reservation(
            resident_id=self.resident.id, common_area_id=self.hall.id, date=colombia_today().isoformat(),
            time_slot="10:00-12:00", status="aprobada",
        )
        db.session.add(reservation)
        db.session.commit()

        self.assertEqual(self.save(self.hall, slotMinutes=60, openTime="09:00").status_code, 302)

        db.session.expire_all()
        kept = db.session.get(Reservation, reservation.id)
        self.assertEqual((kept.time_slot, kept.status), ("10:00-12:00", "aprobada"))

    def test_forms_without_the_security_code_are_refused(self):
        response = self.client.post(f"/web/zonas/{self.hall.id}", data=self.rules(self.hall, capacity=99))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.reload(self.hall).capacity, 40)


class WebTextsTests(unittest.TestCase):
    def test_the_length_of_a_slot_is_written_in_words(self):
        for minutes, expected in (
            (30, "30 minutos"), (60, "1 hora"), (90, "1 hora y media"), (120, "2 horas"), (180, "3 horas"),
            (240, "4 horas"), (75, "1 hora y 15 minutos"), (150, "2 horas y media"),
        ):
            with self.subTest(minutes=minutes):
                self.assertEqual(texts.slot_length_text(minutes), expected)

    def test_the_categories_of_the_badges_are_the_ones_of_the_announcements(self):
        self.assertEqual(
            {key: label for key, (label, _tone) in texts.ANNOUNCEMENT_CATEGORIES.items()}, ANNOUNCEMENT_CATEGORIES,
        )
        self.assertEqual(texts.badge_info("announcement", "urgente"), {"label": "Urgente", "tone": "alert"})


if __name__ == "__main__":
    unittest.main()
