"""Lectura de los archivos que se suben en los formularios de la web (fotos, videos y audios).

La app manda los adjuntos como texto («data:image/jpeg;base64,…»); la web hace lo mismo con el archivo
que elige la administración. El tipo no se toma de lo que dice el navegador: se reconoce por los primeros
bytes del archivo, así uno con la extensión cambiada (o un SVG, que puede llevar scripts) no se cuela.
"""

import base64

#: Lo más que puede pesar un adjunto. Como el texto en base64 pesa un tercio más y todo viaja en una sola
#: solicitud de 12 MB como máximo, 6 MB deja un buen margen.
MAX_MEDIA_BYTES = 6 * 1024 * 1024

#: Lo que se le dice a la persona que puede subir, y lo que acepta el campo del formulario.
MEDIA_FORMATS_TEXT = "PNG, JPG, WebP, MP4, WebM, MP3, M4A, OGG o WAV"
MEDIA_ACCEPT = (
    "image/png,image/jpeg,image/webp,video/mp4,video/webm,audio/mpeg,audio/mp4,audio/ogg,audio/wav"
)

#: Las marcas de los archivos MP4 que son solo audio (M4A y M4B).
_MP4_AUDIO_BRANDS = (b"M4A ", b"M4B ", b"M4P ")


class UploadError(ValueError):
    """Un archivo que no se puede publicar. El mensaje está en español, listo para mostrárselo a la persona."""


def sniff_media(raw):
    """El tipo («image/png») y la clase («image», «video» o «audio») que dicen los primeros bytes; None si no sirve."""
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "image"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "image"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp", "image"
    if raw[4:8] == b"ftyp":
        return ("audio/mp4", "audio") if raw[8:12] in _MP4_AUDIO_BRANDS else ("video/mp4", "video")
    if raw.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm", "video"
    if raw.startswith(b"OggS"):
        return "audio/ogg", "audio"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WAVE":
        return "audio/wav", "audio"
    # MP3: con la etiqueta ID3 al comienzo, o con el encabezado de una trama MPEG (11 bits en 1).
    if raw.startswith(b"ID3") or (
        len(raw) > 1 and raw[0] == 0xFF and raw[1] & 0xE0 == 0xE0 and raw[1] & 0x18 != 0x08 and raw[1] & 0x06 != 0
    ):
        return "audio/mpeg", "audio"
    return None


def read_media(upload):
    """El archivo elegido en un campo de adjunto, listo para la API: ``(texto data:…, clase)``.

    Devuelve None si no se eligió ningún archivo. Si pesa demasiado o no es una imagen, un video ni un
    audio de los permitidos, levanta ``UploadError`` con el mensaje para la persona.
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
    found = sniff_media(raw)
    if found is None:
        raise UploadError(f"El archivo no es una imagen, un video ni un audio que se pueda publicar ({MEDIA_FORMATS_TEXT}).")
    mime, kind = found
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}", kind
