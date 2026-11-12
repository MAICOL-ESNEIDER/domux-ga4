"""Imágenes de prueba para los datos de la unidad: pequeñas, pero con los bytes de verdad de cada formato."""

import base64

# Un PNG de 1×1 píxel, de verdad (no solo el encabezado).
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 32
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 32


def data_url(raw, mime="image/png"):
    """La imagen como la manda la app: «data:image/png;base64,…»."""
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"
