"""Pruebas del permiso de descarga de los archivos adjuntos.

Quien sube un archivo (la administración en un comunicado o en una respuesta, el residente en su PQRS o
en un mensaje) decide si los demás lo pueden descargar. Sin el permiso el archivo solo se ve: la app no
muestra «Guardar» y la web no muestra «Descargar» ni lo entrega para guardar.
"""

import base64
import io

from auth import generate_token
from extensions import db
from models import Announcement, AuditLog, CommonArea, Pqrs, PqrsMessage, Reservation, ReservationMessage
from web_testing import WebTestCase

PNG = b"\x89PNG\r\n\x1a\n" + b"imagen-de-prueba"
PHOTO = "data:image/png;base64," + base64.b64encode(PNG).decode()


class DownloadPermissionTestCase(WebTestCase):
    def bearer(self, user):
        return {"Authorization": f"Bearer {generate_token(user)}"}

    def new_pqrs(self, **extra):
        body = {"category": "Petición", "subject": "Prueba", "message": "Va la prueba", **extra}
        response = self.client.post("/api/pqrs", headers=self.bearer(self.resident), json=body)
        self.assertEqual(response.status_code, 201, response.get_json())
        return Pqrs.query.order_by(Pqrs.id.desc()).first()


class ApiDownloadPermissionTests(DownloadPermissionTestCase):
    def test_sin_marcarlo_el_archivo_solo_se_ve(self):
        pqrs = self.new_pqrs(mediaUrl=PHOTO, mediaType="image")

        self.assertFalse(pqrs.media_downloadable)
        detail = self.client.get(f"/api/pqrs/{pqrs.id}", headers=self.bearer(self.admin)).get_json()
        self.assertIs(detail["pqrs"]["mediaDownloadable"], False)

    def test_el_residente_permite_descargar_su_prueba(self):
        pqrs = self.new_pqrs(mediaUrl=PHOTO, mediaType="image", mediaDownloadable=True)

        self.assertTrue(pqrs.media_downloadable)
        detail = self.client.get(f"/api/pqrs/{pqrs.id}", headers=self.bearer(self.admin)).get_json()
        self.assertIs(detail["pqrs"]["mediaDownloadable"], True)
        self.assertIs(detail["pqrs"]["messages"][0]["mediaDownloadable"], True)

    def test_el_permiso_no_vale_sin_archivo_ni_con_un_valor_raro(self):
        without_file = self.new_pqrs(mediaDownloadable=True)
        odd_value = self.new_pqrs(mediaUrl=PHOTO, mediaType="image", mediaDownloadable="sí")

        self.assertFalse(without_file.media_downloadable)
        self.assertFalse(odd_value.media_downloadable)

    def test_la_administracion_decide_en_su_comunicado(self):
        for allowed in (True, False):
            response = self.client.post("/api/announcements", headers=self.bearer(self.admin), json={
                "title": "Circular", "message": "Va la circular", "category": "mantenimiento", "mediaUrl": PHOTO, "mediaType": "image",
                "mediaDownloadable": allowed,
            })
            self.assertEqual(response.status_code, 201, response.get_json())
            announcement = Announcement.query.order_by(Announcement.id.desc()).first()
            self.assertIs(announcement.media_downloadable, allowed)
            seen = self.client.get(
                f"/api/announcements/{announcement.id}", headers=self.bearer(self.resident),
            ).get_json()
            self.assertIs(seen["announcement"]["mediaDownloadable"], allowed)

    def test_cada_mensaje_lleva_su_propio_permiso(self):
        pqrs = self.new_pqrs()
        self.client.put(f"/api/pqrs/{pqrs.id}/respond", headers=self.bearer(self.admin), json={
            "adminResponse": "Va el acta", "status": "en_proceso", "mediaUrl": PHOTO, "mediaType": "image",
            "mediaDownloadable": True,
        })
        self.client.post(f"/api/pqrs/{pqrs.id}/messages", headers=self.bearer(self.resident), json={
            "message": "Mi prueba", "mediaUrl": PHOTO, "mediaType": "image",
        })

        flags = [message.media_downloadable for message in PqrsMessage.query.filter(
            PqrsMessage.pqrs_id == pqrs.id, PqrsMessage.media_url.is_not(None),
        ).order_by(PqrsMessage.id)]
        self.assertEqual(flags, [True, False])


class WebDownloadPermissionTests(DownloadPermissionTestCase):
    def setUp(self):
        super().setUp()
        self.log_in()

    def test_la_web_no_entrega_para_guardar_lo_que_no_se_permitio(self):
        pqrs = self.new_pqrs(mediaUrl=PHOTO, mediaType="image")

        body = self.page(f"/web/pqrs/{pqrs.id}")
        self.assertIn("quien lo subió no permitió descargarlo", body)
        self.assertNotIn("descargar=1", body)
        self.assertEqual(self.client.get(f"/web/pqrs/{pqrs.id}/adjunto").status_code, 200)
        self.assertEqual(self.client.get(f"/web/pqrs/{pqrs.id}/adjunto?descargar=1").status_code, 403)
        self.assertEqual(AuditLog.query.filter_by(action="attachment_downloaded").count(), 0)

    def test_la_web_descarga_lo_que_el_residente_permitio_y_lo_anota(self):
        pqrs = self.new_pqrs(mediaUrl=PHOTO, mediaType="image", mediaDownloadable=True)

        body = self.page(f"/web/pqrs/{pqrs.id}")
        self.assertIn(f"/web/pqrs/{pqrs.id}/adjunto?descargar=1", body)
        response = self.client.get(f"/web/pqrs/{pqrs.id}/adjunto?descargar=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(), PNG)
        self.assertEqual(response.headers["Content-Disposition"], 'attachment; filename="adjunto.png"')
        log = AuditLog.query.filter_by(action="attachment_downloaded").one()
        self.assertEqual((log.entity_type, log.entity_id, log.actor_id), ("pqrs", pqrs.id, self.admin.id))

    def test_ver_un_adjunto_no_se_anota_como_descarga(self):
        pqrs = self.new_pqrs(mediaUrl=PHOTO, mediaType="image", mediaDownloadable=True)

        self.client.get(f"/web/pqrs/{pqrs.id}/adjunto")

        self.assertEqual(AuditLog.query.filter_by(action="attachment_downloaded").count(), 0)

    def test_la_administracion_siempre_descarga_lo_que_ella_misma_subio(self):
        pqrs = self.new_pqrs()
        self.client.put(f"/api/pqrs/{pqrs.id}/respond", headers=self.bearer(self.admin), json={
            "adminResponse": "Va el acta", "status": "en_proceso", "mediaUrl": PHOTO, "mediaType": "image",
        })
        self.client.post(f"/api/pqrs/{pqrs.id}/messages", headers=self.bearer(self.resident), json={
            "message": "Mi prueba", "mediaUrl": PHOTO, "mediaType": "image",
        })
        mine, theirs = PqrsMessage.query.filter(
            PqrsMessage.pqrs_id == pqrs.id, PqrsMessage.media_url.is_not(None),
        ).order_by(PqrsMessage.id).all()

        base = f"/web/pqrs/{pqrs.id}/mensajes"
        self.assertEqual(self.client.get(f"{base}/{mine.id}/adjunto?descargar=1").status_code, 200)
        self.assertEqual(self.client.get(f"{base}/{theirs.id}/adjunto?descargar=1").status_code, 403)
        self.assertEqual(self.client.get(f"{base}/999/adjunto?descargar=1").status_code, 404)

    def test_el_comunicado_propio_siempre_se_puede_descargar_en_la_web(self):
        announcement = Announcement(
            title="Circular", message="Va", author_id=self.admin.id, media_url=PHOTO, media_type="image",
        )
        db.session.add(announcement)
        db.session.commit()

        response = self.client.get(f"/web/comunicados/{announcement.id}/adjunto?descargar=1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment;", response.headers["Content-Disposition"])

    def test_los_adjuntos_de_una_reserva_siguen_la_misma_regla(self):
        hall = CommonArea(name="Salón social")
        db.session.add(hall)
        db.session.flush()
        reservation = Reservation(
            resident_id=self.resident.id, common_area_id=hall.id, date="2031-01-10", time_slot="10:00-12:00",
            attendees=5, status="pendiente",
        )
        db.session.add(reservation)
        db.session.flush()
        hidden = ReservationMessage(
            reservation_id=reservation.id, author_id=self.resident.id, author_role="RESIDENT", message="Mira",
            media_url=PHOTO, media_type="image",
        )
        shared = ReservationMessage(
            reservation_id=reservation.id, author_id=self.resident.id, author_role="RESIDENT", message="Y esta",
            media_url=PHOTO, media_type="image", media_downloadable=True,
        )
        db.session.add_all([hidden, shared])
        db.session.commit()

        base = f"/web/reservas/{reservation.id}/mensajes"
        self.assertEqual(self.client.get(f"{base}/{hidden.id}/adjunto?descargar=1").status_code, 403)
        self.assertEqual(self.client.get(f"{base}/{shared.id}/adjunto?descargar=1").status_code, 200)
        self.assertEqual(AuditLog.query.filter_by(action="attachment_downloaded").count(), 1)

    def test_la_casilla_de_la_web_manda_el_permiso(self):
        pqrs = self.new_pqrs()
        self.assertIn("Permitir que quien lo reciba lo descargue", self.page(f"/web/pqrs/{pqrs.id}"))

        for marked in (True, False):
            form = {
                "csrf_token": self.token_of("/web/"), "adminResponse": "Va el acta", "status": "en_proceso",
                "media": (io.BytesIO(PNG), "acta.png"),
            }
            if marked:
                form["media_downloadable"] = "1"
            response = self.client.post(
                f"/web/pqrs/{pqrs.id}/responder", data=form, content_type="multipart/form-data",
            )
            self.assertEqual(response.status_code, 302)
            last = PqrsMessage.query.filter(
                PqrsMessage.pqrs_id == pqrs.id, PqrsMessage.media_url.is_not(None),
            ).order_by(PqrsMessage.id.desc()).first()
            self.assertIs(last.media_downloadable, marked)
