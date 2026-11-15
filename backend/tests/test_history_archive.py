"""Pruebas del archivo histórico mensual, la copia de respaldo y la limpieza de intentos (ADR-013).

Nada se borra (DEC-090): lo que cumple su plazo pasa a un archivo JSON comprimido por tipo y por
mes, con su huella SHA-256; el archivo se comprueba y solo entonces los registros salen de la base
(DEC-103). Un archivo se puede volver a cargar. Los secretos no se archivan ni van en la copia.
"""

import gzip
import hashlib
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from werkzeug.security import check_password_hash

from auth import close_sessions
from extensions import db
from models import (
    Announcement,
    AnnouncementRead,
    AuditLog,
    CommonArea,
    HistoryArchive,
    LoginAttempt,
    Notification,
    PackageItem,
    PackagePickupCode,
    Pqrs,
    PqrsMessage,
    Reservation,
    ReservationMessage,
    Visit,
    VisitEvent,
    VisitorVehicleEntry,
    VisitQrPass,
)
from services import history_archive_service as service
from time_utils import utc_now
from web_testing import WebTestCase

#: «Hoy» de las pruebas: los plazos se cuentan desde aquí.
NOW = datetime(2031, 11, 15, 10, 0, 0)
#: Ya cumplió los 5 años (octubre de 2026 es un mes completo anterior a noviembre de 2026).
OLD = datetime(2026, 10, 20, 9, 0, 0)
#: Del mismo mes de hace 5 años: ese mes todavía no se archiva.
SAME_MONTH = datetime(2026, 11, 3, 9, 0, 0)
RECENT = datetime(2030, 5, 1, 9, 0, 0)

PICKUP_TOKEN = "TOKEN-SECRETO-DE-PRUEBA"
PICKUP_HASH = "HASH-SECRETO-DE-PRUEBA"
QR_TOKEN = "QR-SECRETO-DE-PRUEBA"


class ArchiveTestCase(WebTestCase):
    def visit(self, when, name="Carlos Ruiz", qr=None, with_vehicle=False):
        visit = Visit(
            resident_id=self.resident.id, registered_by=self.guard.id, visitor_name=name,
            visitor_document="99887766", type="visitante", approval_status="aprobada",
            authorization_method="app", entered_at=when, created_at=when, qr_pass_id=qr.id if qr else None,
            visitor_photo_url="data:image/jpeg;base64,/9j/4AAQ", visitor_photo_type="image",
        )
        visit.events.append(VisitEvent(event_type="entrada", method="app", actor_id=self.guard.id, created_at=when))
        db.session.add(visit)
        db.session.flush()
        if with_vehicle:
            db.session.add(VisitorVehicleEntry(
                plate="ABC123", visit_id=visit.id, apartment_id=self.resident.apartment_id,
                entered_at=when, registered_by=self.guard.id,
            ))
        db.session.commit()
        return visit

    def package(self, when, with_code=False):
        item = PackageItem(
            resident_id=self.resident.id, registered_by=self.guard.id, status="entregado",
            arrived_at=when, description="Caja", created_at=when,
        )
        db.session.add(item)
        db.session.flush()
        if with_code:
            db.session.add(PackagePickupCode(
                package_id=item.id, token=PICKUP_TOKEN, pin_hash=PICKUP_HASH,
                created_by_id=self.resident.id, created_at=when,
            ))
        db.session.commit()
        return item

    def qr(self, when):
        qr = VisitQrPass(
            resident_id=self.resident.id, token=QR_TOKEN, valid_from="2026-10-20", valid_until="2026-10-21",
            max_people=2, created_at=when,
        )
        db.session.add(qr)
        db.session.commit()
        return qr

    def notification(self, when, title="Aviso"):
        item = Notification(user_id=self.resident.id, title=title, message="Mensaje", created_at=when)
        db.session.add(item)
        db.session.commit()
        return item

    def run_archive(self):
        return service.run_archive(actor=self.admin, now=NOW)

    def archives(self, kind=None):
        query = HistoryArchive.query.order_by(HistoryArchive.id)
        return query.filter_by(kind=kind).all() if kind else query.all()

    def payload(self, archive):
        return json.loads(gzip.decompress(bytes(archive.content)).decode("utf-8"))


class ArchiveRunTests(ArchiveTestCase):
    def test_lo_que_cumplio_el_plazo_pasa_al_archivo_y_lo_demas_se_queda(self):
        old = self.visit(OLD, name="Visita Vieja")
        same_month = self.visit(SAME_MONTH, name="Mismo Mes")
        recent = self.visit(RECENT, name="Visita Reciente")
        old_id, kept = old.id, {same_month.id, recent.id}

        result = self.run_archive()

        self.assertEqual(result["archives"], 1)
        self.assertEqual(result["records"], 1)
        self.assertEqual({visit.id for visit in Visit.query.all()}, kept)
        archive = self.archives("visitas")[0]
        self.assertEqual(archive.period, "2026-10")
        self.assertEqual(archive.record_count, 1)
        self.assertEqual([row["id"] for row in self.payload(archive)["tables"]["visits"]], [old_id])

    def test_el_archivo_lleva_lo_que_cuelga_del_registro_su_manifiesto_y_su_huella(self):
        visit = self.visit(OLD, with_vehicle=True)
        visit_id = visit.id

        self.run_archive()

        self.assertEqual(Visit.query.count(), 0)
        self.assertEqual(VisitEvent.query.count(), 0)
        self.assertEqual(VisitorVehicleEntry.query.count(), 0)
        archive = self.archives("visitas")[0]
        content = bytes(archive.content)
        self.assertEqual(archive.sha256, hashlib.sha256(content).hexdigest())
        self.assertEqual(archive.size_bytes, len(content))
        payload = self.payload(archive)
        self.assertEqual(payload["manifest"]["kind"], "visitas")
        self.assertEqual(payload["manifest"]["period"], "2026-10")
        self.assertEqual(
            payload["manifest"]["tables"], {"visits": 1, "visit_events": 1, "visitor_vehicle_entries": 1},
        )
        row = payload["tables"]["visits"][0]
        self.assertEqual(row["visitor_name"], "Carlos Ruiz")
        self.assertEqual(row["visitor_photo_url"], "data:image/jpeg;base64,/9j/4AAQ")
        self.assertEqual(payload["tables"]["visit_events"][0]["visit_id"], visit_id)
        self.assertEqual(payload["tables"]["visitor_vehicle_entries"][0]["plate"], "ABC123")

    def test_cada_tipo_y_cada_mes_va_en_su_archivo(self):
        self.visit(OLD)
        self.visit(datetime(2026, 9, 5, 8, 0, 0))
        self.package(OLD)
        hall = CommonArea(name="Salón social")
        db.session.add(hall)
        db.session.flush()
        reservation = Reservation(
            resident_id=self.resident.id, common_area_id=hall.id, date="2026-10-25", time_slot="10:00-12:00",
            attendees=8, status="aprobada", created_at=OLD,
        )
        pqrs = Pqrs(
            resident_id=self.resident.id, category="Petición", subject="Luz", message="Se fue la luz",
            status="resuelta", created_at=OLD, updated_at=OLD,
        )
        announcement = Announcement(title="Asamblea", message="Hay asamblea", author_id=self.admin.id, created_at=OLD)
        db.session.add_all([reservation, pqrs, announcement])
        db.session.flush()
        db.session.add_all([
            ReservationMessage(reservation_id=reservation.id, author_id=self.admin.id, author_role="ADMIN",
                               message="Aprobada", created_at=OLD),
            PqrsMessage(pqrs_id=pqrs.id, author_id=self.admin.id, author_role="ADMIN", message="Listo", created_at=OLD),
            AnnouncementRead(announcement_id=announcement.id, user_id=self.resident.id,
                             apartment_id=self.resident.apartment_id, read_at=OLD),
        ])
        db.session.commit()

        result = self.run_archive()

        found = sorted((archive.kind, archive.period) for archive in self.archives())
        self.assertEqual(found, [
            ("comunicados", "2026-10"), ("paquetes", "2026-10"), ("pqrs", "2026-10"),
            ("reservas", "2026-10"), ("visitas", "2026-09"), ("visitas", "2026-10"),
        ])
        self.assertEqual(result["records"], 6)
        for model in (Visit, PackageItem, Reservation, ReservationMessage, Pqrs, PqrsMessage,
                      Announcement, AnnouncementRead):
            self.assertEqual(model.query.count(), 0, model.__name__)
        tables = self.payload(self.archives("pqrs")[0])["manifest"]["tables"]
        self.assertEqual(tables["pqrs_messages"], 1)

    def test_las_notificaciones_salen_al_ano(self):
        old = self.notification(datetime(2030, 9, 10, 8, 0, 0), "Vieja")
        self.notification(datetime(2031, 3, 10, 8, 0, 0), "Nueva")
        old_id = old.id

        self.run_archive()

        self.assertEqual([item.title for item in Notification.query.all()], ["Nueva"])
        archive = self.archives("notificaciones")[0]
        self.assertEqual(archive.period, "2030-09")
        self.assertEqual(self.payload(archive)["tables"]["notifications"][0]["id"], old_id)

    def test_los_secretos_no_se_archivan(self):
        self.package(OLD, with_code=True)
        self.qr(OLD)

        self.run_archive()

        for archive in self.archives():
            text = gzip.decompress(bytes(archive.content)).decode("utf-8")
            for secret in (PICKUP_TOKEN, PICKUP_HASH, QR_TOKEN):
                self.assertNotIn(secret, text)
        code = self.payload(self.archives("paquetes")[0])["tables"]["package_pickup_codes"][0]
        self.assertNotIn("token", code)
        self.assertNotIn("pin_hash", code)

    def test_un_codigo_qr_se_queda_mientras_tenga_una_visita_en_la_base(self):
        qr = self.qr(OLD)
        self.visit(RECENT, qr=qr)

        self.run_archive()

        self.assertEqual(VisitQrPass.query.count(), 1)
        self.assertEqual(self.archives("qr"), [])

    def test_si_la_comprobacion_falla_no_sale_nada_de_la_base(self):
        self.visit(OLD)

        with patch.object(service, "_verify_saved", side_effect=service.ArchiveError("No coincide")):
            with self.assertRaises(service.ArchiveError):
                self.run_archive()

        self.assertEqual(Visit.query.count(), 1)
        self.assertEqual(VisitEvent.query.count(), 1)
        self.assertEqual(HistoryArchive.query.count(), 0)

    def test_un_archivo_cambiado_no_pasa_la_comprobacion(self):
        visit = self.visit(OLD)
        archive = HistoryArchive(
            kind="visitas", period="2026-10", record_count=1, size_bytes=3, sha256="0" * 64, content=b"abc",
        )
        db.session.add(archive)
        db.session.flush()

        with self.assertRaises(service.ArchiveError):
            service._verify_saved(archive.id, service.KINDS_BY_KEY["visitas"], [visit.id], "0" * 64)

    def test_un_mes_grande_se_parte_en_varios_archivos(self):
        for number in range(5):
            self.notification(datetime(2030, 9, 10, 8, number, 0), f"Aviso {number}")

        with patch.object(service, "CHUNK_SIZE", 2):
            result = self.run_archive()

        self.assertEqual(result["archives"], 3)
        self.assertEqual([archive.record_count for archive in self.archives()], [2, 2, 1])
        self.assertEqual(Notification.query.count(), 0)

    def test_archivar_queda_en_la_auditoria(self):
        self.visit(OLD)

        self.run_archive()

        log = AuditLog.query.filter_by(action="history_archived").one()
        self.assertEqual(log.actor_id, self.admin.id)
        details = json.loads(log.details)
        self.assertEqual(details["mes"], "2026-10")
        self.assertEqual(details["sha256"], self.archives()[0].sha256)

    def test_el_resumen_cuenta_lo_que_falta_por_archivar(self):
        self.visit(OLD)
        self.visit(RECENT)
        self.notification(datetime(2030, 9, 10, 8, 0, 0))

        summary = {item["key"]: item["count"] for item in service.pending_summary(NOW)}

        self.assertEqual(summary["visitas"], 1)
        self.assertEqual(summary["notificaciones"], 1)
        self.assertEqual(summary["paquetes"], 0)


class ArchiveRestoreTests(ArchiveTestCase):
    def test_volver_a_cargar_deja_los_registros_como_estaban(self):
        visit = self.visit(OLD, with_vehicle=True)
        before = {column.name: getattr(visit, column.name) for column in Visit.__table__.columns}
        self.run_archive()
        archive = self.archives("visitas")[0]

        restored = service.restore_archive(archive, actor=self.admin)

        self.assertEqual(restored, 1)
        back = db.session.get(Visit, before["id"])
        after = {column.name: getattr(back, column.name) for column in Visit.__table__.columns}
        self.assertEqual(after, before)
        self.assertEqual(VisitEvent.query.count(), 1)
        self.assertEqual(VisitorVehicleEntry.query.one().plate, "ABC123")
        self.assertIsNotNone(db.session.get(HistoryArchive, archive.id).restored_at)
        self.assertEqual(AuditLog.query.filter_by(action="history_restored").count(), 1)

    def test_un_archivo_no_se_carga_dos_veces(self):
        self.visit(OLD)
        self.run_archive()
        archive = self.archives()[0]
        service.restore_archive(archive, actor=self.admin)

        with self.assertRaises(service.ArchiveError):
            service.restore_archive(db.session.get(HistoryArchive, archive.id), actor=self.admin)

        self.assertEqual(Visit.query.count(), 1)

    def test_un_archivo_cambiado_no_se_carga(self):
        self.visit(OLD)
        self.run_archive()
        archive = self.archives()[0]
        archive.content = gzip.compress(b'{"manifest":{},"tables":{"visits":[]}}')
        db.session.commit()

        with self.assertRaises(service.ArchiveError):
            service.restore_archive(db.session.get(HistoryArchive, archive.id), actor=self.admin)

        self.assertEqual(Visit.query.count(), 0)
        self.assertIsNone(db.session.get(HistoryArchive, archive.id).restored_at)

    def test_los_secretos_vuelven_con_valores_nuevos_que_no_abren_nada(self):
        self.package(OLD, with_code=True)
        self.qr(OLD)
        self.run_archive()

        for archive in self.archives():
            service.restore_archive(archive, actor=self.admin)

        code = PackagePickupCode.query.one()
        self.assertNotEqual(code.token, PICKUP_TOKEN)
        self.assertGreaterEqual(len(code.token), 32)
        self.assertFalse(check_password_hash(code.pin_hash, "0000"))
        self.assertNotEqual(VisitQrPass.query.one().token, QR_TOKEN)

    def test_una_visita_vuelve_aunque_su_codigo_qr_siga_archivado(self):
        qr = self.qr(OLD)
        self.visit(OLD, qr=qr)
        self.run_archive()
        self.assertEqual(VisitQrPass.query.count(), 0)

        service.restore_archive(self.archives("visitas")[0], actor=self.admin)

        self.assertIsNone(Visit.query.one().qr_pass_id)

    def test_lo_que_vuelve_se_archiva_otra_vez_en_un_archivo_nuevo(self):
        self.visit(OLD)
        self.run_archive()
        service.restore_archive(self.archives()[0], actor=self.admin)

        result = self.run_archive()

        self.assertEqual(result["archives"], 1)
        self.assertEqual(Visit.query.count(), 0)
        self.assertEqual(len(self.archives("visitas")), 2)


class LoginAttemptPurgeTests(ArchiveTestCase):
    def attempt(self, subject, failed, last_failed=None, locked_until=None):
        db.session.add(LoginAttempt(
            kind="login", subject=subject, failed_count=failed, last_failed_at=last_failed, locked_until=locked_until,
        ))
        db.session.commit()

    def test_se_van_los_intentos_que_ya_no_sirven_y_se_quedan_los_vigentes(self):
        now = utc_now()
        self.attempt("ya-entro@test.local", 0, now - timedelta(hours=1))
        self.attempt("viejo@test.local", 3, now - timedelta(days=45))
        self.attempt("bloqueo-vencido@test.local", 5, now - timedelta(days=40), now - timedelta(days=40))
        self.attempt("reciente@test.local", 2, now - timedelta(days=2))
        self.attempt("bloqueado@test.local", 5, now - timedelta(minutes=3), now + timedelta(minutes=12))

        removed = service.purge_login_attempts()
        db.session.commit()

        self.assertEqual(removed, 3)
        left = sorted(row.subject for row in LoginAttempt.query.all())
        self.assertEqual(left, ["bloqueado@test.local", "reciente@test.local"])

    def test_la_limpieza_tambien_corre_al_archivar(self):
        self.attempt("viejo@test.local", 3, utc_now() - timedelta(days=45))

        result = service.run_archive(actor=self.admin)

        self.assertEqual(result["loginAttemptsPurged"], 1)
        self.assertEqual(LoginAttempt.query.count(), 0)


class ArchiveWebTests(ArchiveTestCase):
    """La página «Archivo histórico» de la web. Aquí «hoy» es el día real, así que lo viejo va con 6 años."""

    def setUp(self):
        super().setUp()
        self.old = utc_now() - timedelta(days=365 * 6)

    def test_sin_sesion_manda_a_iniciar_sesion(self):
        for path in ("/web/archivo-historico", "/web/archivo-historico/copia", "/web/archivo-historico/manifiesto"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertIn("/web/login", response.headers["Location"])

    def test_la_pagina_muestra_lo_pendiente_y_esta_en_el_menu(self):
        self.visit(self.old)
        self.log_in()

        body = self.page("/web/archivo-historico")

        self.assertIn("Archivo histórico y copia de respaldo", body)
        self.assertIn("Pasar al archivo (1)", body)
        self.assertIn('href="/web/archivo-historico"', self.page("/web/"))

    def test_sin_marcar_la_casilla_no_archiva(self):
        self.visit(self.old)
        self.log_in()

        response = self.post("/web/archivo-historico/archivar", follow=True)

        self.assertIn("Marca la casilla", self.text(response))
        self.assertEqual(Visit.query.count(), 1)

    def test_archiva_descarga_y_vuelve_a_cargar_desde_la_web(self):
        self.visit(self.old)
        self.log_in()

        response = self.post("/web/archivo-historico/archivar", {"confirm": "1"}, follow=True)

        body = self.text(response)
        self.assertIn("1 registros pasaron a 1 archivos", body)
        self.assertEqual(Visit.query.count(), 0)
        archive = HistoryArchive.query.one()
        self.assertIn(archive.sha256[:16], body)

        download = self.client.get(f"/web/archivo-historico/{archive.id}/descargar")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.mimetype, "application/gzip")
        self.assertEqual(download.headers["Cache-Control"], "no-store")
        self.assertIn(f'filename="DOMUX_archivo_visitas_{archive.period}_{archive.id}.json.gz"',
                      download.headers["Content-Disposition"])
        self.assertEqual(hashlib.sha256(download.get_data()).hexdigest(), archive.sha256)
        self.assertEqual(AuditLog.query.filter_by(action="history_downloaded").count(), 1)

        manifest = json.loads(self.client.get("/web/archivo-historico/manifiesto").get_data(as_text=True))
        self.assertEqual(manifest["archives"][0]["sha256"], archive.sha256)

        restored = self.post(f"/web/archivo-historico/{archive.id}/cargar", follow=True)
        self.assertIn("1 registros volvieron a la base", self.text(restored))
        self.assertEqual(Visit.query.count(), 1)

    def test_la_web_se_cierra_si_restablecen_la_contrasena_del_administrador(self):
        self.log_in()
        self.page("/web/archivo-historico")
        close_sessions(self.admin)
        db.session.commit()

        response = self.client.get("/web/archivo-historico", follow_redirects=True)

        self.assertIn("cambió tu contraseña", self.text(response))
        self.assertIn("Iniciar sesión", self.text(response))

    def test_un_archivo_que_no_existe_da_404(self):
        self.log_in()

        self.assertEqual(self.client.get("/web/archivo-historico/999/descargar").status_code, 404)
        self.assertEqual(self.post("/web/archivo-historico/999/cargar").status_code, 404)

    def test_la_copia_de_respaldo_trae_los_datos_sin_secretos(self):
        self.package(utc_now(), with_code=True)
        self.guard.pin_hash = "PIN-HASH-SECRETO"
        db.session.commit()
        self.log_in()

        response = self.client.get("/web/archivo-historico/copia")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/gzip")
        content = response.get_data()
        sha256 = hashlib.sha256(content).hexdigest()
        self.assertEqual(response.headers["X-Content-SHA256"], sha256)
        self.assertIn(sha256[:12], response.headers["Content-Disposition"])
        text = gzip.decompress(content).decode("utf-8")
        backup = json.loads(text)
        self.assertEqual(len(backup["tables"]["users"]), 3)
        self.assertIn("Lucía", [user["name"] for user in backup["tables"]["users"]])
        self.assertEqual(len(backup["tables"]["packages"]), 1)
        for secret in (self.admin.password_hash, "PIN-HASH-SECRETO", PICKUP_TOKEN, PICKUP_HASH):
            self.assertNotIn(secret, text)
        for table in ("login_attempts", "device_push_tokens", "history_archives"):
            self.assertNotIn(table, backup["tables"])
        log = AuditLog.query.filter_by(action="copia_respaldo").one()
        self.assertEqual(json.loads(log.details)["sha256"], sha256)
