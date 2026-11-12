"""Pruebas de la revisión de adjuntos que llegan a la API: el tipo se reconoce por los primeros bytes,
no pueden pesar más de 6 MB y los documentos PDF solo se aceptan en PQRS, reservas y comunicados."""

import base64
import unittest

import env_setup  # noqa: F401  (va antes de importar la app)

from models import Announcement, PackageItem, Pqrs, PqrsMessage
from services.media import MAX_MEDIA_BYTES, check_attachment, decode_media
from test_pqrs import PqrsTestCase

PNG = b"\x89PNG\r\n\x1a\n" + b"foto"
JPEG = b"\xff\xd8\xff\xe0" + b"foto"
# Así empieza un audio grabado en el celular: MP4 con la misma marca que un video.
PHONE_AUDIO = b"\x00\x00\x00\x18ftypmp42" + b"audio"
WEBM = b"\x1a\x45\xdf\xa3" + b"webm"
PDF = b"%PDF-1.7 acta de la asamblea"
SVG = b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>"


def data_url(raw, mime="application/octet-stream"):
    return f"data:{mime};base64," + base64.b64encode(raw).decode()


class CheckAttachmentTests(unittest.TestCase):
    def test_the_real_type_comes_from_the_bytes_and_replaces_the_declared_one(self):
        for raw, declared, kind, mime in (
            (PNG, "image/jpeg", "image", "image/png"),
            (JPEG, "image/png", "image", "image/jpeg"),
            (PHONE_AUDIO, "audio/x-m4a", "audio", "audio/mp4"),
            (PHONE_AUDIO, "video/quicktime", "video", "video/mp4"),
            (WEBM, "audio/webm;codecs=opus", "audio", "audio/webm"),
            (b"\xff\xf1\x50\x80" + b"aac", "audio/x-aac", "audio", "audio/aac"),
            (PDF, "application/pdf", "document", "application/pdf"),
        ):
            with self.subTest(kind=kind, mime=mime):
                value, error = check_attachment(data_url(raw, declared), kind, allow_document=True)
                self.assertIsNone(error)
                self.assertEqual(value, data_url(raw, mime))

    def test_a_file_that_is_not_what_it_says_is_refused(self):
        for raw, kind, words in (
            (PDF, "image", "no es una foto"),
            (JPEG, "video", "no es un video"),
            (PNG, "audio", "no es un audio"),
            (PNG, "document", "no es un documento PDF"),
            (SVG, "image", "no es una foto"),
            (b"<html><script>x()</script></html>", "video", "no es un video"),
        ):
            with self.subTest(kind=kind, words=words):
                value, error = check_attachment(data_url(raw), kind, allow_document=True)
                self.assertIsNone(value)
                self.assertIn(words, error)

    def test_a_pdf_only_where_documents_are_allowed(self):
        value, error = check_attachment(data_url(PDF, "application/pdf"), "document")

        self.assertIsNone(value)
        self.assertEqual(error, "Aquí solo se pueden adjuntar fotos, videos o audios.")

    def test_more_than_six_megabytes_is_refused_with_the_weight(self):
        heavy = JPEG + b"0" * MAX_MEDIA_BYTES

        value, error = check_attachment(data_url(heavy, "image/jpeg"), "image")

        self.assertIsNone(value)
        self.assertIn("pesa 6,0 MB y el máximo es 6 MB", error)
        # Justo en el límite sí pasa.
        exact = JPEG + b"0" * (MAX_MEDIA_BYTES - len(JPEG))
        self.assertIsNone(check_attachment(data_url(exact, "image/jpeg"), "image")[1])

    def test_links_broken_text_and_empty_files_are_refused(self):
        for value, words in (
            ("https://otro-sitio.test/foto.jpg", "no como enlace"),
            ("data:image/png," + base64.b64encode(PNG).decode(), "no como enlace"),
            ("data:image/png;base64,!!!no-es-base64!!!", "No se pudo leer"),
            ("data:image/png;base64,", "vacío"),
            (12345, "debe ser un archivo"),
        ):
            with self.subTest(value=str(value)[:30]):
                result, error = check_attachment(value, "image")
                self.assertIsNone(result)
                self.assertIn(words, error)

    def test_line_breaks_inside_the_base64_are_tolerated(self):
        payload = base64.b64encode(PNG + b"x" * 200).decode()
        wrapped = "\n".join(payload[i:i + 76] for i in range(0, len(payload), 76))

        value, error = check_attachment("data:image/png;base64," + wrapped, "image")

        self.assertIsNone(error)
        self.assertEqual(value, data_url(PNG + b"x" * 200, "image/png"))

    def test_a_saved_pdf_is_read_back_only_if_it_really_is_one(self):
        self.assertEqual(decode_media(data_url(PDF, "application/pdf")), (PDF, "application/pdf"))
        self.assertIsNone(decode_media(data_url(b"<html></html>", "application/pdf")))


class AttachmentRoutesTests(PqrsTestCase):
    def post(self, path, user, body):
        return self.client.post(path, headers=self.auth(user), json=body)

    def test_a_resident_can_file_a_pqrs_with_a_pdf(self):
        response = self.post("/api/pqrs", self.resident, {
            "subject": "Cobro doble", "message": "Adjunto el recibo.", "category": "Petición",
            "mediaUrl": data_url(PDF, "application/pdf"), "mediaType": "document",
        })

        self.assertEqual(response.status_code, 201, response.get_json())
        pqrs = Pqrs.query.one()
        self.assertEqual((pqrs.media_type, pqrs.media_url), ("document", data_url(PDF, "application/pdf")))

    def test_a_recorded_audio_is_saved_with_its_real_type(self):
        pqrs = self.make_pqrs()

        response = self.post(f"/api/pqrs/{pqrs.id}/messages", self.resident, {
            "mediaUrl": data_url(PHONE_AUDIO, "audio/aac"), "mediaType": "audio",
        })

        self.assertEqual(response.status_code, 201, response.get_json())
        message = PqrsMessage.query.filter(PqrsMessage.media_url.is_not(None)).one()
        self.assertEqual(message.media_url, data_url(PHONE_AUDIO, "audio/mp4"))

    def test_a_disguised_file_is_refused_and_nothing_is_saved(self):
        pqrs = self.make_pqrs()
        before = PqrsMessage.query.count()

        response = self.post(f"/api/pqrs/{pqrs.id}/messages", self.resident, {
            "message": "Mira la foto", "mediaUrl": data_url(SVG, "image/png"), "mediaType": "image",
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn("no es una foto", response.get_json()["error"])
        self.assertEqual(PqrsMessage.query.count(), before)

    def test_the_porteria_does_not_take_documents(self):
        response = self.post("/api/packages", self.guard, {
            "residentId": self.resident.id, "description": "Caja",
            "mediaUrl": data_url(PDF, "application/pdf"), "mediaType": "document",
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Aquí solo se pueden adjuntar fotos, videos o audios.")
        self.assertEqual(PackageItem.query.count(), 0)

    def test_an_announcement_can_carry_a_pdf_but_not_a_heavy_file(self):
        body = {"title": "Acta", "message": "Acta de la asamblea.", "category": "asamblea"}
        heavy = self.post("/api/announcements", self.admin, {
            **body, "mediaUrl": data_url(JPEG + b"0" * MAX_MEDIA_BYTES, "image/jpeg"), "mediaType": "image",
        })
        published = self.post("/api/announcements", self.admin, {
            **body, "mediaUrl": data_url(PDF, "application/pdf"), "mediaType": "document",
        })

        self.assertEqual(heavy.status_code, 400)
        self.assertIn("el máximo es 6 MB", heavy.get_json()["error"])
        self.assertEqual(published.status_code, 201, published.get_json())
        self.assertEqual(Announcement.query.one().media_type, "document")


if __name__ == "__main__":
    unittest.main()
