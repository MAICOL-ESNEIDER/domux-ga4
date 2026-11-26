"""Más reglas de la unidad que la administración puede ajustar (DEC-032, RN-022).

Agrega a unit_settings las reglas de portería que estaban fijas en el código:

* los días máximos de estadía de una visita;
* las personas por QR y los días de vigencia de un QR;
* desde cuántos días de estadía se crea el QR automáticamente;
* los días que un paquete entregado tarda en archivarse solo;
* cuántas motos caben en un parqueadero de carro cuando faltan de moto.

Una columna vacía significa «usa el valor de DOMUX», así que nada cambia hasta que la administración guarde.

Revision ID: 0025_mas_reglas_de_la_unidad
Revises: 0024_aceptacion_de_textos
Create Date: 2026-11-26 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0025_mas_reglas_de_la_unidad'
down_revision = '0024_aceptacion_de_textos'
branch_labels = None
depends_on = None

TABLE = 'unit_settings'
COLUMNS = (
    'visit_max_stay_days',
    'qr_max_people',
    'qr_max_valid_days',
    'auto_qr_min_stay_days',
    'delivered_archive_days',
    'motos_per_car_spot',
)


def _columns():
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade():
    # Una columna que ya existe (por una base creada con db.create_all) no se repite.
    existing = _columns()
    with op.batch_alter_table(TABLE) as batch:
        for name in COLUMNS:
            if name not in existing:
                batch.add_column(sa.Column(name, sa.Integer(), nullable=True))


def downgrade():
    existing = _columns()
    with op.batch_alter_table(TABLE) as batch:
        for name in COLUMNS:
            if name in existing:
                batch.drop_column(name)
