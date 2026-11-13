"""Documento del visitante en portería: anotar cuando la persona no lo quiso dar.

Agrega a visits la columna document_refused. El guardia siempre pide el documento al registrar una
visita; si la persona no lo quiere dar, la visita queda con document_refused en verdadero en lugar
de quedar sin nada. Las visitas que ya existen quedan en falso.

Revision ID: 0016_documento_visitante
Revises: 0015_varias_franjas
Create Date: 2026-11-13 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0016_documento_visitante'
down_revision = '0015_varias_franjas'
branch_labels = None
depends_on = None


def _columns(table):
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    # Una columna que ya existe (por una base creada con db.create_all) no se repite.
    if 'document_refused' not in _columns('visits'):
        op.add_column('visits', sa.Column(
            'document_refused', sa.Boolean(), nullable=False, server_default=sa.false()
        ))


def downgrade():
    if 'document_refused' in _columns('visits'):
        with op.batch_alter_table('visits') as batch_op:
            batch_op.drop_column('document_refused')
