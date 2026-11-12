"""Pruebas de la lista liviana de PQRS (GET /api/pqrs?view=summary), del filtro por semáforo, de la
lectura de una sola PQRS (GET /api/pqrs/<id>) y de la lectura de sus adjuntos (HU-078)."""

import base64
import unittest
from datetime import timedelta

import env_setup  # noqa: F401  (va antes de importar la app)

from extensions import db
from models import Pqrs, PqrsMessage
from services import pqrs_service
from services.pqrs_rules import pqrs_semaphore, running_semaphore
from test_pqrs import PqrsTestCase
from time_utils import colombia_day_to_utc, colombia_today

#: Una foto de mentira bastante grande como para notar si viaja donde no debe.
PHOTO = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff" + b"x" * 5000).decode()


def days_old_with_color(color):
    """Cuántos días atrás se radicó una PQRS para que hoy tenga ese color de semáforo."""
    today = colombia_today()
    for days in range(0, 60):
        if pqrs_semaphore(today - timedelta(days=days), today, "Daño")["color"] == color:
            return days
    raise AssertionError(f"ningún día da el color {color}")


class SummaryTestCase(PqrsTestCase):
    def add(self, resident=None, status="abierta", category="Daño", days_ago=0, subject="Ascensor",
            media=None, archived=False):
        """Una PQRS radicada hace ``days_ago`` días (a las 3 de la tarde de Colombia)."""
        resident = resident or self.resident
        created = colombia_day_to_utc(colombia_today() - timedelta(days=days_ago)) + timedelta(hours=15)
        pqrs = Pqrs(
            resident_id=resident.id, category=category, subject=subject, message="Descripción larga " * 20,
            status=status, created_at=created, updated_at=created, is_archived=archived,
            media_url=media, media_type="image" if media else None,
        )
        db.session.add(pqrs)
        db.session.flush()
        pqrs.conversation.append(PqrsMessage(
            author_id=resident.id, author_role="RESIDENT", message=pqrs.message,
            media_url=media, media_type="image" if media else None,
        ))
        db.session.commit()
        return pqrs

    def summary(self, user=None, **params):
        response = self.client.get(
            "/api/pqrs", headers=self.auth(user or self.admin), query_string={"view": "summary", **params},
        )
        return response, response.get_json()


class SummaryListTests(SummaryTestCase):
    def test_rows_are_light_and_carry_what_the_inbox_shows(self):
        pqrs = self.add(subject="Fuga de agua", media=PHOTO, days_ago=2)

        response, body = self.summary()

        self.assertEqual(response.status_code, 200)
        self.assertEqual((body["page"], body["total"], body["totalPages"]), (1, 1, 1))
        row = body["pqrs"][0]
        self.assertEqual(row["id"], pqrs.id)
        self.assertEqual(row["radicado"], pqrs.radicado)
        self.assertEqual(row["subject"], "Fuga de agua")
        self.assertEqual(row["category"], "Daño")
        self.assertEqual(row["status"], "abierta")
        self.assertEqual(row["residentName"], "Resident")
        self.assertEqual(row["apartment"], "Torre 1 · Apto 101")
        self.assertEqual(row["residentId"], self.resident.id)
        self.assertFalse(row["createdByAdministration"])
        self.assertFalse(row["isArchived"])
        self.assertTrue(row["hasMedia"])
        self.assertEqual(row["attachmentCount"], 1)
        self.assertIsNotNone(row["createdAt"])
        # Nada pesado: ni el texto largo, ni la conversación, ni la foto.
        for heavy in ("message", "messages", "mediaUrl", "adminResponse"):
            self.assertNotIn(heavy, row)
        self.assertNotIn(PHOTO[:60], response.get_data(as_text=True))

    def test_rows_carry_the_deadline_in_business_days(self):
        pqrs = self.add(days_ago=days_old_with_color("rojo"))

        _response, body = self.summary()

        row = body["pqrs"][0]
        expected = running_semaphore("abierta", pqrs.created_at, "Daño")
        self.assertEqual(row["semaphore"], "rojo")
        self.assertEqual(row["daysRemaining"], expected["daysRemaining"])
        self.assertLess(row["daysRemaining"], 0)
        self.assertEqual(row["dueDate"], expected["dueDate"])

    def test_a_resolved_pqrs_has_no_deadline(self):
        self.add(status="resuelta", days_ago=days_old_with_color("rojo"))

        _response, body = self.summary()

        row = body["pqrs"][0]
        self.assertEqual(row["status"], "resuelta")
        self.assertIsNone(row["semaphore"])
        self.assertIsNone(row["daysRemaining"])
        self.assertIsNone(row["dueDate"])

    def test_one_pqrs_created_by_the_administration_says_so(self):
        pqrs = self.add()
        pqrs.created_by_admin_id = self.admin.id
        db.session.commit()

        _response, body = self.summary()

        self.assertTrue(body["pqrs"][0]["createdByAdministration"])

    def test_attachments_are_counted_once_even_though_the_first_message_repeats_the_photo(self):
        pqrs = self.add(media=PHOTO)
        pqrs.conversation.append(PqrsMessage(
            author_id=self.admin.id, author_role="ADMIN", message="Mira", media_url=PHOTO, media_type="image",
        ))
        self.add(subject="Sin foto")
        db.session.commit()

        _response, body = self.summary()

        by_subject = {row["subject"]: row for row in body["pqrs"]}
        self.assertEqual(by_subject["Ascensor"]["attachmentCount"], 2)
        self.assertEqual(by_subject["Sin foto"]["attachmentCount"], 0)
        self.assertFalse(by_subject["Sin foto"]["hasMedia"])

    def test_a_request_with_a_photo_but_no_conversation_counts_one(self):
        pqrs = self.add(media=PHOTO)
        PqrsMessage.query.filter_by(pqrs_id=pqrs.id).delete()
        db.session.commit()

        _response, body = self.summary()

        self.assertEqual(body["pqrs"][0]["attachmentCount"], 1)

    def test_unresolved_first_oldest_first_then_resolved_newest_first(self):
        resolved_old = self.add(subject="Resuelta vieja", status="resuelta", days_ago=9)
        running_new = self.add(subject="En curso nueva", status="en_proceso", days_ago=1)
        resolved_new = self.add(subject="Resuelta nueva", status="resuelta", days_ago=3)
        running_old = self.add(subject="En curso vieja", status="abierta", days_ago=6)

        _response, body = self.summary()

        self.assertEqual(
            [row["id"] for row in body["pqrs"]],
            [running_old.id, running_new.id, resolved_new.id, resolved_old.id],
        )

    def test_it_is_paginated(self):
        for number in range(5):
            self.add(subject=f"Asunto {number}", days_ago=number)

        _response, first = self.summary(pageSize=2)
        _response, last = self.summary(pageSize=2, page=3)

        self.assertEqual((first["total"], first["totalPages"], len(first["pqrs"])), (5, 3, 2))
        self.assertEqual((last["page"], len(last["pqrs"])), (3, 1))
        self.assertEqual(last["pqrs"][0]["subject"], "Asunto 0")

    def test_an_invalid_page_or_size_is_rejected(self):
        for params in ({"page": 0}, {"pageSize": 0}, {"pageSize": 101}):
            response, body = self.summary(**params)
            self.assertEqual(response.status_code, 400, params)
            self.assertIn("pageSize", body["error"])

    def test_an_unknown_view_is_rejected(self):
        response = self.client.get("/api/pqrs?view=otra", headers=self.auth(self.admin))
        self.assertEqual(response.status_code, 400)
        self.assertIn("summary", response.get_json()["error"])

    def test_the_default_list_keeps_its_old_shape(self):
        self.add(media=PHOTO)

        response = self.client.get("/api/pqrs", headers=self.auth(self.admin))

        body = response.get_json()
        self.assertEqual(list(body), ["pqrs"])
        self.assertEqual(body["pqrs"][0]["mediaUrl"], PHOTO)
        self.assertEqual(len(body["pqrs"][0]["messages"]), 1)


class SummaryFilterTests(SummaryTestCase):
    def setUp(self):
        super().setUp()
        self.resident.last_name = "Gómez"
        db.session.commit()

    def subjects(self, **params):
        response, body = self.summary(**params)
        self.assertEqual(response.status_code, 200, body)
        return sorted(row["subject"] for row in body["pqrs"])

    def test_by_status_and_category(self):
        self.add(subject="A", status="abierta", category="Daño")
        self.add(subject="B", status="en_proceso", category="Queja")
        self.add(subject="C", status="resuelta", category="Queja")

        self.assertEqual(self.subjects(status="en_proceso"), ["B"])
        self.assertEqual(self.subjects(category="Queja"), ["B", "C"])
        self.assertEqual(self.subjects(status="resuelta", category="Queja"), ["C"])

    def test_an_unknown_status_is_rejected(self):
        response, _body = self.summary(status="rara")
        self.assertEqual(response.status_code, 400)

    def test_by_text_radicado_resident_and_apartment(self):
        first = self.add(subject="Ruido en el piso 3")
        self.add(subject="Basuras", resident=self.other_resident)

        self.assertEqual(self.subjects(search="ruido"), ["Ruido en el piso 3"])
        self.assertEqual(self.subjects(search=first.radicado), ["Ruido en el piso 3"])
        self.assertEqual(self.subjects(search="Resident Gómez"), ["Ruido en el piso 3"])
        self.assertEqual(self.subjects(search="Apto 202"), ["Basuras"])
        self.assertEqual(self.subjects(search="nada de nada"), [])

    def test_by_resident(self):
        self.add(subject="Mía")
        self.add(subject="De otro", resident=self.other_resident)

        self.assertEqual(self.subjects(residentId=self.other_resident.id), ["De otro"])

    def test_archived_ones_are_left_out_unless_asked_for(self):
        self.add(subject="Vigente")
        self.add(subject="Archivada", archived=True)

        self.assertEqual(self.subjects(), ["Vigente"])
        self.assertEqual(self.subjects(includeArchived="true"), ["Archivada", "Vigente"])

    def test_by_deadline_color(self):
        self.add(subject="Vencida", days_ago=days_old_with_color("rojo"))
        self.add(subject="Por vencer", days_ago=days_old_with_color("amarillo"))
        self.add(subject="En plazo", days_ago=days_old_with_color("verde"))
        self.add(subject="Resuelta vieja", status="resuelta", days_ago=days_old_with_color("rojo"))

        self.assertEqual(self.subjects(semaphore="rojo"), ["Vencida"])
        self.assertEqual(self.subjects(semaphore="amarillo"), ["Por vencer"])
        self.assertEqual(self.subjects(semaphore="verde"), ["En plazo"])

    def test_the_deadline_filter_combines_with_the_others(self):
        self.add(subject="Vencida mía", days_ago=days_old_with_color("rojo"))
        self.add(subject="Vencida de otro", days_ago=days_old_with_color("rojo"), resident=self.other_resident)

        self.assertEqual(
            self.subjects(semaphore="rojo", residentId=self.other_resident.id), ["Vencida de otro"],
        )
        self.assertEqual(self.subjects(semaphore="rojo", status="resuelta"), [])

    def test_the_deadline_filter_reports_the_right_total(self):
        for _ in range(3):
            self.add(days_ago=days_old_with_color("rojo"))
        self.add(days_ago=days_old_with_color("verde"))

        _response, body = self.summary(semaphore="rojo", pageSize=2)

        self.assertEqual((body["total"], body["totalPages"], len(body["pqrs"])), (3, 2, 2))

    def test_an_unknown_deadline_color_is_rejected(self):
        response, body = self.summary(semaphore="azul")
        self.assertEqual(response.status_code, 400)
        self.assertIn("verde, amarillo o rojo", body["error"])

    def test_the_deadline_filter_also_works_on_the_full_list(self):
        self.add(subject="Vencida", days_ago=days_old_with_color("rojo"))
        self.add(subject="En plazo", days_ago=days_old_with_color("verde"))

        response = self.client.get("/api/pqrs?semaphore=rojo", headers=self.auth(self.admin))

        self.assertEqual([item["subject"] for item in response.get_json()["pqrs"]], ["Vencida"])


class SummaryPermissionTests(SummaryTestCase):
    def test_a_resident_only_sees_their_own(self):
        self.add(subject="Mía")
        self.add(subject="De otro", resident=self.other_resident)

        response, body = self.summary(user=self.resident)

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["subject"] for row in body["pqrs"]], ["Mía"])

    def test_a_resident_cannot_filter_by_another_resident(self):
        response, _body = self.summary(user=self.resident, residentId=self.other_resident.id)
        self.assertEqual(response.status_code, 403)

    def test_a_guard_has_no_access(self):
        response, _body = self.summary(user=self.guard)
        self.assertEqual(response.status_code, 403)

    def test_it_needs_a_session(self):
        response = self.client.get("/api/pqrs?view=summary")
        self.assertEqual(response.status_code, 401)


class OnePqrsTests(SummaryTestCase):
    def test_the_administration_reads_any_pqrs(self):
        pqrs = self.add(media=PHOTO)

        response = self.client.get(f"/api/pqrs/{pqrs.id}", headers=self.auth(self.admin))

        self.assertEqual(response.status_code, 200)
        body = response.get_json()["pqrs"]
        self.assertEqual(body["id"], pqrs.id)
        self.assertEqual(body["mediaUrl"], PHOTO)
        self.assertEqual(len(body["messages"]), 1)

    def test_the_summary_view_leaves_out_the_attachments(self):
        pqrs = self.add(media=PHOTO)
        pqrs.conversation.append(PqrsMessage(author_id=self.admin.id, author_role="ADMIN", message="Hola"))
        db.session.commit()

        response = self.client.get(f"/api/pqrs/{pqrs.id}?view=summary", headers=self.auth(self.admin))

        body = response.get_json()["pqrs"]
        self.assertNotIn("mediaUrl", body)
        self.assertTrue(body["hasMedia"])
        self.assertEqual([message["hasMedia"] for message in body["messages"]], [True, False])
        for message in body["messages"]:
            self.assertNotIn("mediaUrl", message)
        self.assertEqual(body["mediaType"], "image")
        self.assertNotIn(PHOTO[:60], response.get_data(as_text=True))
        self.assertEqual(body["residentName"], "Resident")
        self.assertEqual(body["messages"][1]["authorRole"], "ADMIN")

    def test_a_resident_reads_only_their_own(self):
        mine = self.add()
        theirs = self.add(resident=self.other_resident)

        own = self.client.get(f"/api/pqrs/{mine.id}", headers=self.auth(self.resident))
        foreign = self.client.get(f"/api/pqrs/{theirs.id}", headers=self.auth(self.resident))

        self.assertEqual(own.status_code, 200)
        self.assertEqual(foreign.status_code, 404)
        self.assertEqual(foreign.get_json()["error"], "PQRS no encontrada")

    def test_an_unknown_pqrs_is_not_found(self):
        response = self.client.get("/api/pqrs/9999", headers=self.auth(self.admin))
        self.assertEqual(response.status_code, 404)

    def test_a_guard_and_a_stranger_cannot_read_it(self):
        pqrs = self.add()
        self.assertEqual(self.client.get(f"/api/pqrs/{pqrs.id}", headers=self.auth(self.guard)).status_code, 403)
        self.assertEqual(self.client.get(f"/api/pqrs/{pqrs.id}").status_code, 401)

    def test_an_unknown_view_is_rejected(self):
        pqrs = self.add()
        response = self.client.get(f"/api/pqrs/{pqrs.id}?view=otra", headers=self.auth(self.admin))
        self.assertEqual(response.status_code, 400)

    def test_the_batch_route_still_answers_next_to_the_new_one(self):
        # «/pqrs/batch/respond» no se confunde con «/pqrs/<id>».
        response = self.client.post("/api/pqrs/batch/respond", headers=self.auth(self.admin), json={})
        self.assertEqual(response.status_code, 400)


class AttachmentReadingTests(SummaryTestCase):
    def test_an_image_video_or_audio_is_decoded(self):
        raw = b"\x89PNG\r\n\x1a\n" + b"abc"
        value = "data:image/png;base64," + base64.b64encode(raw).decode()
        self.assertEqual(pqrs_service.decode_media(value), (raw, "image/png"))
        for mime in ("video/mp4", "audio/mpeg", "audio/x-m4a", "audio/webm;codecs=opus"):
            decoded = pqrs_service.decode_media(f"data:{mime};base64," + base64.b64encode(b"datos").decode())
            self.assertEqual(decoded, (b"datos", mime.split(";")[0]), mime)

    def test_line_breaks_inside_the_base64_are_tolerated(self):
        payload = base64.b64encode(b"x" * 200).decode()
        wrapped = "\n".join(payload[i:i + 76] for i in range(0, len(payload), 76))
        self.assertEqual(pqrs_service.decode_media("data:image/png;base64," + wrapped)[0], b"x" * 200)

    def test_anything_else_is_refused(self):
        good = base64.b64encode(b"datos").decode()
        refused = (
            None,
            "",
            "javascript:alert(1)",
            "https://otro-sitio.test/foto.png",
            f"data:image/svg+xml;base64,{good}",
            f"data:text/html;base64,{good}",
            f"data:application/pdf;base64,{good}",
            f"data:image/png,{good}",
            "data:image/png;base64,!!!no-es-base64!!!",
            "data:image/png;base64,",
        )
        for value in refused:
            self.assertIsNone(pqrs_service.decode_media(value), value)

    def test_the_attachment_of_a_request_and_of_a_message(self):
        message_photo = "data:audio/mpeg;base64," + base64.b64encode(b"audio").decode()
        pqrs = self.add(media=PHOTO)
        extra = PqrsMessage(
            author_id=self.admin.id, author_role="ADMIN", message="Nota", media_url=message_photo, media_type="audio",
        )
        pqrs.conversation.append(extra)
        db.session.commit()

        self.assertEqual(pqrs_service.attachment(pqrs.id)[1], "image/jpeg")
        self.assertEqual(pqrs_service.attachment(pqrs.id, extra.id), (b"audio", "audio/mpeg"))
        # Un mensaje de otra PQRS, o uno que no existe, no se entrega.
        other = self.add(subject="Otra")
        self.assertIsNone(pqrs_service.attachment(other.id, extra.id))
        self.assertIsNone(pqrs_service.attachment(pqrs.id, 99999))
        self.assertIsNone(pqrs_service.attachment(99999))
        self.assertIsNone(pqrs_service.attachment(other.id))


if __name__ == "__main__":
    unittest.main()
