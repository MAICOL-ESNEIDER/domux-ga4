"""Lectura de los archivos que se suben en los formularios de la web (fotos, videos, audios y PDF).

La app manda los adjuntos como texto («data:image/jpeg;base64,…»); la web hace lo mismo con el archivo
que elige la administración. El tipo no se toma de lo que dice el navegador: se reconoce por los primeros
bytes del archivo, así uno con la extensión cambiada (o un SVG, que puede llevar scripts) no se cuela.
La revisión de los bytes es la misma que hace la API con lo que manda la app (``services.media``).
"""

import base64

from flask import request

from services.media import MAX_MEDIA_BYTES, PDF_MIME, is_pdf, sniff_media

__all__ = (
    "MAX_MEDIA_BYTES", "MEDIA_ACCEPT", "MEDIA_FORMATS_TEXT", "DOCUMENT_ACCEPT", "DOCUMENT_FORMATS_TEXT",
    "UNIT_DOCUMENT_ACCEPT", "UNIT_DOCUMENT_FORMATS_TEXT",
    "attach_media",
    "UploadError", "read_media", "read_unit_document", "sniff_media",
)

#: Lo que se le dice a la persona que puede subir, y lo que acepta el campo del formulario.
MEDIA_FORMATS_TEXT = "PNG, JPG, WebP, MP4, WebM, MP3, M4A, OGG o WAV"
MEDIA_ACCEPT = (
    "image/png,image/jpeg,image/webp,video/mp4,video/webm,audio/mpeg,audio/mp4,audio/ogg,audio/wav"
)
#: Lo mismo donde además se puede adjuntar un documento PDF (los comunicados).
DOCUMENT_FORMATS_TEXT = MEDIA_FORMATS_TEXT.replace(" o WAV", ", WAV o PDF")
DOCUMENT_ACCEPT = MEDIA_ACCEPT + "," + PDF_MIME


#: Lo que se puede subir como documento de la unidad: PDF y fotos, nada de video ni audio.
UNIT_DOCUMENT_ACCEPT = "application/pdf,image/png,image/jpeg,image/webp"
UNIT_DOCUMENT_FORMATS_TEXT = "PDF, PNG, JPG o WebP"


class UploadError(ValueError):
    """Un archivo que no se puede publicar. El mensaje está en español, listo para mostrárselo a la persona."""


def attach_media(body, upload):
    """Agrega a ``body`` el adjunto elegido en un formulario (foto, video, audio o PDF), si hay uno.

    Devuelve el mensaje para la persona si el archivo no sirve, o None si todo está bien (también
    cuando no se eligió ningún archivo).
    """
    try:
        media = read_media(upload, allow_document=True)
    except UploadError as problem:
        return str(problem)
    if media is not None:
        body["mediaUrl"], body["mediaType"] = media
        if download_allowed():
            body["mediaDownloadable"] = True
    return None


def download_allowed(field="media"):
    """Dice si quien adjunta marcó la casilla para que los demás puedan descargar el archivo."""
    return request.form.get(f"{field}_downloadable") == "1"


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


def read_unit_document(upload):
    """El archivo elegido para un documento de la unidad: ``(texto data:…, nombre del archivo)``.

    Lo único que se revisa aquí es que se haya elegido uno y que no pese demasiado (para no cargar en
    memoria un archivo enorme); el tipo real lo revisa la API por los primeros bytes. Si no hay archivo o pesa
    de más, levanta ``UploadError`` con el mensaje para la persona.
    """
    if upload is None or not upload.filename:
        raise UploadError("Elige el archivo del documento.")
    raw = upload.read(MAX_MEDIA_BYTES + 1)
    if len(raw) > MAX_MEDIA_BYTES:
        raise UploadError(
            f"El archivo pesa demasiado: el máximo es {MAX_MEDIA_BYTES // (1024 * 1024)} MB. "
            "Elige uno más liviano."
        )
    return f"data:application/octet-stream;base64,{base64.b64encode(raw).decode()}", upload.filename
