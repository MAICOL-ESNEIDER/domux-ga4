"""Reservas de varias franjas seguidas o del día completo (HU-055).

Agrega a common_areas dos reglas que la administración ajusta desde la web:

* max_consecutive_slots: cuántas franjas seguidas se pueden reservar de una vez (1 por defecto).
* allow_full_day: si la zona se puede reservar el día completo, por ejemplo el salón social
  (no por defecto).

Las zonas que ya existen quedan como estaban: una franja a la vez y sin día completo. Las reservas
no cambian: siguen guardando su horario como un rango «HH:MM-HH:MM», que ahora puede cubrir varias
franjas.

Revision ID: 0015_varias_franjas
Revises: 0014_datos_unidad
Create Date: 2026-11-12 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0015_varias_franjas'
down_revision = '0014_datos_unidad'
branch_labels = None
depends_on = None


def _columns(table):
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    # Una columna que ya existe (por una base creada con db.create_all) no se repite.
    existing = _columns('common_areas')
    if 'max_consecutive_slots' not in existing:
        op.add_column('common_areas', sa.Column(
            'max_consecutive_slots', sa.Integer(), nullable=False, server_default='1'
        ))
    if 'allow_full_day' not in existing:
        op.add_column('common_areas', sa.Column(
            'allow_full_day', sa.Boolean(), nullable=False, server_default=sa.false()
        ))


def downgrade():
    existing = _columns('common_areas')
    with op.batch_alter_table('common_areas') as batch_op:
        if 'allow_full_day' in existing:
            batch_op.drop_column('allow_full_day')
        if 'max_consecutive_slots' in existing:
            batch_op.drop_column('max_consecutive_slots')
