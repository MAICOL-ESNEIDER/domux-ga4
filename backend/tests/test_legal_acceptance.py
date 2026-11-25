"""Pruebas de la pantalla «Acepto»: cada persona acepta los textos legales al entrar por primera vez.

* Mientras no acepte, la API solo le deja ver su sesión, leer los textos y aceptar (403 con
  ``legalAcceptanceRequired``).
* La aceptación guarda cuándo y qué versión leyó, y queda en la auditoría.
* Si los textos cambian de versión, se vuelve a pedir.
* La web de administración manda a la página «Acepto» antes que a cualquier otra.
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from auth import generate_token
from extensions import db
from models import AuditLog
from services import legal_acceptance
from web_testing import PASSWORD, WebTestCase

#: Una versión inventada, para probar que cambiarla vuelve a pedir la aceptación.
OTHER_VERSION = "terminos:9.9|politica-datos:9.9|autorizacion-datos:9.9"


class AcceptanceTestCase(WebTestCase):
    def setUp(self):
        super().setUp()
        # Estas pruebas sí exigen la pantalla «Acepto» (las demás la dejan apagada).
        patcher = mock.patch.dict(os.environ, {"DOMUX_REQUIRE_LEGAL_ACCEPTANCE": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def bearer(self, user):
        return {"Authorization": f"Bearer {generate_token(user)}"}

    def accept(self, user, **body):
        body = {"accepted": True, "version": legal_acceptance.current_version(), **body}
        return self.client.post("/api/auth/accept-legal", headers=self.bearer(user), json=body)

    def audit(self, user):
        return AuditLog.query.filter_by(entity_type="user", entity_id=user.id, action="legal_accepted").all()


class BlockingTests(AcceptanceTestCase):
    def test_a_person_who_did_not_accept_is_told_so_at_login(self):
        login = self.client.post("/api/auth/login", json={"email": self.resident.email, "password": PASSWORD})

        self.assertEqual(login.status_code, 200)
        user = login.get_json()["user"]
        self.assertTrue(user["legalAcceptanceRequired"])
        self.assertIsNone(user["legalAcceptedAt"])

    def test_every_role_is_blocked_until_it_accepts(self):
        for user in (self.admin, self.guard, self.resident):
            with self.subTest(user.role):
                response = self.client.get("/api/announcements", headers=self.bearer(user))
                self.assertEqual(response.status_code, 403)
                body = response.get_json()
                self.assertTrue(body["legalAcceptanceRequired"])
                self.assertIn("aceptar los textos legales", body["error"])

    def test_what_a_person_can_still_do_before_accepting(self):
        headers = self.bearer(self.resident)

        self.assertEqual(self.client.get("/api/auth/session", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/auth/legal-acceptance", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/legal").status_code, 200)
        self.assertEqual(self.client.get("/api/legal/terminos").status_code, 200)

    def test_the_status_lists_the_three_texts_and_the_version(self):
        body = self.client.get("/api/auth/legal-acceptance", headers=self.bearer(self.resident)).get_json()

        self.assertTrue(body["required"])
        self.assertIsNone(body["acceptedAt"])
        self.assertEqual(body["version"], legal_acceptance.current_version())
        self.assertEqual([item["slug"] for item in body["documents"]], ["terminos", "politica-datos", "autorizacion-datos"])

    def test_without_the_requirement_nobody_is_blocked(self):
        with mock.patch.dict(os.environ, {"DOMUX_REQUIRE_LEGAL_ACCEPTANCE": "0"}):
            self.assertEqual(self.client.get("/api/announcements", headers=self.bearer(self.resident)).status_code, 200)
            body = self.client.get("/api/auth/legal-acceptance", headers=self.bearer(self.resident)).get_json()
            self.assertFalse(body["required"])

    def test_a_temporary_password_comes_before_accepting(self):
        self.resident.must_change_password = True
        db.session.commit()

        body = self.client.get("/api/announcements", headers=self.bearer(self.resident)).get_json()

        self.assertTrue(body["passwordChangeRequired"])
        self.assertNotIn("legalAcceptanceRequired", body)


class AcceptingTests(AcceptanceTestCase):
    def test_accepting_saves_when_and_which_version_and_unblocks(self):
        response = self.accept(self.resident)

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertFalse(body["user"]["legalAcceptanceRequired"])
        self.assertRegex(body["user"]["legalAcceptedAt"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
        db.session.refresh(self.resident)
        self.assertIsNotNone(self.resident.legal_accepted_at)
        self.assertEqual(self.resident.legal_accepted_version, legal_acceptance.current_version())
        self.assertEqual(self.client.get("/api/announcements", headers=self.bearer(self.resident)).status_code, 200)

    def test_accepting_is_in_the_audit_log_with_the_version(self):
        self.accept(self.guard)

        (entry,) = self.audit(self.guard)
        self.assertEqual(entry.actor_id, self.guard.id)
        self.assertEqual(json.loads(entry.details), {"version": legal_acceptance.current_version()})

    def test_the_box_must_be_checked(self):
        for accepted in (False, None, "true", 1):
            with self.subTest(accepted=accepted):
                response = self.accept(self.resident, accepted=accepted)
                self.assertEqual(response.status_code, 400)
        db.session.refresh(self.resident)
        self.assertIsNone(self.resident.legal_accepted_at)

    def test_nobody_accepts_a_version_they_did_not_see(self):
        response = self.accept(self.resident, version=OTHER_VERSION)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["version"], legal_acceptance.current_version())
        db.session.refresh(self.resident)
        self.assertIsNone(self.resident.legal_accepted_at)
        self.assertEqual(self.audit(self.resident), [])

    def test_a_missing_version_is_refused_too(self):
        response = self.client.post("/api/auth/accept-legal", headers=self.bearer(self.resident), json={"accepted": True})
        self.assertEqual(response.status_code, 409)

    def test_one_person_accepting_does_not_unblock_another(self):
        self.accept(self.resident)
        self.assertEqual(self.client.get("/api/announcements", headers=self.bearer(self.guard)).status_code, 403)

    def test_without_a_session_nobody_accepts(self):
        response = self.client.post("/api/auth/accept-legal", json={"accepted": True, "version": "x"})
        self.assertEqual(response.status_code, 401)

    def test_new_texts_ask_again(self):
        self.accept(self.resident)
        self.assertEqual(self.client.get("/api/announcements", headers=self.bearer(self.resident)).status_code, 200)

        with mock.patch.object(legal_acceptance, "current_version", return_value=OTHER_VERSION):
            blocked = self.client.get("/api/announcements", headers=self.bearer(self.resident))
            self.assertEqual(blocked.status_code, 403)
            self.assertTrue(blocked.get_json()["legalAcceptanceRequired"])
            self.assertEqual(self.accept(self.resident, version=OTHER_VERSION).status_code, 200)
            self.assertEqual(self.client.get("/api/announcements", headers=self.bearer(self.resident)).status_code, 200)

        self.assertEqual(len(self.audit(self.resident)), 2)


class VersionTests(unittest.TestCase):
    """La versión depende solo de las versiones de los tres textos."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        for slug in legal_acceptance.ACCEPTANCE_SLUGS:
            self.write(slug, "0.1")

    def write(self, slug, version):
        (self.folder / f"{slug}.md").write_text(
            f"---\ntitulo: Texto {slug}\nresumen: Un texto de prueba.\nestado: vigente\nversion: {version}\n"
            "vigente_desde: 2026-11-25\n---\n## Título\n\nUn párrafo.\n",
            encoding="utf-8",
        )

    def test_the_version_joins_the_three_versions(self):
        self.assertEqual(
            legal_acceptance.current_version(self.folder),
            "terminos:0.1|politica-datos:0.1|autorizacion-datos:0.1",
        )

    def test_changing_one_text_changes_the_version(self):
        before = legal_acceptance.current_version(self.folder)
        self.write("politica-datos", "0.2")
        # Otra marca de tiempo: el archivo cambió.
        os.utime(self.folder / "politica-datos.md", ns=(1, 2_000_000_000_000_000_000))

        after = legal_acceptance.current_version(self.folder)

        self.assertNotEqual(before, after)
        self.assertIn("politica-datos:0.2", after)

    def test_a_text_without_a_version_says_so(self):
        (self.folder / "terminos.md").write_text(
            "---\ntitulo: Términos\nresumen: Un texto.\nestado: pendiente\n---\n## Título\n\nUn párrafo.\n",
            encoding="utf-8",
        )
        self.assertIn("terminos:sin-version", legal_acceptance.current_version(self.folder))


class WebAcceptanceTests(AcceptanceTestCase):
    def setUp(self):
        super().setUp()
        self.log_in()
        # El inicio ya manda a «Acepto»: el código contra CSRF se toma de esa página.
        self._token = self.token_of("/web/acepto")

    def test_every_page_sends_the_administration_to_the_accept_page_first(self):
        for path in ("/web/", "/web/usuarios", "/web/reglas", "/web/descargas"):
            with self.subTest(path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.headers["Location"], "/web/acepto")

    def test_the_page_shows_the_three_texts_and_the_box(self):
        body = self.page("/web/acepto")

        for text in ("Antes de continuar, lee y acepta", "Ley 1581 de 2012", "Acepto y continuar"):
            self.assertIn(text, body)
        self.assertEqual(body.count('class="card legal-accept"'), 3)
        self.assertIn('name="accepted"', body)
        self.assertIn(f'name="version" value="{legal_acceptance.current_version()}"', body)

    def test_accepting_opens_the_panel_and_saves_it(self):
        response = self.post("/web/acepto", {"accepted": "1", "version": legal_acceptance.current_version()})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/web/")
        self.assertEqual(self.client.get("/web/").status_code, 200)
        db.session.refresh(self.admin)
        self.assertIsNotNone(self.admin.legal_accepted_at)

    def test_without_the_box_it_stays_on_the_page_with_a_message(self):
        response = self.post("/web/acepto", {"version": legal_acceptance.current_version()})

        self.assertEqual(response.status_code, 302)
        shown = self.text(self.client.get(response.headers["Location"]))
        self.assertIn("debes marcar que leíste y aceptas", shown)
        db.session.refresh(self.admin)
        self.assertIsNone(self.admin.legal_accepted_at)

    def test_once_accepted_the_page_goes_back_to_the_panel(self):
        self.post("/web/acepto", {"accepted": "1", "version": legal_acceptance.current_version()})

        response = self.client.get("/web/acepto")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/web/")

    def test_the_legal_pages_stay_public_and_logout_still_works(self):
        self.assertEqual(self.client.get("/web/legal").status_code, 200)
        self.assertEqual(self.post("/web/logout").status_code, 302)

    def test_a_temporary_password_comes_first_on_the_web_too(self):
        self.admin.must_change_password = True
        db.session.commit()

        self.assertEqual(self.client.get("/web/").headers["Location"], "/web/cambiar-contrasena")
        self.assertEqual(self.client.get("/web/cambiar-contrasena").status_code, 200)


if __name__ == "__main__":
    unittest.main()
