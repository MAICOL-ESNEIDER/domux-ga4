"""Descarga de la app desde el propio servidor de DOMUX (dirección corta: /descargar).

El QR del póster apuntaba al enlace de GitHub. GitHub responde con un salto a otro dominio y manda el
archivo como «octet-stream» (tipo desconocido); el navegador que abre el lector de QR del celular a veces
corta esa descarga y Android dice «el paquete no es válido». Aquí el servidor trae la última APK
publicada y la entrega él mismo, con el tipo de una app Android y su tamaño, que es lo que el celular
espera. La guarda unos minutos para no pedirla a GitHub en cada descarga.
"""

import logging
import os
import tempfile
import threading
import time

import requests

logger = logging.getLogger(__name__)

#: La APK firmada que GitHub publica con cada cambio en la rama de la versión reducida.
APK_SOURCE_URL = "https://github.com/MAICOL-ESNEIDER/domux-ga4/releases/download/ultima/domux.apk"
#: Cada cuánto se vuelve a traer de GitHub (así una APK nueva llega en máximo 10 minutos).
CACHE_SECONDS = 10 * 60
#: Una APK de DOMUX pesa unos 12 MB; algo mucho más chico no es una APK completa.
MIN_APK_BYTES = 1_000_000
APK_MIME = "application/vnd.android.package-archive"

_lock = threading.Lock()
_cache_path = os.path.join(tempfile.gettempdir(), "domux-descarga.apk")


def _fresh(path):
    return os.path.isfile(path) and time.time() - os.path.getmtime(path) < CACHE_SECONDS


def cached_apk(fetch=None):
    """La ruta de la APK guardada, trayéndola de GitHub si no está o ya pasó el tiempo.

    Si GitHub no responde, se sigue entregando la copia anterior (si hay). Devuelve None si no hay ninguna.
    """
    with _lock:
        if _fresh(_cache_path):
            return _cache_path
        try:
            data = (fetch or _download)()
            if len(data) < MIN_APK_BYTES or not data.startswith(b"PK"):
                raise ValueError(f"lo que llegó no parece una APK ({len(data)} bytes)")
            temp = _cache_path + ".tmp"
            with open(temp, "wb") as handle:
                handle.write(data)
            os.replace(temp, _cache_path)
        except Exception:  # noqa: BLE001  (sin GitHub se entrega la copia anterior)
            logger.exception("No se pudo traer la APK de GitHub")
        return _cache_path if os.path.isfile(_cache_path) else None


def _download():
    response = requests.get(APK_SOURCE_URL, timeout=60, allow_redirects=True)
    response.raise_for_status()
    return response.content
