"""Datos de la unidad: nombre, NIT, dirección, teléfono de portería y logo (HU-077).

Crea complex_profile, con una sola fila (la de la unidad). La fila no se crea aquí: nace la
primera vez que la administración guarda los datos, y mientras no exista la app y la web usan
sus textos por defecto.

Revision ID: 0014_datos_unidad
Revises: 0013_radicado_pqrs
Create Date: 2026-11-12 05:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0014_datos_unidad'
down_revision = '0013_radicado_pqrs'
branch_labels = None
depends_on = None


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    # Una tabla que ya existe (por una base creada con db.create_all) no se repite.
    if 'complex_profile' not in _tables():
        op.create_table(
            'complex_profile',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=120), nullable=False),
            sa.Column('nit', sa.String(length=25), nullable=True),
            sa.Column('address', sa.String(length=200), nullable=True),
            sa.Column('portal_phone', sa.String(length=25), nullable=True),
            sa.Column('logo', sa.LargeBinary(), nullable=True),
            sa.Column('logo_type', sa.String(length=20), nullable=True),
            sa.Column('logo_sha256', sa.String(length=64), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('updated_by_id', sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(
                ['updated_by_id'], ['users.id'], name='fk_complex_profile_updated_by_id_users'
            ),
        )


def downgrade():
    if 'complex_profile' in _tables():
        op.drop_table('complex_profile')
