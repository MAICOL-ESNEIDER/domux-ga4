"""Restaura una copia de seguridad de la base de datos de DOMUX (TT-009).

Uso, desde la carpeta ``backend``::

    python -m scripts.restaurar_copia --ultima
    python -m scripts.restaurar_copia --archivo E:\\copias_domux\\domux_20261116_020000.dump
    python -m scripts.restaurar_copia --ultima --base domux --reemplazar     # SOBRE la base real

Por seguridad, la copia se restaura en una base NUEVA llamada ``<base>_restaurada`` (o el nombre
que se indique con ``--base``). Así se puede comprobar que la copia sirve sin tocar la base real.
Para dejarla en lugar de una base que ya existe hay que escribir ``--reemplazar``; y si esa base es
la real (la de DATABASE_URL), el programa además pide escribir su nombre para confirmar.

Al terminar compara las filas de cada tabla con las que había cuando se hizo la copia y lo muestra
en pantalla: ese resultado es la evidencia de la prueba de restauración.
"""

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql

from scripts import copias_comun as comun
from scripts.copias_comun import BackupError


@dataclass
class RestoreResult:
    """Resultado de una restauración."""

    database: str
    ok: bool
    tables: int
    rows: int
    lines: list = field(default_factory=list)  # una línea por tabla, para mostrar como evidencia


class PgAdmin:
    """Crea y borra bases en el servidor. Se conecta a «postgres», la base de mantenimiento."""

    def __init__(self, url):
        self.connection = psycopg2.connect(**comun.connection_kwargs(url, "postgres"))
        self.connection.autocommit = True  # CREATE y DROP DATABASE no pueden ir dentro de una transacción

    def exists(self, name):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
            return cursor.fetchone() is not None

    def drop(self, name):
        with self.connection.cursor() as cursor:
            # FORCE cierra las conexiones que haya abiertas (por ejemplo, el servidor de DOMUX encendido)
            cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))

    def create(self, name):
        with self.connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))

    def close(self):
        self.connection.close()


def compare_rows(expected, restored):
    """Compara las filas de la ficha con las de la base restaurada. Devuelve (líneas, hay_diferencias)."""
    lines = []
    different = False
    for table in sorted(set(expected) | set(restored)):
        before = expected.get(table)
        after = restored.get(table)
        if before is None:
            state = "SOBRA (no estaba en la ficha)"
        elif after is None:
            state = "FALTA en la base restaurada"
        elif before != after:
            state = "DIFERENTE"
        else:
            state = "igual"
        if state != "igual":
            different = True
        lines.append(f"  {table:<34} copia: {str(before):>7}   restaurada: {str(after):>7}   {state}")
    return lines, different


def restore_backup(
    settings, archive, target, replace=False, confirmed=False,
    run=comun.run_command, admin=None, count=comun.count_rows, say=print,
):
    """Restaura ``archive`` en la base ``target`` y comprueba el resultado."""
    archive = Path(archive)
    if not comun.DATABASE_NAME.match(target):
        raise BackupError("El nombre de la base solo puede tener letras, números y guion bajo (máximo 63).")
    if not archive.is_file():
        raise BackupError(f"No encuentro la copia {archive}.")

    # 1) Antes de tocar nada: que la copia no esté alterada y se pueda leer.
    manifest = comun.read_manifest(archive)
    if manifest is None:
        say("AVISO: la copia no tiene ficha (.json): no se podrá comparar el número de filas.")
    elif manifest.get("sha256") != comun.sha256_of(archive):
        raise BackupError("La huella SHA-256 de la copia no coincide con su ficha: el archivo fue alterado o se dañó.")
    pg_restore = comun.find_tool("pg_restore", settings.pg_bin_dir)
    comun.check_readable(archive, pg_restore, run)

    # 2) Seguro contra accidentes: la base real solo se reemplaza si se pidió y se confirmó.
    if target == settings.database and not (replace and confirmed):
        raise BackupError(
            f"«{target}» es la base real. Para reemplazarla usa --reemplazar y confirma escribiendo su nombre. "
            "Para probar la copia sin riesgo, restaura en otra base (por defecto «<base>_restaurada»)."
        )

    created_admin = admin is None
    admin = admin or PgAdmin(settings.url)
    try:
        # 3) Preparar la base de destino.
        if admin.exists(target):
            if not replace:
                raise BackupError(f"La base «{target}» ya existe. Elige otro nombre con --base o usa --reemplazar.")
            say(f"Borrando la base «{target}» para dejar su lugar a la copia ...")
            admin.drop(target)
        admin.create(target)

        # 4) Restaurar. --exit-on-error: si algo falla, se detiene y no queda una base a medias creída buena.
        say(f"Restaurando {archive.name} en la base «{target}» ...")
        command = [
            pg_restore, "--no-owner", "--no-acl", "--exit-on-error",
            *comun.connection_args(settings.url), "--dbname", target, str(archive),
        ]
        result = run(command, comun.connection_env(settings.url))
        if result.returncode != 0:
            admin.drop(target)  # no se deja una base incompleta
            raise BackupError("pg_restore falló y se borró la base incompleta: " + comun.short(result.stderr))
    finally:
        if created_admin:
            admin.close()

    # 5) Evidencia: filas por tabla, copia contra base restaurada.
    restored = count(settings.url, target)
    expected = (manifest or {}).get("filas_por_tabla")
    if expected is None:
        lines = [f"  {name:<34} restaurada: {rows:>7}" for name, rows in sorted(restored.items())]
        different = False
    else:
        lines, different = compare_rows(expected, restored)
    rows = sum(restored.values())
    say(f"Tablas restauradas: {len(restored)}. Filas en total: {rows}.")
    for line in lines:
        say(line)
    if different:
        say(
            "RESTAURADA CON DIFERENCIAS: el número de filas no coincide con el de la ficha. Si la base estaba en uso "
            "mientras se hacía la copia, es normal que haya filas nuevas; si no, repite la copia y la prueba."
        )
    elif expected is None:
        say("RESTAURACIÓN TERMINADA (sin ficha, no se pudo comparar con la copia).")
    else:
        say("RESTAURACIÓN CORRECTA: todas las tablas tienen las mismas filas que cuando se hizo la copia.")
    return RestoreResult(database=target, ok=not different, tables=len(restored), rows=rows, lines=lines)


def build_parser():
    parser = argparse.ArgumentParser(prog="python -m scripts.restaurar_copia", description=__doc__.split("\n")[0])
    origin = parser.add_mutually_exclusive_group(required=True)
    origin.add_argument("--ultima", action="store_true", help="usa la copia más nueva de la carpeta BACKUP_DIR")
    origin.add_argument("--archivo", help="ruta de la copia (.dump) que se quiere restaurar")
    parser.add_argument("--base", help="nombre de la base de destino (por defecto <base>_restaurada)")
    parser.add_argument("--reemplazar", action="store_true", help="si la base de destino ya existe, la borra y la rehace")
    return parser


def main(argv=None):
    """Punto de entrada. Devuelve 0 si la restauración quedó correcta y 1 en cualquier otro caso."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    load_dotenv(comun.BACKEND_DIR / ".env")
    say = comun.make_logger()
    try:
        settings = comun.load_settings(os.environ, need_folder=args.ultima)
        say = comun.make_logger(settings.backup_dir)
        if args.ultima:
            backups = comun.list_backups(settings.backup_dir)
            if not backups:
                raise BackupError(f"No hay copias en {settings.backup_dir}.")
            archive = backups[0].path
        else:
            archive = Path(args.archivo)
        target = args.base or f"{settings.database}_restaurada"

        confirmed = False
        if args.reemplazar and target == settings.database:
            print(f"ATENCIÓN: vas a BORRAR la base real «{target}» y dejar en su lugar la copia {archive.name}.")
            print("Apaga antes el servidor de DOMUX. Lo que se haya guardado después de la copia se perderá.")
            confirmed = input("Para continuar escribe el nombre de la base: ").strip() == target
            if not confirmed:
                raise BackupError("No se escribió el nombre correcto: no se hizo nada.")

        result = restore_backup(settings, archive, target, replace=args.reemplazar, confirmed=confirmed, say=say)
        return 0 if result.ok else 1
    except BackupError as error:
        say(f"ERROR: {error}")
        return 1
    except psycopg2.Error as error:
        say(f"ERROR con la base de datos: {comun.short(error)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
