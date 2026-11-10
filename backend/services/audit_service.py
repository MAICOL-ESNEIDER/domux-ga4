"""Registro de auditoría (TT-013): quién hizo qué y cuándo.

Las acciones importantes (retirar, aprobar, cambiar datos de otra persona) se
anotan en audit_logs dentro de la misma transacción que el cambio: si el cambio
no se guarda, la anotación tampoco.
"""

import json

from flask import g

from extensions import db
from models import AuditLog


def add_audit_log(entity_type, entity_id, action, details=None, actor=None):
    """Anota una acción en el registro; queda guardada con el próximo commit.

    Por defecto el autor es el usuario de la sesión (g.current_user). Los
    detalles se guardan como JSON con tildes legibles.
    """
    actor = actor or g.current_user
    db.session.add(AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=actor.id,
        actor_role=actor.role,
        details=json.dumps(details, ensure_ascii=False) if details is not None else None,
    ))
