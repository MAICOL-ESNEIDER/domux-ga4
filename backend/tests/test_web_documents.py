"""Pruebas de los documentos de la unidad en la web de administración (DEC-032): la lista, subir un documento,
editarlo, retirarlo, volver a publicarlo y abrir su archivo."""

import hashlib
import io
import re
import unittest

from extensions import db
from models import AuditLog, Notification, UnitDocument, User
from structure_fixtures import apartment_for
from web import uploads
from web_testing import PASSWORD, WebTestCase
from werkzeug.security import generate_password_hash

PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"png" * 20
JPEG = b"\xff\xd8\xff\xe0" + b"jpeg" * 20
WEBP = b"RIFF" + b"\x24\x00\x00\x00" + b"WEBP" + b"VP8 " * 8
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
HTML = b"<html><script>alert(1)</script></html>"
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32


class WebDocumentsTests(WebTestCase):
    def setUp(self):
        super().setUp()
        self.tenant = User(
            name="Inquilina", email="inquilina-web@test.local", role="RESIDENT", is_active=True,
            password_hash=generate_password_hash(PASSWORD), apartment_ref=apartment_for("Torre 3 · 303"),
            occupancy_type="arrendatario",
        )
        db.session.add(self.tenant)
        db.session.commit()
        self.log_in()

    # --- Ayudas ---------------------------------------------------------------------------------------

    def add(self, title="Manual de convivencia", category="convivencia", audiences=("propietario",), raw=PDF,
            mime="application/pdf", name="manual.pdf", retired=False, description=None):
        document = UnitDocument(
            title=title, description=description, category=category, file_name=name, mime_type=mime,
            size_bytes=len(raw), content=raw, content_sha256=hashlib.sha256(raw).hexdigest(),
            uploaded_by_id=self.admin.id,
            **{UnitDocument.AUDIENCE_COLUMNS[key]: True for key in audiences},
        )
        if retired:
            document.retire(self.admin)
        db.session.add(document)
        db.session.commit()
        return document

    def upload(self, data=None, file=("manual.pdf", PDF)):
        """Manda el formulario de «Subir documento» con un manual de convivencia para propietarios."""
        form = {"title": "Manual de convivencia", "category": "convivencia", "publico_propietario": "1", **(data or {})}
        if file is not None:
            form["file"] = (io.BytesIO(file[1]), file[0])
        # Una casilla sin marcar no viaja en el formulario: «None» la quita.
        return self.post("/web/documentos/nuevo", {key: value for key, value in form.items() if value is not None})

    def stored(self, title="Manual de convivencia"):
        return UnitDocument.query.filter_by(title=title).first()

    def flashes(self, response):
        """Los avisos que dejó la respuesta, leídos en la página siguiente."""
        return self.text(self.client.get(response.headers["Location"]))

    def logs(self, action):
        return AuditLog.query.filter_by(entity_type="unit_document", action=action).all()

    # --- La lista -------------------------------------------------------------------------------------

    def test_the_page_explains_what_it_is_for_and_invites_to_upload_the_first_document(self):
        body = self.page("/web/documentos")

        self.assertIn("Documentos de la unidad", body)
        self.assertIn("manual de convivencia", body)
        self.assertIn("Si no marcas a nadie, solo los ve la administración", body)
        self.assertIn("Todavía no hay documentos. Sube el primero con «Subir documento»", body)
        self.assertIn('href="/web/documentos/nuevo"', body)

    def test_the_menu_links_to_the_page_and_marks_it_as_the_current_one(self):
        self.assertIn('href="/web/documentos" aria-current="page"', self.page("/web/documentos"))
        self.assertIn("Documentos de la unidad", self.page("/web/"))

    def test_the_list_shows_title_type_audiences_size_and_who_uploaded_it(self):
        self.add("Presupuesto 2027", "presupuesto", ("propietario", "arrendatario"), description="Aprobado en marzo",
                 name="presupuesto.pdf")

        body = self.page("/web/documentos")

        for text in ("Presupuesto 2027", "Presupuestos aprobados", "Aprobado en marzo", "Propietarios, Arrendatarios",
                     "PDF · 1 KB", "por Lucía Vargas", "Abrir", "Editar", "Retirar"):
            self.assertIn(text, body)
        self.assertNotIn("Todavía no hay documentos", body)

    def test_a_document_nobody_was_given_says_that_only_the_administration_sees_it(self):
        self.add("Borrador", "otro", audiences=())

        self.assertIn("Solo la administración", self.page("/web/documentos"))

    def test_an_image_is_listed_as_an_image(self):
        self.add("Plano del parqueadero", "otro", raw=PNG, mime="image/png", name="plano.png")

        self.assertIn("Imagen · 1 KB", self.page("/web/documentos"))

    def test_the_tabs_filter_by_type_and_show_a_message_when_the_type_is_empty(self):
        self.add("Manual", "convivencia")
        self.add("Acta de marzo", "actas")

        everything = self.page("/web/documentos")
        only_minutes = self.page("/web/documentos?tipo=actas")
        empty = self.page("/web/documentos?tipo=gastos")

        self.assertIn("Manual", everything)
        self.assertIn("Acta de marzo", everything)
        self.assertIn('href="/web/documentos?tipo=actas" aria-current="page"', only_minutes)
        self.assertIn("Acta de marzo", only_minutes)
        self.assertNotIn("<strong>Manual</strong>", only_minutes)
        self.assertIn("No hay documentos de este tipo", empty)

    def test_an_unknown_type_in_the_address_shows_everything(self):
        self.add("Manual", "convivencia")

        self.assertIn("<strong>Manual</strong>", self.page("/web/documentos?tipo=inventado"))

    def test_retired_documents_wait_in_their_own_list_with_the_button_to_publish_them_again(self):
        self.add("Vigente", "otro")
        self.add("Viejo", "otro", retired=True)

        body = self.page("/web/documentos")

        self.assertIn("Documentos retirados (1)", body)
        self.assertIn("Volver a publicar", body)
        published = body.split("Documentos retirados")[0]
        self.assertIn("Vigente", published)
        self.assertNotIn("Viejo", published)
        self.assertIn("retirado el", body.split("Documentos retirados")[1])

    def test_without_a_session_the_page_sends_to_the_login(self):
        response = self.app.test_client().get("/web/documentos")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/web/login", response.headers["Location"])

    def test_a_guard_or_a_resident_cannot_open_the_pages(self):
        document = self.add()
        for email in ("guardia-web@test.local", "residente-web@test.local"):
            client = self.app.test_client()
            token = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/web/login").get_data(as_text=True))
            client.post("/web/login", data={"csrf_token": token.group(1), "email": email, "password": PASSWORD})
            for path in ("/web/documentos", "/web/documentos/nuevo", f"/web/documentos/{document.id}/editar",
                         f"/web/documentos/{document.id}/archivo"):
                self.assertNotEqual(client.get(path).status_code, 200, f"{email} {path}")

    # --- Subir ----------------------------------------------------------------------------------------

    def test_the_form_asks_for_the_file_and_who_can_see_it(self):
        body = self.page("/web/documentos/nuevo")

        self.assertIn('enctype="multipart/form-data"', body)
        for name in ("title", "category", "description", "file", "publico_propietario", "publico_arrendatario",
                     "publico_residente", "publico_guardia", "notify"):
            self.assertIn(f'name="{name}"', body, name)
        self.assertIn('accept="application/pdf,image/png,image/jpeg,image/webp"', body)
        self.assertIn("Formatos: PDF, PNG, JPG o WebP. Pesa hasta 6 MB.", body)
        for text in ("¿Quién puede verlo en la app?", "Propietarios", "Arrendatarios", "Otros residentes", "Portería",
                     "La administración siempre lo ve", "Publicar documento"):
            self.assertIn(text, body)
        self.assertRegex(body, r'id="publico_propietario" name="publico_propietario" value="1" checked')
        self.assertRegex(body, r'id="publico_arrendatario" name="publico_arrendatario" value="1" checked')
        self.assertNotRegex(body, r'id="publico_guardia" name="publico_guardia" value="1" checked')
        self.assertRegex(body, r'id="notify" name="notify" value="1" checked')

    def test_uploading_a_pdf_publishes_it_for_the_people_that_were_checked(self):
        response = self.upload({"description": "  Versión de la asamblea  ", "publico_arrendatario": "1"})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/web/documentos"))
        document = self.stored()
        self.assertEqual(document.audiences, ["propietario", "arrendatario"])
        self.assertEqual(document.category, "convivencia")
        self.assertEqual(document.description, "Versión de la asamblea")
        self.assertEqual(document.mime_type, "application/pdf")
        self.assertEqual(document.file_name, "manual.pdf")
        self.assertEqual(bytes(document.content), PDF)
        self.assertEqual(document.uploaded_by_id, self.admin.id)
        self.assertFalse(document.is_retired)
        self.assertEqual(len(self.logs("uploaded")), 1)

    def test_the_answer_tells_who_sees_it_and_how_many_people_were_told(self):
        response = self.upload({"notify": "1"})

        message = self.flashes(response)
        self.assertIn("Documento publicado", message)
        self.assertIn("Las personas que marcaste ya lo ven en la app", message)
        self.assertIn("Se avisó a 1 persona", message)

    def test_the_people_checked_get_a_notification_only_if_the_box_is_checked(self):
        self.upload({"notify": "1", "publico_arrendatario": "1"})
        self.upload({"title": "Sin aviso"})

        told = Notification.query.filter_by(type="document").all()
        self.assertEqual({item.user_id for item in told}, {self.resident.id, self.tenant.id})
        self.assertEqual(len(told), 2)

    def test_without_any_box_checked_only_the_administration_sees_it(self):
        response = self.upload({"publico_propietario": None})

        self.assertEqual(self.stored().audiences, [])
        self.assertIn("Solo la administración lo ve", self.flashes(response))
        self.assertEqual(Notification.query.filter_by(type="document").count(), 0)

    def test_every_allowed_format_is_stored_with_its_real_type(self):
        for name, content, mime in (("a.png", PNG, "image/png"), ("b.jpg", JPEG, "image/jpeg"),
                                    ("c.webp", WEBP, "image/webp"), ("d.pdf", PDF, "application/pdf")):
            with self.subTest(name=name):
                self.assertEqual(self.upload({"title": name}, (name, content)).status_code, 302)
                self.assertEqual(self.stored(name).mime_type, mime)

    def test_the_type_is_read_from_the_file_not_from_its_name(self):
        self.upload({"title": "Foto con otro nombre"}, ("acta.pdf", PNG))

        self.assertEqual(self.stored("Foto con otro nombre").mime_type, "image/png")

    def test_a_file_that_is_not_a_pdf_or_an_image_is_rejected_and_the_form_keeps_what_was_written(self):
        for name, content in (("dibujo.svg", SVG), ("pagina.html", HTML), ("video.mp4", MP4), ("raro.pdf", b"nada")):
            with self.subTest(name=name):
                response = self.upload({"title": "Con archivo malo", "description": "Para revisar"}, (name, content))
                body = self.text(response)

                self.assertEqual(response.status_code, 400)
                self.assertIn("Con archivo malo", body)
                self.assertIn("Para revisar", body)
                self.assertIn("Vuelve a elegir el archivo", body)
                self.assertEqual(UnitDocument.query.count(), 0)

    def test_not_choosing_a_file_says_so(self):
        response = self.upload(file=None)

        self.assertEqual(response.status_code, 400)
        self.assertIn("Elige el archivo del documento", self.text(response))
        self.assertEqual(UnitDocument.query.count(), 0)

    def test_an_empty_file_input_counts_as_no_file(self):
        response = self.post("/web/documentos/nuevo", {
            "title": "Vacío", "category": "otro", "file": (io.BytesIO(b""), ""),
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn("Elige el archivo del documento", self.text(response))

    def test_a_file_over_the_limit_is_rejected_with_the_maximum_in_the_message(self):
        response = self.upload(file=("enorme.pdf", PDF + b"0" * uploads.MAX_MEDIA_BYTES))

        self.assertEqual(response.status_code, 400)
        self.assertIn("El archivo pesa demasiado: el máximo es 6 MB", self.text(response))
        self.assertEqual(UnitDocument.query.count(), 0)

    def test_an_empty_title_is_rejected_by_the_server_too(self):
        response = self.upload({"title": "   "})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(UnitDocument.query.count(), 0)

    def test_a_title_already_used_by_a_published_document_is_rejected_and_nothing_is_lost(self):
        self.add("Manual de convivencia")

        response = self.upload({"description": "Lo que escribí"})

        self.assertNotEqual(response.status_code, 302)
        self.assertIn("Ya hay un documento llamado «Manual de convivencia»", self.text(response))
        self.assertIn("Lo que escribí", self.text(response))
        self.assertEqual(UnitDocument.query.count(), 1)

    def test_a_title_used_only_by_a_retired_document_can_be_used_again(self):
        self.add("Manual de convivencia", retired=True)

        self.assertEqual(self.upload().status_code, 302)
        self.assertEqual(UnitDocument.query.filter_by(title="Manual de convivencia").count(), 2)

    def test_an_unknown_type_is_rejected(self):
        response = self.upload({"category": "inventado"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(UnitDocument.query.count(), 0)

    def test_the_new_document_shows_up_in_the_list(self):
        self.upload()

        self.assertIn("<strong>Manual de convivencia</strong>", self.page("/web/documentos"))

    def test_posting_without_the_csrf_code_changes_nothing(self):
        response = self.client.post("/web/documentos/nuevo", data={
            "title": "Sin código", "category": "otro", "file": (io.BytesIO(PDF), "x.pdf"),
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(UnitDocument.query.count(), 0)

    # --- Editar ---------------------------------------------------------------------------------------

    def test_the_edit_form_shows_the_current_values_the_file_and_no_file_input(self):
        document = self.add("Reglas", "reglas", ("propietario", "guardia"), description="Vigentes", name="reglas.pdf")

        body = self.page(f"/web/documentos/{document.id}/editar")

        self.assertIn("Editar documento", body)
        self.assertRegex(body, r'name="title" type="text" value="Reglas"')
        self.assertIn("Vigentes", body)
        self.assertIn("reglas.pdf", body)
        self.assertIn(f'href="/web/documentos/{document.id}/archivo"', body)
        self.assertNotIn('type="file"', body)
        self.assertNotIn('enctype="multipart/form-data"', body)
        self.assertNotIn('name="notify"', body)
        self.assertRegex(body, r'id="publico_guardia" name="publico_guardia" value="1" checked')
        self.assertNotRegex(body, r'id="publico_arrendatario" name="publico_arrendatario" value="1" checked')
        self.assertIn('<option value="reglas" selected>', body)

    def edit(self, document, **changes):
        """Manda el formulario de edición con lo que tiene el documento y los cambios indicados."""
        form = {
            "title": document.title, "description": document.description or "", "category": document.category,
            **{f"publico_{key}": "1" for key in document.audiences},
            **changes,
        }
        return self.post(f"/web/documentos/{document.id}/editar", {k: v for k, v in form.items() if v is not None})

    def test_editing_saves_only_what_changed_and_notes_it_in_the_audit(self):
        document = self.add("Reglas", "reglas", ("propietario",), description="Vigentes")

        response = self.edit(document, title="Reglas 2027", category="actas")

        self.assertEqual(response.status_code, 302)
        self.assertIn("Documento actualizado", self.flashes(response))
        fresh = db.session.get(UnitDocument, document.id)
        self.assertEqual((fresh.title, fresh.category, fresh.description), ("Reglas 2027", "actas", "Vigentes"))
        self.assertEqual(fresh.audiences, ["propietario"])
        self.assertEqual(len(self.logs("updated")), 1)

    def test_the_audiences_can_be_changed_and_emptied(self):
        document = self.add("Reglas", "reglas", ("propietario", "arrendatario"))

        self.edit(document, publico_arrendatario=None, publico_guardia="1")
        self.assertEqual(db.session.get(UnitDocument, document.id).audiences, ["propietario", "guardia"])

        document = db.session.get(UnitDocument, document.id)
        self.edit(document, publico_propietario=None, publico_guardia=None)
        self.assertEqual(db.session.get(UnitDocument, document.id).audiences, [])

    def test_clearing_the_description_removes_it(self):
        document = self.add("Reglas", description="Vigentes")

        self.edit(document, description="")

        self.assertIsNone(db.session.get(UnitDocument, document.id).description)

    def test_sending_the_form_without_changes_says_so_and_saves_nothing(self):
        document = self.add("Reglas", description="Vigentes")

        response = self.edit(document)

        self.assertEqual(response.status_code, 200)
        self.assertIn("No cambiaste nada", self.text(response))
        self.assertEqual(self.logs("updated"), [])

    def test_a_title_already_used_by_another_document_is_rejected_and_the_form_keeps_it(self):
        self.add("Manual de convivencia")
        other = self.add("Reglas", "reglas")

        response = self.edit(other, title="manual de CONVIVENCIA")

        self.assertNotEqual(response.status_code, 302)
        self.assertIn("Ya hay un documento llamado «manual de CONVIVENCIA»", self.text(response))
        self.assertIn("manual de CONVIVENCIA", self.text(response))
        self.assertEqual(db.session.get(UnitDocument, other.id).title, "Reglas")

    def test_a_retired_document_cannot_be_edited_and_sends_back_to_the_list_with_a_reason(self):
        document = self.add("Viejo", retired=True)

        for send in (lambda: self.client.get(f"/web/documentos/{document.id}/editar"),
                     lambda: self.edit(document, title="Nuevo título")):
            response = send()
            self.assertEqual(response.status_code, 302)
            self.assertIn("Ese documento está retirado", self.flashes(response))
        self.assertEqual(db.session.get(UnitDocument, document.id).title, "Viejo")

    def test_editing_a_document_that_does_not_exist_shows_the_page_not_found(self):
        self.assertEqual(self.client.get("/web/documentos/999/editar").status_code, 404)
        self.assertEqual(self.post("/web/documentos/999/editar", {"title": "x"}).status_code, 404)

    # --- Retirar y volver a publicar ------------------------------------------------------------------

    def test_retiring_hides_the_document_from_the_residents_but_keeps_it_stored(self):
        document = self.add("Manual", audiences=("propietario",))

        response = self.post(f"/web/documentos/{document.id}/retirar")

        self.assertEqual(response.status_code, 302)
        self.assertIn("Documento retirado", self.flashes(response))
        fresh = db.session.get(UnitDocument, document.id)
        self.assertTrue(fresh.is_retired)
        self.assertEqual(fresh.retired_by_id, self.admin.id)
        self.assertEqual(bytes(fresh.content), PDF)
        self.assertEqual(len(self.logs("retired")), 1)
        body = self.page("/web/documentos")
        self.assertIn("Documentos retirados (1)", body)
        self.assertIn("retirado el", body)
        self.assertIn("por Lucía Vargas", body.split("Documentos retirados")[1])
        # La residente ya no lo ve en la app.
        token = self.app.test_client().post("/api/auth/login", json={"email": "residente-web@test.local", "password": PASSWORD})
        resident_token = token.get_json()["token"]
        listed = self.app.test_client().get("/api/documents", headers={"Authorization": f"Bearer {resident_token}"})
        self.assertEqual(listed.get_json()["documents"], [])

    def test_retiring_asks_for_confirmation_with_the_title(self):
        self.add("Manual de convivencia")

        body = self.page("/web/documentos")

        self.assertIn("¿Retirar «Manual de convivencia»?", body)
        self.assertIn("queda guardado y lo puedes volver a publicar", body)

    def test_retiring_twice_shows_the_message_of_the_api(self):
        document = self.add("Manual", retired=True)

        response = self.post(f"/web/documentos/{document.id}/retirar")

        self.assertEqual(response.status_code, 302)
        self.assertIn("Ese documento ya está retirado", self.flashes(response))

    def test_publishing_again_brings_back_the_same_audiences(self):
        document = self.add("Manual", audiences=("arrendatario", "guardia"), retired=True)

        response = self.post(f"/web/documentos/{document.id}/publicar")

        self.assertEqual(response.status_code, 302)
        self.assertIn("Documento publicado de nuevo", self.flashes(response))
        fresh = db.session.get(UnitDocument, document.id)
        self.assertFalse(fresh.is_retired)
        self.assertEqual(fresh.audiences, ["arrendatario", "guardia"])
        self.assertEqual(len(self.logs("restored")), 1)
        self.assertNotIn("Documentos retirados", self.page("/web/documentos"))

    def test_publishing_again_is_refused_if_another_published_document_took_the_title(self):
        old = self.add("Manual", retired=True)
        self.add("Manual")

        response = self.post(f"/web/documentos/{old.id}/publicar")

        self.assertIn("Ya hay un documento llamado «Manual»", self.flashes(response))
        self.assertTrue(db.session.get(UnitDocument, old.id).is_retired)

    def test_retiring_or_publishing_a_document_that_does_not_exist_shows_the_error(self):
        for action in ("retirar", "publicar"):
            with self.subTest(action=action):
                response = self.post(f"/web/documentos/999/{action}")

                self.assertEqual(response.status_code, 302)
                self.assertRegex(self.flashes(response), r"(?i)no existe|no encontr")

    # --- El archivo -----------------------------------------------------------------------------------

    def test_a_pdf_is_downloaded_with_its_own_name(self):
        document = self.add("Manual", name="manual de convivencia.pdf")

        response = self.client.get(f"/web/documentos/{document.id}/archivo")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertEqual(response.data, PDF)
        self.assertIn('attachment; filename="manual de convivencia.pdf"', response.headers["Content-Disposition"])

    def test_an_image_opens_in_the_browser(self):
        document = self.add("Plano", raw=PNG, mime="image/png", name="plano.png")

        response = self.client.get(f"/web/documentos/{document.id}/archivo")

        self.assertEqual(response.mimetype, "image/png")
        self.assertEqual(response.data, PNG)
        self.assertTrue(response.headers["Content-Disposition"].startswith("inline"))

    def test_the_file_cannot_run_or_load_anything_and_is_not_guessed_as_another_type(self):
        document = self.add("Manual")

        response = self.client.get(f"/web/documentos/{document.id}/archivo")

        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("sandbox", response.headers["Content-Security-Policy"])
        self.assertIn("default-src 'none'", response.headers["Content-Security-Policy"])

    def test_a_retired_document_can_still_be_opened_by_the_administration(self):
        document = self.add("Viejo", retired=True)

        response = self.client.get(f"/web/documentos/{document.id}/archivo")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, PDF)

    def test_opening_the_file_of_a_document_that_does_not_exist_shows_the_page_not_found(self):
        self.assertEqual(self.client.get("/web/documentos/999/archivo").status_code, 404)


if __name__ == "__main__":
    unittest.main()
