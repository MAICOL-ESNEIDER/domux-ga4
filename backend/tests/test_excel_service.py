import base64
import io
import os
import unittest
from datetime import timedelta

os.environ["DATABASE_URL"] = "sqlite://"

from openpyxl import load_workbook

from app import create_app
from auth import generate_token
from extensions import db
from models import (
    AuditLog,
    CommonArea,
    PackageItem,
    Pqrs,
    PqrsMessage,
    Reservation,
    ResidentialUnit,
    User,
    Vehicle,
    Visit,
)
from services.excel_service import (
    CENSUS_HEADERS,
    MIME_XLSX,
    generate_census_template_xlsx,
    generate_legal_report_xlsx,
    import_census_from_bytes,
)
from werkzeug.security import check_password_hash, generate_password_hash
from time_utils import now_colombia


class ExcelServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app({"TESTING": True})
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
        worksheet = workbook["Migracion_Datos_Residentes"]

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
        self.assertEqual(
            template_response.json["fileName"],
            "plantilla_migracion_datos.xlsx",
        )
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
        credentials = result["createdCredentials"]
        self.assertEqual(len(credentials), 2)
        self.assertEqual(len({entry["temporaryPassword"] for entry in credentials}), 2)
        for credential in credentials:
            imported_user = User.query.filter_by(email=credential["email"]).one()
            self.assertTrue(imported_user.must_change_password)
            self.assertTrue(
                check_password_hash(
                    imported_user.password_hash,
                    credential["temporaryPassword"],
                )
            )
            self.assertEqual(imported_user.apartment, credential["apartment"])
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

    def test_census_import_normalizes_and_rejects_phone_numbers(self):
        csv_content = (
            "Apartamento,Nombre,Correo,Telefono\n"
            "Torre 1 Apto 101,Válido,valid-phone@test.local,+57 300-123-4567\n"
            "Torre 2 Apto 202,Inválido,invalid-phone@test.local,123456\n"
        ).encode("utf-8")

        result = import_census_from_bytes(csv_content, "censo.csv", self.admin)

        valid_user = User.query.filter_by(email="valid-phone@test.local").one()
        self.assertEqual(valid_user.phone, "3001234567")
        self.assertIsNone(User.query.filter_by(email="invalid-phone@test.local").first())
        self.assertEqual(result["errors"], [
            "Fila 3: El número de teléfono debe tener exactamente 10 dígitos numéricos."
        ])

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

    def test_census_import_allows_missing_optional_unit_columns(self):
        csv_bytes = (
            "Apartamento,Nombre,Correo\n"
            "Torre 3 Apto 303,Residente Nuevo,new-resident@test.local\n"
        ).encode("utf-8")

        result = import_census_from_bytes(csv_bytes, "censo.csv", self.admin)

        self.assertEqual(result["createdUsers"], 1)
        self.assertEqual(result["errors"], [])
        self.assertIsNotNone(
            ResidentialUnit.query.filter_by(apartment="Torre 3 Apto 303").first()
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
            date=(now_colombia().date() + timedelta(days=5)).isoformat(),
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
        self.assertTrue(response.json["fileName"].startswith("Respaldo_Completo_DOMUX_"))
        self.assertNotIn("Legal", response.json["fileName"])
        workbook = load_workbook(
            io.BytesIO(base64.b64decode(response.json["base64"])),
            read_only=True,
            data_only=True,
        )
        self.assertEqual(workbook.sheetnames, [
            "Usuarios_y_Apartamentos",
            "Fichas_Hogar_Detalle",
            "PQRS_Radicados",
            "PQRS_Historial_Chat",
            "Reservas_Zonas_Comunes",
            "Visitas_Porteria",
            "Paqueteria_Porteria",
            "Logs_Auditoria",
        ])

    def test_scoped_export_returns_exact_valid_workbook_sheets(self):
        expected_sheets = {
            "all": [
                "Usuarios_y_Apartamentos",
                "Fichas_Hogar_Detalle",
                "PQRS_Radicados",
                "PQRS_Historial_Chat",
                "Reservas_Zonas_Comunes",
                "Visitas_Porteria",
                "Paqueteria_Porteria",
                "Logs_Auditoria",
            ],
            "users": ["Usuarios_y_Apartamentos", "Fichas_Hogar_Detalle"],
            "pqrs": ["PQRS_Radicados", "PQRS_Historial_Chat"],
            "reservations": ["Reservas_Zonas_Comunes"],
            "security": ["Visitas_Porteria", "Paqueteria_Porteria"],
            "audit": ["Logs_Auditoria"],
        }

        for scope, sheet_names in expected_sheets.items():
            with self.subTest(scope=scope):
                response = self.client.get(
                    f"/api/admin/export/legal-report?scope={scope}",
                    headers=self.headers(),
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["scope"], scope)
                self.assertEqual(response.json["mimeType"], MIME_XLSX)
                self.assertTrue(response.json["fileName"].endswith(".xlsx"))
                self.assertNotIn("Legal", response.json["fileName"])
                workbook = load_workbook(
                    io.BytesIO(base64.b64decode(response.json["base64"])),
                    read_only=True,
                    data_only=True,
                )
                self.assertEqual(workbook.sheetnames, sheet_names)
                if scope == "users":
                    self.assertEqual(
                        tuple(cell.value for cell in workbook["Usuarios_y_Apartamentos"][1]),
                        (
                            "ID", "Nombre", "Apellido", "Correo", "Teléfono",
                            "Documento", "Rol", "Apartamento", "Tenencia",
                            "Estado Activo", "Fecha Creación",
                        ),
                    )
                    self.assertEqual(
                        tuple(cell.value for cell in workbook["Fichas_Hogar_Detalle"][1]),
                        (
                            "Apartamento", "Parqueadero", "Cuarto Útil", "Integrantes",
                            "Mascotas", "Vehículos",
                        ),
                    )

    def test_invalid_export_scope_is_rejected(self):
        response = self.client.get(
            "/api/admin/export/legal-report?scope=invalido",
            headers=self.headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Alcance inválido", response.json["error"])

    def test_users_and_complete_exports_never_include_credential_fields(self):
        db.session.add(AuditLog(
            entity_type="test",
            action="credential_redaction",
            details='{"temporaryPassword":"TempSecret123!","pushToken":"push-secret"}',
        ))
        db.session.commit()

        for scope in ("users", "all"):
            with self.subTest(scope=scope):
                response = self.client.get(
                    f"/api/admin/export/legal-report?scope={scope}",
                    headers=self.headers(),
                )
                self.assertEqual(response.status_code, 200)
                workbook = load_workbook(
                    io.BytesIO(base64.b64decode(response.json["base64"])),
                    read_only=True,
                    data_only=True,
                )
                for worksheet in workbook.worksheets:
                    for row in worksheet.iter_rows(values_only=True):
                        for value in row:
                            if isinstance(value, str):
                                self.assertNotIn("password_hash", value.lower())
                                self.assertNotIn("token_version", value.lower())
                                self.assertNotIn("TempSecret123!", value)
                                self.assertNotIn("push-secret", value)

    def test_security_export_reports_attachment_type_without_exporting_payload(self):
        attachment = "data:image/jpeg;base64," + ("A" * 33000)
        db.session.add_all([
            Visit(
                resident_id=self.resident.id,
                registered_by=self.admin.id,
                visitor_name="Visitante de prueba",
                visitor_photo_url=attachment,
                visitor_photo_type="image",
                type="visitante",
                approval_status="aprobada",
            ),
            PackageItem(
                resident_id=self.resident.id,
                registered_by=self.admin.id,
                description="Paquete de prueba",
                media_url=attachment,
                media_type="document",
            ),
        ])
        db.session.commit()

        response = self.client.get(
            "/api/admin/export/legal-report?scope=security",
            headers=self.headers(),
        )
        workbook = load_workbook(
            io.BytesIO(base64.b64decode(response.json["base64"])),
            read_only=True,
            data_only=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(workbook["Visitas_Porteria"]["I2"].value, "Sí / image")
        self.assertEqual(workbook["Paqueteria_Porteria"]["I2"].value, "Sí / document")
        for worksheet in workbook.worksheets:
            for row in worksheet.iter_rows(values_only=True):
                self.assertNotIn(attachment, row)

    def test_non_admin_roles_cannot_export_workbooks(self):
        for role in ("RESIDENT", "GUARD"):
            with self.subTest(role=role):
                user = User(
                    name=f"{role} usuario",
                    email=f"{role.lower()}-export@test.local",
                    password_hash=generate_password_hash("User123*"),
                    role=role,
                    is_active=True,
                )
                db.session.add(user)
                db.session.commit()
                response = self.client.get(
                    "/api/admin/export/legal-report",
                    headers=self.headers(user),
                )
                self.assertEqual(response.status_code, 403)

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
            date=(now_colombia().date() - timedelta(days=1)).isoformat(),
            time_slot="10:00-12:00",
            status="aprobada",
        )
        rejected_reservation = Reservation(
            resident_id=self.resident.id,
            common_area_id=self.area.id,
            date=(now_colombia().date() + timedelta(days=3)).isoformat(),
            time_slot="12:00-14:00",
            status="rechazada",
        )
        active_reservation = Reservation(
            resident_id=self.resident.id,
            common_area_id=self.area.id,
            date=(now_colombia().date() + timedelta(days=4)).isoformat(),
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
