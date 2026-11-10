"""Configuración del servidor que depende del entorno donde corre.

Aquí se decide si el servidor está en producción y qué páginas web externas pueden
llamar a la API. Así ningún secreto ni permiso queda escrito en el código (TT-010).
"""

import os

#: Largo mínimo recomendado para la clave que firma los tokens (32 caracteres).
MIN_JWT_SECRET_LENGTH = 32


def is_production() -> bool:
    """Dice si el servidor corre en producción.

    Render define sola la variable ``RENDER=true`` en sus servicios. En cualquier
    otro servidor se indica con ``APP_ENV=production``.
    """
    return (
        os.environ.get("RENDER", "").lower() == "true"
        or os.environ.get("APP_ENV", "").lower() == "production"
    )


def cors_origins() -> list[str]:
    """Devuelve las páginas web de otro dominio que pueden llamar a la API.

    Se leen de ``CORS_ORIGINS``, separadas por comas. Si la variable no existe,
    ninguna página externa puede hacerlo desde un navegador: la app Android no lo
    necesita y la web de administración la sirve este mismo servidor (RNF-005).
    """
    raw = os.environ.get("CORS_ORIGINS", "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]
