"""Pruebas del rediseño «Mixto» de la web (HU-087): la página de Preferencias, el menú con quien
entró y el botón «+ Nuevo», y el contraste de los colores de cada apariencia (HU-086)."""

import re
import unittest
from pathlib import Path

from web_testing import WebTestCase

STATIC = Path(__file__).resolve().parents[1] / "web" / "static"


def _luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first, second):
    """La razón de contraste WCAG entre dos colores «#rrggbb» (de 1 a 21)."""
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _variables(block):
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-f]{6})\s*;", block))


def _block(css, opening):
    start = css.index(opening) + len(opening)
    return css[start:css.index("}", start)]


class AppearanceContrastTests(unittest.TestCase):
    """Cada apariencia (Mixto, Oscuro y Automático en modo oscuro) cumple el contraste AA."""

    @classmethod
    def setUpClass(cls):
        css = (STATIC / "domux.css").read_text(encoding="utf-8")
        base = _variables(_block(css, ":root {"))
        dark = {**base, **_variables(_block(css, ':root[data-tema="oscuro"] {'))}
        auto = {**base, **_variables(_block(css, ':root:not([data-tema="mixto"]) {'))}
        cls.themes = {"mixto": base, "oscuro": dark, "automático en modo oscuro": auto}

    # Texto sobre su fondo: 4,5 a 1 (AA). Los bordes de los campos: 3 a 1.
    TEXT_PAIRS = (
        ("text", "bg"), ("text", "card"), ("soft", "card"), ("muted", "card"), ("muted", "bg"),
        ("primary", "card"), ("primary", "bg"), ("on-primary", "primary"), ("on-primary", "cyan"),
        ("ok", "ok-bg"), ("warn", "warn-bg"), ("bad", "bad-bg"), ("info", "info-bg"),
        ("nav-text", "nav-bg"), ("nav-muted", "nav-bg"), ("nav-strong", "nav-active"),
        ("nav-text", "nav-hover"), ("nav-accent", "nav-bg"),
    )

    def test_text_colors_reach_aa(self):
        for name, colors in self.themes.items():
            for foreground, background in self.TEXT_PAIRS:
                ratio = contrast(colors[foreground], colors[background])
                self.assertGreaterEqual(
                    ratio, 4.5, f"{name}: {foreground} sobre {background} tiene contraste {ratio:.2f}",
                )

    def test_field_border_is_visible(self):
        for name, colors in self.themes.items():
            ratio = contrast(colors["field"], colors["surface"])
            self.assertGreaterEqual(ratio, 3, f"{name}: el borde de los campos tiene contraste {ratio:.2f}")

    def test_the_three_appearances_exist(self):
        css = (STATIC / "domux.css").read_text(encoding="utf-8")
        self.assertIn(':root[data-tema="oscuro"]', css)
        self.assertIn(":root:not([data-tema=\"mixto\"])", css)
        self.assertIn("prefers-color-scheme: dark", css)
        self.assertIn(':root[data-texto="grande"]', css)
        self.assertIn(':root[data-texto="muy-grande"]', css)


class PreferencesWebTests(WebTestCase):
    def setUp(self):
        super().setUp()
        self.log_in()

    # --- La página ---------------------------------------------------------------------------------

    def test_preferences_offers_appearance_text_size_and_accounts(self):
        body = self.page("/web/preferencias")
        for text in ("Apariencia", "Automático", "Mixto", "Oscuro", "Tamaño del texto", "Normal", "Grande", "Muy grande",
                     "Cuentas recordadas en este equipo", "nunca la contraseña"):
            self.assertIn(text, body)
        for name, values in (("apariencia", ("auto", "mixto", "oscuro")), ("texto", ("normal", "grande", "muy-grande"))):
            for value in values:
                self.assertIn(f'name="{name}" value="{value}"', body)
        self.assertIn("data-preferencias", body)
        self.assertIn("data-cuentas-recordadas", body)

    def test_defaults_are_dark_and_normal(self):
        # Desde el 27/11/2026 la web viene en «Oscuro», como la app y la página de presentación.
        body = self.page("/web/preferencias")
        self.assertRegex(body, r'name="apariencia" value="oscuro" checked')
        self.assertIn('<html lang="es" data-tema="oscuro">', body)
        self.assertRegex(body, r'name="texto" value="normal" checked')

    def test_it_says_javascript_is_needed(self):
        self.assertIn("Para cambiar estas opciones hay que activar JavaScript", self.page("/web/preferencias"))

    def test_it_asks_for_a_session(self):
        self.client.post("/web/logout", data={"csrf_token": self.token_of("/web/")})
        response = self.client.get("/web/preferencias")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/web/login", response.headers["Location"])

    def test_the_server_stores_nothing_about_it(self):
        # Es solo del navegador: la página no tiene formularios que manden datos al servidor.
        main = self.page("/web/preferencias").split('<main id="contenido"', 1)[1]
        self.assertNotIn("<form", main)

    # --- Apariencia sin parpadeo ------------------------------------------------------------------

    def test_the_appearance_script_loads_before_the_page_is_drawn(self):
        for path in ("/web/", "/web/login"):
            # El inicio de sesión se pide sin sesión abierta; con ella, la web lleva al inicio.
            if path == "/web/login":
                response = self.app.test_client().get(path)
                self.assertEqual(response.status_code, 200)
                body = self.text(response)
            else:
                body = self.page(path)
            early = body.index("preferencias-inicio.js")
            self.assertNotIn("defer", body[body.rfind("<script", 0, early):early + 80].split(">")[0])
            self.assertLess(early, body.index("domux.js"), path)
            self.assertLess(early, body.index("<body"), path)

    def test_the_appearance_script_is_served_and_only_reads_two_keys(self):
        response = self.client.get("/web/static/preferencias-inicio.js")
        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)
        script = response.get_data(as_text=True)
        self.assertIn("domux.apariencia", script)
        self.assertIn("domux.tamanoTexto", script)
        self.assertNotIn("password", script.lower())

    def test_pages_have_no_inline_scripts(self):
        for path in ("/web/", "/web/preferencias", "/web/buscar?q=Marta"):
            for tag in re.findall(r"<script[^>]*>", self.page(path)):
                self.assertIn("src=", tag, f"{path} tiene un script dentro de la página")

    # --- El menú con quien entró y «+ Nuevo» -------------------------------------------------------

    def test_the_menu_shows_who_signed_in_with_a_link_to_preferences(self):
        body = self.page("/web/")
        sidebar = body.split('<nav class="sidebar"', 1)[1].split("</nav>", 1)[0]
        self.assertIn('class="avatar"', sidebar)
        self.assertIn(">LV<", sidebar)
        self.assertIn("Lucía Vargas", sidebar)
        self.assertIn("Administración", sidebar)
        self.assertIn('href="/web/preferencias"', sidebar)
        self.assertIn("Cambiar contraseña", sidebar)
        self.assertIn("Cerrar sesión", sidebar)

    def test_the_top_bar_no_longer_shows_the_name(self):
        topbar = self.page("/web/").split('<header class="topbar">', 1)[1].split("</header>", 1)[0]
        self.assertNotIn("Cerrar sesión", topbar)
        self.assertNotIn("Lucía Vargas", topbar)

    def test_new_menu_lists_what_can_be_created(self):
        body = self.page("/web/pqrs")
        menu = body.split('data-new-menu', 1)[1].split("</details>", 1)[0]
        for label, href in (
            ("Comunicado", "/web/comunicados/nuevo"),
            ("Usuario", "/web/usuarios/nuevo"),
            ("Torre", "/web/estructura/torres/nueva"),
            ("Apartamento", "/web/estructura/apartamentos/nuevo"),
            ("PQRS a nombre de un residente", "/web/pqrs/nueva"),
        ):
            self.assertIn(label, menu)
            self.assertIn(f'href="{href}"', menu)

    def test_every_link_in_the_new_menu_opens(self):
        body = self.page("/web/")
        menu = body.split('data-new-menu', 1)[1].split("</details>", 1)[0]
        links = re.findall(r'<a href="([^"]+)"', menu)
        self.assertGreaterEqual(len(links), 5)
        for link in links:
            self.assertEqual(self.client.get(link).status_code, 200, link)

    def test_initials(self):
        from web.pages import initials

        self.assertEqual(initials("Lucía Vargas"), "LV")
        self.assertEqual(initials("Guardia"), "GU")
        self.assertEqual(initials("  maría   de los ángeles "), "MD")
        self.assertEqual(initials(""), "?")


if __name__ == "__main__":
    unittest.main()
