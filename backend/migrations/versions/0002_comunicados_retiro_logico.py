"""Retiro lógico de comunicados (TT-029, DEF-005, ADR-013).

Agrega a announcements la fecha del retiro (retired_at) y quién lo hizo
(retired_by_id). Desde aquí, retirar un comunicado lo oculta en la app, pero
la fila se queda en la base (DEC-090).

Revision ID: 0002_comunicados
Revises: 0001_base
Create Date: 2026-11-10 11:05:57.817216

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0002_comunicados'
down_revision = '0001_base'
branch_labels = None
depends_on = None

FOREIGN_KEY = 'fk_announcements_retired_by_id_users'


def _columns(table):
    """Nombres de las columnas que ya tiene la tabla en la base."""
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    # Una base vieja a la que db.create_all le creó la tabla al arrancar ya trae
    # las columnas nuevas: en ese caso no hay nada que agregar.
    if 'retired_at' in _columns('announcements'):
        return
    with op.batch_alter_table('announcements', schema=None) as batch_op:
        batch_op.add_column(sa.Column('retired_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('retired_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(FOREIGN_KEY, 'users', ['retired_by_id'], ['id'])


def downgrade():
    with op.batch_alter_table('announcements', schema=None) as batch_op:
        batch_op.drop_constraint(FOREIGN_KEY, type_='foreignkey')
        batch_op.drop_column('retired_by_id')
        batch_op.drop_column('retired_at')
