"""Archivo histórico mensual y cierre de sesiones viejas (ADR-013, DEC-090 y DEC-103).

* history_archives: cada archivo JSON comprimido con los registros de un tipo y de un mes que ya
  cumplieron su plazo en la base, con su huella SHA-256.
* users.token_version: sube cuando hay que cerrar las sesiones abiertas de una persona (entrega el
  turno de portería o le restablecen la contraseña); un token con un número viejo deja de servir.
  Las sesiones que ya están abiertas siguen valiendo: todas empiezan en 0.

Revision ID: 0017_archivo_y_sesiones
Revises: 0016_documento_visitante
Create Date: 2026-11-15 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0017_archivo_y_sesiones'
down_revision = '0016_documento_visitante'
branch_labels = None
depends_on = None


def upgrade():
    # Lo que ya existe (por una base creada con db.create_all) no se repite.
    inspector = sa.inspect(op.get_bind())
    if 'token_version' not in {column['name'] for column in inspector.get_columns('users')}:
        op.add_column('users', sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'))
    if 'history_archives' not in inspector.get_table_names():
        op.create_table(
            'history_archives',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('kind', sa.String(length=30), nullable=False),
            sa.Column('period', sa.String(length=7), nullable=False),
            sa.Column('record_count', sa.Integer(), nullable=False),
            sa.Column('size_bytes', sa.Integer(), nullable=False),
            sa.Column('sha256', sa.String(length=64), nullable=False),
            sa.Column('content', sa.LargeBinary(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('restored_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_history_archives_kind', 'history_archives', ['kind'])


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if 'history_archives' in inspector.get_table_names():
        op.drop_index('ix_history_archives_kind', table_name='history_archives')
        op.drop_table('history_archives')
    if 'token_version' in {column['name'] for column in inspector.get_columns('users')}:
        with op.batch_alter_table('users') as batch_op:
            batch_op.drop_column('token_version')
