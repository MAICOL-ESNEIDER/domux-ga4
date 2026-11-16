"""Pruebas de las copias de seguridad de la base de datos (TT-009).

Casi todo se prueba con un pg_dump y un pg_restore "de mentira" (así corren igual en cualquier
computador y en el pipeline). Al final hay pruebas con un PostgreSQL de verdad, que se saltan
solas cuando no hay servidor o las herramientas no son compatibles con él.
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import psycopg2

from scripts import copia_diaria, restaurar_copia
from scripts import copias_comun as comun
from scripts.copias_comun import BackupError
from time_utils import COLOMBIA

FAKE_PASSWORD = "CLAVE_FALSA_123"  # no es una clave real: sirve para comprobar que nunca sale en pantalla
FAKE_URL = f"postgresql://domux:{FAKE_PASSWORD}@db.local:5433/domux_prueba"
MORNING = datetime(2026, 11, 16, 2, 0, 0, tzinfo=COLOMBIA)


def fake_tools(name, pg_bin_dir=None):
    """Sustituye a find_tool: así las pruebas no dependen de tener PostgreSQL instalado."""
    return f"/falso/{name}"


class FakePostgres:
    """Hace de pg_dump y pg_restore: guarda cómo los llamaron y devuelve lo que la prueba pida."""

    def __init__(self, dump_ok=True, list_ok=True, restore_ok=True, dump_content=b"PGDMP-copia-falsa"):
        self.dump_ok = dump_ok
        self.list_ok = list_ok
        self.restore_ok = restore_ok
        self.dump_content = dump_content
        self.calls = []

    def __call__(self, args, extra_env=None):
        self.calls.append((list(args), dict(extra_env or {})))
        program = Path(args[0]).name
        if "--version" in args:
            return subprocess.CompletedProcess(args, 0, "pg_dump (PostgreSQL) 16.0\n", "")
        if program == "pg_dump":
            if self.dump_ok:
                Path(args[args.index("--file") + 1]).write_bytes(self.dump_content)
                return subprocess.CompletedProcess(args, 0, "", "")
            return subprocess.CompletedProcess(args, 1, "", "pg_dump: error de prueba")
        if "--list" in args:
            if self.list_ok:
                return subprocess.CompletedProcess(args, 0, "; Archive\n10; 1259 16385 TABLE public users\n", "")
            return subprocess.CompletedProcess(args, 1, "", "pg_restore: archivo ilegible")
        if self.restore_ok:
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 1, "", "pg_restore: error de prueba")

    def restore_calls(self):
        return [call for call in self.calls if "--dbname" in call[0] and "--no-owner" in call[0]
                and Path(call[0][0]).name == "pg_restore"]


class FakeAdmin:
    """Hace de PgAdmin: anota qué bases se crean y borran."""

    def __init__(self, existing=()):
        self.existing = set(existing)
        self.calls = []

    def exists(self, name):
        return name in self.existing

    def drop(self, name):
        self.calls.append(("drop", name))
        self.existing.discard(name)

    def create(self, name):
        self.calls.append(("create", name))
        self.existing.add(name)

    def close(self):
        pass


def fake_count(url, database=None):
    return {"users": 4, "pets": 0, "visits": 12}


class TempFolderTestCase(unittest.TestCase):
    """Da a cada prueba una carpeta de copias nueva (fuera del proyecto) y la borra al terminar."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="domux_copias_prueba_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.messages = []

    def settings(self, **changes):
        environ = {"DATABASE_URL": FAKE_URL, "BACKUP_DIR": str(self.folder)}
        environ.update(changes)
        return comun.load_settings(environ)

    def old_copies(self, days, valid_manifest=True):
        """Crea copias de prueba con fecha 2026-11-<día> y su ficha."""
        paths = []
        for day in days:
            path = self.folder / f"domux_202611{day:02d}_020000.dump"
            path.write_bytes(b"PGDMP-" + str(day).encode())
            manifest = {"sha256": comun.sha256_of(path) if valid_manifest else "0" * 64, "filas_por_tabla": {"users": 1}}
            comun.manifest_path(path).write_text(json.dumps(manifest), encoding="utf-8")
            paths.append(path)
        return paths


class SettingsTests(unittest.TestCase):
    def test_database_url_is_required(self):
        with self.assertRaisesRegex(BackupError, "Falta DATABASE_URL"):
            comun.load_settings({"BACKUP_DIR": tempfile.gettempdir()})

    def test_only_postgresql_is_accepted(self):
        with self.assertRaisesRegex(BackupError, "solo para PostgreSQL"):
            comun.load_settings({"DATABASE_URL": "sqlite:///domux.db", "BACKUP_DIR": tempfile.gettempdir()})

    def test_malformed_url_is_rejected(self):
        with self.assertRaisesRegex(BackupError, "formato"):
            comun.load_settings({"DATABASE_URL": "esto no es una direccion", "BACKUP_DIR": tempfile.gettempdir()})

    def test_database_name_is_required(self):
        with self.assertRaisesRegex(BackupError, "nombre de la base"):
            comun.load_settings({"DATABASE_URL": "postgresql://domux@db.local/", "BACKUP_DIR": tempfile.gettempdir()})

    def test_postgres_scheme_is_rewritten_and_pieces_are_read(self):
        settings = comun.load_settings(
            {"DATABASE_URL": f"postgres://domux:{FAKE_PASSWORD}@db.local:5433/domux_prueba",
             "BACKUP_DIR": tempfile.gettempdir()}
        )
        self.assertEqual(settings.database, "domux_prueba")
        self.assertEqual(settings.url.host, "db.local")
        self.assertEqual(settings.url.port, 5433)
        self.assertEqual(settings.url.username, "domux")
        self.assertEqual(settings.url.password, FAKE_PASSWORD)

    def test_backup_dir_is_required_only_when_needed(self):
        with self.assertRaisesRegex(BackupError, "Falta BACKUP_DIR"):
            comun.load_settings({"DATABASE_URL": FAKE_URL})
        self.assertIsNone(comun.load_settings({"DATABASE_URL": FAKE_URL}, need_folder=False).backup_dir)

    def test_folder_inside_the_project_is_rejected(self):
        for inside in (comun.PROJECT_DIR / "copias", comun.BACKEND_DIR, comun.PROJECT_DIR):
            with self.subTest(inside=inside), self.assertRaisesRegex(BackupError, "dentro del proyecto"):
                comun.load_settings({"DATABASE_URL": FAKE_URL, "BACKUP_DIR": str(inside)})

    def test_destination_argument_wins_over_environment(self):
        other = Path(tempfile.gettempdir()) / "otra_carpeta_de_copias"
        settings = comun.load_settings(
            {"DATABASE_URL": FAKE_URL, "BACKUP_DIR": tempfile.gettempdir()}, destination=str(other)
        )
        self.assertEqual(settings.backup_dir, other.resolve())

    def test_keep_default_and_validation(self):
        base = {"DATABASE_URL": FAKE_URL, "BACKUP_DIR": tempfile.gettempdir()}
        self.assertEqual(comun.load_settings(base).keep, 7)
        self.assertEqual(comun.load_settings({**base, "BACKUP_KEEP": "10"}).keep, 10)
        self.assertEqual(comun.load_settings({**base, "BACKUP_KEEP": "10"}, keep=3).keep, 3)
        with self.assertRaisesRegex(BackupError, "número entero"):
            comun.load_settings({**base, "BACKUP_KEEP": "muchas"})
        with self.assertRaisesRegex(BackupError, "al menos 1"):
            comun.load_settings(base, keep=0)

    def test_pg_bin_dir_is_optional(self):
        base = {"DATABASE_URL": FAKE_URL, "BACKUP_DIR": tempfile.gettempdir()}
        self.assertIsNone(comun.load_settings(base).pg_bin_dir)
        self.assertEqual(comun.load_settings({**base, "PG_BIN_DIR": " /opt/pg/bin "}).pg_bin_dir, "/opt/pg/bin")


class ToolsAndConnectionTests(unittest.TestCase):
    def test_find_tool_explains_what_to_do_when_missing(self):
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaisesRegex(BackupError, "PG_BIN_DIR"):
                comun.find_tool("pg_dump", "C:\\no\\existe")

    def test_find_tool_prefers_the_given_folder_then_path(self):
        answers = {"/mi/carpeta": "/mi/carpeta/pg_dump", None: "/usr/bin/pg_dump"}
        with mock.patch("shutil.which", side_effect=lambda name, path=None: answers.get(path)):
            self.assertEqual(comun.find_tool("pg_dump", "/mi/carpeta"), "/mi/carpeta/pg_dump")
            self.assertEqual(comun.find_tool("pg_dump", None), "/usr/bin/pg_dump")
            self.assertEqual(comun.find_tool("pg_dump", "/otra"), "/usr/bin/pg_dump")

    def test_password_travels_only_in_the_environment(self):
        url = comun.load_settings({"DATABASE_URL": FAKE_URL + "?sslmode=require", "BACKUP_DIR": tempfile.gettempdir()}).url
        args = comun.connection_args(url)
        self.assertEqual(args, ["--host", "db.local", "--port", "5433", "--username", "domux"])
        self.assertNotIn(FAKE_PASSWORD, " ".join(args))
        self.assertEqual(comun.connection_env(url), {"PGPASSWORD": FAKE_PASSWORD, "PGSSLMODE": "require"})
        kwargs = comun.connection_kwargs(url)
        self.assertEqual(kwargs["dbname"], "domux_prueba")
        self.assertEqual(kwargs["sslmode"], "require")
        self.assertEqual(comun.connection_kwargs(url, "postgres")["dbname"], "postgres")

    def test_connection_without_optional_parts(self):
        url = comun.load_settings({"DATABASE_URL": "postgresql:///solo_base", "BACKUP_DIR": tempfile.gettempdir()}).url
        self.assertEqual(comun.connection_args(url), [])
        self.assertEqual(comun.connection_env(url), {})
        self.assertEqual(comun.connection_kwargs(url), {"dbname": "solo_base"})

    def test_run_command_passes_the_extra_environment(self):
        code = "import os; print(os.environ['PGPASSWORD'])"
        result = comun.run_command([sys.executable, "-c", code], {"PGPASSWORD": "valor-de-prueba"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "valor-de-prueba")

    def test_short_trims_long_messages(self):
        self.assertEqual(comun.short("  hola \n  mundo "), "hola mundo")
        self.assertEqual(len(comun.short("x" * 1000, 50)), 53)
        self.assertEqual(comun.short(None), "")

    def test_format_size(self):
        self.assertEqual(comun.format_size(950), "950 B")
        self.assertEqual(comun.format_size(2048), "2.0 KB")
        self.assertEqual(comun.format_size(5 * 1024 * 1024), "5.0 MB")


class RotationTests(TempFolderTestCase):
    def test_list_is_newest_first_and_ignores_other_files(self):
        self.old_copies([3, 1, 2])
        (self.folder / "notas.txt").write_text("mis notas", encoding="utf-8")
        (self.folder / "domux_vacaciones.dump").write_bytes(b"no es una copia")
        (self.folder / "domux_20261105_020000.dump.bak").write_bytes(b"tampoco")
        names = [item.path.name for item in comun.list_backups(self.folder)]
        self.assertEqual(names, ["domux_20261103_020000.dump", "domux_20261102_020000.dump", "domux_20261101_020000.dump"])

    def test_list_of_missing_folder_is_empty(self):
        self.assertEqual(comun.list_backups(self.folder / "no_existe"), [])
        self.assertEqual(comun.list_backups(None), [])

    def test_only_the_oldest_copies_are_removed_with_their_manifest(self):
        self.old_copies(range(1, 11))
        (self.folder / "notas.txt").write_text("mis notas", encoding="utf-8")
        removed = comun.remove_old_backups(self.folder, 7)
        self.assertEqual([path.name for path in removed], [f"domux_202611{day:02d}_020000.dump" for day in (3, 2, 1)])
        remaining = sorted(path.name for path in self.folder.iterdir())
        self.assertEqual(len(remaining), 7 * 2 + 1)  # 7 copias, 7 fichas y las notas
        self.assertIn("notas.txt", remaining)
        self.assertNotIn("domux_20261101_020000.dump", remaining)
        self.assertNotIn("domux_20261101_020000.dump.json", remaining)

    def test_nothing_is_removed_when_there_are_few_copies(self):
        self.old_copies([1, 2])
        self.assertEqual(comun.remove_old_backups(self.folder, 7), [])
        self.assertEqual(len(comun.list_backups(self.folder)), 2)

    def test_partial_files_are_cleaned_but_other_files_stay(self):
        (self.folder / "domux_20261101_020000.dump.parcial").write_bytes(b"a medias")
        (self.folder / "domux_mio.dump.parcial").write_bytes(b"otro archivo")
        comun.remove_partial_files(self.folder)
        self.assertEqual(sorted(path.name for path in self.folder.iterdir()), ["domux_mio.dump.parcial"])

    def test_manifest_reading(self):
        path = self.old_copies([1])[0]
        self.assertEqual(comun.read_manifest(path)["filas_por_tabla"], {"users": 1})
        comun.manifest_path(path).write_text("{no es json", encoding="utf-8")
        self.assertIsNone(comun.read_manifest(path))
        comun.manifest_path(path).write_text("[1, 2]", encoding="utf-8")
        self.assertIsNone(comun.read_manifest(path))
        comun.manifest_path(path).unlink()
        self.assertIsNone(comun.read_manifest(path))


class LoggerTests(TempFolderTestCase):
    def test_messages_go_to_screen_and_to_both_logs(self):
        with mock.patch.object(comun, "BACKEND_DIR", self.folder / "backend"):
            (self.folder / "backend").mkdir()
            say = comun.make_logger(self.folder)
            with mock.patch("builtins.print") as shown:
                say("mensaje de prueba")
        self.assertIn("mensaje de prueba", shown.call_args[0][0])
        self.assertIn("mensaje de prueba", (self.folder / "copias.log").read_text(encoding="utf-8"))
        self.assertIn("mensaje de prueba", (self.folder / "backend" / "instance" / "copias.log").read_text(encoding="utf-8"))

    def test_an_unwritable_log_does_not_break_the_message(self):
        with mock.patch.object(comun, "BACKEND_DIR", self.folder / "no_existe" / "backend"):
            say = comun.make_logger(self.folder / "tampoco" / "existe")
            with mock.patch("builtins.print") as shown:
                say("sigue funcionando")
        shown.assert_called_once()


class MakeBackupTests(TempFolderTestCase):
    def run_backup(self, runner=None, now=MORNING, count=fake_count, **changes):
        runner = runner or FakePostgres()
        with mock.patch.object(comun, "find_tool", fake_tools):
            result = copia_diaria.make_backup(self.settings(**changes), run=runner, count=count, now=now, say=self.messages.append)
        return result, runner

    def test_creates_the_copy_and_its_manifest(self):
        result, runner = self.run_backup()
        self.assertEqual(result.path.name, "domux_20261116_020000.dump")
        self.assertEqual(result.path.read_bytes(), b"PGDMP-copia-falsa")
        self.assertEqual((result.tables, result.rows), (3, 16))
        manifest = comun.read_manifest(result.path)
        self.assertEqual(manifest["sha256"], comun.sha256_of(result.path))
        self.assertEqual(manifest["archivo"], result.path.name)
        self.assertEqual(manifest["base"], "domux_prueba")
        self.assertEqual(manifest["creada"], "2026-11-16T02:00:00-05:00")
        self.assertEqual(manifest["filas_por_tabla"], {"users": 4, "pets": 0, "visits": 12})
        self.assertEqual(manifest["programa"], "pg_dump (PostgreSQL) 16.0")
        self.assertEqual([item.name for item in self.folder.iterdir() if item.name.endswith(".parcial")], [])
        self.assertTrue(any("COPIA LISTA" in message for message in self.messages))

    def test_pg_dump_gets_the_right_options_and_the_password_stays_hidden(self):
        _, runner = self.run_backup()
        command, env = runner.calls[0]
        self.assertEqual(Path(command[0]).name, "pg_dump")
        for option in ("--format=custom", "--no-owner", "--no-acl"):
            self.assertIn(option, command)
        self.assertEqual(command[command.index("--dbname") + 1], "domux_prueba")
        self.assertTrue(command[command.index("--file") + 1].endswith(".dump.parcial"))
        self.assertNotIn(FAKE_PASSWORD, " ".join(command))
        self.assertEqual(env["PGPASSWORD"], FAKE_PASSWORD)
        self.assertFalse(any(FAKE_PASSWORD in message for message in self.messages))

    def test_only_the_newest_copies_are_kept(self):
        for day in range(5):
            self.run_backup(now=MORNING + timedelta(days=day), BACKUP_KEEP="3")
        names = [item.path.name for item in comun.list_backups(self.folder)]
        self.assertEqual(names, ["domux_20261120_020000.dump", "domux_20261119_020000.dump", "domux_20261118_020000.dump"])
        self.assertEqual(len([item for item in self.folder.iterdir() if item.name.endswith(".json")]), 3)

    def test_a_failed_dump_never_deletes_good_copies(self):
        old = self.old_copies([1, 2, 3])
        with self.assertRaisesRegex(BackupError, "pg_dump no pudo"):
            self.run_backup(FakePostgres(dump_ok=False), BACKUP_KEEP="3")
        self.assertTrue(all(path.exists() for path in old))
        self.assertEqual([item.name for item in self.folder.iterdir() if item.name.endswith(".parcial")], [])

    def test_an_unreadable_copy_is_discarded(self):
        old = self.old_copies([1])
        with self.assertRaisesRegex(BackupError, "dañada"):
            self.run_backup(FakePostgres(list_ok=False))
        self.assertTrue(old[0].exists())
        self.assertEqual(len(comun.list_backups(self.folder)), 1)
        self.assertEqual([item.name for item in self.folder.iterdir() if item.name.endswith(".parcial")], [])

    def test_an_empty_copy_is_discarded(self):
        with self.assertRaisesRegex(BackupError, "vacía"):
            self.run_backup(FakePostgres(dump_content=b""))
        self.assertEqual(list(comun.list_backups(self.folder)), [])
        self.assertEqual([item.name for item in self.folder.iterdir() if item.name.endswith(".parcial")], [])

    def test_failing_to_count_rows_does_not_stop_the_copy(self):
        def broken_count(url, database=None):
            raise psycopg2.OperationalError("sin permiso para contar")

        result, _ = self.run_backup(count=broken_count)
        self.assertIsNone(comun.read_manifest(result.path)["filas_por_tabla"])
        self.assertEqual((result.tables, result.rows), (0, 0))
        self.assertTrue(any(message.startswith("AVISO") for message in self.messages))

    def test_two_copies_in_the_same_second_are_refused(self):
        self.run_backup()
        with self.assertRaisesRegex(BackupError, "Ya existe"):
            self.run_backup()

    def test_a_missing_disk_gives_a_clear_message(self):
        with self.assertRaisesRegex(BackupError, "conectado el disco"):
            self.run_backup(BACKUP_DIR=str(self.folder / "disco_que_no_esta" / "copias"))

    def test_stale_partial_files_are_cleaned_before_the_copy(self):
        (self.folder / "domux_20261101_020000.dump.parcial").write_bytes(b"resto")
        self.run_backup()
        self.assertFalse((self.folder / "domux_20261101_020000.dump.parcial").exists())


class ShowBackupsTests(TempFolderTestCase):
    NOW = datetime(2026, 11, 3, 12, 0, 0, tzinfo=COLOMBIA)

    def show(self, now=None):
        return copia_diaria.show_backups(self.settings(), now=now or self.NOW, say=self.messages.append)

    def test_an_empty_folder_is_a_problem(self):
        self.assertEqual(self.show(), 1)
        self.assertIn("No hay copias", self.messages[0])

    def test_intact_copies_report_no_problems(self):
        self.old_copies([2, 3])
        self.assertEqual(self.show(), 0)
        self.assertEqual(sum("íntegra" in message for message in self.messages), 2)

    def test_an_altered_copy_is_detected(self):
        paths = self.old_copies([2, 3])
        paths[0].write_bytes(b"alguien cambio este archivo")
        self.assertEqual(self.show(), 1)
        self.assertTrue(any("ALTERADA" in message for message in self.messages))

    def test_a_copy_without_manifest_is_reported(self):
        paths = self.old_copies([2, 3])
        comun.manifest_path(paths[1]).unlink()
        self.assertEqual(self.show(), 1)
        self.assertTrue(any("SIN FICHA" in message for message in self.messages))

    def test_an_old_newest_copy_raises_a_warning(self):
        self.old_copies([1])
        self.assertEqual(self.show(now=datetime(2026, 11, 4, 12, 0, 0, tzinfo=COLOMBIA)), 1)
        self.assertTrue(any("AVISO" in message and "3 días" in message for message in self.messages))


class RestoreTests(TempFolderTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(comun, "find_tool", fake_tools)
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_copy(self, rows=None):
        path = self.old_copies([1])[0]
        manifest = comun.read_manifest(path)
        manifest["filas_por_tabla"] = rows if rows is not None else {"users": 4, "pets": 0, "visits": 12}
        comun.manifest_path(path).write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def restore(self, path, target="domux_prueba_restaurada", runner=None, admin=None, count=fake_count, **options):
        runner = runner or FakePostgres()
        admin = admin or FakeAdmin()
        result = restaurar_copia.restore_backup(
            self.settings(), path, target, run=runner, admin=admin, count=count, say=self.messages.append, **options
        )
        return result, runner, admin

    def test_restores_into_a_new_database_and_confirms_the_rows(self):
        result, runner, admin = self.restore(self.make_copy())
        self.assertTrue(result.ok)
        self.assertEqual((result.tables, result.rows), (3, 16))
        self.assertEqual(admin.calls, [("create", "domux_prueba_restaurada")])
        command, env = runner.restore_calls()[0]
        self.assertIn("--exit-on-error", command)
        self.assertEqual(command[command.index("--dbname") + 1], "domux_prueba_restaurada")
        self.assertEqual(command[-1], str(self.folder / "domux_20261101_020000.dump"))
        self.assertNotIn(FAKE_PASSWORD, " ".join(command))
        self.assertEqual(env["PGPASSWORD"], FAKE_PASSWORD)
        self.assertTrue(any("RESTAURACIÓN CORRECTA" in message for message in self.messages))

    def test_different_row_counts_are_reported(self):
        result, _, _ = self.restore(self.make_copy({"users": 4, "pets": 1, "viejas": 2}))
        self.assertFalse(result.ok)
        text = "\n".join(self.messages)
        self.assertIn("DIFERENTE", text)
        self.assertIn("FALTA en la base restaurada", text)
        self.assertIn("SOBRA", text)
        self.assertIn("RESTAURADA CON DIFERENCIAS", text)

    def test_a_copy_without_manifest_is_restored_with_a_warning(self):
        path = self.make_copy()
        comun.manifest_path(path).unlink()
        result, _, _ = self.restore(path)
        self.assertTrue(result.ok)
        self.assertTrue(any(message.startswith("AVISO") for message in self.messages))
        self.assertTrue(any("sin ficha" in message for message in self.messages))

    def test_an_altered_copy_is_refused_before_touching_any_database(self):
        path = self.make_copy()
        path.write_bytes(b"alterada")
        runner, admin = FakePostgres(), FakeAdmin()
        with self.assertRaisesRegex(BackupError, "huella"):
            self.restore(path, runner=runner, admin=admin)
        self.assertEqual(admin.calls, [])
        self.assertEqual(runner.restore_calls(), [])

    def test_an_unreadable_copy_is_refused(self):
        with self.assertRaisesRegex(BackupError, "dañada"):
            self.restore(self.make_copy(), runner=FakePostgres(list_ok=False))

    def test_invalid_names_and_missing_files_are_refused(self):
        path = self.make_copy()
        for bad in ("con espacio", "x;DROP", "", "a" * 64):
            with self.subTest(bad=bad), self.assertRaisesRegex(BackupError, "nombre de la base"):
                self.restore(path, target=bad)
        with self.assertRaisesRegex(BackupError, "No encuentro"):
            self.restore(self.folder / "no_existe.dump")

    def test_an_existing_database_needs_replace(self):
        path = self.make_copy()
        with self.assertRaisesRegex(BackupError, "ya existe"):
            self.restore(path, admin=FakeAdmin(existing=["domux_prueba_restaurada"]))
        admin = FakeAdmin(existing=["domux_prueba_restaurada"])
        result, _, _ = self.restore(path, admin=admin, replace=True)
        self.assertTrue(result.ok)
        self.assertEqual(admin.calls, [("drop", "domux_prueba_restaurada"), ("create", "domux_prueba_restaurada")])

    def test_the_real_database_is_protected(self):
        path = self.make_copy()
        for options in ({}, {"replace": True}, {"confirmed": True}):
            admin = FakeAdmin(existing=["domux_prueba"])
            with self.subTest(options=options), self.assertRaisesRegex(BackupError, "es la base real"):
                self.restore(path, target="domux_prueba", admin=admin, **options)
            self.assertEqual(admin.calls, [])
        admin = FakeAdmin(existing=["domux_prueba"])
        result, _, _ = self.restore(path, target="domux_prueba", admin=admin, replace=True, confirmed=True)
        self.assertTrue(result.ok)
        self.assertEqual(admin.calls, [("drop", "domux_prueba"), ("create", "domux_prueba")])

    def test_a_failed_restore_does_not_leave_an_incomplete_database(self):
        admin = FakeAdmin()
        with self.assertRaisesRegex(BackupError, "pg_restore falló"):
            self.restore(self.make_copy(), runner=FakePostgres(restore_ok=False), admin=admin)
        self.assertEqual(admin.calls, [("create", "domux_prueba_restaurada"), ("drop", "domux_prueba_restaurada")])
        self.assertEqual(admin.existing, set())


class CommandLineTests(TempFolderTestCase):
    def setUp(self):
        super().setUp()
        for patcher in (
            mock.patch.object(comun, "BACKEND_DIR", self.folder / "backend"),  # que los registros no ensucien instance/
            mock.patch("scripts.copia_diaria.load_dotenv"),  # que no se lea el .env real del programador
            mock.patch("scripts.restaurar_copia.load_dotenv"),
            mock.patch("builtins.print"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        (self.folder / "backend").mkdir()
        self.copies = self.folder / "copias"
        self.copies.mkdir()

    def environ(self, **extra):
        return mock.patch.dict(os.environ, {"DATABASE_URL": FAKE_URL, "BACKUP_DIR": str(self.copies), **extra}, clear=True)

    def test_backup_without_configuration_fails_with_exit_code_1(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(copia_diaria.main([]), 1)
        self.assertIn("Falta DATABASE_URL", (self.folder / "backend" / "instance" / "copias.log").read_text(encoding="utf-8"))

    def test_backup_runs_with_the_given_options(self):
        with self.environ(), mock.patch.object(copia_diaria, "make_backup") as make:
            self.assertEqual(copia_diaria.main(["--conservar", "3"]), 0)
        self.assertEqual(make.call_args[0][0].keep, 3)

    def test_backup_errors_become_exit_code_1(self):
        with self.environ(), mock.patch.object(copia_diaria, "make_backup", side_effect=BackupError("falló")):
            self.assertEqual(copia_diaria.main([]), 1)
        with self.environ(), mock.patch.object(copia_diaria, "make_backup", side_effect=psycopg2.OperationalError("sin red")):
            self.assertEqual(copia_diaria.main([]), 1)

    def test_listing_reports_by_exit_code(self):
        with self.environ():
            self.assertEqual(copia_diaria.main(["--listar"]), 1)  # carpeta vacía
            path = self.copies / "domux_20261116_020000.dump"
            path.write_bytes(b"PGDMP")
            comun.manifest_path(path).write_text(json.dumps({"sha256": comun.sha256_of(path)}), encoding="utf-8")
            with mock.patch.object(copia_diaria, "colombia_now", return_value=datetime(2026, 11, 16, 8, tzinfo=COLOMBIA)):
                self.assertEqual(copia_diaria.main(["--listar"]), 0)

    def test_restore_needs_to_know_what_to_restore(self):
        with self.environ(), mock.patch("sys.stderr", new=io.StringIO()), self.assertRaises(SystemExit):
            restaurar_copia.main([])

    def test_restore_last_without_copies_fails(self):
        with self.environ():
            self.assertEqual(restaurar_copia.main(["--ultima"]), 1)

    def test_restore_last_uses_the_newest_copy_and_a_new_database_name(self):
        for day in (1, 2):
            (self.copies / f"domux_202611{day:02d}_020000.dump").write_bytes(b"PGDMP")
        answer = restaurar_copia.RestoreResult(database="domux_prueba_restaurada", ok=True, tables=1, rows=1)
        with self.environ(), mock.patch.object(restaurar_copia, "restore_backup", return_value=answer) as restore:
            self.assertEqual(restaurar_copia.main(["--ultima"]), 0)
        args = restore.call_args[0]
        self.assertEqual(args[1].name, "domux_20261102_020000.dump")
        self.assertEqual(args[2], "domux_prueba_restaurada")
        self.assertFalse(restore.call_args[1]["confirmed"])

    def test_restore_with_differences_exits_with_1(self):
        answer = restaurar_copia.RestoreResult(database="x", ok=False, tables=1, rows=1)
        with self.environ(), mock.patch.object(restaurar_copia, "restore_backup", return_value=answer):
            self.assertEqual(restaurar_copia.main(["--archivo", str(self.copies / "una.dump"), "--base", "x"]), 1)

    def test_replacing_the_real_database_asks_for_its_name(self):
        answer = restaurar_copia.RestoreResult(database="domux_prueba", ok=True, tables=1, rows=1)
        arguments = ["--archivo", str(self.copies / "una.dump"), "--base", "domux_prueba", "--reemplazar"]
        with self.environ(), mock.patch.object(restaurar_copia, "restore_backup", return_value=answer) as restore:
            with mock.patch("builtins.input", return_value="otro_nombre"):
                self.assertEqual(restaurar_copia.main(arguments), 1)
            restore.assert_not_called()
            with mock.patch("builtins.input", return_value=" domux_prueba "):
                self.assertEqual(restaurar_copia.main(arguments), 0)
            self.assertTrue(restore.call_args[1]["confirmed"])
            self.assertTrue(restore.call_args[1]["replace"])

    def test_restore_database_errors_become_exit_code_1(self):
        with self.environ(), mock.patch.object(restaurar_copia, "restore_backup", side_effect=psycopg2.OperationalError("sin red")):
            self.assertEqual(restaurar_copia.main(["--archivo", str(self.copies / "una.dump")]), 1)


# ---------------------------------------------------------------------------------------------
# Pruebas con un PostgreSQL de verdad
# ---------------------------------------------------------------------------------------------


def postgres_url():
    """Dirección del PostgreSQL de pruebas, o None si las pruebas corren con SQLite."""
    raw = os.environ.get("TEST_DATABASE_URL", "")
    if not raw.startswith("postgres"):
        return None
    try:
        return comun.load_settings({"DATABASE_URL": raw}, need_folder=False).url
    except BackupError:
        return None


def postgres_tools_problem(url):
    """Dice por qué no se pueden probar pg_dump y pg_restore contra ese servidor (o None si se puede)."""
    try:
        pg_dump = comun.find_tool("pg_dump", os.environ.get("PG_BIN_DIR"))
        comun.find_tool("pg_restore", os.environ.get("PG_BIN_DIR"))
    except BackupError as error:
        return str(error)
    connection = psycopg2.connect(**comun.connection_kwargs(url))
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW server_version_num")
            server_major = int(cursor.fetchone()[0]) // 10000
    finally:
        connection.close()
    client_text = comun.run_command([pg_dump, "--version"]).stdout
    client_major = int(re.search(r"(\d+)", client_text).group(1))
    if client_major < server_major:
        return f"pg_dump {client_major} es más viejo que el servidor {server_major}: no puede copiarlo."
    return None


@unittest.skipUnless(postgres_url(), "Se necesita TEST_DATABASE_URL de PostgreSQL.")
class RealServerTests(TempFolderTestCase):
    """Crea y borra bases de verdad, y cuenta filas de verdad (no necesita pg_dump)."""

    @classmethod
    def setUpClass(cls):
        cls.url = postgres_url()
        cls.suffix = uuid.uuid4().hex[:8]

    def make_database(self, name, statements=()):
        admin = restaurar_copia.PgAdmin(self.url)
        self.addCleanup(self.drop_database, name)
        admin.create(name)
        admin.close()
        connection = psycopg2.connect(**comun.connection_kwargs(self.url, name))
        try:
            with connection, connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
        finally:
            connection.close()

    def drop_database(self, name):
        admin = restaurar_copia.PgAdmin(self.url)
        try:
            admin.drop(name)
        finally:
            admin.close()

    def test_admin_creates_checks_and_drops_a_database(self):
        name = f"domux_cpy_admin_{self.suffix}"
        admin = restaurar_copia.PgAdmin(self.url)
        self.addCleanup(admin.close)
        self.assertFalse(admin.exists(name))
        admin.create(name)
        self.assertTrue(admin.exists(name))
        admin.drop(name)
        self.assertFalse(admin.exists(name))

    def test_count_rows_counts_every_table(self):
        name = f"domux_cpy_conteo_{self.suffix}"
        self.make_database(name, [
            "CREATE TABLE personas (id serial PRIMARY KEY, nombre text)",
            "INSERT INTO personas (nombre) VALUES ('Ana'), ('Beto'), ('Carla')",
            "CREATE TABLE vacia (id int)",
        ])
        self.assertEqual(comun.count_rows(self.url, name), {"personas": 3, "vacia": 0})


@unittest.skipUnless(postgres_url(), "Se necesita TEST_DATABASE_URL de PostgreSQL.")
class RealBackupAndRestoreTests(TempFolderTestCase):
    """Copia y restaura de verdad con pg_dump y pg_restore (se salta si no son compatibles con el servidor)."""

    @classmethod
    def setUpClass(cls):
        cls.url = postgres_url()
        problem = postgres_tools_problem(cls.url)
        if problem:
            raise unittest.SkipTest(problem)

    def test_a_real_copy_can_be_restored_with_the_same_data(self):
        suffix = uuid.uuid4().hex[:8]
        source, restored = f"domux_cpy_origen_{suffix}", f"domux_cpy_origen_{suffix}_restaurada"
        admin = restaurar_copia.PgAdmin(self.url)
        self.addCleanup(admin.close)
        for name in (source, restored):
            self.addCleanup(admin.drop, name)
        admin.create(source)
        connection = psycopg2.connect(**comun.connection_kwargs(self.url, source))
        try:
            with connection, connection.cursor() as cursor:
                cursor.execute("CREATE TABLE personas (id serial PRIMARY KEY, nombre text, nota text)")
                cursor.execute("INSERT INTO personas (nombre, nota) VALUES ('María Pérez', 'ñandú: áéíóú'), ('Juan', NULL)")
                cursor.execute("CREATE TABLE vacia (id int)")
        finally:
            connection.close()

        settings = comun.load_settings(
            {"DATABASE_URL": self.url.set(database=source).render_as_string(hide_password=False),
             "BACKUP_DIR": str(self.folder), "PG_BIN_DIR": os.environ.get("PG_BIN_DIR", "")}
        )
        backup = copia_diaria.make_backup(settings, say=self.messages.append)
        self.assertEqual((backup.tables, backup.rows), (2, 2))
        self.assertTrue(backup.path.is_file())
        self.assertEqual(comun.read_manifest(backup.path)["filas_por_tabla"], {"personas": 2, "vacia": 0})

        result = restaurar_copia.restore_backup(settings, backup.path, restored, say=self.messages.append)
        self.assertTrue(result.ok, "\n".join(self.messages))
        self.assertEqual((result.tables, result.rows), (2, 2))

        connection = psycopg2.connect(**comun.connection_kwargs(self.url, restored))
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT nombre, nota FROM personas ORDER BY id")
                self.assertEqual(cursor.fetchall(), [("María Pérez", "ñandú: áéíóú"), ("Juan", None)])
        finally:
            connection.close()

        # Una copia alterada se rechaza antes de tocar nada.
        backup.path.write_bytes(backup.path.read_bytes() + b"x")
        with self.assertRaisesRegex(BackupError, "huella"):
            restaurar_copia.restore_backup(settings, backup.path, restored + "_2", say=self.messages.append)


if __name__ == "__main__":
    unittest.main()
