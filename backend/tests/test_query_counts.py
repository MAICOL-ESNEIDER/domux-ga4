"""Las listas no hacen una consulta más por cada fila (el problema «N+1»).

Se miden las consultas SQL de cada lista con pocos datos y con varias veces más datos: el número debe
quedar igual (o casi). Si alguien agrega una relación sin cargarla junto con la lista, la lista vuelve a
hacer una consulta por fila, se vuelve lenta con una unidad de verdad y esta prueba lo avisa.
"""

import datetime as dt
import unittest

import env_setup  # noqa: F401  (va antes de importar la app)

from sqlalchemy import event
from werkzeug.security import generate_password_hash

from app import create_app
from auth import generate_token
from extensions import db
from models import (
    Announcement,
    CommonArea,
    Notification,
    PackageItem,
    Pqrs,
    PqrsMessage,
    Reservation,
    ReservationMessage,
    UnitDocument,
    User,
    Visit,
)
from structure_fixtures import apartment_for
from time_utils import colombia_today, utc_now

FEW, MANY = 3, 12

#: (rol, dirección) de cada lista que se vigila.
LISTS = (
    ("ADMIN", "/api/users"),
    ("ADMIN", "/api/pqrs"),
    ("ADMIN", "/api/pqrs?view=summary"),
    ("ADMIN", "/api/reservations"),
    ("ADMIN", "/api/reservations?view=summary"),
    ("ADMIN", "/api/announcements"),
    ("ADMIN", "/api/packages"),
    ("ADMIN", "/api/visits"),
    ("ADMIN", "/api/admin/summary"),
    ("ADMIN", "/api/documents"),
    ("ADMIN", "/api/documents?includeRetired=true"),
    ("ADMIN", "/api/admin/export/legal-report"),
    ("GUARD", "/api/packages"),
    ("GUARD", "/api/visits"),
    ("GUARD", "/api/documents"),
    ("RESIDENT", "/api/documents"),
    ("RESIDENT", "/api/pqrs"),
    ("RESIDENT", "/api/reservations"),
    ("RESIDENT", "/api/announcements"),
    ("RESIDENT", "/api/notifications"),
)


class QueryCountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls.addClassCleanup(env_setup.release_app, cls.app)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.admin = self.person("ADMIN", "admin-consultas@test.local")
        self.guard = self.person("GUARD", "guardia-consultas@test.local")
        self.area = CommonArea(name="Salón social")
        db.session.add(self.area)
        db.session.commit()
        self.client = self.app.test_client()
        self.rows = 0
        self.first_resident = None

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    @staticmethod
    def person(role, email, **fields):
        user = User(
            name=role.title(), email=email, role=role, is_active=True,
            password_hash=generate_password_hash("Clave-de-prueba-1*"), **fields,
        )
        db.session.add(user)
        db.session.flush()
        return user

    def add_rows(self, total):
        """Deja ``total`` residentes, cada uno con su visita, paquete, PQRS, reserva, aviso y notificación."""
        today = colombia_today()
        while self.rows < total:
            index = self.rows
            resident = self.person(
                "RESIDENT", f"residente{index}-consultas@test.local",
                apartment_ref=apartment_for(f"Torre {1 + index % 3} · Apto {101 + index}"),
                phone="3000000000", occupancy_type="propietario",
            )
            self.first_resident = self.first_resident or resident
            db.session.add(Visit(
                resident_id=resident.id, registered_by=self.guard.id, visitor_name=f"Visitante {index}",
                type="visita",
            ))
            db.session.add(PackageItem(
                resident_id=resident.id, registered_by=self.guard.id, description=f"Paquete {index}",
                status="pendiente",
            ))
            pqrs = Pqrs(resident_id=resident.id, subject=f"Asunto {index}", message="Texto", category="Petición")
            reservation = Reservation(
                resident_id=resident.id, common_area_id=self.area.id, status="pendiente",
                date=(today + dt.timedelta(days=3 + index)).isoformat(), time_slot="10:00-12:00",
            )
            db.session.add_all([pqrs, reservation])
            db.session.flush()
            db.session.add(PqrsMessage(
                pqrs_id=pqrs.id, author_id=resident.id, author_role="RESIDENT", message="Hola",
            ))
            db.session.add(ReservationMessage(
                reservation_id=reservation.id, author_id=resident.id, author_role="RESIDENT", message="Hola",
            ))
            db.session.add(Announcement(
                title=f"Aviso {index}", message="Texto", category="general", author_id=self.admin.id,
            ))
            db.session.add(Notification(user_id=resident.id, title="Aviso", message="Texto"))
            # Cada documento lo sube otra persona de la administración: así la lista no puede apoyarse en
            # que quien lo subió ya estaba cargado y tiene que traer a todas juntas.
            author = self.person("ADMIN", f"autor{index}-consultas@test.local")
            document = UnitDocument(
                title=f"Documento {index}", category="otro", file_name=f"documento{index}.pdf",
                mime_type="application/pdf", size_bytes=8, content=b"%PDF-1.4", content_sha256="0" * 64,
                for_owners=True, for_guards=True, uploaded_by_id=author.id,
            )
            if index % 2:  # la mitad retirados, por otra persona, para que la lista también cargue quién los retiró
                retirer = self.person("ADMIN", f"retira{index}-consultas@test.local")
                document.retired_at, document.retired_by_id = utc_now(), retirer.id
            db.session.add(document)
            self.rows += 1
        db.session.commit()

    def count_queries(self, role, url):
        users = {"ADMIN": self.admin, "GUARD": self.guard, "RESIDENT": self.first_resident}
        statements = []

        def record(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(db.engine, "before_cursor_execute", record)
        try:
            response = self.client.get(
                url, headers={"Authorization": f"Bearer {generate_token(users[role])}"}
            )
        finally:
            event.remove(db.engine, "before_cursor_execute", record)
        self.assertEqual(response.status_code, 200, f"{role} {url}: {response.get_data(as_text=True)[:200]}")
        return len(statements)

    def test_a_list_with_more_rows_does_not_make_more_queries(self):
        self.add_rows(FEW)
        before = {entry: self.count_queries(*entry) for entry in LISTS}
        self.add_rows(MANY)
        for entry in LISTS:
            after = self.count_queries(*entry)
            self.assertLessEqual(
                after, before[entry] + 2,
                f"{entry[0]} {entry[1]}: {before[entry]} consultas con {FEW} filas y {after} con {MANY}",
            )


if __name__ == "__main__":
    unittest.main()
