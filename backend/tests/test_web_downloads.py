"""Pruebas de la zona «Descargas» de la web.

El administrador elige qué descargar, de qué fechas y, si quiere, de un apartamento; el Excel junta lo
que sigue en la base de datos con lo que ya está en el archivo histórico. También baja una sola PQRS o
una sola reserva, y ve el historial de lo descargado.
"""

import io
from datetime import datetime, timedelta

from openpyxl import load_workbook

from extensions import db
from models import (
    Announcement,
    AuditLog,
    CommonArea,
    HistoryArchive,
    PackageItem,
    Pqrs,
    PqrsMessage,
    Reservation,
    ReservationMessage,
    User,
    Visit,
    VisitorVehicleEntry,
)
from services import history_archive_service as archive_service
from structure_fixtures import apartment_for
from time_utils import utc_now
from web import downloads
from web_testing import WebTestCase
from werkzeug.security import generate_password_hash

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class DownloadsTestCase(WebTestCase):
    def setUp(self):
        super().setUp()
        self.now = utc_now()
        self.old = self.now - timedelta(days=365 * 6)
        self.other = User(
            name="Pedro", last_name="Sol", email="otro-descargas@test.local", role="RESIDENT", is_active=True,
            password_hash=generate_password_hash("Clave-de-prueba-1*"),
            apartment_ref=apartment_for("Torre 1 · 202"), occupancy_type="arrendatario",
        )
        db.session.add(self.other)
        db.session.commit()
        self.log_in()

    def pqrs(self, when, subject="Luz", resident=None):
        item = Pqrs(
            resident_id=(resident or self.resident).id, category="Queja", subject=subject, message="Se fue la luz",
            status="resuelta", created_at=when, updated_at=when, radicado=f"PQRS-{subject}",
        )
        db.session.add(item)
        db.session.commit()
        return item

    def visit(self, when, name="Carlos Ruiz", with_vehicle=False):
        item = Visit(
            resident_id=self.resident.id, registered_by=self.guard.id, visitor_name=name, visitor_document="99887766",
            type="visitante", approval_status="aprobada", entered_at=when, created_at=when,
            visitor_photo_url="data:image/jpeg;base64,/9j/4AAQ", visitor_photo_type="image",
        )
        db.session.add(item)
        db.session.flush()
        if with_vehicle:
            db.session.add(VisitorVehicleEntry(
                plate="ABC123", visit_id=item.id, apartment_id=self.resident.apartment_id, entered_at=when,
                registered_by=self.guard.id,
            ))
        db.session.commit()
        return item

    def archive_everything_old(self):
        return archive_service.run_archive(actor=self.admin)

    def excel(self, query):
        self.confirm_password()
        response = self.client.get(f"/web/descargas/excel?{query}")
        self.assertEqual(response.status_code, 200, response.headers.get("Location"))
        self.assertEqual(response.mimetype, XLSX)
        return load_workbook(io.BytesIO(response.get_data()))

    def rows(self, workbook, sheet):
        values = list(workbook[sheet].iter_rows(values_only=True))
        return [dict(zip(values[0], row)) for row in values[1:]]


class DownloadsPageTests(DownloadsTestCase):
    def test_la_pagina_esta_en_el_menu_y_reune_las_otras_dos(self):
        body = self.page("/web/descargas")

        self.assertIn("Descargar información", body)
        for link in ('href="/web/descargas"', 'href="/web/archivo-historico"', 'href="/web/respaldo"'):
            self.assertIn(link, body)
        home = self.page("/web/")
        self.assertIn('href="/web/descargas"', home)
        self.assertNotIn('href="/web/respaldo"', home)
        for path in ("/web/archivo-historico", "/web/respaldo"):
            self.assertIn('aria-label="Descargas"', self.page(path))

    def test_sin_sesion_manda_a_iniciar_sesion(self):
        fresh = self.app.test_client()
        for path in ("/web/descargas", "/web/descargas/excel?tipo=pqrs", "/web/pqrs/1/descargar",
                     "/web/reservas/1/descargar"):
            response = fresh.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertIn("/web/login", response.headers["Location"])

    def test_cuenta_los_registros_antes_de_descargar(self):
        self.pqrs(self.now)
        self.pqrs(self.old, "Vieja")
        self.archive_everything_old()

        body = self.page("/web/descargas?tipo=pqrs&tipo=visitas&periodo=todo&contar=1")

        self.assertIn("<strong>2 registros</strong>", body)
        self.assertIn("1 sale del archivo histórico", body)
        self.assertIn("PQRS: 2 (1 del archivo histórico)", body)
        self.assertIn("Visitas: 0", body)

    def test_contar_sin_marcar_nada_o_con_fechas_malas_avisa(self):
        self.assertIn("Marca al menos una cosa", self.page("/web/descargas?contar=1"))
        swapped = self.page("/web/descargas?tipo=pqrs&periodo=fechas&desde=2026-05-10&hasta=2026-05-01&contar=1")
        self.assertIn("no puede ser posterior", swapped)
        self.assertIn("Elige al menos una de las dos fechas", self.page("/web/descargas?tipo=pqrs&periodo=fechas&contar=1"))


class DownloadsExcelTests(DownloadsTestCase):
    def test_pide_la_contrasena_y_vuelve_con_lo_elegido(self):
        response = self.client.get("/web/descargas/excel?tipo=pqrs&periodo=todo")

        self.assertEqual(response.status_code, 302)
        location = response.headers["Location"]
        self.assertIn("/web/confirmar-contrasena", location)
        self.assertIn("tipo%3Dpqrs", location)
        self.assertIn("periodo%3Dtodo", location)

    def test_sin_marcar_nada_no_descarga(self):
        self.confirm_password()

        response = self.client.get("/web/descargas/excel?periodo=todo", follow_redirects=True)

        self.assertIn("Marca al menos una cosa", self.text(response))
        self.assertEqual(AuditLog.query.filter_by(action="descarga_a_la_medida").count(), 0)

    def test_junta_la_base_con_el_archivo_historico(self):
        self.pqrs(self.now, "Nueva")
        self.pqrs(self.old, "Vieja")
        self.archive_everything_old()
        self.assertEqual(Pqrs.query.count(), 1)

        workbook = self.excel("tipo=pqrs&periodo=todo")

        self.assertEqual(workbook.sheetnames, ["PQRS", "Acerca de"])
        rows = self.rows(workbook, "PQRS")
        self.assertEqual([row["Asunto"] for row in rows], ["Vieja", "Nueva"])
        self.assertEqual([row["Dónde está"] for row in rows], ["Archivo histórico", "Base de datos"])
        self.assertEqual(rows[0]["Residente"], "Marta Ríos")
        self.assertEqual(rows[0]["Apartamento"], "Torre 1 · Apto 101")
        self.assertEqual(rows[0]["Estado"], "Resuelta")
        about = dict(workbook["Acerca de"].iter_rows(min_row=2, values_only=True))
        self.assertEqual(about["Filas"], 2)
        self.assertEqual(about["Del archivo histórico"], 1)
        # Leer el archivo no lo vuelve a cargar en la base.
        self.assertEqual(Pqrs.query.count(), 1)
        self.assertIsNone(HistoryArchive.query.filter_by(kind="pqrs").one().restored_at)

    def test_un_archivo_que_se_volvio_a_cargar_no_sale_dos_veces(self):
        self.pqrs(self.old, "Vieja")
        self.archive_everything_old()
        archive_service.restore_archive(HistoryArchive.query.one(), actor=self.admin)

        rows = self.rows(self.excel("tipo=pqrs&periodo=todo"), "PQRS")

        self.assertEqual([(row["Asunto"], row["Dónde está"]) for row in rows], [("Vieja", "Base de datos")])

    def test_las_fechas_acotan_lo_que_sale(self):
        self.pqrs(datetime(2026, 3, 10, 15, 0, 0), "Marzo")
        self.pqrs(datetime(2026, 4, 2, 15, 0, 0), "Abril")
        self.pqrs(datetime(2026, 4, 30, 23, 30, 0), "Abril de noche")  # 30 de abril, 6:30 p. m. en Colombia
        self.pqrs(datetime(2026, 5, 1, 4, 0, 0), "Todavía abril")      # 30 de abril, 11 p. m. en Colombia
        self.pqrs(datetime(2026, 5, 1, 6, 0, 0), "Mayo")               # 1 de mayo, 1 a. m. en Colombia

        rows = self.rows(self.excel("tipo=pqrs&periodo=fechas&desde=2026-04-01&hasta=2026-04-30"), "PQRS")

        self.assertEqual([row["Asunto"] for row in rows], ["Abril", "Abril de noche", "Todavía abril"])

    def test_un_solo_apartamento(self):
        self.pqrs(self.now, "De Marta")
        self.pqrs(self.now, "De Pedro", resident=self.other)

        workbook = self.excel(f"tipo=pqrs&tipo=usuarios&periodo=todo&apto={self.other.apartment_id}")

        self.assertEqual([row["Asunto"] for row in self.rows(workbook, "PQRS")], ["De Pedro"])
        self.assertEqual([row["Nombre"] for row in self.rows(workbook, "Usuarios")], ["Pedro Sol"])

    def test_cada_tipo_va_en_su_hoja_sin_fotos_ni_secretos(self):
        self.pqrs(self.now)
        self.visit(self.now, with_vehicle=True)
        hall = CommonArea(name="Salón social")
        db.session.add(hall)
        db.session.flush()
        db.session.add_all([
            Reservation(resident_id=self.resident.id, common_area_id=hall.id, date="2026-12-24",
                        time_slot="10:00-12:00", attendees=8, status="aprobada", created_at=self.now),
            PackageItem(resident_id=self.resident.id, registered_by=self.guard.id, status="entregado",
                        description="Caja", arrived_at=self.now, created_at=self.now,
                        media_url="data:image/jpeg;base64,/9j/FOTO", media_type="image"),
            Announcement(title="Asamblea", message="Hay asamblea", category="asamblea", author_id=self.admin.id,
                         created_at=self.now),
        ])
        db.session.commit()
        every = "&".join(f"tipo={key}" for key, _label in downloads.CHOICES)

        self.confirm_password()
        response = self.client.get(f"/web/descargas/excel?{every}&periodo=todo")
        workbook = load_workbook(io.BytesIO(response.get_data()))

        self.assertEqual(workbook.sheetnames, [
            "PQRS", "Reservas", "Visitas", "Paquetes", "Vehículos de visitantes", "Comunicados", "Usuarios",
            "Acerca de",
        ])
        self.assertEqual(self.rows(workbook, "Reservas")[0]["Zona"], "Salón social")
        self.assertEqual(self.rows(workbook, "Visitas")[0]["Visitante"], "Carlos Ruiz")
        self.assertEqual(self.rows(workbook, "Vehículos de visitantes")[0]["Placa"], "ABC123")
        self.assertEqual(self.rows(workbook, "Paquetes")[0]["Estado"], "Entregado")
        self.assertEqual(self.rows(workbook, "Comunicados")[0]["Publicó"], "Lucía Vargas")
        self.assertEqual(len(self.rows(workbook, "Usuarios")), 4)
        text = " ".join(
            str(cell) for sheet in workbook for row in sheet.iter_rows(values_only=True) for cell in row if cell
        )
        for secret in ("base64", self.admin.password_hash, "scrypt:"):
            self.assertNotIn(secret, text)

    def test_los_vehiculos_archivados_con_su_visita_tambien_salen(self):
        self.visit(self.old, with_vehicle=True)
        self.archive_everything_old()
        self.assertEqual(VisitorVehicleEntry.query.count(), 0)

        rows = self.rows(self.excel("tipo=vehiculos&periodo=todo"), "Vehículos de visitantes")

        self.assertEqual([(row["Placa"], row["Dónde está"]) for row in rows], [("ABC123", "Archivo histórico")])

    def test_un_texto_que_parece_formula_sale_como_texto(self):
        self.pqrs(self.now, "=HYPERLINK(1)")

        workbook = self.excel("tipo=pqrs&periodo=todo")

        cell = workbook["PQRS"]["F2"]
        self.assertEqual(cell.data_type, "s")
        self.assertTrue(str(cell.value).startswith("'="))

    def test_la_descarga_queda_en_la_auditoria_y_en_el_historial(self):
        self.pqrs(self.now)

        self.excel("tipo=pqrs&periodo=todo")

        log = AuditLog.query.filter_by(action="descarga_a_la_medida").one()
        self.assertEqual(log.actor_id, self.admin.id)
        self.assertIn('"filas": 1', log.details)
        body = self.page("/web/descargas")
        self.assertIn("Descarga a la medida: PQRS", body)
        self.assertIn("Lucía Vargas", body)


class SingleDownloadTests(DownloadsTestCase):
    def test_una_sola_pqrs_con_su_conversacion(self):
        pqrs = self.pqrs(self.now, "Ruido")
        db.session.add(PqrsMessage(
            pqrs_id=pqrs.id, author_id=self.admin.id, author_role="ADMIN", message="Ya hablamos con el vecino",
            created_at=self.now,
        ))
        db.session.commit()
        self.assertIn(f'href="/web/pqrs/{pqrs.id}/descargar"', self.page(f"/web/pqrs/{pqrs.id}"))

        response = self.client.get(f"/web/pqrs/{pqrs.id}/descargar")

        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(io.BytesIO(response.get_data()))
        self.assertEqual(workbook.sheetnames, ["PQRS", "Conversación", "Acerca de"])
        facts = dict(workbook["PQRS"].iter_rows(min_row=2, values_only=True))
        self.assertEqual(facts["Asunto"], "Ruido")
        self.assertEqual(facts["Residente"], "Marta Ríos")
        talk = self.rows(workbook, "Conversación")
        self.assertEqual(talk[0]["Mensaje"], "Ya hablamos con el vecino")
        self.assertEqual(talk[0]["Rol"], "Administración")
        self.assertEqual(AuditLog.query.filter_by(action="pqrs_individual").count(), 1)

    def test_una_sola_reserva_con_su_conversacion(self):
        hall = CommonArea(name="Salón social")
        db.session.add(hall)
        db.session.flush()
        reservation = Reservation(
            resident_id=self.resident.id, common_area_id=hall.id, date="2026-12-24", time_slot="10:00-12:00",
            attendees=8, status="aprobada", created_at=self.now,
        )
        db.session.add(reservation)
        db.session.flush()
        db.session.add(ReservationMessage(
            reservation_id=reservation.id, author_id=self.resident.id, author_role="RESIDENT", message="Gracias",
            created_at=self.now,
        ))
        db.session.commit()

        response = self.client.get(f"/web/reservas/{reservation.id}/descargar")

        workbook = load_workbook(io.BytesIO(response.get_data()))
        facts = dict(workbook["Reserva"].iter_rows(min_row=2, values_only=True))
        self.assertEqual(facts["Zona"], "Salón social")
        self.assertEqual(facts["Asistentes"], 8)
        self.assertEqual(self.rows(workbook, "Conversación")[0]["Mensaje"], "Gracias")

    def test_lo_que_no_existe_da_404(self):
        self.assertEqual(self.client.get("/web/pqrs/999/descargar").status_code, 404)
        self.assertEqual(self.client.get("/web/reservas/999/descargar").status_code, 404)
