"""Alertas que el servidor calcula al consultar, sin un proceso aparte (RN-012, RN-015 y RN-018).

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
from models import User, Visit, VisitorVehicleEntry
from services.notification_service import notify_user
from time_utils import to_colombia, utc_now


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


def _stay_text(minutes):
    """Una duración en minutos como «45 minutos», «2 horas» o «1 hora y 30 minutos»."""
    hours, rest = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hora" if hours == 1 else f"{hours} horas")
    if rest:
        parts.append(f"{rest} minuto" if rest == 1 else f"{rest} minutos")
    return " y ".join(parts)


def alert_overstays(now=None):
    """Le pregunta al residente si su visitante sigue en la unidad cuando pasa la estadía prevista (RN-012, HU-031).

    Solo mira las visitas que están dentro y tienen una estadía anotada. Devuelve
    cuántas avisó. No hace commit: lo hace run_alerts.
    """
    now = now or utc_now()
    candidates = Visit.query.filter(
        Visit.entered_at.isnot(None),
        Visit.exited_at.is_(None),
        Visit.expected_stay_minutes.isnot(None),
        Visit.overstay_alerted_at.is_(None),
    ).all()
    sent = 0
    for visit in candidates:
        if not visit.is_overstay(now) or not visit.resident.is_active:
            continue
        if not _claim(Visit, visit.id, Visit.overstay_alerted_at, now):
            continue
        notify_user(
            visit.resident_id,
            "¿Tu visitante sigue en la unidad?",
            f"{visit.visitor_name} entró a las {to_colombia(visit.entered_at).strftime('%H:%M')} "
            f"y su estadía prevista de {_stay_text(visit.expected_stay_minutes)} ya terminó. "
            "Si ya salió, avisa a portería para registrar su salida.",
            "visit",
        )
        sent += 1
    return sent


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
    total = alert_overdue_vehicles(now) + alert_overstays(now)
    if total:
        db.session.commit()
    return total
