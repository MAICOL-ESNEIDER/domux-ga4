"""Pruebas de los comunicados (HU-057 a HU-062, TT-029 y DEF-005).

Comprueban que retirar un comunicado lo oculta en la app pero lo deja en la
base (DEC-090), que cada uno lleva una de las cinco categorías (HU-058), que el
residente ve cuáles no ha leído (HU-059), que al vencer pasan a «Archivados»
(HU-060), que los de una torre solo los ve esa torre (HU-061) y que la
administración sabe cuántos apartamentos los leyeron (HU-062).
"""

import unittest
from datetime import timedelta

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import generate_password_hash

from app import create_app
from auth import generate_token
from extensions import db
from models import Announcement, AnnouncementRead, AuditLog, Notification, User
from structure_fixtures import apartment_for
from time_utils import colombia_today


class AnnouncementTestCase(unittest.TestCase):
    """Base con la unidad de ejemplo: dos torres, una administración y una portería."""

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.admin = self.user("ADMIN", "admin-anuncios@test.local")
        self.resident = self.user(
            "RESIDENT", "residente-anuncios@test.local", apartment_ref=apartment_for("Apto 101")
        )
        self.guard = self.user("GUARD", "guardia-anuncios@test.local")
        db.session.commit()
        self.tower_1 = self.resident.apartment_ref.tower_id
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def user(self, role, email, **fields):
        person = User(
            name=role.title(),
            email=email,
            password_hash=generate_password_hash("Clave-de-prueba-1*"),
            role=role,
            is_active=True,
            **fields,
        )
        db.session.add(person)
        return person

    def resident_in(self, label, email):
        person = self.user("RESIDENT", email, apartment_ref=apartment_for(label))
        db.session.commit()
        return person

    def headers(self, user):
        return {"Authorization": f"Bearer {generate_token(user)}"}

    def publish(self, title, category="mantenimiento", **fields):
        response = self.client.post(
            "/api/announcements",
            json={
                "title": title,
                "message": "Mensaje de prueba para los residentes.",
                "category": category,
                **fields,
            },
            headers=self.headers(self.admin),
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["announcement"]["id"]

    def listing(self, user, query=""):
        response = self.client.get(f"/api/announcements{query}", headers=self.headers(user))
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def listed_ids(self, user, query=""):
        return [item["id"] for item in self.listing(user, query)["announcements"]]

    def retire(self, announcement_id, user=None):
        return self.client.put(
            f"/api/announcements/{announcement_id}/retire",
            headers=self.headers(user or self.admin),
        )

    def read(self, announcement_id, user=None):
        return self.client.post(
            f"/api/announcements/{announcement_id}/read",
            headers=self.headers(user or self.resident),
        )

    def expired_announcement(self, days_ago=1, **fields):
        item = Announcement(
            title="Comunicado vencido",
            message="Ya pasó su fecha.",
            category="asamblea",
            expires_at=colombia_today() - timedelta(days=days_ago),
            author_id=self.admin.id,
            **fields,
        )
        db.session.add(item)
        db.session.commit()
        return item.id


class AnnouncementRetireTests(AnnouncementTestCase):
    def test_retired_announcement_is_hidden_but_stays_in_database(self):
        kept = self.publish("Asamblea de copropietarios", "asamblea")
        retired = self.publish("Corte de agua")

        response = self.retire(retired)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["announcement"]["isRetired"])
        self.assertEqual(self.listed_ids(self.resident), [kept])
        self.assertEqual(self.listed_ids(self.admin), [kept])
        row = db.session.get(Announcement, retired)
        self.assertIsNotNone(row)
        self.assertIsNotNone(row.retired_at)
        self.assertEqual(row.retired_by_id, self.admin.id)
        log = AuditLog.query.filter_by(
            entity_type="announcement", entity_id=retired, action="retired"
        ).one()
        self.assertEqual(log.actor_id, self.admin.id)

    def test_retiring_twice_answers_conflict(self):
        announcement_id = self.publish("Fumigación", "seguridad")
        self.assertEqual(self.retire(announcement_id).status_code, 200)

        response = self.retire(announcement_id)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Announcement.query.count(), 1)

    def test_old_delete_route_retires_instead_of_deleting(self):
        announcement_id = self.publish("Mantenimiento del ascensor")

        response = self.client.delete(
            f"/api/announcements/{announcement_id}", headers=self.headers(self.admin)
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(db.session.get(Announcement, announcement_id))
        self.assertEqual(self.listed_ids(self.resident), [])

    def test_only_administration_can_retire(self):
        announcement_id = self.publish("Jornada de reciclaje", "zonas_comunes")

        for user in (self.resident, self.guard):
            with self.subTest(role=user.role):
                self.assertEqual(self.retire(announcement_id, user).status_code, 403)

        self.assertEqual(self.listed_ids(self.resident), [announcement_id])

    def test_unknown_announcement_answers_not_found(self):
        self.assertEqual(self.retire(9999).status_code, 404)


class AnnouncementCategoryTests(AnnouncementTestCase):
    """HU-058 y RN-026: cinco categorías y sin categoría no se publica."""

    def post(self, **fields):
        return self.client.post(
            "/api/announcements",
            json={"title": "Aviso", "message": "Texto del aviso.", **fields},
            headers=self.headers(self.admin),
        )

    def test_announcement_without_category_is_not_published(self):
        response = self.post()

        self.assertEqual(response.status_code, 400)
        self.assertIn("categoría", response.get_json()["error"])
        self.assertEqual(Announcement.query.count(), 0)
        self.assertEqual(Notification.query.count(), 0)

    def test_category_outside_the_five_is_refused(self):
        for category in ("general", "Urgentísimo", 3, True, [], ""):
            with self.subTest(category=category):
                self.assertEqual(self.post(category=category).status_code, 400)
        self.assertEqual(Announcement.query.count(), 0)

    def test_the_five_categories_are_accepted_and_shown_with_their_name(self):
        expected = {
            "mantenimiento": "Mantenimiento",
            "urgente": "Urgente",
            "asamblea": "Asamblea",
            "seguridad": "Seguridad",
            "zonas_comunes": "Zonas comunes",
        }
        for category, label in expected.items():
            with self.subTest(category=category):
                response = self.post(category=category)
                self.assertEqual(response.status_code, 201)
                announcement = response.get_json()["announcement"]
                self.assertEqual(announcement["category"], category)
                self.assertEqual(announcement["categoryLabel"], label)

    def test_category_can_be_written_with_spaces_and_capitals(self):
        response = self.post(category="Zonas comunes")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["announcement"]["category"], "zonas_comunes")

    def test_list_can_be_filtered_by_category(self):
        urgent = self.publish("Fuga de gas", "urgente")
        self.publish("Cambio de bombillas", "mantenimiento")

        self.assertEqual(self.listed_ids(self.resident, "?category=urgente"), [urgent])
        self.assertEqual(self.client.get(
            "/api/announcements?category=otra", headers=self.headers(self.resident)
        ).status_code, 400)

    def test_old_announcements_without_category_still_show_up(self):
        db.session.add(Announcement(
            title="Anterior", message="Sin categoría.", author_id=self.admin.id
        ))
        db.session.commit()

        item = self.listing(self.resident)["announcements"][0]

        self.assertIsNone(item["category"])
        self.assertIsNone(item["categoryLabel"])

    def test_urgent_announcement_notifies_with_a_stronger_title(self):
        self.publish("Evacuación por simulacro", "urgente")
        self.publish("Podado de jardines", "zonas_comunes")

        titles = {
            row.message: row.title
            for row in Notification.query.filter_by(user_id=self.resident.id)
        }

        self.assertEqual(titles["Urgente: Evacuación por simulacro"], "Anuncio urgente")
        self.assertEqual(titles["Zonas comunes: Podado de jardines"], "Nuevo anuncio")

    def test_only_administration_can_publish(self):
        for user in (self.resident, self.guard):
            with self.subTest(role=user.role):
                response = self.client.post(
                    "/api/announcements",
                    json={"title": "T", "message": "M", "category": "urgente"},
                    headers=self.headers(user),
                )
                self.assertEqual(response.status_code, 403)


class AnnouncementReadTests(AnnouncementTestCase):
    """HU-059 y HU-062: no leídos para el residente y conteo de apartamentos para la administración."""

    def test_new_announcement_is_unread_until_the_resident_opens_it(self):
        first = self.publish("Primero")
        second = self.publish("Segundo")

        listing = self.listing(self.resident)
        self.assertEqual([item["isRead"] for item in listing["announcements"]], [False, False])
        self.assertEqual(listing["unreadCount"], 2)

        response = self.read(first)

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["announcement"]["isRead"])
        self.assertEqual(body["unreadCount"], 1)
        listing = self.listing(self.resident)
        read_by_id = {item["id"]: item["isRead"] for item in listing["announcements"]}
        self.assertEqual(read_by_id, {first: True, second: False})
        self.assertEqual(listing["unreadCount"], 1)

    def test_unread_filter_only_returns_what_is_left_to_read(self):
        first = self.publish("Primero")
        second = self.publish("Segundo")
        self.read(first)

        self.assertEqual(self.listed_ids(self.resident, "?unread=true"), [second])
        self.assertEqual(set(self.listed_ids(self.resident, "?unread=false")), {first, second})

    def test_opening_twice_leaves_a_single_reading(self):
        announcement_id = self.publish("Aviso")

        self.assertEqual(self.read(announcement_id).status_code, 200)
        self.assertEqual(self.read(announcement_id).status_code, 200)

        self.assertEqual(AnnouncementRead.query.count(), 1)

    def test_reading_keeps_the_apartment_of_the_resident(self):
        announcement_id = self.publish("Aviso")
        self.read(announcement_id)

        reading = AnnouncementRead.query.one()

        self.assertEqual(reading.user_id, self.resident.id)
        self.assertEqual(reading.apartment_id, self.resident.apartment_id)

    def test_the_unread_badge_does_not_count_archived_announcements(self):
        self.publish("Vigente")
        self.expired_announcement()

        self.assertEqual(self.listing(self.resident)["unreadCount"], 1)

    def test_each_resident_has_their_own_reading(self):
        neighbor = self.resident_in("Apto 102", "vecino-anuncios@test.local")
        announcement_id = self.publish("Aviso")
        self.read(announcement_id)

        self.assertEqual(self.listing(self.resident)["unreadCount"], 0)
        self.assertEqual(self.listing(neighbor)["unreadCount"], 1)

    def test_administration_and_guards_cannot_mark_readings(self):
        announcement_id = self.publish("Aviso")

        for user in (self.admin, self.guard):
            with self.subTest(role=user.role):
                self.assertEqual(self.read(announcement_id, user).status_code, 403)

        self.assertEqual(AnnouncementRead.query.count(), 0)

    def test_non_residents_have_nothing_unread(self):
        self.publish("Aviso")

        for user in (self.admin, self.guard):
            with self.subTest(role=user.role):
                listing = self.listing(user)
                self.assertEqual(listing["unreadCount"], 0)
                self.assertTrue(listing["announcements"][0]["isRead"])

    def test_retired_or_unknown_announcement_cannot_be_read(self):
        announcement_id = self.publish("Aviso")
        self.retire(announcement_id)

        self.assertEqual(self.read(announcement_id).status_code, 404)
        self.assertEqual(self.read(9999).status_code, 404)
        self.assertEqual(AnnouncementRead.query.count(), 0)

    def test_archived_announcement_can_still_be_opened_and_read(self):
        archived = self.expired_announcement()

        self.assertEqual(self.read(archived).status_code, 200)

        item = self.listing(self.resident, "?archived=true")["announcements"][0]
        self.assertTrue(item["isRead"])

    def test_administration_sees_how_many_apartments_read_each_announcement(self):
        neighbor = self.resident_in("Apto 102", "vecino-anuncios@test.local")
        self.resident_in("Apto 103", "otro-vecino-anuncios@test.local")
        announcement_id = self.publish("Aviso")
        self.read(announcement_id)
        self.read(announcement_id, neighbor)

        item = self.listing(self.admin)["announcements"][0]

        self.assertEqual(item["readApartments"], 2)
        self.assertEqual(item["totalApartments"], 3)

    def test_two_residents_of_the_same_apartment_count_as_one_apartment(self):
        roommate = self.resident_in("Apto 101", "compañero-anuncios@test.local")
        announcement_id = self.publish("Aviso")
        self.read(announcement_id)
        self.read(announcement_id, roommate)

        item = self.listing(self.admin)["announcements"][0]

        self.assertEqual(AnnouncementRead.query.count(), 2)
        self.assertEqual(item["readApartments"], 1)
        self.assertEqual(item["totalApartments"], 1)

    def test_total_apartments_ignore_inactive_residents(self):
        gone = self.resident_in("Apto 102", "se-fue-anuncios@test.local")
        gone.is_active = False
        db.session.commit()
        self.publish("Aviso")

        self.assertEqual(self.listing(self.admin)["announcements"][0]["totalApartments"], 1)

    def test_published_announcement_starts_with_zero_readings(self):
        response = self.client.post(
            "/api/announcements",
            json={"title": "Aviso", "message": "Texto.", "category": "asamblea"},
            headers=self.headers(self.admin),
        )

        announcement = response.get_json()["announcement"]

        self.assertEqual(announcement["readApartments"], 0)
        self.assertEqual(announcement["totalApartments"], 1)

    def test_residents_and_guards_never_see_the_reading_counts(self):
        self.publish("Aviso")

        for user in (self.resident, self.guard):
            with self.subTest(role=user.role):
                item = self.listing(user)["announcements"][0]
                self.assertNotIn("readApartments", item)
                self.assertNotIn("totalApartments", item)


class AnnouncementTowerTests(AnnouncementTestCase):
    """HU-061: un comunicado enviado a una torre solo lo ven los residentes de esa torre."""

    def setUp(self):
        super().setUp()
        self.other_tower_resident = self.resident_in(
            "Torre 2 · Apto 202", "torre2-anuncios@test.local"
        )
        self.tower_2 = self.other_tower_resident.apartment_ref.tower_id

    def test_tower_announcement_is_only_seen_by_that_tower(self):
        for_tower_1 = self.publish("Solo torre 1", towerId=self.tower_1)
        for_tower_2 = self.publish("Solo torre 2", towerId=self.tower_2)
        for_everyone = self.publish("Para todos")

        self.assertEqual(
            set(self.listed_ids(self.resident)), {for_tower_1, for_everyone}
        )
        self.assertEqual(
            set(self.listed_ids(self.other_tower_resident)), {for_tower_2, for_everyone}
        )

    def test_administration_and_guards_see_every_tower(self):
        ids = {
            self.publish("Solo torre 1", towerId=self.tower_1),
            self.publish("Solo torre 2", towerId=self.tower_2),
            self.publish("Para todos"),
        }

        for user in (self.admin, self.guard):
            with self.subTest(role=user.role):
                self.assertEqual(set(self.listed_ids(user)), ids)

    def test_only_the_residents_of_that_tower_get_the_notification(self):
        self.publish("Solo torre 2", towerId=self.tower_2)

        receivers = {row.user_id for row in Notification.query.filter_by(type="announcement")}

        self.assertEqual(receivers, {self.other_tower_resident.id})

    def test_announcement_for_everyone_notifies_every_resident(self):
        self.publish("Para todos")

        receivers = {row.user_id for row in Notification.query.filter_by(type="announcement")}

        self.assertEqual(receivers, {self.resident.id, self.other_tower_resident.id})

    def test_a_resident_cannot_open_the_announcement_of_another_tower(self):
        for_tower_2 = self.publish("Solo torre 2", towerId=self.tower_2)

        self.assertEqual(self.read(for_tower_2).status_code, 404)
        self.assertEqual(AnnouncementRead.query.count(), 0)
        self.assertEqual(self.read(for_tower_2, self.other_tower_resident).status_code, 200)

    def test_unread_count_only_counts_the_announcements_the_resident_can_see(self):
        self.publish("Solo torre 2", towerId=self.tower_2)
        self.publish("Para todos")

        self.assertEqual(self.listing(self.resident)["unreadCount"], 1)
        self.assertEqual(self.listing(self.other_tower_resident)["unreadCount"], 2)

    def test_total_apartments_follow_the_tower_of_the_announcement(self):
        self.resident_in("Torre 2 · Apto 203", "torre2-otro-anuncios@test.local")
        self.publish("Solo torre 2", towerId=self.tower_2)
        self.publish("Para todos")

        by_title = {
            item["title"]: item for item in self.listing(self.admin)["announcements"]
        }

        self.assertEqual(by_title["Solo torre 2"]["totalApartments"], 2)
        self.assertEqual(by_title["Solo torre 2"]["towerName"], "Torre 2")
        self.assertEqual(by_title["Para todos"]["totalApartments"], 3)
        self.assertIsNone(by_title["Para todos"]["towerName"])

    def test_a_resident_without_apartment_only_sees_announcements_for_everyone(self):
        homeless = self.user("RESIDENT", "sin-apto-anuncios@test.local")
        db.session.commit()
        for_everyone = self.publish("Para todos")
        self.publish("Solo torre 1", towerId=self.tower_1)

        self.assertEqual(self.listed_ids(homeless), [for_everyone])

    def test_tower_must_exist_and_be_active(self):
        for tower_id in (9999, True, "1", 0):
            with self.subTest(tower_id=tower_id):
                response = self.client.post(
                    "/api/announcements",
                    json={
                        "title": "Aviso", "message": "Texto.", "category": "urgente",
                        "towerId": tower_id,
                    },
                    headers=self.headers(self.admin),
                )
                self.assertEqual(response.status_code, 400)
        self.assertEqual(Announcement.query.count(), 0)


class AnnouncementExpiryTests(AnnouncementTestCase):
    """HU-060: pasada su fecha de vencimiento, el comunicado sale de la lista y queda en «Archivados»."""

    def test_expired_announcement_leaves_the_main_list_and_goes_to_archived(self):
        current = self.publish("Vigente")
        archived = self.expired_announcement()

        self.assertEqual(self.listed_ids(self.resident), [current])
        self.assertEqual(self.listed_ids(self.resident, "?archived=true"), [archived])
        self.assertEqual(self.listed_ids(self.admin, "?archived=true"), [archived])

    def test_the_expiry_day_itself_is_still_current(self):
        today = colombia_today()
        last_day = self.publish("Vence hoy", expiresAt=today.isoformat())

        self.assertEqual(self.listed_ids(self.resident), [last_day])
        self.assertEqual(self.listed_ids(self.resident, "?archived=true"), [])

    def test_announcement_without_expiry_never_goes_to_archived(self):
        announcement_id = self.publish("Siempre vigente")
        item = db.session.get(Announcement, announcement_id)
        item.created_at = item.created_at - timedelta(days=900)
        db.session.commit()

        self.assertEqual(self.listed_ids(self.resident), [announcement_id])
        self.assertEqual(self.listed_ids(self.resident, "?archived=true"), [])

    def test_the_payload_shows_the_expiry_and_whether_it_already_passed(self):
        tomorrow = (colombia_today() + timedelta(days=1)).isoformat()
        self.publish("Vigente", expiresAt=tomorrow)
        self.expired_announcement(days_ago=3)

        current = self.listing(self.resident)["announcements"][0]
        archived = self.listing(self.resident, "?archived=true")["announcements"][0]

        self.assertEqual(current["expiresAt"], tomorrow)
        self.assertFalse(current["isExpired"])
        self.assertTrue(archived["isExpired"])

    def test_expiry_date_cannot_be_in_the_past_or_badly_written(self):
        yesterday = (colombia_today() - timedelta(days=1)).isoformat()
        for value in (yesterday, "mañana", "2026-13-40", 20261231):
            with self.subTest(value=value):
                response = self.client.post(
                    "/api/announcements",
                    json={
                        "title": "Aviso", "message": "Texto.", "category": "asamblea",
                        "expiresAt": value,
                    },
                    headers=self.headers(self.admin),
                )
                self.assertEqual(response.status_code, 400)
        self.assertEqual(Announcement.query.count(), 0)

    def test_retired_announcements_are_not_archived_either(self):
        archived = self.expired_announcement()
        self.retire(archived)

        self.assertEqual(self.listed_ids(self.admin, "?archived=true"), [])
        self.assertIsNotNone(db.session.get(Announcement, archived))

    def test_archived_list_is_paginated(self):
        ids = [self.expired_announcement(days_ago=day) for day in range(1, 6)]

        page = self.listing(self.resident, "?archived=true&pageSize=2&page=2")

        self.assertEqual(page["total"], 5)
        self.assertEqual(page["totalPages"], 3)
        self.assertEqual(len(page["announcements"]), 2)
        self.assertEqual(
            {item["id"] for item in self.listing(self.resident, "?archived=true&pageSize=200")["announcements"]},
            set(ids),
        )
        self.assertEqual(
            self.client.get(
                "/api/announcements?pageSize=0", headers=self.headers(self.resident)
            ).status_code,
            400,
        )


if __name__ == "__main__":
    unittest.main()
