"""Motos de visitantes en un parqueadero de carro compartido (regla «motos por cupo de carro», RN-022).

* visitor_vehicle_entries.vehicle_type: «carro» o «moto».
* visitor_vehicle_entries.shared_spot_id: el parqueadero marcado «para motos» donde quedó la moto. Va aparte
  de spot_id porque en ese parqueadero caben varias motos a la vez (spot_id sigue siendo de un solo vehículo).

Revision ID: 0027_motos_en_parqueadero
Revises: 0026_esperados_de_la_unidad
Create Date: 2026-11-27 02:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '0027_motos_en_parqueadero'
down_revision = '0026_esperados_de_la_unidad'
branch_labels = None
depends_on = None

TABLE = 'visitor_vehicle_entries'


def _columns():
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade():
    existing = _columns()
    with op.batch_alter_table(TABLE) as batch:
        if 'vehicle_type' not in existing:
            batch.add_column(sa.Column('vehicle_type', sa.String(length=10), nullable=False, server_default='carro'))
        if 'shared_spot_id' not in existing:
            batch.add_column(sa.Column('shared_spot_id', sa.Integer(), nullable=True))
            batch.create_foreign_key(
                'fk_visitor_vehicle_entries_shared_spot_id_parking_spots', 'parking_spots', ['shared_spot_id'], ['id']
            )
            batch.create_index('ix_visitor_vehicle_entries_shared_spot_id', ['shared_spot_id'])


def downgrade():
    existing = _columns()
    with op.batch_alter_table(TABLE) as batch:
        if 'shared_spot_id' in existing:
            batch.drop_index('ix_visitor_vehicle_entries_shared_spot_id')
            batch.drop_constraint('fk_visitor_vehicle_entries_shared_spot_id_parking_spots', type_='foreignkey')
            batch.drop_column('shared_spot_id')
        if 'vehicle_type' in existing:
            batch.drop_column('vehicle_type')
