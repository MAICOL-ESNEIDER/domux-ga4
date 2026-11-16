"""Copia de seguridad diaria de la base de datos de DOMUX (TT-009).

Uso, desde la carpeta ``backend``::

    python -m scripts.copia_diaria                  # hace una copia nueva y deja las últimas 7
    python -m scripts.copia_diaria --listar         # muestra las copias y revisa que estén íntegras
    python -m scripts.copia_diaria --destino E:\\copias_domux --conservar 10

La configuración sale de ``backend/.env`` (o de las variables del sistema):
``DATABASE_URL``, ``BACKUP_DIR``, ``BACKUP_KEEP`` (opcional) y ``PG_BIN_DIR`` (opcional).
Termina con código 0 si todo salió bien y con 1 si hubo un error, para que el Programador de
tareas o cron puedan detectarlo.
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

from scripts import copias_comun as comun
from scripts.copias_comun import BackupError
from time_utils import colombia_now


@dataclass
class BackupResult:
    """Lo que quedó después de hacer una copia."""

    path: Path
    size: int
    sha256: str
    tables: int
    rows: int
    removed: list = field(default_factory=list)


def make_backup(settings, run=comun.run_command, count=comun.count_rows, now=None, say=print):
    """Hace una copia nueva, la revisa y borra las que sobran. Si algo falla, no borra ninguna copia buena."""
    folder = settings.backup_dir
    try:
        folder.mkdir(exist_ok=True)  # solo la última carpeta: si el disco no está, que falle y avise
    except OSError as error:
        raise BackupError(
            f"No pude usar la carpeta {folder}: {error}. ¿Está conectado el disco o el USB?"
        ) from error
    comun.remove_partial_files(folder)

    pg_dump = comun.find_tool("pg_dump", settings.pg_bin_dir)
    pg_restore = comun.find_tool("pg_restore", settings.pg_bin_dir)
    now = now or colombia_now()
    final = folder / f"domux_{now:%Y%m%d_%H%M%S}.dump"
    if final.exists():
        raise BackupError(f"Ya existe una copia con esta misma hora ({final.name}); espera un segundo y repite.")
    partial = final.with_name(final.name + ".parcial")  # así nunca se confunde una copia a medias con una buena

    # 1) Filas de cada tabla, para comparar cuando se restaure. Si falla, la copia sigue sin ese dato.
    try:
        rows_by_table = count(settings.url)
    except psycopg2.Error as error:
        rows_by_table = None
        say(f"AVISO: no pude contar las filas de las tablas ({comun.short(error)}). La copia sigue sin ese dato.")

    # 2) La copia. La clave de la base viaja en una variable de entorno, no en la línea de comandos.
    say(f"Haciendo la copia de la base «{settings.database}» en {folder} ...")
    command = [
        pg_dump,
        "--format=custom",  # formato comprimido que lee pg_restore
        "--no-owner",  # no amarra la copia al usuario de esta máquina
        "--no-acl",  # tampoco a sus permisos
        "--file", str(partial),
        *comun.connection_args(settings.url),
        "--dbname", settings.database,
    ]
    result = run(command, comun.connection_env(settings.url))
    if result.returncode != 0:
        partial.unlink(missing_ok=True)
        raise BackupError("pg_dump no pudo hacer la copia: " + comun.short(result.stderr))

    # 3) Revisión: que el archivo exista, no esté vacío y pg_restore pueda leerlo.
    try:
        if not partial.exists() or partial.stat().st_size == 0:
            raise BackupError("La copia quedó vacía.")
        comun.check_readable(partial, pg_restore, run)
    except BackupError:
        partial.unlink(missing_ok=True)
        raise

    # 4) Huella y ficha; recién ahora el archivo recibe su nombre definitivo.
    sha256 = comun.sha256_of(partial)
    size = partial.stat().st_size
    version = run([pg_dump, "--version"], {}).stdout.strip()
    os.replace(partial, final)
    manifest = {
        "version_de_la_ficha": 1,
        "archivo": final.name,
        "creada": now.isoformat(timespec="seconds"),
        "base": settings.database,
        "servidor": settings.url.host or "local",
        "programa": version,
        "tamano_bytes": size,
        "sha256": sha256,
        "filas_por_tabla": rows_by_table,
    }
    with open(comun.manifest_path(final), "w", encoding="utf-8") as target:
        json.dump(manifest, target, ensure_ascii=False, indent=2)

    # 5) Rotación: solo ahora, con la copia nueva ya revisada, se borran las más viejas.
    removed = comun.remove_old_backups(folder, settings.keep)
    tables = len(rows_by_table) if rows_by_table else 0
    rows = sum(rows_by_table.values()) if rows_by_table else 0
    say(
        f"COPIA LISTA: {final.name} ({comun.format_size(size)}, {tables} tablas, {rows} filas). "
        f"Huella SHA-256: {sha256}"
    )
    for old in removed:
        say(f"Copia vieja borrada: {old.name}")
    return BackupResult(path=final, size=size, sha256=sha256, tables=tables, rows=rows, removed=removed)


def show_backups(settings, now=None, say=print):
    """Muestra las copias y revisa su huella. Devuelve cuántos problemas encontró (0 = todo bien)."""
    backups = comun.list_backups(settings.backup_dir)
    if not backups:
        say(f"No hay copias en {settings.backup_dir}.")
        return 1
    say(f"Copias en {settings.backup_dir} (la más nueva primero):")
    problems = 0
    for number, item in enumerate(backups, start=1):
        manifest = comun.read_manifest(item.path)
        if manifest is None:
            state = "SIN FICHA (no se puede comprobar)"
            problems += 1
        elif manifest.get("sha256") == comun.sha256_of(item.path):
            state = "íntegra"
        else:
            state = "ALTERADA (la huella no coincide)"
            problems += 1
        say(f"  {number}. {item.path.name}  {item.taken_at:%Y-%m-%d %H:%M}  {comun.format_size(item.size)}  {state}")
    today = (now or colombia_now()).replace(tzinfo=None)
    days = (today - backups[0].taken_at).days
    if days >= 2:
        say(f"AVISO: la copia más nueva tiene {days} días. Revisa que la tarea diaria siga funcionando.")
        problems += 1
    return problems


def build_parser():
    parser = argparse.ArgumentParser(prog="python -m scripts.copia_diaria", description=__doc__.split("\n")[0])
    parser.add_argument("--listar", action="store_true", help="muestra las copias y revisa que estén íntegras")
    parser.add_argument("--destino", help="carpeta de las copias (si no, se usa BACKUP_DIR)")
    parser.add_argument("--conservar", type=int, help="cuántas copias dejar (si no, BACKUP_KEEP o 7)")
    return parser


def main(argv=None):
    """Punto de entrada. Devuelve 0 si todo salió bien y 1 si hubo un problema."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")  # la consola de Windows no siempre admite todos los símbolos
    args = build_parser().parse_args(argv)
    load_dotenv(comun.BACKEND_DIR / ".env")  # las variables del sistema tienen prioridad sobre el .env
    say = comun.make_logger()
    try:
        settings = comun.load_settings(os.environ, destination=args.destino, keep=args.conservar)
        say = comun.make_logger(settings.backup_dir)
        if args.listar:
            return 1 if show_backups(settings, say=say) else 0
        make_backup(settings, say=say)
        return 0
    except BackupError as error:
        say(f"ERROR: {error}")
        return 1
    except psycopg2.Error as error:
        say(f"ERROR con la base de datos: {comun.short(error)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
