"""Número de radicado de las PQRS (HU-072).

Agrega pqrs.radicado, único, con el formato «PQRS-2026-000123»: el año de Colombia en que
se radicó y el número propio de la PQRS. Las PQRS que ya existían reciben el suyo con la
fecha en que se crearon. Las nuevas lo reciben al guardarse (ver models.py).

Revision ID: 0013_radicado_pqrs
Revises: 0012_comunicados_extra
Create Date: 2026-11-12 00:10:00.000000

"""
from datetime import datetime, timedelta

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0013_radicado_pqrs'
down_revision = '0012_comunicados_extra'
branch_labels = None
depends_on = None

#: Colombia no cambia de hora en todo el año: siempre está 5 horas atrás de la hora universal.
COLOMBIA_OFFSET = timedelta(hours=5)


def _columns(table):
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table):
    return {index['name'] for index in sa.inspect(op.get_bind()).get_indexes(table)}


def _colombia_year(created_at):
    """Año de Colombia de una fecha guardada en UTC (SQLite la devuelve como texto)."""
    if created_at is None:
        return datetime.utcnow().year
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    return (created_at - COLOMBIA_OFFSET).year


def upgrade():
    if 'radicado' not in _columns('pqrs'):
        op.add_column('pqrs', sa.Column('radicado', sa.String(length=30), nullable=True))
    bind = op.get_bind()
    pending = bind.execute(sa.text('SELECT id, created_at FROM pqrs WHERE radicado IS NULL')).fetchall()
    for pqrs_id, created_at in pending:
        bind.execute(
            sa.text('UPDATE pqrs SET radicado = :radicado WHERE id = :id'),
            {'radicado': f'PQRS-{_colombia_year(created_at)}-{pqrs_id:06d}', 'id': pqrs_id},
        )
    if 'ix_pqrs_radicado' not in _indexes('pqrs'):
        op.create_index('ix_pqrs_radicado', 'pqrs', ['radicado'], unique=True)


def downgrade():
    with op.batch_alter_table('pqrs') as batch_op:
        if 'ix_pqrs_radicado' in _indexes('pqrs'):
            batch_op.drop_index('ix_pqrs_radicado')
        if 'radicado' in _columns('pqrs'):
            batch_op.drop_column('radicado')
