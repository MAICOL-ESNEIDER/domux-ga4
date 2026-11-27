"""Documentos legales (política de datos, términos, cookies...): los textos, las rutas públicas y la web.

Hoy los ocho textos son borradores del equipo (vigentes, versión 0.1, con un aviso visible al principio):
lo que se prueba es que los espacios funcionan (la API, la web y la revisión de los archivos) y que, el día que
cada texto lo revise una persona con conocimiento legal, solo haya que reemplazar su archivo. También se prueba el programa ``scripts/verificar_legal.py``, que es la puerta de
la versión final. La app Android no tiene pruebas automáticas; ver ``backend/legal/LEEME.md``.
"""

import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import env_setup  # noqa: F401  (va antes de importar la app)

from app import create_app
from scripts import verificar_legal
from services import legal_service
from services.legal_service import (
    DOCUMENT_SLUGS,
    LEGAL_DIR,
    LegalDocumentError,
    check_all,
    check_document,
    parse_blocks,
    pending_slugs,
    split_front_matter,
)
from web_testing import WebTestCase

PENDING_BODY = "## Documento en preparación\n\nTodavía no está publicado.\n"


def document_text(title="Un título", summary="Un resumen.", status="pendiente", version="", since="", body=PENDING_BODY):
    """El contenido de un archivo de documento legal armado como corresponde."""
    return (
        f"---\ntitulo: {title}\nresumen: {summary}\nestado: {status}\n"
        f"version: {version}\nvigente_desde: {since}\n---\n{body}"
    )


def write_documents(directory, **replaced):
    """Escribe los ocho documentos en esa carpeta; ``replaced`` cambia el texto de alguno (nombre → contenido)."""
    for slug in DOCUMENT_SLUGS:
        content = replaced.get(slug.replace("-", "_"), document_text(title=f"Título de {slug}"))
        (Path(directory) / f"{slug}.md").write_text(content, encoding="utf-8")


PUBLISHED_BODY = """## 1. Quién es el responsable

El conjunto residencial
decide sobre tus datos.

## 2. Para qué se usan

- Controlar el ingreso de visitas.
- Entregar paquetes.

1. Primer paso
2. Segundo paso
   que sigue en otra línea
"""


class FrontMatterTests(unittest.TestCase):
    def test_reads_the_header_and_returns_the_body(self):
        data, body = split_front_matter("---\ntitulo: Hola: mundo\nversion:\n---\nTexto\n")
        self.assertEqual(data, {"titulo": "Hola: mundo", "version": ""})
        self.assertEqual(body, "Texto\n")

    def test_accepts_windows_line_breaks_and_a_leading_bom(self):
        data, body = split_front_matter("﻿---\r\ntitulo: Uno\r\n---\r\nTexto\r\n")
        self.assertEqual(data, {"titulo": "Uno"})
        self.assertEqual(body, "Texto\n")

    def test_refuses_a_file_that_does_not_start_with_a_header(self):
        with self.assertRaisesRegex(LegalDocumentError, "empezar con una línea"):
            split_front_matter("titulo: Uno\n---\nTexto")

    def test_refuses_a_header_that_is_never_closed(self):
        with self.assertRaisesRegex(LegalDocumentError, "no se cierra"):
            split_front_matter("---\ntitulo: Uno\nTexto")

    def test_refuses_a_header_line_without_colon(self):
        with self.assertRaisesRegex(LegalDocumentError, "no tiene"):
            split_front_matter("---\ntitulo Uno\n---\nTexto")

    def test_refuses_a_repeated_field(self):
        with self.assertRaisesRegex(LegalDocumentError, "repetido"):
            split_front_matter("---\ntitulo: Uno\ntitulo: Dos\n---\nTexto")


class ParseBlocksTests(unittest.TestCase):
    def test_headings_keep_their_level_up_to_three(self):
        blocks = parse_blocks("# Uno\n## Dos\n### Tres\n#### Cuatro\n")
        self.assertEqual([block["level"] for block in blocks], [1, 2, 3, 3])
        self.assertEqual(blocks[0], {"type": "heading", "level": 1, "text": "Uno"})

    def test_consecutive_lines_make_one_paragraph_and_a_blank_line_splits_them(self):
        blocks = parse_blocks("Primera línea\nsegunda línea\n\nOtro párrafo\n")
        self.assertEqual(blocks, [
            {"type": "paragraph", "text": "Primera línea segunda línea"},
            {"type": "paragraph", "text": "Otro párrafo"},
        ])

    def test_bulleted_and_numbered_lists(self):
        blocks = parse_blocks("- uno\n- dos\n\n1. primero\n2) segundo\n")
        self.assertEqual(blocks, [
            {"type": "list", "ordered": False, "items": ["uno", "dos"]},
            {"type": "list", "ordered": True, "items": ["primero", "segundo"]},
        ])

    def test_a_list_changes_when_the_kind_of_marker_changes_without_a_blank_line(self):
        blocks = parse_blocks("- uno\n1. primero\n")
        self.assertEqual([block["ordered"] for block in blocks], [False, True])

    def test_an_indented_line_continues_the_list_item_above(self):
        blocks = parse_blocks("- uno\n  que sigue\n- dos\n")
        self.assertEqual(blocks, [{"type": "list", "ordered": False, "items": ["uno que sigue", "dos"]}])

    def test_a_plain_line_after_a_list_closes_it_and_starts_a_paragraph(self):
        blocks = parse_blocks("- uno\nTexto suelto\n")
        self.assertEqual([block["type"] for block in blocks], ["list", "paragraph"])

    def test_a_paragraph_followed_by_a_list_keeps_both(self):
        blocks = parse_blocks("Antes\n- uno\n")
        self.assertEqual([block["type"] for block in blocks], ["paragraph", "list"])

    def test_comment_lines_are_notes_for_the_writer_and_never_show(self):
        blocks = parse_blocks("<!-- revisar con una persona experta -->\nTexto\n<!-- otra nota -->\nsigue\n")
        self.assertEqual(blocks, [{"type": "paragraph", "text": "Texto sigue"}])

    def test_an_empty_text_has_no_blocks(self):
        self.assertEqual(parse_blocks(""), [])
        self.assertEqual(parse_blocks("\n\n   \n"), [])

    def test_a_published_example_comes_out_as_expected(self):
        blocks = parse_blocks(PUBLISHED_BODY)
        self.assertEqual([block["type"] for block in blocks], ["heading", "paragraph", "heading", "list", "list"])
        self.assertEqual(blocks[1]["text"], "El conjunto residencial decide sobre tus datos.")
        self.assertEqual(blocks[4], {
            "type": "list", "ordered": True, "items": ["Primer paso", "Segundo paso que sigue en otra línea"],
        })


class DocumentCheckTests(unittest.TestCase):
    """La revisión que avisa a quien escribe un texto de lo que está mal armado."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.directory = Path(self.folder.name)
        write_documents(self.directory)

    def put(self, slug, content):
        (self.directory / f"{slug}.md").write_text(content, encoding="utf-8")

    def problems(self, slug="terminos"):
        return check_document(slug, self.directory)

    def test_a_pending_set_is_well_formed(self):
        self.assertEqual(check_all(self.directory), [])

    def test_the_real_documents_are_well_formed(self):
        self.assertEqual(check_all(), [])

    def test_the_folder_holds_exactly_the_listed_documents(self):
        files = {path.stem for path in LEGAL_DIR.glob("*.md")} - {"LEEME"}
        self.assertEqual(files, set(DOCUMENT_SLUGS))

    def test_a_missing_file_is_reported(self):
        (self.directory / "terminos.md").unlink()
        self.assertEqual(self.problems(), ["falta el archivo terminos.md"])
        self.assertIn("terminos.md: falta el archivo terminos.md", check_all(self.directory))

    def test_a_missing_header_field_is_reported(self):
        self.put("terminos", "---\ntitulo: Algo\nestado: pendiente\n---\nTexto\n")
        self.assertIn("falta en el encabezado: resumen", self.problems())

    def test_an_unknown_header_field_is_reported(self):
        self.put("terminos", document_text().replace("version:", "versoin:"))
        self.assertIn("el dato «versoin» del encabezado no existe", self.problems())

    def test_an_unknown_status_is_reported(self):
        self.put("terminos", document_text(status="borrador"))
        self.assertTrue(any("«borrador» no existe" in problem for problem in self.problems()))

    def test_the_effective_date_must_be_a_real_date(self):
        for wrong in ("01/12/2026", "2026-13-45", "20261201", "ayer"):
            with self.subTest(wrong=wrong):
                self.put("terminos", document_text(since=wrong))
                self.assertTrue(any("AAAA-MM-DD" in problem for problem in self.problems()), wrong)

    def test_an_empty_body_is_reported(self):
        self.put("terminos", document_text(body="\n\n"))
        self.assertIn("el texto está vacío", self.problems())

    def test_an_in_force_document_needs_its_version_and_date(self):
        self.put("terminos", document_text(status="vigente", body=PUBLISHED_BODY))
        self.assertEqual(
            self.problems(), ["un documento vigente necesita «version»", "un documento vigente necesita «vigente_desde»"],
        )

    def test_a_complete_in_force_document_has_no_problems(self):
        self.put("terminos", document_text(status="vigente", version="1.0", since="2026-12-01", body=PUBLISHED_BODY))
        self.assertEqual(self.problems(), [])

    def test_an_in_force_document_cannot_keep_the_placeholder_notice(self):
        self.put("terminos", document_text(status="vigente", version="1.0", since="2026-12-01"))
        self.assertEqual(self.problems(), ["está como vigente pero conserva el aviso «Documento en preparación»"])

    def test_unsupported_syntax_is_reported_with_its_line(self):
        cases = {
            "texto con **negrita**": "negrita",
            "texto con `código`": "comillas invertidas",
            "mira [esto](https://example.com)": "enlaces",
            "| a | b |": "tablas",
            "> una cita": "citas",
            "* un elemento": "listas empiezan con",
            "un <b>tag</b>": "etiquetas HTML",
            "```": "bloques de código",
        }
        for line, reason in cases.items():
            with self.subTest(line=line):
                self.put("terminos", document_text(body=f"## Título\n\n{line}\n"))
                problems = self.problems()
                self.assertTrue(
                    any(reason in problem and "línea 3" in problem for problem in problems), (line, problems),
                )

    def test_the_document_title_belongs_in_the_header_and_there_are_only_two_heading_levels(self):
        self.put("terminos", document_text(body="# Título repetido\n\n#### Muy profundo\n\nTexto\n"))
        problems = self.problems()
        self.assertTrue(any("usa «##» o «###»" in problem for problem in problems))
        self.assertTrue(any("solo hay títulos de" in problem for problem in problems))

    def test_a_note_for_the_writer_is_not_checked_as_text(self):
        self.put("terminos", document_text(body="<!-- **nota** con [cosas](raras) -->\n## Título\n\nTexto\n"))
        self.assertEqual(self.problems(), [])

    def test_pending_documents_are_listed_until_each_one_is_in_force(self):
        self.assertEqual(pending_slugs(self.directory), list(DOCUMENT_SLUGS))
        self.put("terminos", document_text(status="vigente", version="1.0", since="2026-12-01", body=PUBLISHED_BODY))
        self.assertNotIn("terminos", pending_slugs(self.directory))
        self.assertEqual(len(pending_slugs(self.directory)), len(DOCUMENT_SLUGS) - 1)

    def test_a_missing_or_broken_file_counts_as_pending(self):
        (self.directory / "cookies.md").unlink()
        self.put("terminos", "sin encabezado")
        self.assertIn("cookies", pending_slugs(self.directory))
        self.assertIn("terminos", pending_slugs(self.directory))


class LegalApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.addClassCleanup(env_setup.release_app, cls.app)

    def setUp(self):
        self.client = self.app.test_client()

    def use_folder(self, **replaced):
        """Hace que el servidor lea los documentos de una carpeta de prueba."""
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        write_documents(folder.name, **replaced)
        patcher = mock.patch.object(legal_service, "LEGAL_DIR", Path(folder.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_list_is_public_and_comes_in_order(self):
        response = self.client.get("/api/legal")
        self.assertEqual(response.status_code, 200)
        documents = response.get_json()["documents"]
        self.assertEqual([document["slug"] for document in documents], list(DOCUMENT_SLUGS))
        for document in documents:
            self.assertEqual(
                set(document), {"slug", "title", "summary", "status", "version", "effectiveFrom", "audience"}, document["slug"],
            )
            self.assertTrue(document["title"] and document["summary"], document["slug"])
            self.assertEqual(document["status"], "vigente")
            self.assertEqual(document["version"], "0.1")
            self.assertEqual(document["effectiveFrom"], "2026-11-25")
        by_slug = {document["slug"]: document["audience"] for document in documents}
        self.assertEqual(by_slug["compromiso-porteria"], ["GUARD"])
        self.assertEqual(by_slug["compromiso-administracion"], ["ADMIN"])
        self.assertEqual(by_slug["terminos"], ["RESIDENT", "GUARD", "ADMIN"])

    def test_a_document_is_public_and_carries_its_blocks(self):
        for slug in DOCUMENT_SLUGS:
            with self.subTest(slug=slug):
                response = self.client.get(f"/api/legal/{slug}")
                self.assertEqual(response.status_code, 200)
                document = response.get_json()
                self.assertEqual(document["slug"], slug)
                self.assertEqual(document["status"], "vigente")
                # Cada texto dice, desde la primera línea, que no es asesoría legal y que la unidad debe revisarlo con su asesor jurídico.
                self.assertEqual(document["blocks"][0], {"type": "heading", "level": 2, "text": "Aviso importante"})
                self.assertEqual(document["blocks"][1]["type"], "paragraph")
                self.assertIn("asesor jurídico", document["blocks"][1]["text"])
                self.assertGreater(len(document["blocks"]), 4)

    def test_a_published_document_shows_its_version_date_and_every_kind_of_block(self):
        self.use_folder(terminos=document_text(
            title="Términos y condiciones", status="vigente", version="1.0", since="2026-12-01", body=PUBLISHED_BODY,
        ))
        listed = {item["slug"]: item for item in self.client.get("/api/legal").get_json()["documents"]}
        self.assertEqual(listed["terminos"]["status"], "vigente")
        self.assertEqual(listed["terminos"]["version"], "1.0")
        self.assertEqual(listed["terminos"]["effectiveFrom"], "2026-12-01")
        document = self.client.get("/api/legal/terminos").get_json()
        self.assertEqual([block["type"] for block in document["blocks"]], ["heading", "paragraph", "heading", "list", "list"])
        self.assertEqual(document["blocks"][3], {
            "type": "list", "ordered": False, "items": ["Controlar el ingreso de visitas.", "Entregar paquetes."],
        })

    def test_the_session_is_not_needed_and_a_wrong_token_does_not_matter(self):
        response = self.client.get("/api/legal/terminos", headers={"Authorization": "Bearer no-es-un-token"})
        self.assertEqual(response.status_code, 200)

    def test_an_unknown_document_is_a_404_with_the_usual_error(self):
        response = self.client.get("/api/legal/no-existe")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {"error": "No existe ese documento legal.", "status": 404})

    def test_only_the_listed_documents_are_served_and_nothing_else_from_the_folder(self):
        for slug in ("LEEME", "terminos.md", "TERMINOS", "..%2Fapp", "%2e%2e%2fapp.py", "terminos%00"):
            with self.subTest(slug=slug):
                self.assertEqual(self.client.get(f"/api/legal/{slug}").status_code, 404)

    def test_the_documents_only_answer_to_get(self):
        for path in ("/api/legal", "/api/legal/terminos"):
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                with self.subTest(path=path, method=method):
                    response = self.client.open(path, method=method)
                    self.assertEqual(response.status_code, 405)
                    self.assertEqual(response.get_json()["status"], 405)

    def test_a_broken_file_is_a_server_error_not_a_blank_page(self):
        self.use_folder(terminos="sin encabezado")
        self.app.config.update(PROPAGATE_EXCEPTIONS=False)
        response = self.client.get("/api/legal/terminos")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["status"], 500)


class LegalWebTests(WebTestCase):
    def use_folder(self, **replaced):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        write_documents(folder.name, **replaced)
        patcher = mock.patch.object(legal_service, "LEGAL_DIR", Path(folder.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_list_is_public_and_links_every_document(self):
        body = self.page("/web/legal")
        for slug in DOCUMENT_SLUGS:
            self.assertIn(f'href="/web/legal/{slug}"', body, slug)
        self.assertNotIn("En preparación", body)
        self.assertEqual(body.count("Vigente"), len(DOCUMENT_SLUGS))
        self.assertIn("Volver al inicio de sesión", body)

    def test_a_document_page_shows_the_title_the_summary_and_the_notice(self):
        body = self.page("/web/legal/terminos")
        self.assertIn("<h1>Términos y condiciones de uso</h1>", body)
        self.assertIn("Las reglas para usar la app y la web de DOMUX", body)
        self.assertIn("Aviso importante", body)
        self.assertNotIn("Documento en preparación", body)
        self.assertIn("Todos los documentos", body)

    def test_a_published_document_shows_its_blocks_version_and_date(self):
        self.use_folder(terminos=document_text(
            title="Términos y condiciones", status="vigente", version="1.0", since="2026-12-01", body=PUBLISHED_BODY,
        ))
        body = self.page("/web/legal/terminos")
        self.assertIn("Vigente", body)
        self.assertIn("Versión 1.0", body)
        self.assertIn("01/12/2026", body)
        self.assertIn("<h2>1. Quién es el responsable</h2>", body)
        self.assertIn("<p>El conjunto residencial decide sobre tus datos.</p>", body)
        self.assertIn("<ul><li>Controlar el ingreso de visitas.</li><li>Entregar paquetes.</li></ul>", body)
        self.assertIn("<ol><li>Primer paso</li><li>Segundo paso que sigue en otra línea</li></ol>", body)
        self.assertNotIn("Documento en preparación", body)

    def test_the_text_of_a_document_can_never_inject_html(self):
        self.use_folder(terminos=document_text(body="## <script>alert(1)</script>\n\nUn <img src=x onerror=alert(2)> párrafo\n"))
        body = self.page("/web/legal/terminos")
        self.assertNotIn("<script>alert", body)
        self.assertNotIn("<img src=x", body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)

    def test_an_unknown_document_is_the_usual_not_found_page(self):
        response = self.client.get("/web/legal/no-existe")
        self.assertEqual(response.status_code, 404)
        self.assertIn("No encontramos esa página", self.text(response))

    def test_the_login_page_links_the_legal_documents(self):
        body = self.page("/web/login")
        for slug in ("politica-datos", "terminos", "cookies"):
            self.assertIn(f'href="/web/legal/{slug}"', body, slug)
        self.assertIn('href="/web/legal"', body)

    def test_a_logged_in_administrator_reads_the_documents_with_the_usual_menu_and_footer(self):
        self.log_in()
        for path in ("/web/legal", "/web/legal/terminos"):
            body = self.page(path)
            self.assertIn('class="sidebar"', body, path)
            self.assertIn("Lucía Vargas", body, path)
            self.assertIn('class="site-footer"', body, path)
            self.assertIn('href="/web/legal/politica-datos"', body, path)
            self.assertNotIn("Volver al inicio de sesión", body, path)

    def test_a_visitor_with_a_closed_session_reads_the_documents_without_the_menu(self):
        self.log_in()
        self.post("/web/logout")
        body = self.page("/web/legal/terminos")
        self.assertNotIn('class="sidebar"', body)
        self.assertIn("Volver al inicio de sesión", body)

    def test_the_forms_that_ask_for_the_data_authorization_link_to_its_text(self):
        self.log_in()
        for path in ("/web/usuarios/nuevo", "/web/usuarios/censo"):
            body = self.page(path)
            self.assertIn('href="/web/legal/autorizacion-datos"', body, path)
            self.assertIn("Ver el texto de la autorización", body, path)

    def test_the_pages_keep_the_security_headers(self):
        response = self.client.get("/web/legal/terminos")
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Cache-Control"], "no-store")


class VerifyLegalScriptTests(unittest.TestCase):
    """``python -m scripts.verificar_legal``: la revisión diaria y la puerta de la versión final."""

    BACKEND = Path(__file__).resolve().parent.parent
    ALL_IN_FORCE = {
        slug.replace("-", "_"): document_text(
            title=f"Título de {slug}", status="vigente", version="1.0", since="2026-12-01", body=PUBLISHED_BODY,
        )
        for slug in DOCUMENT_SLUGS
    }

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.directory = Path(self.folder.name)
        self.lines = []

    def run_check(self, *options):
        code = verificar_legal.main(["--carpeta", str(self.directory), *options], say=self.lines.append)
        return code, "\n".join(self.lines)

    def test_a_well_made_set_of_pending_documents_passes_the_daily_check(self):
        write_documents(self.directory)
        code, output = self.run_check()
        self.assertEqual(code, 0)
        self.assertIn(f"{len(DOCUMENT_SLUGS)} documentos legales: 0 vigentes y {len(DOCUMENT_SLUGS)} en preparación.", output)

    def test_the_real_documents_pass_the_daily_check(self):
        lines = []
        self.assertEqual(verificar_legal.main([], say=lines.append), 0)
        self.assertEqual(len(lines), 1)

    def test_the_real_documents_pass_the_delivery_gate(self):
        lines = []
        self.assertEqual(verificar_legal.main(["--exigir-vigentes"], say=lines.append), 0, lines)
        self.assertIn(f"{len(DOCUMENT_SLUGS)} documentos legales: {len(DOCUMENT_SLUGS)} vigentes y 0 en preparación", lines[0])

    def test_the_delivery_gate_refuses_while_documents_are_pending_and_names_each_one(self):
        write_documents(self.directory)
        code, output = self.run_check("--exigir-vigentes")
        self.assertEqual(code, 1)
        self.assertIn("No se puede entregar la versión final", output)
        for slug in DOCUMENT_SLUGS:
            self.assertIn(f"  - {slug}", output)

    def test_the_delivery_gate_names_only_the_documents_that_are_still_pending(self):
        write_documents(self.directory, **{**self.ALL_IN_FORCE, "cookies": document_text(title="Cookies")})
        code, output = self.run_check("--exigir-vigentes")
        self.assertEqual(code, 1)
        self.assertIn("  - cookies", output)
        self.assertNotIn("  - terminos", output)
        self.assertIn(f"{len(DOCUMENT_SLUGS) - 1} vigentes y 1 en preparación", output)

    def test_the_delivery_gate_passes_when_every_document_is_in_force(self):
        write_documents(self.directory, **self.ALL_IN_FORCE)
        code, output = self.run_check("--exigir-vigentes")
        self.assertEqual(code, 0)
        self.assertIn(f"{len(DOCUMENT_SLUGS)} vigentes y 0 en preparación", output)

    def test_a_pending_set_is_fine_for_the_daily_check_even_though_the_gate_refuses_it(self):
        write_documents(self.directory)
        self.assertEqual(self.run_check()[0], 0)
        self.assertEqual(self.run_check("--exigir-vigentes")[0], 1)

    def test_a_badly_made_document_fails_even_without_the_gate_and_says_which_file(self):
        write_documents(self.directory, terminos="sin encabezado")
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("Hay documentos legales mal armados", output)
        self.assertIn("terminos.md: ", output)
        self.assertNotIn("No se puede entregar", output)

    def test_a_missing_document_fails_the_daily_check(self):
        write_documents(self.directory)
        (self.directory / "cookies.md").unlink()
        code, output = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("cookies.md: ", output)

    def test_an_in_force_document_with_no_date_does_not_get_through_the_gate(self):
        write_documents(self.directory, **{**self.ALL_IN_FORCE, "terminos": document_text(status="vigente", body=PUBLISHED_BODY)})
        code, output = self.run_check("--exigir-vigentes")
        self.assertEqual(code, 1)
        self.assertIn("terminos.md: ", output)

    def test_it_runs_as_a_program_from_the_backend_folder_and_the_exit_code_reaches_the_pipeline(self):
        write_documents(self.directory)
        command = [sys.executable, "-m", "scripts.verificar_legal", "--carpeta", str(self.directory)]
        daily = subprocess.run(command, cwd=self.BACKEND, capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(daily.returncode, 0, daily.stderr)
        self.assertIn("en preparación", daily.stdout)
        gate = subprocess.run(
            [*command, "--exigir-vigentes"], cwd=self.BACKEND, capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        self.assertEqual(gate.returncode, 1, gate.stderr)
        self.assertIn("No se puede entregar la versión final", gate.stdout)

    def test_an_unknown_option_is_refused_by_the_program(self):
        with mock.patch("sys.stderr", new=io.StringIO()), self.assertRaises(SystemExit) as raised:
            verificar_legal.main(["--opcion-que-no-existe"], say=self.lines.append)
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
