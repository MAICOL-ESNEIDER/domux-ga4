"""Cambio obligatorio de contraseña después de un restablecimiento.

users.must_change_password queda en verdadero cuando el administrador le restablece la contraseña
a una persona: al entrar debe poner una propia antes de seguir. Las cuentas que ya existen quedan
en falso.

Revision ID: 0018_cambio_de_contrasena
Revises: 0017_archivo_y_sesiones
Create Date: 2026-11-15 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0018_cambio_de_contrasena'
down_revision = '0017_archivo_y_sesiones'
branch_labels = None
depends_on = None


def upgrade():
    # Si la columna ya existe (por una base creada con db.create_all) no se repite.
    inspector = sa.inspect(op.get_bind())
    if 'must_change_password' not in {column['name'] for column in inspector.get_columns('users')}:
        op.add_column(
            'users',
            sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if 'must_change_password' in {column['name'] for column in inspector.get_columns('users')}:
        with op.batch_alter_table('users') as batch_op:
            batch_op.drop_column('must_change_password')
