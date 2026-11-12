"""Reglas de cada zona común: horario, aforo, anticipación y plazos (HU-055, RN-020 a RN-022).

Agrega a common_areas lo que la administración ajusta desde la web sin tocar el código:

* open_time, close_time y slot_minutes: el horario y la duración de cada franja.
* capacity: el aforo máximo de personas (vacío si todavía no se define).
* min_advance_days y max_advance_days: la anticipación mínima y máxima para reservar.
* cancel_deadline_days: hasta cuántos días antes de la fecha puede cancelar el residente.
* weekly_limit: las reservas por semana de cada residente en la zona (antes eran 2 en total).
* maintenance_weekday: el día de la semana de mantenimiento, si la zona tiene (RN-021).

Las zonas que ya existen quedan con las reglas por defecto: de 08:00 a 22:00 en franjas
de 2 horas, cancelación hasta 3 días antes y 2 reservas por semana. Agrega también
reservations.attendees, el número de personas de la reserva (se compara con el aforo).

Revision ID: 0011_reglas_zona
Revises: 0010_paquetes
Create Date: 2026-11-11 23:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0011_reglas_zona'
down_revision = '0010_paquetes'
branch_labels = None
depends_on = None

# (nombre, tipo, ¿admite vacío?, valor por defecto) de las columnas nuevas de common_areas.
ZONE_COLUMNS = (
    ('open_time', sa.String(length=5), False, '08:00'),
    ('close_time', sa.String(length=5), False, '22:00'),
    ('slot_minutes', sa.Integer(), False, '120'),
    ('capacity', sa.Integer(), True, None),
    ('min_advance_days', sa.Integer(), False, '0'),
    ('max_advance_days', sa.Integer(), False, '60'),
    ('cancel_deadline_days', sa.Integer(), False, '3'),
    ('weekly_limit', sa.Integer(), False, '2'),
    ('maintenance_weekday', sa.Integer(), True, None),
)


def _columns(table):
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    # Una columna que ya existe (por una base creada con db.create_all) no se repite.
    existing = _columns('common_areas')
    for name, column_type, nullable, default in ZONE_COLUMNS:
        if name not in existing:
            op.add_column('common_areas', sa.Column(
                name, column_type, nullable=nullable, server_default=default
            ))
    if 'attendees' not in _columns('reservations'):
        op.add_column('reservations', sa.Column('attendees', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('reservations') as batch_op:
        if 'attendees' in _columns('reservations'):
            batch_op.drop_column('attendees')
    existing = _columns('common_areas')
    with op.batch_alter_table('common_areas') as batch_op:
        for name, _, _, _ in reversed(ZONE_COLUMNS):
            if name in existing:
                batch_op.drop_column(name)
