"""Visitas y paquetes que la administración espera para la unidad, y parqueaderos de carro para motos.

* visits: ``for_unit`` (la visita es de la unidad, no de un residente: un técnico o un contratista
  que viene a trabajar en las zonas comunes), ``expected_date`` y ``expected_time`` (cuándo llega).
* packages: ``for_unit`` (repuestos, materiales, plantas o herramientas para la unidad).
* parking_spots: ``for_motos`` (un parqueadero de carro que se usa para varias motos, RN-022).

Revision ID: 0026_esperados_de_la_unidad
Revises: 0025_mas_reglas_de_la_unidad
Create Date: 2026-11-27 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '0026_esperados_de_la_unidad'
down_revision = '0025_mas_reglas_de_la_unidad'
branch_labels = None
depends_on = None

NEW = {
    'visits': (
        ('for_unit', lambda: sa.Column('for_unit', sa.Boolean(), nullable=False, server_default=sa.false())),
        ('expected_date', lambda: sa.Column('expected_date', sa.String(length=10), nullable=True)),
        ('expected_time', lambda: sa.Column('expected_time', sa.String(length=5), nullable=True)),
    ),
    'packages': (
        ('for_unit', lambda: sa.Column('for_unit', sa.Boolean(), nullable=False, server_default=sa.false())),
    ),
    'parking_spots': (
        ('for_motos', lambda: sa.Column('for_motos', sa.Boolean(), nullable=False, server_default=sa.false())),
    ),
}


def _columns(table):
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    for table, columns in NEW.items():
        existing = _columns(table)
        with op.batch_alter_table(table) as batch:
            for name, make in columns:
                if name not in existing:
                    batch.add_column(make())


def downgrade():
    for table, columns in NEW.items():
        existing = _columns(table)
        with op.batch_alter_table(table) as batch:
            for name, _ in columns:
                if name in existing:
                    batch.drop_column(name)
