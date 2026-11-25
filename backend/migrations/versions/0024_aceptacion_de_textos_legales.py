"""Aceptación de los textos legales (pantalla «Acepto»).

Agrega a users dos columnas: cuándo la persona aceptó los textos legales y cuál versión leyó. Quien ya tenía
cuenta queda sin aceptar y la verá al entrar la próxima vez: así cada persona deja su propia constancia, no
solo la del administrador que la creó.

Revision ID: 0024_aceptacion_de_textos_legales
Revises: 0023_documentos_de_la_unidad
Create Date: 2026-11-25 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0024_aceptacion_de_textos_legales'
down_revision = '0023_documentos_de_la_unidad'
branch_labels = None
depends_on = None


def _columns():
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns('users')}


def upgrade():
    # Una columna que ya existe (por una base creada con db.create_all) no se repite.
    existing = _columns()
    if 'legal_accepted_at' not in existing:
        op.add_column('users', sa.Column('legal_accepted_at', sa.DateTime(), nullable=True))
    if 'legal_accepted_version' not in existing:
        op.add_column('users', sa.Column('legal_accepted_version', sa.String(length=200), nullable=True))


def downgrade():
    existing = _columns()
    with op.batch_alter_table('users') as batch:
        if 'legal_accepted_version' in existing:
            batch.drop_column('legal_accepted_version')
        if 'legal_accepted_at' in existing:
            batch.drop_column('legal_accepted_at')
