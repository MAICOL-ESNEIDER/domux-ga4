"""Lectura de los adjuntos guardados como «data:image/jpeg;base64,…» (fotos, videos y audios).

La app manda los adjuntos de las PQRS, las reservas y los comunicados dentro del mismo texto que
guarda la base. La web de administración no los lleva dentro de la página: cada uno se pide aparte y
pasa por aquí, que solo deja mostrar lo que la app acepta (imagen, video y audio).

Ninguna función de este archivo guarda en la base.
"""

import base64
import binascii
import re

#: Tipos de archivo que la web muestra. Son los tres que acepta la app (imagen, video y audio); un
#: SVG o cualquier tipo con XML o HTML se descarta porque puede llevar scripts.
MEDIA_MIME = re.compile(r"(?:image|video|audio)/[a-z0-9][a-z0-9.+-]*")


def decode_media(value):
    """Los bytes y el tipo de un adjunto guardado como «data:image/jpeg;base64,…».

    Devuelve None si no es una imagen, un video o un audio, o si no se puede leer: la web no muestra
    nada que no sea de esos tres tipos ni sigue enlaces a otros sitios.
    """
    if not isinstance(value, str):
        return None
    header, _, payload = value.partition(",")
    header = header.strip().lower()
    if not header.startswith("data:") or not header.endswith(";base64"):
        return None
    mime = header[len("data:"):-len(";base64")].split(";")[0].strip()
    if MEDIA_MIME.fullmatch(mime) is None or "xml" in mime or "html" in mime:
        return None
    try:
        raw = base64.b64decode("".join(payload.split()), validate=True)
    except (binascii.Error, ValueError):
        return None
    return (raw, mime) if raw else None
