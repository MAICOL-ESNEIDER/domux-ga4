"""Configuración del servidor que depende del entorno donde corre.

Aquí se decide si el servidor está en producción y qué páginas web externas pueden
llamar a la API. Así ningún secreto ni permiso queda escrito en el código (TT-010).
"""

import os

#: Largo mínimo recomendado para la clave que firma los tokens (32 caracteres).
MIN_JWT_SECRET_LENGTH = 32

#: Días que un vehículo visitante puede quedarse en el parqueadero de visitantes (RN-015).
DEFAULT_VISITOR_PARKING_MAX_DAYS = 3


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


def visitor_parking_max_days() -> int:
    """Días máximos que un vehículo visitante puede quedarse en la unidad (RN-015).

    Son 3 días, pero cada conjunto puede cambiarlo con la variable de entorno
    ``VISITOR_PARKING_MAX_DAYS`` sin tocar el código (RN-022). Si el valor no es
    un número entero positivo se ignora y se usa el de 3 días.
    """
    try:
        days = int(os.environ.get("VISITOR_PARKING_MAX_DAYS", ""))
    except ValueError:
        return DEFAULT_VISITOR_PARKING_MAX_DAYS
    return days if days > 0 else DEFAULT_VISITOR_PARKING_MAX_DAYS
