"""Pruebas de los documentos de la unidad (DEC-032).

La administración sube el manual de convivencia, las reglas, los presupuestos aprobados y demás documentos, y
marca quién los puede ver: propietarios, arrendatarios, otros residentes y portería. Aquí se prueba que cada
persona vea solo lo suyo, que el archivo se revise por sus primeros bytes, que nada se borre y que todo
cambio quede en la auditoría.
"""

import base64
import json
import unittest

import env_setup  # noqa: F401  (va antes de importar la app)

from extensions import db
from models import AuditLog, Notification, UnitDocument, User
from services import document_service
from services.media import MAX_MEDIA_BYTES
from structure_fixtures import apartment_for
from test_pqrs import PqrsTestCase
from werkzeug.security import generate_password_hash

PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"png" * 20
JPEG = b"\xff\xd8\xff\xe0" + b"jpeg" * 20
WEBP = b"RIFF" + b"\x24\x00\x00\x00" + b"WEBP" + b"VP8 " * 8
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
HTML = b"<html><script>alert(1)</script></html>"
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32

ALL_RESIDENTS = ["propietario", "arrendatario", "residente"]


def data_url(raw, mime="application/octet-stream"):
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


class DocumentsTestCase(PqrsTestCase):
    """Base con un administrador, un guardia y un residente de cada tipo."""

    def setUp(self):
        super().setUp()
        # self.resident es propietario (el tipo por defecto); se suman un arrendatario y otro residente.
        self.tenant = self.make_resident("Inquilina", "tenant@test.local", "arrendatario", "Torre 3 · 303")
        self.relative = self.make_resident("Familiar", "relative@test.local", "residente", "Torre 4 · 404")
        db.session.commit()

    def make_resident(self, name, email, occupancy, apartment):
        user = User(
            name=name, email=email, password_hash=generate_password_hash("Resident123*"), role="RESIDENT",
            apartment_ref=apartment_for(apartment), occupancy_type=occupancy, is_active=True,
        )
        db.session.add(user)
        return user

    def body(self, **changes):
        body = {
            "title": "Manual de convivencia", "category": "convivencia", "fileName": "manual.pdf",
            "file": data_url(PDF, "application/pdf"), "visibleTo": ALL_RESIDENTS,
        }
        body.update(changes)
        return {key: value for key, value in body.items() if value is not None}

    def upload(self, user=None, **changes):
        return self.client.post("/api/documents", json=self.body(**changes), headers=self.auth(user or self.admin))

    def made(self, **changes):
        """Sube un documento y devuelve lo que contestó la API."""
        response = self.upload(**changes)
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True)[:300])
        return response.get_json()["document"]

    def listing(self, user, **query):
        return self.client.get("/api/documents", headers=self.auth(user), query_string=query)

    def titles(self, user, **query):
        return [item["title"] for item in self.listing(user, **query).get_json()["documents"]]

    def fetch(self, user, document_id, suffix=""):
        return self.client.get(f"/api/documents/{document_id}{suffix}", headers=self.auth(user))

    def edit(self, document_id, body, user=None):
        return self.client.put(f"/api/documents/{document_id}", json=body, headers=self.auth(user or self.admin))

    def retire(self, document_id, user=None):
        return self.client.delete(f"/api/documents/{document_id}", headers=self.auth(user or self.admin))

    def restore(self, document_id, user=None):
        return self.client.post(f"/api/documents/{document_id}/restore", headers=self.auth(user or self.admin))

    def logs(self):
        return AuditLog.query.filter_by(entity_type="unit_document").order_by(AuditLog.id).all()


class PermissionsTests(DocumentsTestCase):
    def test_only_the_administration_changes_documents(self):
        document = self.made()
        for user in (self.guard, self.resident, self.tenant):
            with self.subTest(user=user.email):
                self.assertEqual(self.upload(user, title="Otro").status_code, 403)
                self.assertEqual(self.edit(document["id"], {"title": "Otro"}, user).status_code, 403)
                self.assertEqual(self.retire(document["id"], user).status_code, 403)
                self.assertEqual(self.restore(document["id"], user).status_code, 403)
        self.assertEqual(UnitDocument.query.count(), 1)
        self.assertEqual(self.logs()[0].action, "uploaded")
        self.assertEqual(len(self.logs()), 1)

    def test_everything_needs_a_session(self):
        document = self.made()
        for method, path in (
            ("get", "/api/documents"), ("post", "/api/documents"),
            ("get", f"/api/documents/{document['id']}"), ("put", f"/api/documents/{document['id']}"),
            ("get", f"/api/documents/{document['id']}/file"), ("delete", f"/api/documents/{document['id']}"),
            ("post", f"/api/documents/{document['id']}/restore"),
        ):
            with self.subTest(path=path, method=method):
                self.assertEqual(getattr(self.client, method)(path).status_code, 401)


class UploadTests(DocumentsTestCase):
    def test_the_administration_publishes_a_document(self):
        response = self.upload(description="  Versión aprobada en la asamblea.  ")

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        document = body["document"]
        self.assertEqual(body["message"], "Documento publicado")
        self.assertEqual(body["notified"], 0)
        self.assertEqual(document["title"], "Manual de convivencia")
        self.assertEqual(document["description"], "Versión aprobada en la asamblea.")
        self.assertEqual((document["category"], document["categoryLabel"]), ("convivencia", "Manual de convivencia"))
        self.assertEqual((document["fileName"], document["mimeType"], document["kind"]), ("manual.pdf", "application/pdf", "pdf"))
        self.assertEqual(document["sizeBytes"], len(PDF))
        self.assertEqual(len(document["version"]), 12)
        self.assertEqual(document["visibleTo"], ALL_RESIDENTS)
        self.assertEqual(document["uploadedByName"], "Admin")
        self.assertFalse(document["isRetired"])
        self.assertNotIn("content", document)
        self.assertNotIn("file", document)

        row = db.session.get(UnitDocument, document["id"])
        self.assertEqual(bytes(row.content), PDF)
        self.assertEqual(row.uploaded_by_id, self.admin.id)

    def test_the_audit_records_who_published_what(self):
        document = self.made(visibleTo=["propietario", "guardia"])

        (log,) = self.logs()
        self.assertEqual((log.entity_id, log.action, log.actor_id), (document["id"], "uploaded", self.admin.id))
        details = json.loads(log.details)
        self.assertEqual(details["title"], "Manual de convivencia")
        self.assertEqual(details["visibleTo"], ["propietario", "guardia"])
        self.assertEqual(details["sizeBytes"], len(PDF))
        self.assertNotIn("content", details)

    def test_pdf_and_the_three_image_types_are_accepted_with_their_real_extension(self):
        for index, (raw, mime, extension, kind) in enumerate((
            (PDF, "application/pdf", ".pdf", "pdf"),
            (PNG, "image/png", ".png", "image"),
            (JPEG, "image/jpeg", ".jpg", "image"),
            (WEBP, "image/webp", ".webp", "image"),
        )):
            with self.subTest(mime=mime):
                document = self.made(title=f"Documento {index}", file=data_url(raw, mime), fileName="archivo")
                self.assertEqual(
                    (document["mimeType"], document["fileName"], document["kind"]), (mime, "archivo" + extension, kind),
                )

    def test_the_type_comes_from_the_bytes_not_from_what_the_sender_says(self):
        document = self.made(file=data_url(PDF, "image/png"), fileName="manual.png")

        self.assertEqual((document["mimeType"], document["fileName"]), ("application/pdf", "manual.pdf"))

    def test_category_and_description_are_optional(self):
        document = self.made(category=None, description=None)

        self.assertEqual((document["category"], document["categoryLabel"]), ("otro", "Otros"))
        self.assertIsNone(document["description"])

    def test_a_document_nobody_can_see_is_only_for_the_administration(self):
        document = self.made(visibleTo=[])

        self.assertEqual(document["visibleTo"], [])
        self.assertEqual(self.titles(self.admin), ["Manual de convivencia"])
        for user in (self.resident, self.tenant, self.relative, self.guard):
            self.assertEqual(self.titles(user), [])

    def test_the_audiences_are_saved_once_and_in_the_usual_order(self):
        document = self.made(visibleTo=["guardia", "arrendatario", "guardia", "propietario"])

        self.assertEqual(document["visibleTo"], ["propietario", "arrendatario", "guardia"])

    def test_what_is_required(self):
        for field, text in (("title", "título"), ("file", "archivo"), ("visibleTo", "visibleTo")):
            with self.subTest(field=field):
                body = self.body()
                body.pop(field)
                response = self.client.post("/api/documents", json=body, headers=self.auth(self.admin))
                self.assertEqual(response.status_code, 400)
                self.assertIn(text, response.get_json()["error"])
        self.assertEqual(UnitDocument.query.count(), 0)

    def test_the_title_is_checked(self):
        for value, text in (("   ", "vacío"), (7, "obligatorio"), ("x" * 151, "150")):
            with self.subTest(value=value):
                response = self.upload(title=value)
                self.assertEqual(response.status_code, 400)
                self.assertIn(text, response.get_json()["error"])
        self.assertEqual(self.made(title="x" * 150)["title"], "x" * 150)

    def test_extra_spaces_in_the_title_are_cleaned(self):
        self.assertEqual(self.made(title="  Presupuesto   2026 ")["title"], "Presupuesto 2026")

    def test_the_description_is_checked(self):
        self.assertEqual(self.upload(description="x" * 501).status_code, 400)
        self.assertEqual(self.upload(description=123).status_code, 400)
        self.assertEqual(UnitDocument.query.count(), 0)

    def test_category_and_audience_must_exist(self):
        self.assertEqual(self.upload(category="secreto").status_code, 400)
        self.assertEqual(self.upload(category=5).status_code, 400)
        response = self.upload(visibleTo=["propietario", "vecinos"])
        self.assertEqual(response.status_code, 400)
        self.assertIn("vecinos", response.get_json()["error"])
        self.assertEqual(self.upload(visibleTo="propietario").status_code, 400)
        self.assertEqual(self.upload(visibleTo=[1]).status_code, 400)
        self.assertEqual(UnitDocument.query.count(), 0)

    def test_notify_must_be_true_or_false(self):
        self.assertEqual(self.upload(notify="si").status_code, 400)
        self.assertEqual(UnitDocument.query.count(), 0)


class FileCheckTests(DocumentsTestCase):
    def refused(self, file, text):
        response = self.upload(file=file)
        self.assertEqual(response.status_code, 400, response.get_data(as_text=True)[:200])
        self.assertIn(text, response.get_json()["error"])
        self.assertEqual(UnitDocument.query.count(), 0)

    def test_what_is_not_a_document_is_refused_whatever_its_name_says(self):
        for name, raw in (("svg", SVG), ("html", HTML), ("video", MP4), ("texto", b"hola, esto no es un pdf")):
            with self.subTest(name=name):
                self.refused(data_url(raw, "application/pdf"), "PDF, PNG, JPG o WebP")

    def test_the_file_must_arrive_as_a_base64_file(self):
        self.refused("https://ejemplo.com/manual.pdf", "no como enlace")
        self.refused(12345, "texto")
        self.refused("data:application/pdf;base64,@@@", "No se pudo leer")
        self.refused(data_url(b""), "vacío")

    def test_the_file_cannot_weigh_more_than_six_megabytes(self):
        big = PDF + b"0" * (MAX_MEDIA_BYTES - len(PDF) + 1)
        self.refused(data_url(big, "application/pdf"), "6 MB")
        exact = PDF + b"0" * (MAX_MEDIA_BYTES - len(PDF))
        self.assertEqual(self.upload(file=data_url(exact, "application/pdf")).status_code, 201)

    def test_the_file_name_is_cleaned(self):
        for name, expected in (
            ("../../etc/passwd.pdf", "passwd.pdf"),
            ("C:\\Documentos\\Acta 5.pdf", "Acta 5.pdf"),
            ("manual.exe", "manual.pdf"),
            ('presupuesto<2026>?.pdf', "presupuesto2026.pdf"),
            ("   Acta   de   asamblea .PDF", "Acta de asamblea.pdf"),
            ("Presupuesto ñandú.pdf", "Presupuesto ñandú.pdf"),
        ):
            with self.subTest(name=name):
                document = self.made(title=f"Doc {expected}", fileName=name)
                self.assertEqual(document["fileName"], expected)

    def test_without_a_name_the_title_is_used(self):
        self.assertEqual(self.made(fileName=None)["fileName"], "Manual de convivencia.pdf")
        self.assertEqual(self.made(title="Reglas", fileName="***")["fileName"], "Reglas.pdf")

    def test_a_long_name_is_cut(self):
        document = self.made(fileName="a" * 400 + ".pdf")
        self.assertEqual(document["fileName"], "a" * document_service.FILE_NAME_MAX + ".pdf")


class DuplicatedTitleTests(DocumentsTestCase):
    def test_two_published_documents_cannot_share_a_title(self):
        self.made()

        for title in ("Manual de convivencia", "manual de CONVIVENCIA", "  Manual  de convivencia "):
            with self.subTest(title=title):
                response = self.upload(title=title)
                self.assertEqual(response.status_code, 409)
                self.assertIn("Ya hay un documento llamado", response.get_json()["error"])
        self.assertEqual(UnitDocument.query.count(), 1)

    def test_a_retired_document_frees_its_title(self):
        first = self.made()
        self.retire(first["id"])

        self.assertEqual(self.upload().status_code, 201)
        self.assertEqual(UnitDocument.query.count(), 2)


class VisibilityTests(DocumentsTestCase):
    def setUp(self):
        super().setUp()
        self.owners = self.made(title="Para propietarios", visibleTo=["propietario"])
        self.tenants = self.made(title="Para arrendatarios", visibleTo=["arrendatario"])
        self.others = self.made(title="Para otros residentes", visibleTo=["residente"])
        self.guards = self.made(title="Para portería", visibleTo=["guardia"])
        self.nobody = self.made(title="Solo administración", visibleTo=[])
        self.everyone = self.made(title="Para todos", visibleTo=[*ALL_RESIDENTS, "guardia"])

    def test_each_person_sees_only_what_was_marked_for_them(self):
        for user, expected in (
            (self.resident, {"Para propietarios", "Para todos"}),
            (self.tenant, {"Para arrendatarios", "Para todos"}),
            (self.relative, {"Para otros residentes", "Para todos"}),
            (self.guard, {"Para portería", "Para todos"}),
            (self.other_resident, {"Para propietarios", "Para todos"}),
        ):
            with self.subTest(user=user.email):
                self.assertEqual(set(self.titles(user)), expected)

    def test_the_administration_sees_everything(self):
        self.assertEqual(len(self.titles(self.admin)), 6)

    def test_a_resident_without_a_type_counts_as_owner(self):
        self.resident.occupancy_type = None
        db.session.commit()

        self.assertEqual(set(self.titles(self.resident)), {"Para propietarios", "Para todos"})

    def test_only_the_administration_sees_who_can_see_a_document(self):
        admin_item = self.listing(self.admin).get_json()["documents"][0]
        resident_item = self.listing(self.resident).get_json()["documents"][0]

        self.assertIn("visibleTo", admin_item)
        self.assertIn("isRetired", admin_item)
        for key in ("visibleTo", "isRetired", "retiredAt", "retiredByName"):
            self.assertNotIn(key, resident_item)

    def test_a_document_that_is_not_yours_does_not_exist(self):
        missing = self.fetch(self.resident, 9999)
        for suffix in ("", "/file"):
            with self.subTest(suffix=suffix):
                hidden = self.fetch(self.resident, self.tenants["id"], suffix)
                self.assertEqual(hidden.status_code, 404)
                self.assertEqual(hidden.get_json(), missing.get_json())
                self.assertEqual(self.fetch(self.resident, self.owners["id"], suffix).status_code, 200)

    def test_the_list_can_be_narrowed_by_type(self):
        self.made(title="Presupuesto 2027", category="presupuesto", visibleTo=["propietario"])

        self.assertEqual(self.titles(self.resident, category="presupuesto"), ["Presupuesto 2027"])
        self.assertEqual(self.listing(self.resident, category="secreto").status_code, 400)

    def test_the_list_brings_the_types_and_audiences_that_exist(self):
        body = self.listing(self.resident).get_json()

        self.assertEqual([item["key"] for item in body["categories"]], list(document_service.DOCUMENT_CATEGORIES))
        self.assertEqual(
            [item["key"] for item in body["audiences"]], ["propietario", "arrendatario", "residente", "guardia"],
        )

    def test_the_newest_documents_come_first(self):
        self.assertEqual(self.titles(self.admin)[0], "Para todos")

    def test_changing_who_sees_a_document_takes_effect_at_once(self):
        self.assertEqual(self.edit(self.nobody["id"], {"visibleTo": ["arrendatario", "guardia"]}).status_code, 200)

        self.assertIn("Solo administración", self.titles(self.tenant))
        self.assertIn("Solo administración", self.titles(self.guard))
        self.assertNotIn("Solo administración", self.titles(self.resident))

    def test_a_retired_document_disappears_for_everyone_but_the_administration(self):
        self.assertEqual(self.retire(self.everyone["id"]).status_code, 200)

        for user in (self.resident, self.tenant, self.relative, self.guard):
            self.assertNotIn("Para todos", self.titles(user))
            self.assertEqual(self.fetch(user, self.everyone["id"]).status_code, 404)
            self.assertEqual(self.fetch(user, self.everyone["id"], "/file").status_code, 404)
        self.assertNotIn("Para todos", self.titles(self.admin))
        self.assertIn("Para todos", self.titles(self.admin, includeRetired="true"))
        self.assertEqual(self.fetch(self.admin, self.everyone["id"]).status_code, 200)

    def test_include_retired_is_ignored_for_everyone_but_the_administration(self):
        self.retire(self.owners["id"])

        self.assertNotIn("Para propietarios", self.titles(self.resident, includeRetired="true"))
        self.assertEqual(self.listing(self.admin, includeRetired="quizás").status_code, 400)


class FileDeliveryTests(DocumentsTestCase):
    def test_the_file_comes_back_exactly_as_it_was_uploaded(self):
        document = self.made()

        response = self.fetch(self.resident, document["id"], "/file")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, PDF)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertEqual(response.headers["Content-Disposition"], 'inline; filename="manual.pdf"')
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["Cache-Control"], "private, no-cache")
        self.assertIn("sandbox", response.headers["Content-Security-Policy"])

    def test_an_image_comes_back_with_its_own_type(self):
        document = self.made(title="Plano", file=data_url(PNG, "image/png"), fileName="plano")

        response = self.fetch(self.resident, document["id"], "/file")

        self.assertEqual((response.mimetype, response.data), ("image/png", PNG))

    def test_a_name_with_accents_travels_with_its_encoded_form(self):
        document = self.made(title="Presupuesto", fileName="Presupuesto ñandú 2026.pdf")

        header = self.fetch(self.resident, document["id"], "/file").headers["Content-Disposition"]

        self.assertIn("filename*=UTF-8''Presupuesto%20%C3%B1and%C3%BA%202026.pdf", header)
        header.encode("ascii")  # la cabecera completa viaja en ASCII

    def test_if_the_file_did_not_change_the_answer_is_empty(self):
        document = self.made()
        first = self.fetch(self.resident, document["id"], "/file")

        again = self.client.get(
            f"/api/documents/{document['id']}/file",
            headers={**self.auth(self.resident), "If-None-Match": first.headers["ETag"]},
        )

        self.assertEqual(again.status_code, 304)
        self.assertEqual(again.data, b"")
        self.assertEqual(again.headers["ETag"], first.headers["ETag"])

    def test_a_304_still_requires_being_allowed_to_see_the_document(self):
        document = self.made(visibleTo=["arrendatario"])
        etag = self.fetch(self.tenant, document["id"], "/file").headers["ETag"]

        hidden = self.client.get(
            f"/api/documents/{document['id']}/file", headers={**self.auth(self.resident), "If-None-Match": etag},
        )

        self.assertEqual(hidden.status_code, 404)

    def test_the_version_changes_only_with_the_file(self):
        first = self.made(title="Uno")
        second = self.made(title="Dos", file=data_url(PDF + b"otra version", "application/pdf"))
        same = self.made(title="Tres")

        self.assertEqual(first["version"], same["version"])
        self.assertNotEqual(first["version"], second["version"])

    def test_listing_does_not_read_the_files(self):
        self.made()
        statements = []

        from sqlalchemy import event

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(db.engine, "before_cursor_execute", record)
        try:
            self.listing(self.resident)
        finally:
            event.remove(db.engine, "before_cursor_execute", record)

        selects = [text for text in statements if "unit_documents" in text and text.lstrip().upper().startswith("SELECT")]
        self.assertTrue(selects)
        for text in selects:
            self.assertNotIn("unit_documents.content ", text.replace(",", " "), "la lista no debe leer el archivo")


class UpdateTests(DocumentsTestCase):
    def test_the_administration_changes_the_details(self):
        document = self.made(description="Primera")

        response = self.edit(document["id"], {
            "title": "Manual de convivencia 2027", "description": "Segunda", "category": "reglas",
            "visibleTo": ["propietario"],
        })

        self.assertEqual(response.status_code, 200)
        body = response.get_json()["document"]
        self.assertEqual(response.get_json()["message"], "Documento actualizado")
        self.assertEqual(
            (body["title"], body["description"], body["category"], body["visibleTo"]),
            ("Manual de convivencia 2027", "Segunda", "reglas", ["propietario"]),
        )

    def test_only_what_is_sent_changes(self):
        document = self.made(description="Primera")

        body = self.edit(document["id"], {"description": "Cambiada"}).get_json()["document"]

        self.assertEqual(
            (body["title"], body["category"], body["visibleTo"], body["description"]),
            ("Manual de convivencia", "convivencia", ALL_RESIDENTS, "Cambiada"),
        )

    def test_the_description_can_be_cleared(self):
        document = self.made(description="Primera")

        body = self.edit(document["id"], {"description": None}).get_json()["document"]

        self.assertIsNone(body["description"])

    def test_the_audit_keeps_what_there_was_and_what_there_is_now(self):
        document = self.made()

        self.edit(document["id"], {"title": "Otro título", "visibleTo": ["guardia"], "category": "convivencia"})

        log = self.logs()[-1]
        self.assertEqual(log.action, "updated")
        details = json.loads(log.details)
        self.assertEqual(details["before"], {"title": "Manual de convivencia", "visibleTo": ALL_RESIDENTS})
        self.assertEqual(details["after"], {"title": "Otro título", "visibleTo": ["guardia"]})

    def test_saving_the_same_values_leaves_no_trace_in_the_audit(self):
        document = self.made()

        response = self.edit(document["id"], {"title": "Manual de convivencia", "visibleTo": ALL_RESIDENTS})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.logs()), 1)

    def test_a_change_needs_at_least_one_value(self):
        document = self.made()

        self.assertEqual(self.edit(document["id"], {}).status_code, 400)
        self.assertEqual(self.edit(document["id"], {"otraCosa": 1}).status_code, 400)

    def test_the_values_are_checked_like_when_uploading(self):
        document = self.made()

        for body in (
            {"title": ""}, {"title": "x" * 151}, {"description": "x" * 501}, {"category": "secreto"},
            {"visibleTo": ["vecinos"]}, {"visibleTo": "guardia"},
        ):
            with self.subTest(body=body):
                self.assertEqual(self.edit(document["id"], body).status_code, 400)

    def test_the_file_is_not_replaced_and_the_message_says_what_to_do(self):
        document = self.made()

        response = self.edit(document["id"], {"file": data_url(PNG, "image/png")})

        self.assertEqual(response.status_code, 400)
        self.assertIn("sube un documento nuevo", response.get_json()["error"])
        self.assertEqual(bytes(db.session.get(UnitDocument, document["id"]).content), PDF)

    def test_the_title_cannot_be_taken_by_another_published_document(self):
        self.made(title="Reglas")
        other = self.made(title="Presupuesto")

        response = self.edit(other["id"], {"title": "reglas"})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.edit(other["id"], {"title": "PRESUPUESTO"}).status_code, 200)  # el suyo propio sí

    def test_a_retired_document_cannot_be_changed(self):
        document = self.made()
        self.retire(document["id"])

        response = self.edit(document["id"], {"title": "Otro"})

        self.assertEqual(response.status_code, 409)
        self.assertIn("retirado", response.get_json()["error"])

    def test_a_document_that_does_not_exist(self):
        self.assertEqual(self.edit(9999, {"title": "Otro"}).status_code, 404)
        self.assertEqual(self.retire(9999).status_code, 404)
        self.assertEqual(self.restore(9999).status_code, 404)


class RetireAndRestoreTests(DocumentsTestCase):
    def test_retiring_does_not_delete_anything(self):
        document = self.made()

        response = self.retire(document["id"])

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["message"], "Documento retirado")
        self.assertTrue(body["document"]["isRetired"])
        self.assertEqual(body["document"]["retiredByName"], "Admin")
        row = db.session.get(UnitDocument, document["id"])
        self.assertIsNotNone(row.retired_at)
        self.assertEqual(row.retired_by_id, self.admin.id)
        self.assertEqual(bytes(row.content), PDF)
        self.assertEqual(self.logs()[-1].action, "retired")

    def test_retiring_twice_is_refused(self):
        document = self.made()
        self.retire(document["id"])

        self.assertEqual(self.retire(document["id"]).status_code, 409)
        self.assertEqual(len(self.logs()), 2)

    def test_the_administration_publishes_it_again_with_the_same_audiences(self):
        document = self.made(visibleTo=["arrendatario"])
        self.retire(document["id"])
        self.assertEqual(self.titles(self.tenant), [])

        response = self.restore(document["id"])

        self.assertEqual(response.status_code, 200)
        body = response.get_json()["document"]
        self.assertEqual(response.get_json()["message"], "Documento publicado de nuevo")
        self.assertFalse(body["isRetired"])
        self.assertIsNone(body["retiredAt"])
        self.assertEqual(body["visibleTo"], ["arrendatario"])
        self.assertEqual(self.titles(self.tenant), ["Manual de convivencia"])
        self.assertEqual(self.logs()[-1].action, "restored")

    def test_publishing_what_is_already_published_is_refused(self):
        document = self.made()

        self.assertEqual(self.restore(document["id"]).status_code, 409)

    def test_it_cannot_come_back_if_another_document_took_its_title(self):
        first = self.made()
        self.retire(first["id"])
        self.made()

        response = self.restore(first["id"])

        self.assertEqual(response.status_code, 409)
        self.assertIn("Ya hay un documento llamado", response.get_json()["error"])


class NoticeTests(DocumentsTestCase):
    def notices(self):
        return Notification.query.filter_by(type="document").order_by(Notification.id).all()

    def test_nobody_is_notified_unless_the_administration_asks(self):
        self.made()

        self.assertEqual(self.notices(), [])

    def test_the_people_who_can_see_it_are_notified(self):
        response = self.upload(visibleTo=["propietario"], notify=True)

        # Los dos residentes de la prueba son propietarios; la arrendataria, el familiar y el guardia no.
        self.assertEqual(response.get_json()["notified"], 2)
        self.assertEqual({notice.user_id for notice in self.notices()}, {self.resident.id, self.other_resident.id})
        notice = self.notices()[0]
        self.assertEqual(notice.title, "Nuevo documento")
        self.assertEqual(notice.message, "Manual de convivencia: Manual de convivencia")
        self.assertFalse(notice.is_read)

    def test_each_audience_gets_its_own_notice(self):
        self.upload(visibleTo=["arrendatario", "residente", "guardia"], notify=True)

        self.assertEqual(
            {notice.user_id for notice in self.notices()}, {self.tenant.id, self.relative.id, self.guard.id},
        )

    def test_an_owner_without_a_type_is_notified_as_owner(self):
        self.resident.occupancy_type = None
        db.session.commit()

        self.upload(visibleTo=["propietario"], notify=True)

        self.assertEqual([notice.user_id for notice in self.notices()], [self.resident.id, self.other_resident.id])

    def test_deactivated_people_are_not_notified(self):
        self.other_resident.is_active = False
        db.session.commit()

        response = self.upload(visibleTo=["propietario"], notify=True)

        self.assertEqual(response.get_json()["notified"], 1)
        self.assertEqual([notice.user_id for notice in self.notices()], [self.resident.id])

    def test_a_document_only_for_the_administration_notifies_nobody(self):
        response = self.upload(visibleTo=[], notify=True)

        self.assertEqual(response.get_json()["notified"], 0)
        self.assertEqual(self.notices(), [])

    def test_a_rejected_upload_notifies_nobody(self):
        self.upload(visibleTo=ALL_RESIDENTS, notify=True, file=data_url(SVG, "image/svg+xml"))

        self.assertEqual(self.notices(), [])


if __name__ == "__main__":
    unittest.main()
