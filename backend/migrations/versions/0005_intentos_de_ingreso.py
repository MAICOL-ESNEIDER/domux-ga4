"""Intentos fallidos de ingreso y bloqueo de la cuenta (HU-006, RN-002, DAT-02).

Crea login_attempts: una fila por correo (o por guardia, para el PIN) con los
intentos fallidos seguidos y, si llegó a 5, hasta cuándo está bloqueado.

Revision ID: 0005_intentos
Revises: 0004_mascotas
Create Date: 2026-11-10 16:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0005_intentos'
down_revision = '0004_mascotas'
branch_labels = None
depends_on = None


def upgrade():
    # Una base vieja a la que db.create_all ya le creó la tabla no necesita nada más.
    if 'login_attempts' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        'login_attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('subject', sa.String(length=160), nullable=False),
        sa.Column('failed_count', sa.Integer(), nullable=False),
        sa.Column('locked_until', sa.DateTime(), nullable=True),
        sa.Column('last_failed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('kind', 'subject', name='uq_login_attempts_kind_subject'),
    )


def downgrade():
    op.drop_table('login_attempts')
