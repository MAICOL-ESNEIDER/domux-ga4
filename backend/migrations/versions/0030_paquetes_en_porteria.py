"""Los paquetes de los residentes quedan siempre guardados en portería.

Desde ahora un paquete para un residente se registra cuando ya llegó y queda en portería, sin
que el residente tenga que aceptarlo. Los que habían quedado «por llegar» pasan a «en portería»;
el tiempo de espera se cuenta desde que se registraron. Los paquetes de la unidad no cambian.

Revision ID: 0030_paquetes_en_porteria
Revises: 0029_vehiculo_en_el_qr
Create Date: 2026-11-27 13:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '0030_paquetes_en_porteria'
down_revision = '0029_vehiculo_en_el_qr'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        sa.text(
            "UPDATE packages SET status = 'pendiente', arrived_at = COALESCE(arrived_at, created_at) "
            "WHERE status = 'por_llegar' AND for_unit = :no"
        ).bindparams(no=False)
    )


def downgrade():
    # No se puede saber cuáles estaban «por llegar»: quedan en portería.
    pass
