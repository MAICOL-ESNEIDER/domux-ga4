"""Pruebas de la lista liviana de comunicados (GET /api/announcements?view=summary), de sus filtros y de los
números de cada pestaña, de la lectura de un solo comunicado (GET /api/announcements/<id>), del título
demasiado largo y de la lectura del adjunto (HU-080)."""

import base64
import unittest
from datetime import timedelta

import env_setup  # noqa: F401  (va antes de importar la app)

from extensions import db
from models import Announcement
from services import announcement_view
from test_announcements import AnnouncementTestCase
from time_utils import colombia_today

#: Una foto de mentira bastante grande como para notar si viaja donde no debe.
JPEG = b"\xff\xd8\xff" + b"x" * 5000
PHOTO = "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()


class SummaryTestCase(AnnouncementTestCase):
    def day(self, offset):
        """La fecha de hoy (en Colombia) más ``offset`` días, como AAAA-MM-DD."""
        return (colombia_today() + timedelta(days=offset)).isoformat()

    def summary(self, user=None, **params):
        response = self.client.get(
            "/api/announcements", headers=self.headers(user or self.admin),
            query_string={"view": "summary", **params},
        )
        return response, response.get_json()

    def ids(self, body):
        return [row["id"] for row in body["announcements"]]

    def single(self, announcement_id, user=None, **params):
        response = self.client.get(
            f"/api/announcements/{announcement_id}", headers=self.headers(user or self.admin), query_string=params,
        )
        return response, response.get_json()


class SummaryListTests(SummaryTestCase):
    def test_rows_are_light_and_carry_what_the_list_shows(self):
        announcement_id = self.publish(
            "Corte de agua", "mantenimiento", towerId=self.tower_1, expiresAt=self.day(10),
            eventDate=self.day(5), eventTime="08:00", mediaUrl=PHOTO, mediaType="image",
        )

        response, body = self.summary()

        self.assertEqual(response.status_code, 200)
        self.assertEqual((body["page"], body["pageSize"], body["total"], body["totalPages"]), (1, 50, 1, 1))
        row = body["announcements"][0]
        self.assertEqual(row["id"], announcement_id)
        self.assertEqual(row["title"], "Corte de agua")
        self.assertEqual(row["message"], "Mensaje de prueba para los residentes.")
        self.assertEqual((row["category"], row["categoryLabel"]), ("mantenimiento", "Mantenimiento"))
        self.assertEqual((row["towerId"], row["towerName"]), (self.tower_1, "Torre 1"))
        self.assertEqual((row["expiresAt"], row["isExpired"]), (self.day(10), False))
        self.assertEqual((row["eventDate"], row["eventTime"]), (self.day(5), "08:00"))
        self.assertEqual(row["mediaType"], "image")
        self.assertTrue(row["hasMedia"])
        self.assertEqual(row["authorName"], "Admin")
        self.assertFalse(row["isRetired"])
        self.assertRegex(row["createdAt"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
        # Lo que pesa no viaja: ni en la fila ni en ninguna otra parte de la respuesta.
        self.assertNotIn("mediaUrl", row)
        self.assertNotIn(PHOTO[30:130], response.get_data(as_text=True))

    def test_a_row_without_attachment_or_tower_says_so(self):
        self.publish("Reunión de comité", "asamblea")

        _response, body = self.summary()

        row = body["announcements"][0]
        self.assertFalse(row["hasMedia"])
        self.assertIsNone(row["mediaType"])
        self.assertIsNone(row["towerId"])
        self.assertIsNone(row["towerName"])
        self.assertIsNone(row["expiresAt"])

    def test_the_full_list_still_carries_the_attachment(self):
        # La app depende de esta respuesta: no cambia.
        self.publish("Corte de agua", mediaUrl=PHOTO, mediaType="image")

        body = self.listing(self.admin)

        self.assertEqual(body["announcements"][0]["mediaUrl"], PHOTO)
        self.assertNotIn("counts", body)
        self.assertNotIn("hasMedia", body["announcements"][0])

    def test_an_unknown_view_is_refused(self):
        response = self.client.get(
            "/api/announcements?view=todo", headers=self.headers(self.admin),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("solo acepta el valor 'summary'", response.get_json()["error"])

    def test_newest_first_and_paginated(self):
        published = [self.publish(f"Comunicado {number}") for number in range(5)]

        _response, first = self.summary(pageSize=2)
        _response, second = self.summary(pageSize=2, page=2)
        _response, third = self.summary(pageSize=2, page=3)

        self.assertEqual(self.ids(first), published[::-1][:2])
        self.assertEqual(self.ids(second), published[::-1][2:4])
        self.assertEqual(self.ids(third), published[::-1][4:])
        self.assertEqual((first["total"], first["totalPages"], third["page"]), (5, 3, 3))

    def test_current_and_archived_are_separate_tabs_with_their_numbers(self):
        current = self.publish("Vigente", expiresAt=self.day(3))
        endless = self.publish("Sin vencimiento")
        archived = self.expired_announcement()

        _response, now = self.summary()
        _response, old = self.summary(archived="true")

        self.assertEqual(sorted(self.ids(now)), sorted([current, endless]))
        self.assertEqual(self.ids(old), [archived])
        self.assertTrue(old["announcements"][0]["isExpired"])
        # Los números de las dos pestañas son los mismos se esté en la que se esté.
        self.assertEqual(now["counts"], {"current": 2, "archived": 1})
        self.assertEqual(old["counts"], {"current": 2, "archived": 1})

    def test_retired_announcements_are_not_listed_nor_counted(self):
        kept = self.publish("Se queda")
        gone = self.publish("Se retira")
        self.retire(gone)

        _response, body = self.summary()

        self.assertEqual(self.ids(body), [kept])
        self.assertEqual(body["counts"], {"current": 1, "archived": 0})
        self.assertEqual(body["total"], 1)


class SummaryFilterTests(SummaryTestCase):
    def test_category_filter_also_narrows_the_numbers_of_the_tabs(self):
        urgent = self.publish("Fuga de gas", "urgente")
        self.publish("Revisión de ascensores", "mantenimiento")
        self.expired_announcement()  # asamblea, archivado

        _response, body = self.summary(category="urgente")
        _response, archived = self.summary(category="asamblea", archived="true")

        self.assertEqual(self.ids(body), [urgent])
        self.assertEqual(body["counts"], {"current": 1, "archived": 0})
        self.assertEqual(archived["counts"], {"current": 0, "archived": 1})

    def test_an_unknown_category_is_refused_like_in_the_full_list(self):
        response, body = self.summary(category="chisme")

        self.assertEqual(response.status_code, 400)
        self.assertIn("categoría", body["error"])

    def test_tower_filter_picks_a_tower_or_the_whole_unit(self):
        whole = self.publish("Para todos")
        tower = self.publish("Solo la torre 1", towerId=self.tower_1)

        _response, in_tower = self.summary(towerId=self.tower_1)
        _response, in_unit = self.summary(towerId="unit")

        self.assertEqual(self.ids(in_tower), [tower])
        self.assertEqual(self.ids(in_unit), [whole])
        self.assertEqual(in_tower["counts"], {"current": 1, "archived": 0})

    def test_a_badly_written_tower_is_refused(self):
        for value in ("abc", "0", "-1", "1.5"):
            with self.subTest(value=value):
                response, body = self.summary(towerId=value)
                self.assertEqual(response.status_code, 400)
                self.assertIn("towerId", body["error"])

    def test_search_looks_in_the_title_and_in_the_message_without_caring_about_capitals(self):
        by_title = self.publish("Fumigación de zonas comunes", "seguridad")
        by_message = self.publish("Aviso importante", "seguridad", message="Recuerden que la Fumigación será el sábado.")
        self.publish("Corte de agua", "mantenimiento")

        _response, body = self.summary(search="fumigación")
        _response, short = self.summary(q="FUMIG")

        self.assertEqual(sorted(self.ids(body)), sorted([by_title, by_message]))
        self.assertEqual(sorted(self.ids(short)), sorted([by_title, by_message]))
        self.assertEqual(body["counts"], {"current": 2, "archived": 0})

    def test_filters_add_up(self):
        match = self.publish("Fumigación", "seguridad", towerId=self.tower_1)
        self.publish("Fumigación", "seguridad")
        self.publish("Fumigación", "mantenimiento", towerId=self.tower_1)

        _response, body = self.summary(search="fumig", category="seguridad", towerId=self.tower_1)

        self.assertEqual(self.ids(body), [match])


class SummaryAudienceTests(SummaryTestCase):
    def test_the_administration_sees_how_many_apartments_read_each_one(self):
        announcement_id = self.publish("Asamblea", "asamblea")
        self.assertEqual(self.read(announcement_id).status_code, 200)

        _response, body = self.summary()

        row = body["announcements"][0]
        self.assertEqual((row["readApartments"], row["totalApartments"]), (1, 1))
        self.assertTrue(row["isRead"])

    def test_residents_never_see_the_reading_numbers_but_do_see_what_is_unread(self):
        read = self.publish("Ya lo leí")
        unread = self.publish("Sin leer")
        self.assertEqual(self.read(read).status_code, 200)

        response, body = self.summary(user=self.resident)

        self.assertEqual(response.status_code, 200)
        by_id = {row["id"]: row for row in body["announcements"]}
        self.assertTrue(by_id[read]["isRead"])
        self.assertFalse(by_id[unread]["isRead"])
        for row in body["announcements"]:
            self.assertNotIn("readApartments", row)
            self.assertNotIn("totalApartments", row)
            self.assertNotIn("mediaUrl", row)
        self.assertEqual(body["unreadCount"], 1)

    def test_a_resident_only_gets_what_their_tower_can_see(self):
        other_tower = self.resident_in("Torre 2 · Apto 202", "vecina-resumen@test.local").apartment_ref.tower_id
        mine = self.publish("De mi torre", towerId=self.tower_1)
        self.publish("De la otra torre", towerId=other_tower)
        whole = self.publish("Para todos")

        _response, body = self.summary(user=self.resident)

        self.assertEqual(sorted(self.ids(body)), sorted([mine, whole]))

    def test_guards_get_the_summary_without_the_reading_numbers(self):
        self.publish("Aviso")

        response, body = self.summary(user=self.guard)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("readApartments", body["announcements"][0])
        self.assertTrue(body["announcements"][0]["isRead"])


class SingleAnnouncementTests(SummaryTestCase):
    def test_summary_view_of_one_announcement_comes_without_the_attachment(self):
        announcement_id = self.publish("Con foto", mediaUrl=PHOTO, mediaType="image")

        response, body = self.single(announcement_id, view="summary")

        self.assertEqual(response.status_code, 200)
        announcement = body["announcement"]
        self.assertEqual(announcement["title"], "Con foto")
        self.assertTrue(announcement["hasMedia"])
        self.assertNotIn("mediaUrl", announcement)
        self.assertEqual((announcement["readApartments"], announcement["totalApartments"]), (0, 1))
        self.assertNotIn(PHOTO[30:130], response.get_data(as_text=True))

    def test_without_view_it_carries_the_attachment(self):
        announcement_id = self.publish("Con foto", mediaUrl=PHOTO, mediaType="image")

        _response, body = self.single(announcement_id)

        self.assertEqual(body["announcement"]["mediaUrl"], PHOTO)

    def test_a_retired_or_unknown_announcement_is_not_found(self):
        gone = self.publish("Se retira")
        self.retire(gone)

        for announcement_id in (gone, 9999):
            with self.subTest(announcement_id=announcement_id):
                response, body = self.single(announcement_id)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(body["error"], "Anuncio no encontrado")

    def test_an_expired_announcement_can_still_be_opened(self):
        archived = self.expired_announcement()

        response, body = self.single(archived, view="summary")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["announcement"]["isExpired"])

    def test_a_resident_cannot_open_the_announcement_of_another_tower(self):
        other_tower = self.resident_in("Torre 2 · Apto 202", "vecina-uno@test.local").apartment_ref.tower_id
        elsewhere = self.publish("De la otra torre", towerId=other_tower)
        mine = self.publish("De mi torre", towerId=self.tower_1)

        self.assertEqual(self.single(elsewhere, user=self.resident)[0].status_code, 404)
        response, body = self.single(mine, user=self.resident)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("readApartments", body["announcement"])

    def test_an_unknown_view_is_refused(self):
        announcement_id = self.publish("Aviso")

        response, _body = self.single(announcement_id, view="todo")

        self.assertEqual(response.status_code, 400)

    def test_it_needs_a_session(self):
        announcement_id = self.publish("Aviso")

        self.assertEqual(self.client.get(f"/api/announcements/{announcement_id}").status_code, 401)


class TitleLengthTests(SummaryTestCase):
    def post(self, title):
        return self.client.post(
            "/api/announcements", json={"title": title, "message": "Mensaje.", "category": "urgente"},
            headers=self.headers(self.admin),
        )

    def test_a_title_of_150_letters_is_accepted_and_one_more_is_refused_with_a_clear_message(self):
        self.assertEqual(self.post("A" * 150).status_code, 201)

        response = self.post("A" * 151)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "El título no puede pasar de 150 caracteres.")
        self.assertEqual(Announcement.query.count(), 1)


class AttachmentTests(SummaryTestCase):
    def test_it_gives_the_bytes_and_the_type_of_the_attachment(self):
        announcement_id = self.publish("Con foto", mediaUrl=PHOTO, mediaType="image")

        self.assertEqual(announcement_view.attachment(announcement_id), (JPEG, "image/jpeg"))

    def test_there_is_nothing_to_give_without_attachment_or_when_it_was_retired_or_is_not_media(self):
        plain = self.publish("Sin foto")
        retired = self.publish("Retirado", mediaUrl=PHOTO, mediaType="image")
        self.retire(retired)
        svg = Announcement(
            title="Raro", message="x", category="urgente", author_id=self.admin.id,
            media_url="data:image/svg+xml;base64," + base64.b64encode(b"<svg onload='alert(1)'/>").decode(),
            media_type="image",
        )
        link = Announcement(
            title="Enlace", message="x", category="urgente", author_id=self.admin.id,
            media_url="https://example.com/foto.jpg", media_type="image",
        )
        db.session.add_all([svg, link])
        db.session.commit()

        for announcement_id in (plain, retired, svg.id, link.id, 9999):
            with self.subTest(announcement_id=announcement_id):
                self.assertIsNone(announcement_view.attachment(announcement_id))


class TowerFilterParsingTests(unittest.TestCase):
    def test_it_understands_nothing_the_whole_unit_or_a_tower_number(self):
        self.assertIsNone(announcement_view.parse_tower_filter(None))
        self.assertIsNone(announcement_view.parse_tower_filter(""))
        self.assertEqual(announcement_view.parse_tower_filter("unit"), "unit")
        self.assertEqual(announcement_view.parse_tower_filter("12"), 12)


if __name__ == "__main__":
    unittest.main()
