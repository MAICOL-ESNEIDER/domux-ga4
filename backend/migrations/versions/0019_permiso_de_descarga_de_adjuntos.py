"""Permiso de descarga de los archivos adjuntos.

Quien sube un archivo (en un comunicado, una PQRS o un mensaje de PQRS o de reserva) decide si los
demás lo pueden descargar. Los archivos que ya existen quedan sin permiso: solo se ven.

Revision ID: 0019_descarga_de_adjuntos
Revises: 0018_cambio_de_contrasena
Create Date: 2026-11-15 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0019_descarga_de_adjuntos'
down_revision = '0018_cambio_de_contrasena'
branch_labels = None
depends_on = None

TABLES = ('announcements', 'pqrs', 'pqrs_messages', 'reservation_messages')


def upgrade():
    # Si la columna ya existe (por una base creada con db.create_all) no se repite.
    inspector = sa.inspect(op.get_bind())
    for table in TABLES:
        if 'media_downloadable' not in {column['name'] for column in inspector.get_columns(table)}:
            op.add_column(
                table,
                sa.Column('media_downloadable', sa.Boolean(), nullable=False, server_default=sa.false()),
            )


def downgrade():
    inspector = sa.inspect(op.get_bind())
    for table in TABLES:
        if 'media_downloadable' in {column['name'] for column in inspector.get_columns(table)}:
            with op.batch_alter_table(table) as batch_op:
                batch_op.drop_column('media_downloadable')
