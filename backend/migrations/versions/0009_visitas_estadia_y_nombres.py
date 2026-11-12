"""Visitas: estadía prevista y nombres de los visitantes del QR (HU-031 y HU-033, RN-012).

Agrega:

* visits.expected_stay_minutes: la estadía que el guardia anota al registrar la
  visita; si pasa sin salida, el residente recibe «¿Tu visitante sigue en la unidad?».
* visits.overstay_alerted_at: cuándo se le avisó, para no avisar dos veces.
* ix_visits_pending_overstay: índice parcial solo con las visitas que están dentro
  y tienen una estadía por vigilar, que son las que busca la alerta.
* visit_qr_passes.visitor_names: los nombres que el residente escribió al crear el QR.

Revision ID: 0009_visitas
Revises: 0008_vehiculos
Create Date: 2026-11-10 21:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0009_visitas'
down_revision = '0008_vehiculos'
branch_labels = None
depends_on = None

PENDING_OVERSTAY = sa.text(
    'exited_at IS NULL AND expected_stay_minutes IS NOT NULL AND overstay_alerted_at IS NULL'
)


def _columns(table):
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table):
    return {index['name'] for index in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade():
    # Una columna que ya existe (por una base creada con db.create_all) no se repite.
    visit_columns = _columns('visits')
    if 'expected_stay_minutes' not in visit_columns:
        op.add_column('visits', sa.Column('expected_stay_minutes', sa.Integer(), nullable=True))
    if 'overstay_alerted_at' not in visit_columns:
        op.add_column('visits', sa.Column('overstay_alerted_at', sa.DateTime(), nullable=True))
    if 'visitor_names' not in _columns('visit_qr_passes'):
        op.add_column('visit_qr_passes', sa.Column('visitor_names', sa.Text(), nullable=True))
    if 'ix_visits_pending_overstay' not in _indexes('visits'):
        op.create_index(
            'ix_visits_pending_overstay', 'visits', ['entered_at'],
            sqlite_where=PENDING_OVERSTAY, postgresql_where=PENDING_OVERSTAY,
        )


def downgrade():
    if 'ix_visits_pending_overstay' in _indexes('visits'):
        op.drop_index('ix_visits_pending_overstay', table_name='visits')
    visit_columns = _columns('visits')
    with op.batch_alter_table('visits') as batch_op:
        if 'overstay_alerted_at' in visit_columns:
            batch_op.drop_column('overstay_alerted_at')
        if 'expected_stay_minutes' in visit_columns:
            batch_op.drop_column('expected_stay_minutes')
    if 'visitor_names' in _columns('visit_qr_passes'):
        with op.batch_alter_table('visit_qr_passes') as batch_op:
            batch_op.drop_column('visitor_names')
