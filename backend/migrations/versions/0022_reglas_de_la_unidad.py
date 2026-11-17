"""Reglas de la unidad que la administración ajusta (DEC-032, RN-022).

Crea unit_settings, con una sola fila (la de la unidad), para que los plazos y las alertas que antes
estaban fijos en el código se puedan cambiar cuando la asamblea lo decide:

* el plazo para responder una PQRS (general y por tipo) y los días hábiles que faltan para que el semáforo
  pase a amarillo (RN-025);
* las horas sin reclamar para que un paquete se ponga naranja y rojo (RN-018);
* los días que un vehículo visitante puede quedarse en el parqueadero (RN-015).

La fila no se crea aquí: nace la primera vez que la administración guarda las reglas. Una columna vacía
significa «usa el valor de DOMUX», así que mientras la fila no exista todo funciona como hasta ahora.

Revision ID: 0022_reglas_de_la_unidad
Revises: 0021_zonas_completas
Create Date: 2026-11-17 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0022_reglas_de_la_unidad'
down_revision = '0021_zonas_completas'
branch_labels = None
depends_on = None

TABLE = 'unit_settings'


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    # Una tabla que ya existe (por una base creada con db.create_all) no se repite.
    if TABLE in _tables():
        return
    op.create_table(
        TABLE,
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pqrs_term_days', sa.Integer(), nullable=True),
        sa.Column('pqrs_warning_days', sa.Integer(), nullable=True),
        sa.Column('pqrs_terms_by_category', sa.String(length=400), nullable=True),
        sa.Column('package_orange_hours', sa.Integer(), nullable=True),
        sa.Column('package_red_hours', sa.Integer(), nullable=True),
        sa.Column('visitor_parking_max_days', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_by_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['updated_by_id'], ['users.id'], name='fk_unit_settings_updated_by_id_users'
        ),
    )


def downgrade():
    if TABLE in _tables():
        op.drop_table(TABLE)
