"""Zonas comunes completas: cerrar con motivo y retirar sin borrar.

Agrega a common_areas lo que la administración necesita para manejar las zonas de su unidad sin tocar el
código (DEC-032):

* closed_at, closed_reason y closed_by_id: cierre temporal de una zona (por una falla, por ejemplo). La
  zona sigue existiendo, pero no recibe reservas nuevas y a quien la consulta se le muestra el motivo que
  escribió la administración.
* retired_at y retired_by_id: retiro lógico (ADR-013). Una zona que ya no existe en la unidad no se borra,
  porque sus reservas viejas siguen apuntando a ella; queda retirada y deja de ofrecerse.

No cambia ningún dato: todas las zonas siguen abiertas y vigentes.

Revision ID: 0021_zonas_completas
Revises: 0020_indices_de_las_listas
Create Date: 2026-11-17 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0021_zonas_completas'
down_revision = '0020_indices_de_las_listas'
branch_labels = None
depends_on = None

TABLE = 'common_areas'
#: (columna, tipo): todas pueden quedar vacías, que es como están las zonas que ya existen.
NEW_COLUMNS = (
    ('closed_at', sa.DateTime()),
    ('closed_reason', sa.String(length=300)),
    ('closed_by_id', sa.Integer()),
    ('retired_at', sa.DateTime()),
    ('retired_by_id', sa.Integer()),
)
#: Las columnas que apuntan a un usuario, con el nombre de su llave foránea.
USER_COLUMNS = ('closed_by_id', 'retired_by_id')


def _columns():
    """Nombres de las columnas que ya tiene la tabla en la base."""
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade():
    existing = _columns()
    missing = [(name, kind) for name, kind in NEW_COLUMNS if name not in existing]
    if not missing:
        return
    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        for name, kind in missing:
            batch_op.add_column(sa.Column(name, kind, nullable=True))
            if name in USER_COLUMNS:
                batch_op.create_foreign_key(f'fk_{TABLE}_{name}_users', 'users', [name], ['id'])


def downgrade():
    existing = _columns()
    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        for name, _ in reversed(NEW_COLUMNS):
            if name not in existing:
                continue
            if name in USER_COLUMNS:
                batch_op.drop_constraint(f'fk_{TABLE}_{name}_users', type_='foreignkey')
            batch_op.drop_column(name)
