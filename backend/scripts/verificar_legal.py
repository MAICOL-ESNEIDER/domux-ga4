"""Revisión de los documentos legales de DOMUX (política de datos, términos, cookies...).

Uso, desde la carpeta ``backend``::

    python -m scripts.verificar_legal                    # revisa que los textos estén bien armados
    python -m scripts.verificar_legal --exigir-vigentes  # además falla si alguno sigue en preparación
    python -m scripts.verificar_legal --carpeta RUTA      # revisa los textos de otra carpeta

La primera forma se usa a diario: también la corre la prueba automática. La segunda es la **puerta de la
entrega**: antes de poner la etiqueta de la versión final (``v1.0.0``), los ocho documentos deben estar escritos,
revisados y marcados como ``vigente``. El pipeline la corre solo cuando se sube una etiqueta de versión final
(las etiquetas de prueba, como ``v1.0.0-rc.1``, no la exigen).

Termina con código 0 si todo está bien y con 1 si hay algo que arreglar, para que el pipeline lo detecte.
"""

import argparse
import sys
from pathlib import Path

from services import legal_service as legal


def main(argv=None, say=print):
    """Revisa los documentos y devuelve el código de salida: 0 si todo está bien y 1 si algo falla."""
    parser = argparse.ArgumentParser(
        prog="python -m scripts.verificar_legal",
        description="Revisa los documentos legales de DOMUX (carpeta backend/legal).",
    )
    parser.add_argument(
        "--exigir-vigentes", action="store_true",
        help="falla también si algún documento sigue «pendiente» (la puerta de la versión final)",
    )
    parser.add_argument("--carpeta", help="carpeta con los textos; si no se indica, se usa backend/legal")
    args = parser.parse_args(argv)
    directory = Path(args.carpeta) if args.carpeta else None

    problems = legal.check_all(directory)
    if problems:
        say("Hay documentos legales mal armados:")
        for problem in problems:
            say(f"  - {problem}")
        return 1

    pending = legal.pending_slugs(directory)
    total = len(legal.DOCUMENT_SLUGS)
    say(f"{total} documentos legales: {total - len(pending)} vigentes y {len(pending)} en preparación.")
    if args.exigir_vigentes and pending:
        say("No se puede entregar la versión final: faltan por escribir y publicar (estado «vigente»):")
        for slug in pending:
            say(f"  - {slug}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
