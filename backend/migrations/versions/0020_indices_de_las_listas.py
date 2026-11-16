"""Índices para las listas que crecen con el tiempo.

Las listas del residente (sus visitas, paquetes, PQRS y reservas) y el conteo de apartamentos que
leyeron un comunicado buscan por columnas que no tenían índice. Con pocos datos no se nota; con los
años de una unidad sí. No cambia ningún dato ni ninguna respuesta.

Revision ID: 0020_indices_de_las_listas
Revises: 0019_descarga_de_adjuntos
Create Date: 2026-11-15 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0020_indices_de_las_listas'
down_revision = '0019_descarga_de_adjuntos'
branch_labels = None
depends_on = None

#: (tabla, columna): el índice se llama como lo nombra SQLAlchemy para ``index=True``.
INDEXES = (
    ('visits', 'resident_id'),
    ('packages', 'resident_id'),
    ('pqrs', 'resident_id'),
    ('reservations', 'resident_id'),
    ('announcement_reads', 'apartment_id'),
)


def _existing(inspector, table):
    return {index['name'] for index in inspector.get_indexes(table)}


def upgrade():
    # Si el índice ya existe (por una base creada con db.create_all) no se repite.
    inspector = sa.inspect(op.get_bind())
    for table, column in INDEXES:
        name = f'ix_{table}_{column}'
        if name not in _existing(inspector, table):
            op.create_index(name, table, [column])


def downgrade():
    inspector = sa.inspect(op.get_bind())
    for table, column in INDEXES:
        name = f'ix_{table}_{column}'
        if name in _existing(inspector, table):
            op.drop_index(name, table_name=table)
