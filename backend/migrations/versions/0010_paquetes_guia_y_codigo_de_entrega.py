"""Paquetes: transportadora, guía, llegada y código de entrega (HU-047, HU-048 y HU-049).

Agrega:

* packages.carrier y packages.tracking_number: la transportadora y el número de guía.
* packages.arrived_at: cuándo llegó el paquete a la portería; desde ahí se cuentan las
  48 y 72 horas sin reclamar (RN-018). Los paquetes que ya estaban en portería o
  entregados toman la hora en que se registraron.
* package_pickup_codes: el código (QR y PIN con hash) que el residente genera para que
  otra persona recoja su paquete. Un índice único parcial deja un solo código vigente
  por paquete; los usados y anulados quedan como historial.

Revision ID: 0010_paquetes
Revises: 0009_visitas
Create Date: 2026-11-11 21:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0010_paquetes'
down_revision = '0009_visitas'
branch_labels = None
depends_on = None

ACTIVE_CODE = sa.text('revoked_at IS NULL AND used_at IS NULL')


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table):
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    # Una columna o tabla que ya existe (por una base creada con db.create_all) no se repite.
    package_columns = _columns('packages')
    if 'carrier' not in package_columns:
        op.add_column('packages', sa.Column('carrier', sa.String(length=60), nullable=True))
    if 'tracking_number' not in package_columns:
        op.add_column('packages', sa.Column('tracking_number', sa.String(length=60), nullable=True))
    if 'arrived_at' not in package_columns:
        op.add_column('packages', sa.Column('arrived_at', sa.DateTime(), nullable=True))
    # Los que aún no llegan («por_llegar») se quedan sin hora hasta que lleguen.
    op.execute(
        "UPDATE packages SET arrived_at = created_at "
        "WHERE arrived_at IS NULL AND status IN ('pendiente', 'entregado')"
    )
    if 'package_pickup_codes' not in _tables():
        op.create_table(
            'package_pickup_codes',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('package_id', sa.Integer(), nullable=False),
            sa.Column('token', sa.String(length=80), nullable=False),
            sa.Column('pin_hash', sa.String(length=255), nullable=False),
            sa.Column('created_by_id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('used_at', sa.DateTime(), nullable=True),
            sa.Column('revoked_at', sa.DateTime(), nullable=True),
            sa.Column('failed_attempts', sa.Integer(), nullable=False, server_default='0'),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(
                ['package_id'], ['packages.id'], name='fk_package_pickup_codes_package_id_packages'
            ),
            sa.ForeignKeyConstraint(
                ['created_by_id'], ['users.id'], name='fk_package_pickup_codes_created_by_id_users'
            ),
        )
        op.create_index('ix_package_pickup_codes_package_id', 'package_pickup_codes', ['package_id'])
        op.create_index('ix_package_pickup_codes_token', 'package_pickup_codes', ['token'], unique=True)
        op.create_index(
            'uq_package_pickup_codes_active', 'package_pickup_codes', ['package_id'],
            unique=True, sqlite_where=ACTIVE_CODE, postgresql_where=ACTIVE_CODE,
        )


def downgrade():
    if 'package_pickup_codes' in _tables():
        op.drop_table('package_pickup_codes')
    package_columns = _columns('packages')
    with op.batch_alter_table('packages') as batch_op:
        for name in ('arrived_at', 'tracking_number', 'carrier'):
            if name in package_columns:
                batch_op.drop_column(name)
