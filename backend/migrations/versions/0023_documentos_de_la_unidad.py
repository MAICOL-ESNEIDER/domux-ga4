"""Documentos de la unidad (DEC-032).

Crea unit_documents, donde la administración guarda los documentos que quiere compartir con la unidad:
el manual de convivencia, las reglas, los presupuestos aprobados, los históricos de gastos, las actas...
Cada documento lleva marcado quién lo puede ver (propietarios, arrendatarios, otros residentes y portería).

El archivo (PDF o imagen de hasta 6 MB) se guarda en la misma base, revisado por sus primeros bytes al
subirlo. Nada se borra: un documento retirado deja de verse para los demás pero queda guardado (ADR-013).

Revision ID: 0023_documentos_de_la_unidad
Revises: 0022_reglas_de_la_unidad
Create Date: 2026-11-17 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0023_documentos_de_la_unidad'
down_revision = '0022_reglas_de_la_unidad'
branch_labels = None
depends_on = None

TABLE = 'unit_documents'
INDEX = 'ix_unit_documents_retired_at_created_at'


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    # Una tabla que ya existe (por una base creada con db.create_all) no se repite.
    if TABLE in _tables():
        return
    op.create_table(
        TABLE,
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=150), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('category', sa.String(length=20), nullable=False),
        sa.Column('file_name', sa.String(length=160), nullable=False),
        sa.Column('mime_type', sa.String(length=30), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.Column('content_sha256', sa.String(length=64), nullable=False),
        sa.Column('for_owners', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('for_tenants', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('for_residents', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('for_guards', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('uploaded_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('retired_at', sa.DateTime(), nullable=True),
        sa.Column('retired_by_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['uploaded_by_id'], ['users.id'], name='fk_unit_documents_uploaded_by_id_users'
        ),
        sa.ForeignKeyConstraint(
            ['retired_by_id'], ['users.id'], name='fk_unit_documents_retired_by_id_users'
        ),
    )
    op.create_index(INDEX, TABLE, ['retired_at', 'created_at'], unique=False)


def downgrade():
    if TABLE in _tables():
        op.drop_index(INDEX, table_name=TABLE)
        op.drop_table(TABLE)
