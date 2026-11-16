"""La dirección de la base de datos que lee el servidor (variable DATABASE_URL).

Caso real: quien copia ``.env.example`` como ``.env`` y no llena la línea ``DATABASE_URL=`` deja la variable
vacía. El servidor tiene que tratarla como si no existiera y usar SQLite, no fallar al arrancar.
"""

import os
import unittest
from unittest.mock import patch

import env_setup  # noqa: F401  (va antes de importar las demás piezas del servidor)

from config import DEFAULT_DATABASE_URL, database_url


class DatabaseUrlTests(unittest.TestCase):
    def read(self, value):
        """Lo que devuelve ``database_url()`` con ``DATABASE_URL`` en ese valor (None = la variable no existe)."""
        with patch.dict(os.environ):
            if value is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = value
            return database_url()

    def test_the_default_is_a_sqlite_file(self):
        self.assertTrue(DEFAULT_DATABASE_URL.startswith("sqlite:///"))

    def test_a_missing_variable_uses_the_default(self):
        self.assertEqual(self.read(None), DEFAULT_DATABASE_URL)

    def test_an_empty_variable_uses_the_default(self):
        self.assertEqual(self.read(""), DEFAULT_DATABASE_URL)

    def test_a_variable_with_only_spaces_uses_the_default(self):
        self.assertEqual(self.read("   "), DEFAULT_DATABASE_URL)

    def test_the_address_that_was_given_is_kept(self):
        self.assertEqual(self.read("postgresql://usuario:clave@servidor:5432/base"), "postgresql://usuario:clave@servidor:5432/base")
        self.assertEqual(self.read("sqlite://"), "sqlite://")

    def test_spaces_around_the_address_are_ignored(self):
        self.assertEqual(self.read("  postgresql://usuario@servidor/base \n"), "postgresql://usuario@servidor/base")

    def test_the_old_postgres_scheme_is_fixed(self):
        # Render entrega "postgres://", que SQLAlchemy ya no entiende.
        self.assertEqual(self.read("postgres://usuario:clave@servidor:5432/base"), "postgresql://usuario:clave@servidor:5432/base")

    def test_the_server_starts_with_an_empty_variable(self):
        """De punta a punta: la app se arma con la variable vacía y queda con la base por defecto."""
        from app import create_app

        with patch.dict(os.environ, {"DATABASE_URL": "", "DOMUX_SKIP_STARTUP": "1"}):
            app = create_app()
        self.addCleanup(env_setup.release_app, app)
        self.assertEqual(app.config["SQLALCHEMY_DATABASE_URI"], DEFAULT_DATABASE_URL)


if __name__ == "__main__":
    unittest.main()
