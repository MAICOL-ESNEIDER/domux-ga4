"""El QR de visitas puede decir en qué vehículo llegan (tipo, placa, marca y color).

Así el guardia, al leer el QR, ya sabe qué vehículo entra y registra su entrada con un toque.

Revision ID: 0029_vehiculo_en_el_qr
Revises: 0028_comunicado_tipo_propio
Create Date: 2026-11-27 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '0029_vehiculo_en_el_qr'
down_revision = '0028_comunicado_tipo_propio'
branch_labels = None
depends_on = None

COLUMNS = (
    ('vehicle_type', 10),
    ('vehicle_plate', 10),
    ('vehicle_brand', 40),
    ('vehicle_color', 30),
)


def _columns():
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns('visit_qr_passes')}


def upgrade():
    existing = _columns()
    with op.batch_alter_table('visit_qr_passes') as batch:
        for name, length in COLUMNS:
            if name not in existing:
                batch.add_column(sa.Column(name, sa.String(length=length), nullable=True))


def downgrade():
    existing = _columns()
    with op.batch_alter_table('visit_qr_passes') as batch:
        for name, _ in COLUMNS:
            if name in existing:
                batch.drop_column(name)
