"""Copia el contrato de la API (docs/api/openapi.yaml) a backend/openapi, de donde lo sirve /docs.

Se corre después de cambiar el contrato:  python scripts/sync_openapi.py
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs" / "api" / "openapi.yaml"
TARGET = ROOT / "backend" / "openapi" / "openapi.yaml"

if __name__ == "__main__":
    TARGET.parent.mkdir(exist_ok=True)
    shutil.copyfile(SOURCE, TARGET)
    print(f"Contrato copiado a {TARGET.relative_to(ROOT)}")
