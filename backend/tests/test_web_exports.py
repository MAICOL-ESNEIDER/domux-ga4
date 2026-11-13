"""Pruebas del Excel de la web: cada lista con sus filtros, el censo y el respaldo legal.

El Excel se maneja solo en la web, desde el computador. Cada lista trae solo los datos necesarios
(sin correos, teléfonos, documentos ni fotos), una hoja «Acerca de» con quién la descargó, sus filtros
y el aviso de datos personales, y cada descarga queda anotada en la auditoría.
"""

import io
import json
import unittest
from datetime import timedelta

from openpyxl import load_workbook

from extensions import db
from models import AuditLog, CommonArea, PackageItem, Pqrs, Reservation, User, Visit, VisitorVehicleEntry
from services.excel_service import generate_census_template_xlsx
from structure_fixtures import apartment_for
from time_utils import colombia_today, utc_now
from web_testing import WebTestCase

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class WebExcelTestCase(WebTestCase):
    def setUp(self):
        super().setUp()
        self.log_in()

    def download(self, path):
        """El Excel que entrega esa dirección, ya abierto: (respuesta, libro)."""
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, f"{path} respondió {response.status_code}")
        self.assertEqual(response.mimetype, XLSX)
        self.assertTrue(response.headers["Content-Disposition"].startswith('attachment; filename="DOMUX_'))
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        return response, load_workbook(io.BytesIO(response.get_data()))

    @staticmethod
    def rows(sheet):
        return [[cell.value for cell in row] for row in sheet.iter_rows()]

    @staticmethod
    def about(workbook):
        return {row[0].value: row[1].value for row in workbook["Acerca de"].iter_rows(min_row=2)}

    def everything(self, workbook):
        return json.dumps([self.rows(sheet) for sheet in workbook.worksheets], ensure_ascii=False, default=str)

    def last_export(self):
        return AuditLog.query.filter_by(entity_type="export").order_by(AuditLog.id.desc()).first()


class WebListExcelTests(WebExcelTestCase):
    def pqrs(self, subject, status="abierta", **fields):
        item = Pqrs(
            resident_id=self.resident.id, category="Petición", subject=subject, message="Mensaje privado",
            status=status, **fields,
        )
        db.session.add(item)
        db.session.commit()
        return item

    def test_the_pqrs_excel_has_the_filtered_list_and_only_what_is_needed(self):
        self.pqrs("Luz del pasillo")
        self.pqrs("Ruido en la noche", status="resuelta")

        _response, workbook = self.download("/web/pqrs/excel?estado=abierta")

        self.assertEqual(workbook.sheetnames, ["PQRS", "Acerca de"])
        rows = self.rows(workbook["PQRS"])
        self.assertEqual(rows[0], [
            "Radicado", "Radicada", "Tipo", "Asunto", "Apartamento", "Estado", "Plazo", "Vence",
            "Última actualización", "Archivada",
        ])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][3:6], ["Luz del pasillo", str(self.resident.apartment), "Abierta"])
        # Ni el mensaje, ni el correo, ni el teléfono de la residente.
        text = self.everything(workbook)
        for private in ("Mensaje privado", "residente-web@test.local", "3000000000"):
            self.assertNotIn(private, text)

    def test_the_about_sheet_says_who_when_which_filters_and_that_it_has_personal_data(self):
        self.pqrs("Luz del pasillo")

        _response, workbook = self.download("/web/pqrs/excel?estado=abierta&q=Luz")

        about = self.about(workbook)
        self.assertEqual(about["Lista"], "PQRS")
        self.assertEqual(about["Descargado por"], "Lucía Vargas")
        self.assertEqual(about["Filtros"], "Búsqueda: Luz · Estado: Abierta")
        self.assertEqual(about["Filas"], 1)
        self.assertIn("datos personales", about["Datos personales"])
        self.assertIn("Ley 1581", about["Datos personales"])

    def test_every_download_is_noted_in_the_audit_log(self):
        self.pqrs("Luz del pasillo")

        self.download("/web/pqrs/excel?estado=abierta")

        log = self.last_export()
        self.assertEqual((log.action, log.actor_id, log.actor_role), ("pqrs", self.admin.id, "ADMIN"))
        details = json.loads(log.details)
        self.assertEqual((details["lista"], details["filas"]), ("PQRS", 1))
        self.assertEqual(details["filtros"], "Estado: Abierta")

    def test_a_text_that_looks_like_a_formula_stays_as_text(self):
        self.pqrs("=HYPERLINK(\"http://malo.example\",\"clic\")")

        _response, workbook = self.download("/web/pqrs/excel")

        cell = workbook["PQRS"]["D2"]
        self.assertEqual(cell.data_type, "s")
        self.assertTrue(str(cell.value).startswith("'="))

    def test_the_reservations_excel_keeps_the_tab_and_the_zone(self):
        hall = CommonArea(name="Salón social")
        pool = CommonArea(name="Piscina")
        db.session.add_all([hall, pool])
        db.session.flush()
        day = (colombia_today() + timedelta(days=3)).isoformat()
        for area, status in ((hall, "aprobada"), (pool, "aprobada"), (hall, "pendiente")):
            db.session.add(Reservation(
                resident_id=self.resident.id, common_area_id=area.id, date=day, time_slot="10:00-12:00",
                attendees=8, status=status,
            ))
        db.session.commit()

        _response, workbook = self.download(f"/web/reservas/excel?estado=aprobada&zona={hall.id}")

        rows = self.rows(workbook["Reservas"])
        self.assertEqual(rows[0][:6], ["Zona", "Fecha", "Horario", "Personas", "Apartamento", "Estado"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "Salón social")
        self.assertEqual(rows[1][5], "Aprobada")
        self.assertEqual(self.about(workbook)["Filtros"], "Estado: Aprobadas · Zona: Salón social")

    def test_the_packages_excel_has_no_photo_or_tracking_number(self):
        now = utc_now()
        db.session.add(PackageItem(
            resident_id=self.resident.id, registered_by=self.guard.id, status="pendiente", arrived_at=now,
            description="Caja grande", carrier="Servientrega", tracking_number="GUIA-SECRETA-123",
            media_url="data:image/png;base64,iVBORw0KGgo=", media_type="image",
        ))
        db.session.commit()

        _response, workbook = self.download("/web/paqueteria/excel?estado=pendiente")

        rows = self.rows(workbook["Paquetes"])
        self.assertEqual(rows[0], [
            "Apartamento", "Descripción", "Transportadora", "Estado", "Llegó", "Entregado", "Lo recibió", "Archivado",
        ])
        self.assertEqual(rows[1][1:4], ["Caja grande", "Servientrega", "En portería"])
        text = self.everything(workbook)
        self.assertNotIn("GUIA-SECRETA-123", text)
        self.assertNotIn("base64", text)
        self.assertEqual(self.last_export().action, "paquetes")

    def test_the_visits_excel_says_if_the_document_was_given_but_never_the_number(self):
        now = utc_now()
        db.session.add_all([
            Visit(resident_id=self.resident.id, registered_by=self.guard.id, visitor_name="Carlos Ruiz",
                  visitor_document="99887766", media_consent=True, type="visitante", approval_status="aprobada",
                  authorization_method="app", entered_at=now),
            Visit(resident_id=self.resident.id, registered_by=self.guard.id, visitor_name="Sin Documento",
                  document_refused=True, type="domiciliario", approval_status="pendiente"),
        ])
        db.session.commit()

        _response, workbook = self.download("/web/visitas/excel")

        rows = self.rows(workbook["Visitas"])
        by_name = {row[0]: row for row in rows[1:]}
        self.assertEqual(by_name["Carlos Ruiz"][3], "Lo dio")
        self.assertEqual(by_name["Carlos Ruiz"][5], "Desde la app")
        self.assertEqual(by_name["Sin Documento"][3], "No quiso darlo")
        self.assertEqual(by_name["Sin Documento"][1], "Domiciliario")
        self.assertNotIn("99887766", self.everything(workbook))

    def test_the_vehicles_excel_keeps_the_plate_filter(self):
        now = utc_now()
        visit = Visit(resident_id=self.resident.id, registered_by=self.guard.id, visitor_name="Visitante",
                      type="visitante", approval_status="aprobada", entered_at=now)
        db.session.add(visit)
        db.session.flush()
        for plate in ("ABC123", "XYZ987"):
            db.session.add(VisitorVehicleEntry(
                plate=plate, visit_id=visit.id, apartment_id=self.resident.apartment_id, entered_at=now,
                registered_by=self.guard.id,
            ))
        db.session.commit()

        _response, workbook = self.download("/web/vehiculos/excel?placa=ABC")

        rows = self.rows(workbook["Vehículos de visitantes"])
        self.assertEqual([row[0] for row in rows[1:]], ["ABC123"])
        self.assertEqual(self.about(workbook)["Filtros"], "Situación: Todos · Placa: ABC")

    def test_the_users_excel_has_no_email_phone_or_document(self):
        self.resident.document_id = "1020304050"
        db.session.commit()

        _response, workbook = self.download("/web/usuarios/excel?rol=RESIDENT")

        rows = self.rows(workbook["Usuarios"])
        self.assertEqual(rows[0], ["Nombre", "Rol", "Apartamento", "Tipo de residente", "Cuenta"])
        self.assertEqual(rows[1:], [["Marta Ríos", "Residente", str(self.resident.apartment), "Propietario", "Activa"]])
        text = self.everything(workbook)
        for private in ("residente-web@test.local", "3000000000", "1020304050"):
            self.assertNotIn(private, text)

    def test_every_list_page_offers_its_excel_with_the_same_filters(self):
        for page, link in (
            ("/web/pqrs?estado=abierta", "/web/pqrs/excel?estado=abierta"),
            ("/web/reservas?estado=todas", "/web/reservas/excel?estado=todas"),
            ("/web/paqueteria?estado=entregado", "/web/paqueteria/excel?estado=entregado"),
            ("/web/visitas?estado=dentro", "/web/visitas/excel?estado=dentro"),
            ("/web/vehiculos?placa=ABC", "/web/vehiculos/excel?placa=ABC"),
            ("/web/usuarios?rol=GUARD", "/web/usuarios/excel?rol=GUARD"),
        ):
            with self.subTest(page=page):
                body = self.page(page)
                self.assertIn(f'href="{link}"', body)
                self.assertIn("Descargar Excel", body)

    def test_the_excel_needs_the_administrators_session(self):
        self.client.get("/web/logout")
        fresh = self.app.test_client()
        for path in ("/web/pqrs/excel", "/web/reservas/excel", "/web/paqueteria/excel", "/web/visitas/excel",
                     "/web/vehiculos/excel", "/web/usuarios/excel", "/web/respaldo/descargar",
                     "/web/usuarios/censo/plantilla"):
            with self.subTest(path=path):
                response = fresh.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/web/login", response.headers["Location"])
        self.assertEqual(AuditLog.query.filter_by(entity_type="export").count(), 0)


class WebCensusTests(WebExcelTestCase):
    def upload(self, content, name="censo.xlsx", consent=True):
        data = {"file": (io.BytesIO(content), name)}
        if consent:
            data["consent"] = "1"
        return self.post("/web/usuarios/censo", data)

    def test_the_users_page_leads_to_the_census(self):
        self.assertIn('href="/web/usuarios/censo"', self.page("/web/usuarios"))
        body = self.page("/web/usuarios/censo")
        self.assertIn("Importar el censo", body)
        self.assertIn('href="/web/usuarios/censo/plantilla"', body)
        self.assertIn("autorización de tratamiento de datos", body)

    def test_the_template_downloads_as_excel(self):
        response = self.client.get("/web/usuarios/censo/plantilla")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, XLSX)
        self.assertIn("Plantilla_Censo_DOMUX.xlsx", response.headers["Content-Disposition"])
        self.assertEqual(load_workbook(io.BytesIO(response.get_data())).sheetnames, ["Censo_Residentes"])

    def test_importing_the_census_creates_the_residents_and_shows_the_result(self):
        apartment_for("Torre 2 Apto 202")
        db.session.commit()

        response = self.upload(generate_census_template_xlsx())

        body = self.text(response)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Resultado de la importación", body)
        self.assertIn("aún no tienen contraseña", body)
        self.assertEqual(User.query.filter_by(email="maria.perez@example.com").count(), 1)

    def test_without_the_consent_nothing_is_imported(self):
        apartment_for("Torre 2 Apto 202")
        db.session.commit()

        response = self.upload(generate_census_template_xlsx(), consent=False)

        self.assertEqual(response.status_code, 400)
        self.assertIn("autorización de tratamiento de datos", self.text(response))
        self.assertEqual(User.query.filter_by(email="maria.perez@example.com").count(), 0)

    def test_only_an_excel_or_a_csv_is_accepted(self):
        for content, name in ((b"%PDF-1.4", "censo.pdf"), (b"", "censo.xlsx")):
            with self.subTest(name=name, size=len(content)):
                response = self.upload(content, name)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(User.query.filter_by(role="RESIDENT").count(), 1)

    def test_rows_with_errors_are_listed(self):
        csv = "Apartamento,Nombre\nTorre 1 Apto 101,Sin correo ni documento\n".encode("utf-8")

        response = self.upload(csv, "censo.csv")

        body = self.text(response)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Filas que no se cargaron", body)
        self.assertIn("Fila 2: Se requiere Correo o Documento", body)


class WebBackupTests(WebExcelTestCase):
    def test_the_menu_has_the_legal_backup(self):
        body = self.page("/web/respaldo")
        self.assertIn('href="/web/respaldo"', body)
        self.assertIn("Descargar el respaldo", body)
        self.assertIn("Archivar lo terminado", body)

    def test_the_backup_downloads_and_is_noted_in_the_audit_log(self):
        response = self.client.get("/web/respaldo/descargar")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, XLSX)
        self.assertIn("attachment;", response.headers["Content-Disposition"])
        sheets = load_workbook(io.BytesIO(response.get_data())).sheetnames
        self.assertIn("PQRS_Radicados", sheets)
        self.assertEqual(self.last_export().action, "respaldo_legal")

    def test_archiving_needs_the_confirmation_and_never_deletes(self):
        resolved = Pqrs(resident_id=self.resident.id, category="Petición", subject="Ya resuelta",
                        message="Listo", status="resuelta")
        db.session.add(resolved)
        db.session.commit()

        refused = self.post("/web/respaldo/archivar", follow=True)
        self.assertIn("Marca la casilla", self.text(refused))
        self.assertFalse(db.session.get(Pqrs, resolved.id).is_archived)

        done = self.post("/web/respaldo/archivar", {"confirm": "1"}, follow=True)
        self.assertIn("se archivaron 1 PQRS", self.text(done))
        db.session.expire_all()
        self.assertTrue(db.session.get(Pqrs, resolved.id).is_archived)
        self.assertEqual(Pqrs.query.count(), 1)


if __name__ == "__main__":
    unittest.main()
