"""Pruebas de la lista liviana de reservas (GET /api/reservations?view=summary), de sus filtros y de los
números por estado, de la lectura de una sola reserva (GET /api/reservations/<id>) y de los adjuntos de
su conversación (HU-079)."""

import base64
import unittest
from datetime import timedelta

import env_setup  # noqa: F401  (va antes de importar la app)

from extensions import db
from models import CommonArea, Reservation, ReservationMessage
from services import reservation_view
from test_reservations import ReservationTestCase
from time_utils import colombia_today

#: Una foto de mentira bastante grande como para notar si viaja donde no debe.
PHOTO = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff" + b"x" * 5000).decode()


class SummaryTestCase(ReservationTestCase):
    def day(self, offset):
        """La fecha de hoy (en Colombia) más ``offset`` días, como AAAA-MM-DD."""
        return (colombia_today() + timedelta(days=offset)).isoformat()

    def add(self, resident=None, offset=3, slot="10:00-12:00", status="pendiente", area=None,
            attendees=None, archived=False, by_admin=False, messages=()):
        """Una reserva guardada directamente, con su conversación: ``messages`` son pares (texto, adjunto)."""
        resident = resident or self.resident
        reservation = Reservation(
            resident_id=resident.id, common_area_id=(area or self.area).id, date=self.day(offset),
            time_slot=slot, attendees=attendees, status=status, is_archived=archived,
            created_by_admin_id=self.admin.id if by_admin else None,
        )
        db.session.add(reservation)
        db.session.flush()
        for text, media in messages:
            reservation.messages.append(ReservationMessage(
                author_id=resident.id, author_role="RESIDENT", message=text,
                media_url=media, media_type="image" if media else None,
            ))
        db.session.commit()
        return reservation

    def summary(self, user=None, **params):
        response = self.client.get(
            "/api/reservations", headers=self.headers(user or self.admin),
            query_string={"view": "summary", **params},
        )
        return response, response.get_json()

    def ids(self, body):
        return [row["id"] for row in body["reservations"]]


class SummaryListTests(SummaryTestCase):
    def test_rows_are_light_and_carry_what_the_list_shows(self):
        reservation = self.add(
            attendees=12, by_admin=True,
            messages=[("Necesito el salón para un cumpleaños.", None), ("Adjunto el recibo.", PHOTO)],
        )

        response, body = self.summary()

        self.assertEqual(response.status_code, 200)
        self.assertEqual((body["page"], body["pageSize"], body["total"], body["totalPages"]), (1, 25, 1, 1))
        row = body["reservations"][0]
        self.assertEqual(row["id"], reservation.id)
        self.assertEqual(row["commonAreaId"], self.area.id)
        self.assertEqual(row["commonAreaName"], "Salón social")
        self.assertEqual(row["date"], self.day(3))
        self.assertEqual(row["timeSlot"], "10:00-12:00")
        self.assertEqual(row["attendees"], 12)
        self.assertEqual(row["status"], "pendiente")
        self.assertFalse(row["isArchived"])
        self.assertEqual(row["residentId"], self.resident.id)
        self.assertEqual(row["residentName"], "Resident")
        self.assertEqual(row["apartment"], "Torre 1 · Apto 101")
        self.assertTrue(row["createdByAdministration"])
        self.assertEqual(row["messageCount"], 2)
        self.assertEqual(row["attachmentCount"], 1)
        self.assertIsNotNone(row["createdAt"])
        # Nada pesado: ni la conversación ni la foto.
        for heavy in ("messages", "mediaUrl"):
            self.assertNotIn(heavy, row)
        self.assertNotIn("data:image", response.get_data(as_text=True))

    def test_a_reservation_without_messages_counts_zero(self):
        self.add()
        _response, body = self.summary()
        row = body["reservations"][0]
        self.assertEqual((row["messageCount"], row["attachmentCount"]), (0, 0))
        self.assertFalse(row["createdByAdministration"])

    def test_an_unknown_view_is_rejected(self):
        response = self.client.get(
            "/api/reservations", headers=self.headers(self.admin), query_string={"view": "completa"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "El parámetro 'view' solo acepta el valor 'summary'.")

    def test_the_full_list_of_the_app_is_unchanged(self):
        self.add(messages=[("Hola", PHOTO)])
        response = self.client.get("/api/reservations", headers=self.headers(self.admin))
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(list(body), ["reservations"])
        message = body["reservations"][0]["messages"][0]
        self.assertEqual(message["mediaUrl"], PHOTO)

    def test_pages_are_cut_by_page_and_page_size(self):
        for offset in range(1, 8):
            self.add(offset=offset, slot=f"{8 + offset:02d}:00-{9 + offset:02d}:00")

        _response, first = self.summary(pageSize=3)
        _response, last = self.summary(pageSize=3, page=3)
        _response, beyond = self.summary(pageSize=3, page=9)

        self.assertEqual((first["total"], first["totalPages"], len(first["reservations"])), (7, 3, 3))
        self.assertEqual((last["page"], len(last["reservations"])), (3, 1))
        self.assertEqual((beyond["total"], beyond["reservations"]), (7, []))

    def test_the_order_puts_what_waits_for_a_decision_first_and_then_what_is_coming(self):
        later = self.add(offset=5, slot="10:00-12:00")
        afternoon = self.add(offset=2, slot="14:00-16:00")
        morning = self.add(offset=2, slot="08:00-10:00")
        legacy = self.add(offset=3, slot="16:00-18:00", status="activa")
        soon = self.add(offset=1, slot="10:00-12:00", status="aprobada")
        far = self.add(offset=4, slot="10:00-12:00", status="aprobada")
        past = self.add(offset=-2, slot="10:00-12:00", status="aprobada")
        rejected = self.add(offset=6, slot="10:00-12:00", status="rechazada")
        cancelled = self.add(offset=-5, slot="10:00-12:00", status="cancelada")

        _response, body = self.summary()

        self.assertEqual(
            self.ids(body),
            [
                # Esperan decisión: la fecha más próxima primero y, el mismo día, la franja más temprana.
                morning.id, afternoon.id, legacy.id, later.id,
                # Aprobadas que todavía no llegan: de la más próxima a la más lejana.
                soon.id, far.id,
                # Lo demás, de la fecha más reciente a la más antigua.
                rejected.id, past.id, cancelled.id,
            ],
        )

    def test_residents_only_see_their_own_reservations_and_guards_none(self):
        mine = self.add()
        self.add(resident=self.other_resident, slot="14:00-16:00")

        _response, resident_view = self.summary(user=self.resident)
        guard_response, _body = self.summary(user=self.guard)

        self.assertEqual(self.ids(resident_view), [mine.id])
        self.assertEqual(resident_view["counts"]["all"], 1)
        self.assertEqual(guard_response.status_code, 403)

    def test_archived_reservations_are_left_out_unless_asked(self):
        visible = self.add()
        archived = self.add(slot="14:00-16:00", archived=True)

        _response, normal = self.summary()
        _response, with_archived = self.summary(includeArchived="true")
        bad_response, _body = self.summary(includeArchived="quizas")

        self.assertEqual(self.ids(normal), [visible.id])
        self.assertEqual(normal["counts"]["all"], 1)
        self.assertEqual(set(self.ids(with_archived)), {visible.id, archived.id})
        self.assertTrue(next(row for row in with_archived["reservations"] if row["id"] == archived.id)["isArchived"])
        self.assertEqual(bad_response.status_code, 400)


class SummaryFilterTests(SummaryTestCase):
    def setUp(self):
        super().setUp()
        self.pool = CommonArea(name="Piscina")
        db.session.add(self.pool)
        db.session.commit()

    def test_the_status_filter_takes_one_state_or_everything_that_waits(self):
        waiting = self.add(slot="08:00-10:00")
        legacy = self.add(slot="10:00-12:00", status="activa")
        approved = self.add(slot="12:00-14:00", status="aprobada")
        rejected = self.add(slot="14:00-16:00", status="rechazada")
        cancelled = self.add(slot="16:00-18:00", status="cancelada")

        for status, expected in (
            ("por_aprobar", {waiting.id, legacy.id}),
            ("pendiente", {waiting.id}),
            ("activa", {legacy.id}),
            ("aprobada", {approved.id}),
            ("rechazada", {rejected.id}),
            ("cancelada", {cancelled.id}),
        ):
            with self.subTest(status=status):
                _response, body = self.summary(status=status)
                self.assertEqual(set(self.ids(body)), expected)
                self.assertEqual(body["total"], len(expected))

    def test_an_unknown_status_is_rejected(self):
        response, body = self.summary(status="olvidada")
        self.assertEqual(response.status_code, 400)
        self.assertIn("El filtro 'status' debe ser", body["error"])

    def test_counts_cover_every_state_whatever_the_status_filter(self):
        self.add(slot="08:00-10:00")
        self.add(slot="10:00-12:00", status="activa")
        self.add(slot="12:00-14:00", status="aprobada")
        self.add(slot="14:00-16:00", status="rechazada")
        self.add(slot="16:00-18:00", status="cancelada")
        self.add(offset=4, slot="16:00-18:00", status="cancelada")

        for params in ({}, {"status": "aprobada"}, {"status": "por_aprobar"}):
            with self.subTest(params=params):
                _response, body = self.summary(**params)
                self.assertEqual(
                    body["counts"], {"pending": 2, "approved": 1, "rejected": 1, "cancelled": 2, "all": 6},
                )

    def test_the_other_filters_also_change_the_counts(self):
        self.add(slot="08:00-10:00")
        self.add(area=self.pool, slot="08:00-10:00", status="aprobada")
        self.add(area=self.pool, offset=4, slot="08:00-10:00", status="cancelada")

        _response, body = self.summary(commonAreaId=self.pool.id)

        self.assertEqual(body["counts"], {"pending": 0, "approved": 1, "rejected": 0, "cancelled": 1, "all": 2})
        self.assertEqual(body["total"], 2)

    def test_filter_by_zone(self):
        hall = self.add()
        pool = self.add(area=self.pool)

        _response, only_pool = self.summary(commonAreaId=self.pool.id)
        _response, only_hall = self.summary(commonAreaId=self.area.id)

        self.assertEqual(self.ids(only_pool), [pool.id])
        self.assertEqual(self.ids(only_hall), [hall.id])

    def test_filter_by_dates_includes_both_ends(self):
        first = self.add(offset=2)
        middle = self.add(offset=4, slot="14:00-16:00")
        last = self.add(offset=6, slot="16:00-18:00")
        outside = self.add(offset=9, slot="08:00-10:00")

        _response, between = self.summary(dateFrom=self.day(2), dateTo=self.day(6))
        _response, one_day = self.summary(dateFrom=self.day(4), dateTo=self.day(4))
        _response, from_only = self.summary(dateFrom=self.day(6))
        _response, to_only = self.summary(dateTo=self.day(2))

        self.assertEqual(set(self.ids(between)), {first.id, middle.id, last.id})
        self.assertEqual(self.ids(one_day), [middle.id])
        self.assertEqual(set(self.ids(from_only)), {last.id, outside.id})
        self.assertEqual(self.ids(to_only), [first.id])

    def test_bad_dates_are_rejected(self):
        for params in ({"dateFrom": "13/11/2026"}, {"dateTo": "mañana"}, {"dateFrom": "2026-02-30"}):
            with self.subTest(params=params):
                response, body = self.summary(**params)
                self.assertEqual(response.status_code, 400)
                self.assertIn("debe ser una fecha con formato AAAA-MM-DD", body["error"])
        response, body = self.summary(dateFrom=self.day(5), dateTo=self.day(2))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(body["error"], "La fecha 'dateFrom' no puede ser posterior a 'dateTo'.")

    def test_search_by_resident_apartment_or_zone(self):
        mine = self.add()
        theirs = self.add(resident=self.other_resident, area=self.pool, slot="14:00-16:00")

        for term, expected in (
            ("resident", {mine.id}),        # el nombre, sin importar mayúsculas
            ("Apto 202", {theirs.id}),      # el apartamento
            ("202", {theirs.id}),
            ("Salón", {mine.id}),           # la zona
            ("pisci", {theirs.id}),
            ("nadie", set()),
        ):
            with self.subTest(term=term):
                _response, body = self.summary(q=term)
                self.assertEqual(set(self.ids(body)), expected)
        # «search» es otro nombre del mismo filtro.
        _response, body = self.summary(search="Piscina")
        self.assertEqual(self.ids(body), [theirs.id])

    def test_filters_also_work_on_the_full_list(self):
        mine = self.add()
        self.add(area=self.pool)

        response = self.client.get(
            "/api/reservations", headers=self.headers(self.admin),
            query_string={"commonAreaId": self.area.id, "status": "por_aprobar"},
        )

        self.assertEqual([item["id"] for item in response.get_json()["reservations"]], [mine.id])


class SingleReservationTests(SummaryTestCase):
    def test_the_summary_view_hides_attachments_but_says_which_messages_have_them(self):
        reservation = self.add(messages=[("Sin foto", None), ("Con foto", PHOTO)])

        response = self.client.get(
            f"/api/reservations/{reservation.id}", headers=self.headers(self.admin),
            query_string={"view": "summary"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["reservation"]
        self.assertEqual([m["hasMedia"] for m in data["messages"]], [False, True])
        self.assertTrue(all("mediaUrl" not in m for m in data["messages"]))
        self.assertEqual(data["messages"][1]["mediaType"], "image")
        self.assertNotIn("data:image", response.get_data(as_text=True))
        self.assertEqual(data["residentName"], "Resident")
        self.assertFalse(data["slotTaken"])

    def test_without_the_view_it_is_the_full_reservation(self):
        reservation = self.add(messages=[("Con foto", PHOTO)])

        response = self.client.get(f"/api/reservations/{reservation.id}", headers=self.headers(self.admin))

        data = response.get_json()["reservation"]
        self.assertEqual(data["messages"][0]["mediaUrl"], PHOTO)
        self.assertNotIn("slotTaken", data)

    def test_an_unknown_view_is_rejected(self):
        reservation = self.add()
        response = self.client.get(
            f"/api/reservations/{reservation.id}", headers=self.headers(self.admin), query_string={"view": "x"},
        )
        self.assertEqual(response.status_code, 400)

    def test_residents_read_only_their_own_and_guards_none(self):
        mine = self.add()
        theirs = self.add(resident=self.other_resident, slot="14:00-16:00")

        own = self.client.get(f"/api/reservations/{mine.id}", headers=self.headers(self.resident))
        other = self.client.get(f"/api/reservations/{theirs.id}", headers=self.headers(self.resident))
        guard = self.client.get(f"/api/reservations/{mine.id}", headers=self.headers(self.guard))
        missing = self.client.get("/api/reservations/99999", headers=self.headers(self.admin))

        self.assertEqual(own.status_code, 200)
        self.assertEqual(other.status_code, 404)
        self.assertEqual(guard.status_code, 403)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.get_json()["error"], "Reserva no encontrada")

    def test_it_warns_when_the_slot_of_a_waiting_reservation_is_taken(self):
        approved = self.add(slot="10:00-12:00", status="aprobada")
        clash = self.add(resident=self.other_resident, slot="10:00-12:00")
        free = self.add(resident=self.other_resident, slot="14:00-16:00", offset=3)
        elsewhere = self.add(resident=self.other_resident, slot="10:00-12:00", offset=5)

        def taken(reservation):
            response = self.client.get(
                f"/api/reservations/{reservation.id}", headers=self.headers(self.admin),
                query_string={"view": "summary"},
            )
            return response.get_json()["reservation"]["slotTaken"]

        self.assertTrue(taken(clash))
        self.assertFalse(taken(free))
        self.assertFalse(taken(elsewhere))
        # La que ya está aprobada no es «una pendiente con la franja ocupada».
        self.assertFalse(taken(approved))


class AttachmentTests(SummaryTestCase):
    def test_an_attachment_comes_back_as_bytes_and_type(self):
        reservation = self.add(messages=[("Sin foto", None), ("Con foto", PHOTO)])
        no_photo, with_photo = reservation.messages

        self.assertEqual(
            reservation_view.attachment(reservation.id, with_photo.id),
            (b"\xff\xd8\xff" + b"x" * 5000, "image/jpeg"),
        )
        self.assertIsNone(reservation_view.attachment(reservation.id, no_photo.id))

    def test_a_message_of_another_reservation_or_a_missing_one_is_not_found(self):
        mine = self.add(messages=[("Con foto", PHOTO)])
        other = self.add(resident=self.other_resident, slot="14:00-16:00", messages=[("Con foto", PHOTO)])

        self.assertIsNone(reservation_view.attachment(mine.id, other.messages[0].id))
        self.assertIsNone(reservation_view.attachment(mine.id, 99999))
        self.assertIsNone(reservation_view.attachment(99999, mine.messages[0].id))

    def test_only_images_videos_and_audios_are_served(self):
        svg = "data:image/svg+xml;base64," + base64.b64encode(b"<svg onload='x()'/>").decode()
        page = "data:text/html;base64," + base64.b64encode(b"<script>x()</script>").decode()
        remote = "https://ejemplo.com/foto.jpg"
        reservation = self.add(messages=[("a", svg), ("b", page), ("c", remote)])

        for message in reservation.messages:
            with self.subTest(media=message.media_url[:20]):
                self.assertIsNone(reservation_view.attachment(reservation.id, message.id))


if __name__ == "__main__":
    unittest.main()
