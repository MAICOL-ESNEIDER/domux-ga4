"""Adjuntos guardados como «data:image/jpeg;base64,…» (fotos, videos, audios y documentos PDF).

La app manda los adjuntos de las PQRS, las reservas, los comunicados y la portería dentro del mismo
texto que guarda la base. Aquí se revisan dos veces:

- Al llegar (``check_attachment``): el tipo no se cree por lo que dice el texto, se reconoce por los
  primeros bytes del archivo, y no puede pesar más de 6 MB. Así un archivo con la extensión cambiada,
  un SVG o una página HTML (que pueden llevar scripts) no se cuela, y se guarda con su tipo real.
- Al mostrarlos (``decode_media``): la web de administración no los lleva dentro de la página; cada
  uno se pide aparte y pasa por aquí, que solo deja salir imagen, video, audio o PDF.

Ninguna función de este archivo guarda en la base.
"""

import base64
import binascii
import re

#: Lo más que puede pesar un adjunto. Como el texto en base64 pesa un tercio más y todo viaja en una
#: sola solicitud de 12 MB como máximo, 6 MB deja un buen margen.
MAX_MEDIA_BYTES = 6 * 1024 * 1024

#: Las clases de adjunto. «document» (PDF) solo se acepta donde la ruta lo permite: PQRS, reservas y
#: comunicados; en portería no.
MEDIA_KINDS = ("image", "video", "audio", "document")

PDF_MIME = "application/pdf"

#: Tipos de archivo que la web muestra o deja descargar. Un SVG o cualquier tipo con XML o HTML se
#: descarta porque puede llevar scripts.
MEDIA_MIME = re.compile(r"(?:image|video|audio)/[a-z0-9][a-z0-9.+-]*")

#: Las marcas de los archivos MP4 que son solo audio (M4A y M4B).
_MP4_AUDIO_BRANDS = (b"M4A ", b"M4B ", b"M4P ")

#: Cómo se nombra cada clase en los mensajes de error.
_KIND_TEXT = {
    "image": "una foto (PNG, JPG o WebP)",
    "video": "un video (MP4 o WebM)",
    "audio": "un audio (M4A, AAC, MP3, OGG, WAV o WebM)",
    "document": "un documento PDF",
}


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
    # AAC suelto (ADTS), como lo guardan algunas grabadoras de voz: 12 bits en 1 y la capa en 00.
    if len(raw) > 1 and raw[0] == 0xFF and raw[1] & 0xF6 == 0xF0:
        return "audio/aac", "audio"
    # MP3: con la etiqueta ID3 al comienzo, o con el encabezado de una trama MPEG (11 bits en 1).
    if raw.startswith(b"ID3") or (
        len(raw) > 1 and raw[0] == 0xFF and raw[1] & 0xE0 == 0xE0 and raw[1] & 0x18 != 0x08 and raw[1] & 0x06 != 0
    ):
        return "audio/mpeg", "audio"
    return None


def is_pdf(raw):
    """True si los bytes son un documento PDF (empiezan con «%PDF-»)."""
    return raw.startswith(b"%PDF-")


def _real_mime(raw, kind):
    """El tipo real del archivo, si coincide con la clase que dijo quien lo manda; None si no coincide."""
    if kind == "document":
        return PDF_MIME if is_pdf(raw) else None
    # MP4 (y M4A, 3GP o MOV) y WebM son contenedores que sirven igual para audio o para video: el
    # celular graba los audios en MP4 con la misma marca que un video, así que manda la clase dicha.
    if raw[4:8] == b"ftyp":
        return {"audio": "audio/mp4", "video": "video/mp4"}.get(kind)
    if raw.startswith(b"\x1a\x45\xdf\xa3"):
        return {"audio": "audio/webm", "video": "video/webm"}.get(kind)
    found = sniff_media(raw)
    if found is None:
        return None
    mime, found_kind = found
    return mime if found_kind == kind else None


def megabytes(size):
    """Los bytes en megas con un decimal, como se le dicen a la persona: 6291457 pasa a «6,0»."""
    return f"{size / (1024 * 1024):.1f}".replace(".", ",")


def check_attachment(value, kind, allow_document=False):
    """Revisa un adjunto que llega a la API y lo deja con su tipo real.

    ``value`` es el texto «data:…;base64,…» y ``kind`` la clase que dice quien lo manda («image»,
    «video», «audio» o «document»). Devuelve ``(texto, None)`` con el adjunto listo para guardar, o
    ``(None, mensaje)`` con el error en palabras para la persona.
    """
    if kind not in MEDIA_KINDS or (kind == "document" and not allow_document):
        return None, "Aquí solo se pueden adjuntar fotos, videos o audios."
    if not isinstance(value, str):
        return None, "El adjunto debe ser un archivo."
    header, separator, payload = value.partition(",")
    header = header.strip().lower()
    if not separator or not header.startswith("data:") or not header.endswith(";base64"):
        return None, "El adjunto debe llegar como archivo, no como enlace."
    try:
        raw = base64.b64decode("".join(payload.split()), validate=True)
    except (binascii.Error, ValueError):
        return None, "No se pudo leer el adjunto. Vuelve a elegirlo."
    if not raw:
        return None, "El adjunto está vacío. Vuelve a elegirlo."
    if len(raw) > MAX_MEDIA_BYTES:
        return None, (
            f"El adjunto pesa {megabytes(len(raw))} MB y el máximo es "
            f"{MAX_MEDIA_BYTES // (1024 * 1024)} MB. Elige uno más liviano."
        )
    mime = _real_mime(raw, kind)
    if mime is None:
        return None, f"El archivo no es {_KIND_TEXT[kind]} válido."
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}", None


def decode_media(value):
    """Los bytes y el tipo de un adjunto guardado como «data:image/jpeg;base64,…».

    Devuelve None si no es una imagen, un video, un audio o un PDF, o si no se puede leer: la web no
    muestra nada que no sea de esos tipos ni sigue enlaces a otros sitios.
    """
    if not isinstance(value, str):
        return None
    header, _, payload = value.partition(",")
    header = header.strip().lower()
    if not header.startswith("data:") or not header.endswith(";base64"):
        return None
    mime = header[len("data:"):-len(";base64")].split(";")[0].strip()
    is_document = mime == PDF_MIME
    if not is_document and (MEDIA_MIME.fullmatch(mime) is None or "xml" in mime or "html" in mime):
        return None
    try:
        raw = base64.b64decode("".join(payload.split()), validate=True)
    except (binascii.Error, ValueError):
        return None
    if not raw or (is_document and not is_pdf(raw)):
        return None
    return raw, mime
