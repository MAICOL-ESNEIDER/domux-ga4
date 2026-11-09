import base64
import io
import os
import unittest
from datetime import date, timedelta

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "unit-test-only-secret-with-enough-bytes"

from openpyxl import load_workbook

from app import create_app
from auth import generate_token
from extensions import db
from models import (
    AuditLog,
    CommonArea,
    Pqrs,
    PqrsMessage,
    Reservation,
    ResidentialUnit,
    User,
    Vehicle,
)
from services.excel_service import (
    CENSUS_HEADERS,
    MIME_XLSX,
    generate_census_template_xlsx,
    generate_legal_report_xlsx,
    import_census_from_bytes,
)
from werkzeug.security import generate_password_hash


class ExcelServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.admin = User(
            name="Admin",
            email="admin-excel@test.local",
            password_hash=generate_password_hash("Admin123*"),
            role="ADMIN",
            is_active=True,
        )
        self.resident = User(
            name="Residente",
            last_name="Prueba",
            email="resident-excel@test.local",
            document_id="123456789",
            password_hash=generate_password_hash("Resident123*"),
            role="RESIDENT",
            apartment="Torre 1 Apto 101",
            is_active=True,
        )
        self.area = CommonArea(name="Salón social")
        db.session.add_all([
            self.admin,
            self.resident,
            self.area,
            ResidentialUnit(apartment=self.resident.apartment),
        ])
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def headers(self, user=None):
        return {"Authorization": f"Bearer {generate_token(user or self.admin)}"}

    def test_census_template_has_expected_columns_and_examples(self):
        workbook = load_workbook(io.BytesIO(generate_census_template_xlsx()), data_only=True)
        worksheet = workbook["Censo_Residentes"]

        self.assertEqual(tuple(cell.value for cell in worksheet[1]), CENSUS_HEADERS)
        self.assertEqual(worksheet.max_row, 3)
        self.assertEqual(worksheet["A2"].value, "Torre 1 Apto 101")
        self.assertEqual(worksheet["A3"].value, "Torre 2 Apto 202")

    def test_admin_template_and_import_endpoints_exchange_base64_xlsx(self):
        template_response = self.client.get(
            "/api/admin/census-template",
            headers=self.headers(),
        )
        self.assertEqual(template_response.status_code, 200)
        self.assertEqual(template_response.json["fileName"], "Plantilla_Censo_DOMUX.xlsx")
        self.assertEqual(template_response.json["mimeType"], MIME_XLSX)

        import_response = self.client.post(
            "/api/admin/import-census",
            headers=self.headers(),
            json={
                "fileBase64": (
                    "data:application/vnd.openxmlformats-officedocument."
                    f"spreadsheetml.sheet;base64,{template_response.json['base64']}"
                ),
                "fileName": template_response.json["fileName"],
            },
        )
        self.assertEqual(import_response.status_code, 200)
        self.assertEqual(import_response.json["createdUsers"], 2)
        self.assertEqual(import_response.json["errors"], [])

    def test_census_import_creates_residents_units_and_related_records(self):
        result = import_census_from_bytes(
            generate_census_template_xlsx(),
            "Plantilla_Censo_DOMUX.xlsx",
            self.admin,
        )

        self.assertEqual(result["createdUsers"], 2)
        self.assertEqual(result["updatedUsers"], 0)
        self.assertEqual(result["unitsProcessed"], 2)
        self.assertEqual(result["errors"], [])
        self.assertEqual(User.query.filter_by(role="RESIDENT").count(), 3)
        imported = User.query.filter_by(email="maria.perez@example.com").one()
        self.assertTrue(imported.data_processing_consent)
        self.assertEqual(imported.birth_date, "1990-05-14")
        self.assertEqual(
            ResidentialUnit.query.filter_by(apartment="Torre 1 Apto 101").one().parking_identifier,
            "P-101",
        )
        self.assertEqual(Vehicle.query.filter_by(plate="ABC123").count(), 1)
        self.assertEqual(AuditLog.query.filter_by(entity_type="census").count(), 1)

    def test_census_csv_aliases_update_by_identity_without_clearing_missing_fields(self):
        self.resident.parental_consent = True
        unit = ResidentialUnit.query.filter_by(apartment=self.resident.apartment).first()
        unit.parking_identifier = "P-OLD"
        db.session.commit()
        csv_bytes = (
            "Apto,Nombre,Email,Identificación\n"
            "Torre 1 Apto 101,Residente Actual,resident-excel@test.local,123456789\n"
        ).encode("utf-8")

        result = import_census_from_bytes(csv_bytes, "censo.csv", self.admin)

        self.assertEqual(result["createdUsers"], 0)
        self.assertEqual(result["updatedUsers"], 1)
        self.assertEqual(result["errors"], [])
        self.assertEqual(self.resident.name, "Residente Actual")
        self.assertTrue(self.resident.parental_consent)
        self.assertEqual(unit.parking_identifier, "P-OLD")

    def test_census_import_returns_row_warnings_as_strings(self):
        csv_bytes = (
            "Apartamento,Nombre\n"
            "Torre 1 Apto 101,Residente sin identificador\n"
        ).encode("utf-8")

        result = import_census_from_bytes(csv_bytes, "censo.csv", self.admin)

        self.assertEqual(
            result["errors"],
            ["Fila 2: Se requiere Correo o Documento para identificar al residente."],
        )

    def test_legal_report_contains_all_sheets_and_expected_counts(self):
        pqrs = Pqrs(
            resident_id=self.resident.id,
            subject="Daño",
            message="Descripción",
            status="resuelta",
        )
        reservation = Reservation(
            resident_id=self.resident.id,
            common_area_id=self.area.id,
            date=(date.today() + timedelta(days=5)).isoformat(),
            time_slot="10:00-12:00",
            status="pendiente",
        )
        db.session.add_all([pqrs, reservation])
        db.session.flush()
        db.session.add(PqrsMessage(
            pqrs_id=pqrs.id,
            author_id=self.resident.id,
            author_role="RESIDENT",
            message="Mensaje de seguimiento",
        ))
        db.session.add(AuditLog(
            entity_type="PQRS",
            entity_id=pqrs.id,
            action="created",
            actor_id=self.admin.id,
            actor_role="ADMIN",
        ))
        db.session.commit()

        report_bytes, counts = generate_legal_report_xlsx()
        workbook = load_workbook(io.BytesIO(report_bytes), read_only=True, data_only=True)

        self.assertEqual(
            workbook.sheetnames,
            [
                "PQRS_Radicados",
                "PQRS_Historial_Chat",
                "Reservas_Zonas_Comunes",
                "Logs_Auditoria",
            ],
        )
        self.assertEqual(counts, {
            "pqrsCount": 1,
            "pqrsMessagesCount": 1,
            "reservationsCount": 1,
            "auditLogsCount": 1,
        })
        self.assertEqual(workbook["PQRS_Radicados"].max_row, 2)
        self.assertEqual(workbook["PQRS_Historial_Chat"].max_row, 2)

    def test_legal_report_endpoint_returns_base64_workbook(self):
        response = self.client.get(
            "/api/admin/export/legal-report",
            headers=self.headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["mimeType"], MIME_XLSX)
        self.assertTrue(response.json["fileName"].startswith("Reporte_Legal_DOMUX_"))
        workbook = load_workbook(
            io.BytesIO(base64.b64decode(response.json["base64"])),
            read_only=True,
            data_only=True,
        )
        self.assertIn("Logs_Auditoria", workbook.sheetnames)

    def test_archive_history_archives_records_and_returns_legal_workbook(self):
        resolved = Pqrs(
            resident_id=self.resident.id,
            subject="Resuelta",
            message="Descripción",
            status="resuelta",
        )
        open_pqrs = Pqrs(
            resident_id=self.resident.id,
            subject="Abierta",
            message="Descripción",
            status="abierta",
        )
        old_reservation = Reservation(
            resident_id=self.resident.id,
            common_area_id=self.area.id,
            date=(date.today() - timedelta(days=1)).isoformat(),
            time_slot="10:00-12:00",
            status="aprobada",
        )
        rejected_reservation = Reservation(
            resident_id=self.resident.id,
            common_area_id=self.area.id,
            date=(date.today() + timedelta(days=3)).isoformat(),
            time_slot="12:00-14:00",
            status="rechazada",
        )
        active_reservation = Reservation(
            resident_id=self.resident.id,
            common_area_id=self.area.id,
            date=(date.today() + timedelta(days=4)).isoformat(),
            time_slot="14:00-16:00",
            status="pendiente",
        )
        db.session.add_all([
            resolved, open_pqrs, old_reservation, rejected_reservation, active_reservation
        ])
        db.session.commit()

        response = self.client.post(
            "/api/admin/archive-history",
            headers=self.headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["archivedPqrsCount"], 1)
        self.assertEqual(response.json["archivedReservationsCount"], 2)
        self.assertEqual(response.json["mimeType"], MIME_XLSX)
        self.assertTrue(response.json["base64"])
        self.assertTrue(db.session.get(Pqrs, resolved.id).is_archived)
        self.assertFalse(db.session.get(Pqrs, open_pqrs.id).is_archived)
        self.assertTrue(db.session.get(Reservation, old_reservation.id).is_archived)
        self.assertTrue(db.session.get(Reservation, rejected_reservation.id).is_archived)
        self.assertFalse(db.session.get(Reservation, active_reservation.id).is_archived)
        self.assertEqual(
            AuditLog.query.filter_by(entity_type="history_archive", action="archived").count(),
            1,
        )
        workbook = load_workbook(
            io.BytesIO(base64.b64decode(response.json["base64"])),
            read_only=True,
            data_only=True,
        )
        self.assertEqual(workbook.sheetnames[0], "PQRS_Radicados")


if __name__ == "__main__":
    unittest.main()
