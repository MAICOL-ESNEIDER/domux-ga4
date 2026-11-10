"""Alertas que el servidor calcula al consultar, sin un proceso aparte (RN-012 y RN-015).

Render no tiene aquí un programador de tareas que corra cada cierto tiempo, así
que las alertas se revisan cuando alguien abre las notificaciones o la vista de
portería. Cada alerta se marca en su fila al avisarla (una sola instrucción UPDATE
que pregunta y marca a la vez), de modo que nunca se avisa dos veces aunque dos
personas consulten a la vez.

Más adelante, si hay un programador, basta con llamar a run_alerts() desde él.
"""

from datetime import timedelta

from sqlalchemy import update

from config import visitor_parking_max_days
from extensions import db
from models import User, VisitorVehicleEntry
from services.notification_service import notify_user
from time_utils import utc_now


def _claim(model, row_id, column, moment):
    """Marca la alerta de una fila como avisada solo si nadie la había marcado.

    Devuelve True si esta llamada fue la que la marcó, y entonces debe avisar.
    """
    result = db.session.execute(
        update(model)
        .where(model.id == row_id, column.is_(None))
        .values({column.key: moment})
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def _days_text(days):
    return f"{days} día" if days == 1 else f"{days} días"


def alert_overdue_vehicles(now=None):
    """Avisa a los guardias de los vehículos visitantes que pasaron el tiempo máximo (RN-015, HU-041).

    Son 3 días, o el plazo que fije la unidad. Devuelve cuántos vehículos avisó.
    No hace commit: lo hace run_alerts.
    """
    now = now or utc_now()
    max_days = visitor_parking_max_days()
    pending = VisitorVehicleEntry.query.filter(
        VisitorVehicleEntry.exited_at.is_(None),
        VisitorVehicleEntry.overdue_alerted_at.is_(None),
        VisitorVehicleEntry.entered_at <= now - timedelta(days=max_days),
    ).all()
    if not pending:
        return 0
    guards = User.query.filter_by(role="GUARD", is_active=True).all()
    if not guards:
        return 0
    sent = 0
    for entry in pending:
        if not _claim(VisitorVehicleEntry, entry.id, VisitorVehicleEntry.overdue_alerted_at, now):
            continue
        days = entry.parked_minutes(now) // (24 * 60)
        spot = f" en el parqueadero {entry.spot.code}" if entry.spot else ""
        apartment = entry.apartment.label if entry.apartment else "un apartamento sin identificar"
        for guard in guards:
            notify_user(
                guard.id,
                "Vehículo visitante pasó el tiempo máximo",
                f"El vehículo {entry.plate}, que visita {apartment}, lleva {_days_text(days)}"
                f"{spot}. El máximo es {_days_text(max_days)}.",
                "vehicle",
            )
        sent += 1
    return sent


def run_alerts(now=None):
    """Revisa todas las alertas pendientes y guarda los avisos; devuelve cuántos generó."""
    now = now or utc_now()
    total = alert_overdue_vehicles(now)
    if total:
        db.session.commit()
    return total
