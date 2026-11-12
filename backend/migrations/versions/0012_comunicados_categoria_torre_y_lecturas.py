"""Comunicados: categoría, torre, vencimiento y lecturas (HU-058 a HU-062).

Agrega a announcements:

* category: una de las cinco categorías (RN-026). Los comunicados que ya existían se
  quedan sin categoría; los nuevos la exigen.
* tower_id: la torre a la que va el comunicado; vacío es para toda la unidad (HU-061).
* expires_at: la fecha de vencimiento; pasada, el comunicado pasa a «Archivados» (HU-060).

Crea announcement_reads: qué residente abrió cada comunicado, con su apartamento, para
mostrar los no leídos y contar cuántos apartamentos lo leyeron (HU-059 y HU-062). Cada
residente deja una sola lectura por comunicado.

Revision ID: 0012_comunicados_extra
Revises: 0011_reglas_zona
Create Date: 2026-11-11 23:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0012_comunicados_extra'
down_revision = '0011_reglas_zona'
branch_labels = None
depends_on = None

TOWER_FOREIGN_KEY = 'fk_announcements_tower_id_towers'


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table):
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    # Una columna o tabla que ya existe (por una base creada con db.create_all) no se repite.
    existing = _columns('announcements')
    if not {'category', 'tower_id', 'expires_at'} <= existing:
        with op.batch_alter_table('announcements') as batch_op:
            if 'category' not in existing:
                batch_op.add_column(sa.Column('category', sa.String(length=20), nullable=True))
            if 'tower_id' not in existing:
                batch_op.add_column(sa.Column('tower_id', sa.Integer(), nullable=True))
                batch_op.create_foreign_key(TOWER_FOREIGN_KEY, 'towers', ['tower_id'], ['id'])
                batch_op.create_index('ix_announcements_tower_id', ['tower_id'])
            if 'expires_at' not in existing:
                batch_op.add_column(sa.Column('expires_at', sa.Date(), nullable=True))
    if 'announcement_reads' not in _tables():
        op.create_table(
            'announcement_reads',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('announcement_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('apartment_id', sa.Integer(), nullable=True),
            sa.Column('read_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(
                ['announcement_id'], ['announcements.id'],
                name='fk_announcement_reads_announcement_id_announcements',
            ),
            sa.ForeignKeyConstraint(
                ['user_id'], ['users.id'], name='fk_announcement_reads_user_id_users'
            ),
            sa.ForeignKeyConstraint(
                ['apartment_id'], ['apartments.id'],
                name='fk_announcement_reads_apartment_id_apartments',
            ),
            sa.UniqueConstraint('announcement_id', 'user_id', name='uq_announcement_reads_user'),
        )
        op.create_index(
            'ix_announcement_reads_announcement_id', 'announcement_reads', ['announcement_id']
        )
        op.create_index('ix_announcement_reads_user_id', 'announcement_reads', ['user_id'])


def downgrade():
    if 'announcement_reads' in _tables():
        op.drop_table('announcement_reads')
    existing = _columns('announcements')
    with op.batch_alter_table('announcements') as batch_op:
        if 'tower_id' in existing:
            batch_op.drop_index('ix_announcements_tower_id')
            batch_op.drop_constraint(TOWER_FOREIGN_KEY, type_='foreignkey')
            batch_op.drop_column('tower_id')
        if 'expires_at' in existing:
            batch_op.drop_column('expires_at')
        if 'category' in existing:
            batch_op.drop_column('category')
