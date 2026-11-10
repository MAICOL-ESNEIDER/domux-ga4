"""Estructura de la unidad: torres, apartamentos, parqueaderos y cuartos útiles (HU-013 a HU-018, DT-006).

El apartamento deja de ser un texto suelto («Torre 1 · Apto 101») y pasa a ser
una llave:

* Se crean towers, apartments, parking_spots y storage_rooms.
* users y residential_units apuntan a su apartamento con apartment_id.
* Los textos que ya había se convierten en torres y apartamentos, sin perder
  ningún usuario ni ninguna ficha del hogar. Un texto que no dice la torre cae
  en la torre «Sin torre», para que el administrador lo corrija.
* Los parqueaderos y cuartos útiles que la ficha guardaba como texto pasan a ser
  parqueaderos de residente (ubicación «Por definir») y cuartos asignados al
  apartamento; si dos fichas repetían un código, queda con la primera.
* Se quitan las columnas de texto: users.apartment, users.apartment_number,
  residential_units.apartment, parking_identifier y storage_identifier.

Bajar de versión vuelve a escribir esos textos desde la estructura.

Revision ID: 0006_estructura
Revises: 0005_intentos
Create Date: 2026-11-10 18:05:00.000000

"""
import re

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0006_estructura'
down_revision = '0005_intentos'
branch_labels = None
depends_on = None

ONLY_ACTIVE = sa.text('retired_at IS NULL')
NO_TOWER = 'Sin torre'
LABEL_SEPARATOR = ' · Apto '

# Cómo se escribía un apartamento: «Torre 1 · Apto 101», «Torre 1 Apto 101», «Torre 1, Apto 101».
_LEGACY_TEXT = re.compile(
    r'^\s*(?P<tower>.+?)\s*[·•|,;/–—-]?\s+(?:apto|apartamento|apt|ap)\.?\s*#?\s*'
    r'(?P<code>[A-Za-z0-9][A-Za-z0-9._/-]*)\s*$',
    re.IGNORECASE,
)


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table):
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table):
    return {index['name'] for index in sa.inspect(op.get_bind()).get_indexes(table)}


def _retirement_columns(table):
    return [
        sa.Column('retired_at', sa.DateTime(), nullable=True),
        sa.Column('retired_by_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['retired_by_id'], ['users.id'], name=f'fk_{table}_retired_by_id_users'),
    ]


def _active_unique_index(name, table, columns):
    op.create_index(
        name, table, columns, unique=True, sqlite_where=ONLY_ACTIVE, postgresql_where=ONLY_ACTIVE
    )


def _create_tables():
    """Crea las cuatro tablas nuevas; una que db.create_all ya creó al arrancar no se repite."""
    existing = _tables()
    if 'towers' not in existing:
        op.create_table(
            'towers',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=60), nullable=False),
            sa.Column('floors', sa.Integer(), nullable=False),
            *_retirement_columns('towers'),
            sa.PrimaryKeyConstraint('id'),
        )
        _active_unique_index('uq_towers_active_name', 'towers', ['name'])
    if 'apartments' not in existing:
        op.create_table(
            'apartments',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tower_id', sa.Integer(), nullable=False),
            sa.Column('code', sa.String(length=20), nullable=False),
            sa.Column('floor', sa.Integer(), nullable=False),
            sa.Column('number', sa.Integer(), nullable=True),
            *_retirement_columns('apartments'),
            sa.ForeignKeyConstraint(['tower_id'], ['towers.id'], name='fk_apartments_tower_id_towers'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_apartments_tower_id', 'apartments', ['tower_id'], unique=False)
        op.create_index('ix_apartments_number', 'apartments', ['number'], unique=False)
        _active_unique_index('uq_apartments_active_code', 'apartments', ['tower_id', 'code'])
    if 'parking_spots' not in existing:
        op.create_table(
            'parking_spots',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('code', sa.String(length=20), nullable=False),
            sa.Column('kind', sa.String(length=12), nullable=False),
            sa.Column('location', sa.String(length=120), nullable=False),
            sa.Column('apartment_id', sa.Integer(), nullable=True),
            sa.Column('occupied', sa.Boolean(), server_default=sa.false(), nullable=False),
            *_retirement_columns('parking_spots'),
            sa.ForeignKeyConstraint(
                ['apartment_id'], ['apartments.id'], name='fk_parking_spots_apartment_id_apartments'
            ),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_parking_spots_apartment_id', 'parking_spots', ['apartment_id'], unique=False)
        _active_unique_index('uq_parking_spots_active_code', 'parking_spots', ['code'])
    if 'storage_rooms' not in existing:
        op.create_table(
            'storage_rooms',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('code', sa.String(length=20), nullable=False),
            sa.Column('apartment_id', sa.Integer(), nullable=True),
            *_retirement_columns('storage_rooms'),
            sa.ForeignKeyConstraint(
                ['apartment_id'], ['apartments.id'], name='fk_storage_rooms_apartment_id_apartments'
            ),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_storage_rooms_apartment_id', 'storage_rooms', ['apartment_id'], unique=False)
        _active_unique_index('uq_storage_rooms_active_code', 'storage_rooms', ['code'])


# --- Convertir los textos de la base vieja en estructura ----------------------

def _split_legacy_text(text):
    """(torre, código, ¿se entendió?) de un texto viejo de apartamento."""
    match = _LEGACY_TEXT.match(text)
    if match:
        return ' '.join(match.group('tower').split()), match.group('code').upper(), True
    # Sin torre en el texto: «Apto 305» queda como el apartamento 305 de «Sin torre».
    cleaned = ' '.join(text.split())
    bare = re.sub(r'^(?:apto|apartamento|apt|ap)\.?\s*#?\s*', '', cleaned, flags=re.IGNORECASE)
    return NO_TOWER, (bare or cleaned).upper()[:20], False


def _floor_of(code):
    """El piso que sugiere un código numérico de tres o más cifras (301 es el piso 3); si no, el 1."""
    return int(code[:-2]) if code.isdigit() and len(code) >= 3 else 1


def _number_of(code):
    digits = re.findall(r'\d+', code)
    return int(digits[-1]) if digits else None


def _split_codes(text):
    codes = []
    for part in re.split(r'[,;]|\s+y\s+', text or ''):
        code = ' '.join(part.split()).upper()[:20]
        if code and code not in codes:
            codes.append(code)
    return codes


def _convert_texts_to_structure(bind):
    """Crea las torres y los apartamentos que dicen los textos viejos y los enlaza."""
    metadata = sa.MetaData()
    towers = sa.Table(
        'towers', metadata, sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String), sa.Column('floors', sa.Integer),
    )
    apartments = sa.Table(
        'apartments', metadata, sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('tower_id', sa.Integer), sa.Column('code', sa.String),
        sa.Column('floor', sa.Integer), sa.Column('number', sa.Integer),
    )
    parking = sa.Table(
        'parking_spots', metadata, sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('code', sa.String), sa.Column('kind', sa.String), sa.Column('location', sa.String),
        sa.Column('apartment_id', sa.Integer), sa.Column('occupied', sa.Boolean),
    )
    storage = sa.Table(
        'storage_rooms', metadata, sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('code', sa.String), sa.Column('apartment_id', sa.Integer),
    )
    users = sa.Table(
        'users', metadata, sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('apartment', sa.String), sa.Column('apartment_id', sa.Integer),
    )
    units = sa.Table(
        'residential_units', metadata, sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('apartment', sa.String), sa.Column('parking_identifier', sa.String),
        sa.Column('storage_identifier', sa.String), sa.Column('apartment_id', sa.Integer),
    )

    originals = set()
    for table in (users, units):
        originals.update(
            text for (text,) in bind.execute(sa.select(table.c.apartment).distinct())
            if text is not None and text.strip()
        )

    tower_ids = {}          # nombre de la torre (sin mayúsculas) -> id
    tower_floors = {}       # id de la torre -> piso más alto
    apartment_ids = {}      # (id de la torre, código) -> id del apartamento
    apartment_for = {}      # texto original -> id del apartamento
    for original in sorted(originals):
        tower_name, code, understood = _split_legacy_text(original.strip())
        key = tower_name.casefold()
        if key not in tower_ids:
            tower_ids[key] = bind.execute(
                sa.insert(towers).values(name=tower_name, floors=1)
            ).inserted_primary_key[0]
            tower_floors[tower_ids[key]] = 1
        tower_id = tower_ids[key]
        if not understood:
            # Dos textos distintos que se recortan igual no deben quedar como el mismo apartamento.
            base, suffix = code, 2
            while (tower_id, code) in apartment_ids:
                code = f'{base[:17]}-{suffix}'
                suffix += 1
        if (tower_id, code) not in apartment_ids:
            floor = _floor_of(code)
            apartment_ids[(tower_id, code)] = bind.execute(
                sa.insert(apartments).values(
                    tower_id=tower_id, code=code, floor=floor, number=_number_of(code)
                )
            ).inserted_primary_key[0]
            tower_floors[tower_id] = max(tower_floors[tower_id], floor)
        apartment_for[original] = apartment_ids[(tower_id, code)]

    for tower_id, floors in tower_floors.items():
        bind.execute(sa.update(towers).where(towers.c.id == tower_id).values(floors=floors))
    for table in (users, units):
        for original, apartment_id in apartment_for.items():
            bind.execute(
                sa.update(table).where(table.c.apartment == original).values(apartment_id=apartment_id)
            )

    # Los parqueaderos y cuartos útiles que la ficha guardaba como texto.
    taken_parking, taken_storage = set(), set()
    for apartment_id, parking_text, storage_text in bind.execute(
        sa.select(units.c.apartment_id, units.c.parking_identifier, units.c.storage_identifier)
        .order_by(units.c.id)
    ).fetchall():
        for code in _split_codes(parking_text):
            if code not in taken_parking:
                taken_parking.add(code)
                bind.execute(sa.insert(parking).values(
                    code=code, kind='residente', location='Por definir',
                    apartment_id=apartment_id, occupied=False,
                ))
        for code in _split_codes(storage_text):
            if code not in taken_storage:
                taken_storage.add(code)
                bind.execute(sa.insert(storage).values(code=code, apartment_id=apartment_id))


def upgrade():
    _create_tables()
    bind = op.get_bind()
    legacy = 'apartment' in _columns('residential_units')

    if 'apartment_id' not in _columns('users'):
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.add_column(sa.Column('apartment_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_users_apartment_id_apartments', 'apartments', ['apartment_id'], ['id']
            )
            batch_op.create_index(batch_op.f('ix_users_apartment_id'), ['apartment_id'], unique=False)
    if 'apartment_id' not in _columns('residential_units'):
        with op.batch_alter_table('residential_units', schema=None) as batch_op:
            batch_op.add_column(sa.Column('apartment_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_residential_units_apartment_id_apartments', 'apartments', ['apartment_id'], ['id']
            )

    if legacy:
        _convert_texts_to_structure(bind)
        with op.batch_alter_table('residential_units', schema=None) as batch_op:
            batch_op.alter_column('apartment_id', existing_type=sa.Integer(), nullable=False)
            batch_op.drop_index('ix_residential_units_apartment')
            batch_op.drop_column('apartment')
            batch_op.drop_column('parking_identifier')
            batch_op.drop_column('storage_identifier')
            batch_op.create_index(
                batch_op.f('ix_residential_units_apartment_id'), ['apartment_id'], unique=True
            )

    user_columns = _columns('users')
    if 'apartment' in user_columns:
        with op.batch_alter_table('users', schema=None) as batch_op:
            if 'ix_users_apartment_number' in _indexes('users'):
                batch_op.drop_index('ix_users_apartment_number')
            batch_op.drop_column('apartment_number')
            batch_op.drop_column('apartment')


def downgrade():
    bind = op.get_bind()
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('apartment', sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column('apartment_number', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_users_apartment_number'), ['apartment_number'], unique=False)
    with op.batch_alter_table('residential_units', schema=None) as batch_op:
        batch_op.add_column(sa.Column('apartment', sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column('parking_identifier', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('storage_identifier', sa.String(length=80), nullable=True))

    # Los textos vuelven a escribirse desde la estructura.
    metadata = sa.MetaData()
    apartments = sa.Table(
        'apartments', metadata, sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('tower_id', sa.Integer), sa.Column('code', sa.String),
        sa.Column('number', sa.Integer), sa.Column('retired_at', sa.DateTime),
    )
    towers = sa.Table(
        'towers', metadata, sa.Column('id', sa.Integer, primary_key=True), sa.Column('name', sa.String),
    )
    parking = sa.Table(
        'parking_spots', metadata, sa.Column('code', sa.String), sa.Column('kind', sa.String),
        sa.Column('apartment_id', sa.Integer), sa.Column('retired_at', sa.DateTime),
    )
    storage = sa.Table(
        'storage_rooms', metadata, sa.Column('code', sa.String),
        sa.Column('apartment_id', sa.Integer), sa.Column('retired_at', sa.DateTime),
    )
    users = sa.Table(
        'users', metadata, sa.Column('apartment', sa.String), sa.Column('apartment_number', sa.Integer),
        sa.Column('apartment_id', sa.Integer),
    )
    units = sa.Table(
        'residential_units', metadata, sa.Column('apartment', sa.String),
        sa.Column('parking_identifier', sa.String), sa.Column('storage_identifier', sa.String),
        sa.Column('apartment_id', sa.Integer),
    )
    rows = bind.execute(
        sa.select(apartments.c.id, towers.c.name, apartments.c.code, apartments.c.number,
                  apartments.c.retired_at)
        .join(towers, towers.c.id == apartments.c.tower_id)
        .order_by(apartments.c.id)
    ).fetchall()
    for apartment_id, tower_name, code, number, retired_at in rows:
        label = f'{tower_name}{LABEL_SEPARATOR}{code}'[:60]
        # En la base vieja el texto de cada ficha era único: la de un apartamento retirado lleva su id.
        unit_label = f'{label[:45]} [retirado {apartment_id}]' if retired_at is not None else label
        spots = [
            spot_code for (spot_code,) in bind.execute(
                sa.select(parking.c.code).where(
                    parking.c.apartment_id == apartment_id,
                    parking.c.kind == 'residente',
                    parking.c.retired_at.is_(None),
                ).order_by(parking.c.code)
            )
        ]
        rooms = [
            room_code for (room_code,) in bind.execute(
                sa.select(storage.c.code).where(
                    storage.c.apartment_id == apartment_id, storage.c.retired_at.is_(None)
                ).order_by(storage.c.code)
            )
        ]
        bind.execute(sa.update(users).where(users.c.apartment_id == apartment_id).values(
            apartment=label, apartment_number=number
        ))
        bind.execute(sa.update(units).where(units.c.apartment_id == apartment_id).values(
            apartment=unit_label,
            parking_identifier=(', '.join(spots) or None),
            storage_identifier=(', '.join(rooms) or None),
        ))

    with op.batch_alter_table('residential_units', schema=None) as batch_op:
        batch_op.drop_index('ix_residential_units_apartment_id')
        batch_op.drop_constraint('fk_residential_units_apartment_id_apartments', type_='foreignkey')
        batch_op.drop_column('apartment_id')
        batch_op.alter_column('apartment', existing_type=sa.String(length=60), nullable=False)
        batch_op.create_index(batch_op.f('ix_residential_units_apartment'), ['apartment'], unique=True)
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_apartment_id')
        batch_op.drop_constraint('fk_users_apartment_id_apartments', type_='foreignkey')
        batch_op.drop_column('apartment_id')

    op.drop_table('storage_rooms')
    op.drop_table('parking_spots')
    op.drop_table('apartments')
    op.drop_table('towers')
