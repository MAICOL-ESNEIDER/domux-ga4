"""Lectura de los archivos que se suben en los formularios de la web (fotos, videos, audios y PDF).

La app manda los adjuntos como texto («data:image/jpeg;base64,…»); la web hace lo mismo con el archivo
que elige la administración. El tipo no se toma de lo que dice el navegador: se reconoce por los primeros
bytes del archivo, así uno con la extensión cambiada (o un SVG, que puede llevar scripts) no se cuela.
La revisión de los bytes es la misma que hace la API con lo que manda la app (``services.media``).
"""

import base64

from services.media import MAX_MEDIA_BYTES, PDF_MIME, is_pdf, sniff_media

__all__ = (
    "MAX_MEDIA_BYTES", "MEDIA_ACCEPT", "MEDIA_FORMATS_TEXT", "DOCUMENT_ACCEPT", "DOCUMENT_FORMATS_TEXT",
    "UploadError", "read_media", "sniff_media",
)

#: Lo que se le dice a la persona que puede subir, y lo que acepta el campo del formulario.
MEDIA_FORMATS_TEXT = "PNG, JPG, WebP, MP4, WebM, MP3, M4A, OGG o WAV"
MEDIA_ACCEPT = (
    "image/png,image/jpeg,image/webp,video/mp4,video/webm,audio/mpeg,audio/mp4,audio/ogg,audio/wav"
)
#: Lo mismo donde además se puede adjuntar un documento PDF (los comunicados).
DOCUMENT_FORMATS_TEXT = MEDIA_FORMATS_TEXT.replace(" o WAV", ", WAV o PDF")
DOCUMENT_ACCEPT = MEDIA_ACCEPT + "," + PDF_MIME


class UploadError(ValueError):
    """Un archivo que no se puede publicar. El mensaje está en español, listo para mostrárselo a la persona."""


def read_media(upload, allow_document=False):
    """El archivo elegido en un campo de adjunto, listo para la API: ``(texto data:…, clase)``.

    Devuelve None si no se eligió ningún archivo. Si pesa demasiado o no es una imagen, un video ni un
    audio de los permitidos (ni un PDF, cuando ``allow_document``), levanta ``UploadError`` con el
    mensaje para la persona.
    """
    if upload is None or not upload.filename:
        return None
    # Se lee un byte más que el máximo: alcanza para saber que se pasó sin cargar un archivo enorme.
    raw = upload.read(MAX_MEDIA_BYTES + 1)
    if len(raw) > MAX_MEDIA_BYTES:
        raise UploadError(
            f"El archivo pesa demasiado: el máximo es {MAX_MEDIA_BYTES // (1024 * 1024)} MB. "
            "Elige uno más liviano."
        )
    if allow_document and is_pdf(raw):
        return f"data:{PDF_MIME};base64,{base64.b64encode(raw).decode()}", "document"
    found = sniff_media(raw)
    if found is None:
        formats = DOCUMENT_FORMATS_TEXT if allow_document else MEDIA_FORMATS_TEXT
        what = "una imagen, un video, un audio ni un PDF" if allow_document else "una imagen, un video ni un audio"
        raise UploadError(f"El archivo no es {what} que se pueda publicar ({formats}).")
    mime, kind = found
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}", kind
