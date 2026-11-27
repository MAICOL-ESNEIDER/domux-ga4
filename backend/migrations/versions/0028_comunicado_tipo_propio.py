"""Comunicados de tipo «Otra» con un nombre que escribe la administración.

Agrega announcements.category_label: el nombre del tipo cuando la categoría es «otra» (por ejemplo
«Cumpleaños», «Mascotas» o «Novedades»).

Revision ID: 0028_comunicado_tipo_propio
Revises: 0027_motos_en_parqueadero
Create Date: 2026-11-27 03:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '0028_comunicado_tipo_propio'
down_revision = '0027_motos_en_parqueadero'
branch_labels = None
depends_on = None


def _columns():
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns('announcements')}


def _user_columns():
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns('users')}


def upgrade():
    if 'category_label' not in _columns():
        with op.batch_alter_table('announcements') as batch:
            batch.add_column(sa.Column('category_label', sa.String(length=40), nullable=True))
    if 'contact_unverified' not in _user_columns():
        with op.batch_alter_table('users') as batch:
            batch.add_column(sa.Column('contact_unverified', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    if 'category_label' in _columns():
        with op.batch_alter_table('announcements') as batch:
            batch.drop_column('category_label')
    if 'contact_unverified' in _user_columns():
        with op.batch_alter_table('users') as batch:
            batch.drop_column('contact_unverified')
