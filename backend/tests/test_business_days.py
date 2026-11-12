"""Pruebas del calendario de Colombia y del semáforo de PQRS (HU-073, RN-021 y RN-025)."""

import unittest
from datetime import date, datetime, timedelta

import env_setup  # noqa: F401  (va antes de importar las demás piezas del servidor)

from business_days import (
    add_business_days,
    business_days_between,
    colombian_holidays,
    easter_sunday,
    is_business_day,
    is_holiday,
)
from services.pqrs_rules import (
    GREEN,
    RED,
    YELLOW,
    make_radicado,
    pqrs_semaphore,
)


class ColombianHolidaysTests(unittest.TestCase):
    def test_easter_sunday_matches_known_dates(self):
        self.assertEqual(easter_sunday(2024), date(2024, 3, 31))
        self.assertEqual(easter_sunday(2025), date(2025, 4, 20))
        self.assertEqual(easter_sunday(2026), date(2026, 4, 5))
        self.assertEqual(easter_sunday(2027), date(2027, 3, 28))

    def test_holidays_of_2026_are_the_eighteen_official_ones(self):
        expected = {
            date(2026, 1, 1), date(2026, 1, 12), date(2026, 3, 23), date(2026, 4, 2),
            date(2026, 4, 3), date(2026, 5, 1), date(2026, 5, 18), date(2026, 6, 8),
            date(2026, 6, 15), date(2026, 6, 29), date(2026, 7, 20), date(2026, 8, 7),
            date(2026, 8, 17), date(2026, 10, 12), date(2026, 11, 2), date(2026, 11, 16),
            date(2026, 12, 8), date(2026, 12, 25),
        }
        self.assertEqual(set(colombian_holidays(2026)), expected)

    def test_holidays_of_2027_move_to_monday_and_follow_easter(self):
        holidays = colombian_holidays(2027)
        for day in (
            date(2027, 1, 11),    # Reyes Magos (6 de enero, miércoles) pasa al lunes
            date(2027, 3, 22),    # San José (19 de marzo, viernes) pasa al lunes
            date(2027, 3, 25),    # Jueves Santo
            date(2027, 3, 26),    # Viernes Santo
            date(2027, 5, 10),    # Ascensión
            date(2027, 5, 31),    # Corpus Christi
            date(2027, 6, 7),     # Sagrado Corazón
            date(2027, 7, 5),     # San Pedro y San Pablo (29 de junio, martes) pasa al lunes
            date(2027, 8, 16),    # Asunción (15 de agosto, domingo) pasa al lunes
            date(2027, 10, 18),   # Día de la Raza (12 de octubre, martes) pasa al lunes
            date(2027, 11, 1),    # Todos los Santos (ya es lunes) se queda
            date(2027, 11, 15),   # Independencia de Cartagena (11 de noviembre, jueves)
        ):
            with self.subTest(day=day):
                self.assertIn(day, holidays)
        self.assertNotIn(date(2027, 1, 6), holidays)
        self.assertNotIn(date(2027, 3, 19), holidays)

    def test_every_year_has_at_most_eighteen_holidays_and_all_moved_ones_are_mondays(self):
        for year in range(2024, 2036):
            holidays = colombian_holidays(year)
            with self.subTest(year=year):
                self.assertLessEqual(len(holidays), 18)
                self.assertGreaterEqual(len(holidays), 16)
                fixed = {(1, 1), (5, 1), (7, 20), (8, 7), (12, 8), (12, 25)}
                easter = easter_sunday(year)
                holy_week = {easter - timedelta(days=3), easter - timedelta(days=2)}
                for day in holidays:
                    if (day.month, day.day) not in fixed and day not in holy_week:
                        self.assertEqual(day.weekday(), 0, f"{day} debería ser lunes")

    def test_business_day_rules(self):
        self.assertTrue(is_business_day(date(2026, 11, 11)))     # miércoles normal
        self.assertFalse(is_business_day(date(2026, 11, 14)))    # sábado
        self.assertFalse(is_business_day(date(2026, 11, 15)))    # domingo
        self.assertFalse(is_business_day(date(2026, 11, 16)))    # lunes festivo
        self.assertTrue(is_holiday(date(2026, 11, 16)))
        self.assertFalse(is_holiday(date(2026, 11, 11)))         # el 11 se pasó al lunes 16

    def test_counting_business_days_skips_weekends_and_holidays(self):
        # Del miércoles 11 al viernes 20 de noviembre de 2026: jueves 12, viernes 13,
        # (sábado, domingo y lunes 16 festivo no cuentan), martes 17, miércoles 18,
        # jueves 19 y viernes 20.
        self.assertEqual(business_days_between(date(2026, 11, 11), date(2026, 11, 20)), 6)
        self.assertEqual(business_days_between(date(2026, 11, 20), date(2026, 11, 20)), 0)
        self.assertEqual(business_days_between(date(2026, 11, 20), date(2026, 11, 11)), 0)
        self.assertEqual(add_business_days(date(2026, 11, 11), 6), date(2026, 11, 20))
        self.assertEqual(add_business_days(date(2026, 11, 11), 0), date(2026, 11, 11))


class PqrsSemaphoreTests(unittest.TestCase):
    CREATED = date(2026, 9, 1)  # martes sin festivos cerca

    def semaphore_after(self, business_days):
        today = add_business_days(self.CREATED, business_days)
        return pqrs_semaphore(self.CREATED, today)

    def test_due_date_is_fifteen_business_days_after_the_filing_day(self):
        result = pqrs_semaphore(self.CREATED, self.CREATED)
        self.assertEqual(result["daysRemaining"], 15)
        self.assertEqual(result["color"], GREEN)
        self.assertEqual(result["dueDate"], add_business_days(self.CREATED, 15).isoformat())
        self.assertEqual(result["dueDate"], "2026-09-22")

    def test_green_while_more_than_five_business_days_remain(self):
        for elapsed in (0, 1, 9):
            with self.subTest(elapsed=elapsed):
                result = self.semaphore_after(elapsed)
                self.assertEqual(result["color"], GREEN)
                self.assertGreater(result["daysRemaining"], 5)

    def test_yellow_with_five_or_fewer_business_days_left_including_the_last_day(self):
        for elapsed, remaining in ((10, 5), (14, 1), (15, 0)):
            with self.subTest(elapsed=elapsed):
                result = self.semaphore_after(elapsed)
                self.assertEqual(result["color"], YELLOW)
                self.assertEqual(result["daysRemaining"], remaining)

    def test_red_once_the_term_has_expired(self):
        result = self.semaphore_after(16)
        self.assertEqual(result["color"], RED)
        self.assertEqual(result["daysRemaining"], -1)
        self.assertEqual(self.semaphore_after(30)["color"], RED)

    def test_weekends_and_holidays_do_not_consume_the_term(self):
        # Radicada el miércoles 11 de noviembre de 2026: el lunes 16 es festivo, así que
        # el día 15 hábil cae el 3 de diciembre y no el 2.
        created = date(2026, 11, 11)
        result = pqrs_semaphore(created, created)
        self.assertEqual(result["dueDate"], "2026-12-03")
        on_saturday = pqrs_semaphore(created, date(2026, 11, 14))
        on_friday = pqrs_semaphore(created, date(2026, 11, 13))
        self.assertEqual(on_saturday["daysRemaining"], on_friday["daysRemaining"])

    def test_filed_on_a_weekend_starts_counting_on_the_next_business_day(self):
        saturday = date(2026, 9, 5)
        result = pqrs_semaphore(saturday, saturday)
        self.assertEqual(result["daysRemaining"], 15)
        self.assertEqual(result["dueDate"], add_business_days(saturday, 15).isoformat())


class RadicadoTests(unittest.TestCase):
    def test_radicado_carries_the_colombia_year_and_the_id(self):
        self.assertEqual(make_radicado(7, datetime(2026, 11, 11, 15, 0)), "PQRS-2026-000007")
        self.assertEqual(make_radicado(123456, datetime(2027, 3, 1, 9, 30)), "PQRS-2027-123456")

    def test_radicado_uses_the_colombia_year_near_new_year(self):
        # 1 de enero a las 02:00 UTC todavía es 31 de diciembre en Colombia.
        self.assertEqual(make_radicado(1, datetime(2027, 1, 1, 2, 0)), "PQRS-2026-000001")
        self.assertEqual(make_radicado(2, datetime(2027, 1, 1, 6, 0)), "PQRS-2027-000002")


if __name__ == "__main__":
    unittest.main()
