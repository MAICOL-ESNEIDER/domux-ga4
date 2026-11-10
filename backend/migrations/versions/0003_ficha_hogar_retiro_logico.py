"""Retiro lógico en la ficha del hogar (TT-032, DEF-007, ADR-013).

Agrega retired_at y retired_by_id a household_members, pets y vehicles: al
guardar la ficha, lo que se quita queda retirado en lugar de borrarse
(DEC-090). La placa deja de ser única en toda la tabla y pasa a ser única solo
entre los vehículos vigentes (IDX-013), para que una placa retirada pueda
volver a registrarse.

Revision ID: 0003_ficha_hogar
Revises: 0002_comunicados
Create Date: 2026-11-10 12:08:29.471369

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0003_ficha_hogar'
down_revision = '0002_comunicados'
branch_labels = None
depends_on = None

TABLES = ('household_members', 'pets', 'vehicles')
ACTIVE_PLATE_INDEX = 'uq_vehicles_active_plate'
ONLY_ACTIVE = sa.text('retired_at IS NULL')


def _columns(table):
    """Nombres de las columnas que ya tiene la tabla en la base."""
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    for table in TABLES:
        # Una tabla que db.create_all creó al arrancar una base vieja ya viene
        # con las columnas y los índices nuevos: no hay nada que agregar.
        if 'retired_at' in _columns(table):
            continue
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('retired_at', sa.DateTime(), nullable=True))
            batch_op.add_column(sa.Column('retired_by_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                f'fk_{table}_retired_by_id_users', 'users', ['retired_by_id'], ['id']
            )
            if table == 'vehicles':
                batch_op.drop_index('ix_vehicles_plate')
                batch_op.create_index('ix_vehicles_plate', ['plate'], unique=False)
                batch_op.create_index(
                    ACTIVE_PLATE_INDEX, ['plate'], unique=True,
                    sqlite_where=ONLY_ACTIVE, postgresql_where=ONLY_ACTIVE,
                )


def downgrade():
    # Volver atrás solo funciona si ninguna placa se repite entre vigentes y
    # retirados, porque la placa vuelve a ser única en toda la tabla.
    for table in reversed(TABLES):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(f'fk_{table}_retired_by_id_users', type_='foreignkey')
            if table == 'vehicles':
                batch_op.drop_index(
                    ACTIVE_PLATE_INDEX, sqlite_where=ONLY_ACTIVE, postgresql_where=ONLY_ACTIVE
                )
                batch_op.drop_index('ix_vehicles_plate')
                batch_op.create_index('ix_vehicles_plate', ['plate'], unique=True)
            batch_op.drop_column('retired_by_id')
            batch_op.drop_column('retired_at')
