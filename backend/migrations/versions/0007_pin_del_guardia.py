"""PIN del guardia para cambiar de turno en la tablet (HU-010, RF-010 y RN-029).

Agrega users.pin_hash: el PIN de 4 dígitos de cada guardia, guardado con hash
(como la contraseña) y vacío mientras el administrador no se lo asigne.

Revision ID: 0007_pin
Revises: 0006_estructura
Create Date: 2026-11-10 18:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0007_pin'
down_revision = '0006_estructura'
branch_labels = None
depends_on = None


def _columns(bind):
    return {column['name'] for column in sa.inspect(bind).get_columns('users')}


def upgrade():
    # Una base vieja a la que db.create_all ya le creó la columna no necesita nada más.
    if 'pin_hash' in _columns(op.get_bind()):
        return
    op.add_column('users', sa.Column('pin_hash', sa.String(length=255), nullable=True))


def downgrade():
    if 'pin_hash' not in _columns(op.get_bind()):
        return
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('pin_hash')
