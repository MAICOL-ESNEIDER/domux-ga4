"""Salud de las mascotas y fin del plan funerario (HU-021, DEF-013, DT-017).

pets suma si la vacunación y la desparasitación están al día y la fecha de la
última de cada una (RN-028). residential_units deja de guardar el plan
funerario, que DEC-015 decidió no pedir: son datos personales que la unidad no
necesita, y en el servidor de pruebas solo había datos de ejemplo.

Revision ID: 0004_mascotas
Revises: 0003_ficha_hogar
Create Date: 2026-11-10 12:52:41.218904

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0004_mascotas'
down_revision = '0003_ficha_hogar'
branch_labels = None
depends_on = None


def _columns(table):
    """Nombres de las columnas que ya tiene la tabla en la base."""
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    # Si db.create_all ya creó la tabla con la estructura nueva, no se repite.
    if 'vaccines_up_to_date' not in _columns('pets'):
        with op.batch_alter_table('pets', schema=None) as batch_op:
            batch_op.add_column(sa.Column(
                'vaccines_up_to_date', sa.Boolean(), server_default=sa.false(), nullable=False
            ))
            batch_op.add_column(sa.Column('last_vaccination_date', sa.String(length=10), nullable=True))
            batch_op.add_column(sa.Column(
                'deworming_up_to_date', sa.Boolean(), server_default=sa.false(), nullable=False
            ))
            batch_op.add_column(sa.Column('last_deworming_date', sa.String(length=10), nullable=True))

    if 'funeral_plan' in _columns('residential_units'):
        with op.batch_alter_table('residential_units', schema=None) as batch_op:
            batch_op.drop_column('funeral_provider')
            batch_op.drop_column('funeral_plan')


def downgrade():
    # Las columnas vuelven vacías: el plan funerario no se guardó en ningún otro lado.
    with op.batch_alter_table('residential_units', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'funeral_plan', sa.Boolean(), server_default=sa.false(), nullable=False
        ))
        batch_op.add_column(sa.Column('funeral_provider', sa.String(length=120), nullable=True))

    with op.batch_alter_table('pets', schema=None) as batch_op:
        batch_op.drop_column('last_deworming_date')
        batch_op.drop_column('deworming_up_to_date')
        batch_op.drop_column('last_vaccination_date')
        batch_op.drop_column('vaccines_up_to_date')
