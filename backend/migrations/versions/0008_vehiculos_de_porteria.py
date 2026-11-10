"""Portería vehicular: vehículos visitantes y movimientos de residentes (HU-035 a HU-041, DAT-05 y DAT-07).

Crea dos tablas:

* visitor_vehicle_entries: cada entrada de un vehículo visitante, con la visita
  que la autorizó, su parqueadero y las horas de entrada y salida. Dos índices
  únicos parciales impiden que una placa tenga dos entradas abiertas y que un
  parqueadero tenga dos vehículos adentro (RN-013).
* vehicle_movements: las entradas y salidas de los vehículos de residentes que
  registra el guardia con un toque.

Revision ID: 0008_vehiculos
Revises: 0007_pin
Create Date: 2026-11-10 20:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0008_vehiculos'
down_revision = '0007_pin'
branch_labels = None
depends_on = None

STILL_INSIDE = sa.text('exited_at IS NULL')


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    # Una tabla que db.create_all ya creó al arrancar no se repite.
    existing = _tables()
    if 'visitor_vehicle_entries' not in existing:
        op.create_table(
            'visitor_vehicle_entries',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('plate', sa.String(length=10), nullable=False),
            sa.Column('visit_id', sa.Integer(), nullable=False),
            sa.Column('apartment_id', sa.Integer(), nullable=True),
            sa.Column('spot_id', sa.Integer(), nullable=True),
            sa.Column('entered_at', sa.DateTime(), nullable=False),
            sa.Column('exited_at', sa.DateTime(), nullable=True),
            sa.Column('registered_by', sa.Integer(), nullable=False),
            sa.Column('exited_by_id', sa.Integer(), nullable=True),
            sa.Column('overdue_alerted_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(
                ['visit_id'], ['visits.id'], name='fk_visitor_vehicle_entries_visit_id_visits'
            ),
            sa.ForeignKeyConstraint(
                ['apartment_id'], ['apartments.id'],
                name='fk_visitor_vehicle_entries_apartment_id_apartments',
            ),
            sa.ForeignKeyConstraint(
                ['spot_id'], ['parking_spots.id'],
                name='fk_visitor_vehicle_entries_spot_id_parking_spots',
            ),
            sa.ForeignKeyConstraint(
                ['registered_by'], ['users.id'], name='fk_visitor_vehicle_entries_registered_by_users'
            ),
            sa.ForeignKeyConstraint(
                ['exited_by_id'], ['users.id'], name='fk_visitor_vehicle_entries_exited_by_id_users'
            ),
        )
        op.create_index('ix_visitor_vehicle_entries_plate', 'visitor_vehicle_entries', ['plate'])
        op.create_index('ix_visitor_vehicle_entries_visit_id', 'visitor_vehicle_entries', ['visit_id'])
        op.create_index(
            'ix_visitor_vehicle_entries_apartment_id', 'visitor_vehicle_entries', ['apartment_id']
        )
        op.create_index('ix_visitor_vehicle_entries_entered_at', 'visitor_vehicle_entries', ['entered_at'])
        op.create_index(
            'uq_visitor_vehicle_entries_open_plate', 'visitor_vehicle_entries', ['plate'],
            unique=True, sqlite_where=STILL_INSIDE, postgresql_where=STILL_INSIDE,
        )
        op.create_index(
            'uq_visitor_vehicle_entries_open_spot', 'visitor_vehicle_entries', ['spot_id'],
            unique=True, sqlite_where=STILL_INSIDE, postgresql_where=STILL_INSIDE,
        )
    if 'vehicle_movements' not in existing:
        op.create_table(
            'vehicle_movements',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('vehicle_id', sa.Integer(), nullable=False),
            sa.Column('plate', sa.String(length=10), nullable=False),
            sa.Column('movement_type', sa.String(length=10), nullable=False),
            sa.Column('registered_by', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(
                ['vehicle_id'], ['vehicles.id'], name='fk_vehicle_movements_vehicle_id_vehicles'
            ),
            sa.ForeignKeyConstraint(
                ['registered_by'], ['users.id'], name='fk_vehicle_movements_registered_by_users'
            ),
        )
        op.create_index('ix_vehicle_movements_created_at', 'vehicle_movements', ['created_at'])
        op.create_index('ix_vehicle_movements_vehicle_id_id', 'vehicle_movements', ['vehicle_id', 'id'])


def downgrade():
    existing = _tables()
    if 'vehicle_movements' in existing:
        op.drop_table('vehicle_movements')
    if 'visitor_vehicle_entries' in existing:
        op.drop_table('visitor_vehicle_entries')
