"""Piezas comunes de las copias de seguridad de la base de datos (TT-009).

Las usan dos programas que se ejecutan desde la carpeta ``backend``:

* ``python -m scripts.copia_diaria``: hace la copia y deja solo las últimas 7.
* ``python -m scripts.restaurar_copia``: restaura una copia en una base nueva.

La copia se hace con ``pg_dump`` (formato "custom", que ya sale comprimido) y se revisa con
``pg_restore --list``. Junto a cada copia queda un archivo ``.json`` (la "ficha") con la huella
SHA-256 y el número de filas de cada tabla; la restauración lo usa como prueba de que todo volvió.

Importante: la copia incluye las contraseñas protegidas (hash) de los usuarios. Por eso la carpeta
de destino debe ser solo del administrador y nunca estar dentro del proyecto (el repositorio es
público).
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2 import sql
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from time_utils import colombia_now

# Carpeta del servidor (backend) y raíz del proyecto (donde está .git).
BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent

# Cuántas copias se guardan si no se dice otra cosa.
DEFAULT_KEEP = 7

# Las copias se llaman domux_AAAAMMDD_HHMMSS.dump. Solo se tocan archivos con este nombre exacto,
# para no borrar nunca algo que el usuario guardó en la misma carpeta.
BACKUP_NAME = re.compile(r"^domux_(\d{8})_(\d{6})\.dump$")
PARTIAL_NAME = re.compile(r"^domux_\d{8}_\d{6}\.dump\.parcial$")

# Nombres de base de datos permitidos al restaurar (letras, números y guion bajo).
DATABASE_NAME = re.compile(r"^[A-Za-z0-9_]{1,63}$")


class BackupError(Exception):
    """Problema esperado (falta una variable, no hay disco...). Se muestra sin traza técnica."""


@dataclass
class Settings:
    """Lo que necesitan los programas de copia, ya revisado."""

    url: object  # dirección de la base (URL de SQLAlchemy ya separada en partes)
    backup_dir: Path | None  # carpeta donde se guardan las copias
    keep: int  # cuántas copias se conservan
    pg_bin_dir: str | None  # carpeta de pg_dump y pg_restore, si no están en el PATH

    @property
    def database(self):
        return self.url.database


@dataclass
class BackupFile:
    """Una copia encontrada en la carpeta."""

    path: Path
    taken_at: datetime  # fecha y hora que dice el nombre (hora de Colombia, sin zona)
    size: int


def load_settings(environ, destination=None, keep=None, need_folder=True):
    """Lee y revisa la configuración. ``environ`` es un diccionario como ``os.environ``."""
    raw_url = (environ.get("DATABASE_URL") or "").strip()
    if not raw_url:
        raise BackupError(
            "Falta DATABASE_URL: escribe en el archivo backend/.env la dirección de la base PostgreSQL."
        )
    if raw_url.startswith("postgres://"):  # Render y otros la entregan así; SQLAlchemy pide "postgresql://"
        raw_url = "postgresql://" + raw_url[len("postgres://"):]
    try:
        url = make_url(raw_url)
    except ArgumentError as error:
        raise BackupError("DATABASE_URL no tiene un formato válido.") from error
    if url.get_backend_name() != "postgresql":
        raise BackupError(
            f"Estas copias son solo para PostgreSQL y DATABASE_URL usa {url.get_backend_name()}."
        )
    if not url.database:
        raise BackupError("DATABASE_URL no dice el nombre de la base de datos.")

    folder = None
    folder_text = str(destination or environ.get("BACKUP_DIR") or "").strip()
    if folder_text:
        folder = Path(folder_text).expanduser().resolve()
        if folder == PROJECT_DIR or PROJECT_DIR in folder.parents:
            raise BackupError(
                "La carpeta de copias no puede estar dentro del proyecto: las copias llevan datos reales y el "
                "repositorio es público. Usa un disco o USB aparte, por ejemplo E:\\copias_domux."
            )
    elif need_folder:
        raise BackupError(
            "Falta BACKUP_DIR: escribe en backend/.env la carpeta donde se guardan las copias, "
            "de preferencia en un disco o USB distinto al del computador."
        )

    keep_value = keep if keep is not None else (environ.get("BACKUP_KEEP") or DEFAULT_KEEP)
    try:
        keep_number = int(keep_value)
    except (TypeError, ValueError) as error:
        raise BackupError("BACKUP_KEEP debe ser un número entero, por ejemplo 7.") from error
    if keep_number < 1:
        raise BackupError("Hay que conservar al menos 1 copia.")

    pg_bin_dir = (environ.get("PG_BIN_DIR") or "").strip() or None
    return Settings(url=url, backup_dir=folder, keep=keep_number, pg_bin_dir=pg_bin_dir)


# ---------------------------------------------------------------------------------------------
# Programas de PostgreSQL y conexión
# ---------------------------------------------------------------------------------------------


def find_tool(name, pg_bin_dir=None):
    """Devuelve la ruta de pg_dump o pg_restore: primero la carpeta PG_BIN_DIR y si no, el PATH."""
    path = shutil.which(name, path=pg_bin_dir) if pg_bin_dir else None
    if not path:
        path = shutil.which(name)  # si no se indicó carpeta (o ahí no está), se busca en el PATH
    if not path:
        raise BackupError(
            f"No encontré {name}. Instala las herramientas de PostgreSQL (vienen con su instalador) o escribe "
            "en PG_BIN_DIR la carpeta donde están, por ejemplo C:\\Program Files\\PostgreSQL\\16\\bin."
        )
    return path


def run_command(args, extra_env=None):
    """Ejecuta un programa y devuelve su resultado (código, salida y errores como texto)."""
    env = dict(os.environ)
    env.update(extra_env or {})
    return subprocess.run(args, env=env, capture_output=True, text=True, errors="replace", check=False)


def connection_args(url):
    """Opciones de conexión para pg_dump y pg_restore. La clave NO va aquí (se vería en la lista de procesos)."""
    args = []
    if url.host:
        args += ["--host", url.host]
    if url.port:
        args += ["--port", str(url.port)]
    if url.username:
        args += ["--username", url.username]
    return args


def connection_env(url):
    """Variables de entorno con la clave y el modo seguro, que sí leen pg_dump y pg_restore."""
    env = {}
    if url.password:
        env["PGPASSWORD"] = url.password
    if url.query.get("sslmode"):
        env["PGSSLMODE"] = url.query["sslmode"]
    return env


def connection_kwargs(url, database=None):
    """Datos de conexión para psycopg2. ``database`` permite conectarse a otra base del mismo servidor."""
    kwargs = {"dbname": database or url.database}
    if url.host:
        kwargs["host"] = url.host
    if url.port:
        kwargs["port"] = url.port
    if url.username:
        kwargs["user"] = url.username
    if url.password:
        kwargs["password"] = url.password
    if url.query.get("sslmode"):
        kwargs["sslmode"] = url.query["sslmode"]
    return kwargs


def short(text, limit=400):
    """Recorta un mensaje largo de error para mostrarlo en pantalla."""
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit] + "..."


def count_rows(url, database=None):
    """Cuenta las filas de cada tabla (esquema public) dentro de una sola foto consistente de la base."""
    connection = psycopg2.connect(**connection_kwargs(url, database))
    try:
        connection.set_session(isolation_level="REPEATABLE READ", readonly=True)
        counts = {}
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
            )
            names = [row[0] for row in cursor.fetchall()]
            for name in names:
                cursor.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(name)))
                counts[name] = cursor.fetchone()[0]
        return counts
    finally:
        connection.close()


# ---------------------------------------------------------------------------------------------
# Archivos de copia: lista, huella, ficha y rotación
# ---------------------------------------------------------------------------------------------


def sha256_of(path):
    """Huella SHA-256 de un archivo: cambia si se altera un solo byte."""
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_path(dump_path):
    """Ruta de la ficha de una copia: el mismo nombre más ``.json``."""
    return Path(str(dump_path) + ".json")


def read_manifest(dump_path):
    """Lee la ficha de una copia. Devuelve None si no existe o está dañada."""
    try:
        with open(manifest_path(dump_path), encoding="utf-8") as source:
            data = json.load(source)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def list_backups(folder):
    """Copias de la carpeta, de la más nueva a la más vieja. Ignora todo lo que no tenga el nombre exacto."""
    found = []
    if folder is None or not Path(folder).is_dir():
        return found
    for path in Path(folder).iterdir():
        match = BACKUP_NAME.match(path.name)
        if match and path.is_file():
            taken_at = datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S")
            found.append(BackupFile(path=path, taken_at=taken_at, size=path.stat().st_size))
    found.sort(key=lambda item: item.taken_at, reverse=True)
    return found


def remove_old_backups(folder, keep):
    """Borra las copias que sobran (y su ficha), dejando las ``keep`` más nuevas. Devuelve lo borrado."""
    removed = []
    for old in list_backups(folder)[keep:]:
        for path in (old.path, manifest_path(old.path)):
            if path.exists():
                path.unlink()
        removed.append(old.path)
    return removed


def remove_partial_files(folder):
    """Quita restos de copias que quedaron a medias (por un corte de luz o un USB desconectado)."""
    for path in Path(folder).iterdir():
        if PARTIAL_NAME.match(path.name) and path.is_file():
            path.unlink()


def format_size(size):
    """Tamaño en palabras sencillas: 950 B, 12.3 KB, 4.5 MB."""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def make_logger(folder=None):
    """Devuelve una función que muestra un mensaje en pantalla y lo anota en los registros.

    Se anota en dos sitios: en la carpeta de copias (viaja con ellas) y en ``backend/instance`` del
    computador, para que quede huella aunque el disco de copias esté desconectado.
    """
    log_files = [BACKEND_DIR / "instance" / "copias.log"]
    if folder is not None:
        log_files.append(Path(folder) / "copias.log")

    def say(message):
        line = f"[{colombia_now():%Y-%m-%d %H:%M:%S}] {message}"
        print(line)
        for log_file in log_files:
            try:
                log_file.parent.mkdir(exist_ok=True)
                with open(log_file, "a", encoding="utf-8") as target:
                    target.write(line + "\n")
            except OSError:
                pass  # si no se puede escribir el registro, el mensaje ya salió en pantalla

    return say


def check_readable(dump_path, pg_restore, run=run_command):
    """Comprueba que pg_restore puede leer la copia (su índice está completo)."""
    result = run([pg_restore, "--list", str(dump_path)], {})
    if result.returncode != 0 or not (result.stdout or "").strip():
        raise BackupError("La copia quedó dañada, pg_restore no pudo leerla: " + short(result.stderr))
