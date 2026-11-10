"""Pruebas de la estructura de la unidad: torres, apartamentos, parqueaderos y cuartos útiles.

Cubren HU-013 a HU-018 y HU-023 con sus criterios de aceptación:
torres (CA-HU-013-01), apartamentos y su código único por torre (CA-HU-014-01 y
02), parqueaderos (CA-HU-015-01 y 02), cuartos útiles (CA-HU-016-01 y 02),
vínculo del residente con su apartamento (CA-HU-017-01 a 03), duplicados
(CA-HU-018-01) y los apartamentos de un piso de una vez (CA-HU-023-01 y 02).
"""

import unittest

import env_setup  # noqa: F401  (va antes de importar la app)

from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from auth import generate_token
from extensions import db
from models import (
    Apartment,
    AuditLog,
    ParkingSpot,
    ResidentialUnit,
    StorageRoom,
    Tower,
    User,
    Vehicle,
)
from services.excel_service import import_census_from_bytes
from services.structure_service import apartment_by_text, parse_apartment_text
from structure_fixtures import apartment_in, parking_spot, storage_room, tower_named

PASSWORD = "Clave-de-prueba-1*"


class StructureTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.admin = self.make_user("ADMIN", "admin-estructura@test.local")
        self.guard = self.make_user("GUARD", "guardia-estructura@test.local")
        self.resident = self.make_user(
            "RESIDENT", "residente-estructura@test.local",
            apartment_ref=apartment_in("Torre 1", "101"), occupancy_type="propietario",
        )
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def make_user(self, role, email, **fields):
        user = User(
            name=role.title(), email=email, role=role, is_active=True,
            password_hash=generate_password_hash(PASSWORD), **fields,
        )
        db.session.add(user)
        return user

    def headers(self, user=None):
        return {"Authorization": f"Bearer {generate_token(user or self.admin)}"}

    def call(self, method, path, user=None, **kwargs):
        return getattr(self.client, method)(path, headers=self.headers(user), **kwargs)

    def create_tower(self, name="Torre 2", floors=8):
        response = self.call("post", "/api/admin/towers", json={"name": name, "floors": floors})
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["tower"]

    def audit_actions(self, entity_type):
        return [log.action for log in AuditLog.query.filter_by(entity_type=entity_type).all()]


class TowerTests(StructureTestCase):
    def test_admin_creates_a_tower_and_sees_it_in_the_list(self):
        tower = self.create_tower("Torre 2", 8)

        self.assertEqual((tower["name"], tower["floors"], tower["apartmentCount"]), ("Torre 2", 8, 0))
        listed = self.call("get", "/api/admin/towers").get_json()["towers"]
        self.assertEqual([item["name"] for item in listed], ["Torre 1", "Torre 2"])
        self.assertIn("created", self.audit_actions("tower"))

    def test_towers_are_listed_in_natural_order(self):
        for name in ("Torre 10", "Torre 3"):
            self.create_tower(name)

        names = [t["name"] for t in self.call("get", "/api/admin/towers").get_json()["towers"]]

        self.assertEqual(names, ["Torre 1", "Torre 3", "Torre 10"])

    def test_tower_name_is_unique_ignoring_case_and_extra_spaces(self):
        for name in ("Torre 1", "torre 1", "  TORRE   1 "):
            with self.subTest(name=name):
                response = self.call("post", "/api/admin/towers", json={"name": name, "floors": 5})
                self.assertEqual(response.status_code, 409)
                self.assertIn("Torre 1", response.get_json()["error"])
        self.assertEqual(Tower.query.count(), 1)

    def test_invalid_tower_data_is_rejected(self):
        cases = {
            "sin nombre": {"floors": 5},
            "sin pisos": {"name": "Torre 2"},
            "pisos en texto": {"name": "Torre 2", "floors": "cinco"},
            "cero pisos": {"name": "Torre 2", "floors": 0},
            "demasiados pisos": {"name": "Torre 2", "floors": 101},
            "pisos verdadero o falso": {"name": "Torre 2", "floors": True},
            "nombre muy largo": {"name": "T" * 61, "floors": 5},
        }
        for case, body in cases.items():
            with self.subTest(case=case):
                self.assertEqual(self.call("post", "/api/admin/towers", json=body).status_code, 400)
        self.assertEqual(Tower.query.count(), 1)

    def test_tower_can_be_renamed_and_its_apartments_show_the_new_name(self):
        response = self.call(
            "put", f"/api/admin/towers/{self.resident.apartment_ref.tower_id}", json={"name": "Torre Norte"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.resident.apartment, "Torre Norte · Apto 101")
        self.assertEqual(self.resident.to_dict()["apartment"], "Torre Norte · Apto 101")

    def test_tower_cannot_have_fewer_floors_than_its_highest_apartment(self):
        tower = self.create_tower("Torre 2", 8)
        self.call("post", "/api/admin/apartments", json={"towerId": tower["id"], "code": "603", "floor": 6})

        response = self.call("put", f"/api/admin/towers/{tower['id']}", json={"floors": 5})

        self.assertEqual(response.status_code, 409)
        self.assertIn("piso 6", response.get_json()["error"])
        self.assertEqual(self.call("put", f"/api/admin/towers/{tower['id']}", json={"floors": 6}).status_code, 200)

    def test_empty_update_is_rejected(self):
        tower = self.create_tower()
        self.assertEqual(self.call("put", f"/api/admin/towers/{tower['id']}", json={}).status_code, 400)

    def test_tower_with_apartments_cannot_be_retired(self):
        response = self.call("delete", f"/api/admin/towers/{self.resident.apartment_ref.tower_id}")

        self.assertEqual(response.status_code, 409)
        self.assertIn("1 apartamento", response.get_json()["error"])
        self.assertIsNone(db.session.get(Tower, self.resident.apartment_ref.tower_id).retired_at)

    def test_empty_tower_is_retired_not_deleted_and_frees_its_name(self):
        tower = self.create_tower("Torre 2")

        response = self.call("delete", f"/api/admin/towers/{tower['id']}")

        self.assertEqual(response.status_code, 200)
        retired = db.session.get(Tower, tower["id"])
        self.assertIsNotNone(retired.retired_at)
        self.assertEqual(retired.retired_by_id, self.admin.id)
        self.assertEqual([t["name"] for t in self.call("get", "/api/admin/towers").get_json()["towers"]], ["Torre 1"])
        # El nombre vuelve a estar libre y la torre retirada ya no se puede editar.
        self.create_tower("Torre 2")
        self.assertEqual(self.call("put", f"/api/admin/towers/{tower['id']}", json={"floors": 3}).status_code, 404)
        self.assertEqual(Tower.query.filter_by(name="Torre 2").count(), 2)
        self.assertIn("retired", self.audit_actions("tower"))


class ApartmentTests(StructureTestCase):
    def setUp(self):
        super().setUp()
        self.tower = self.create_tower("Torre 2", 8)

    def create_apartment(self, **body):
        return self.call("post", "/api/admin/apartments", json={"towerId": self.tower["id"], **body})

    def test_admin_creates_an_apartment_with_code_and_floor(self):
        response = self.create_apartment(code="302", floor=3)

        self.assertEqual(response.status_code, 201)
        apartment = response.get_json()["apartment"]
        self.assertEqual(
            (apartment["tower"], apartment["code"], apartment["floor"], apartment["number"], apartment["label"]),
            ("Torre 2", "302", 3, 302, "Torre 2 · Apto 302"),
        )
        # Cada apartamento nace con la ficha de su hogar.
        self.assertIsNotNone(db.session.get(Apartment, apartment["id"]).unit)

    def test_floor_is_taken_from_the_code_when_it_is_not_sent(self):
        self.assertEqual(self.create_apartment(code="502").get_json()["apartment"]["floor"], 5)
        self.assertEqual(self.create_apartment(code="PH").status_code, 400)

    def test_code_is_saved_in_capital_letters(self):
        apartment = self.create_apartment(code="ph-1", floor=8).get_json()["apartment"]

        self.assertEqual((apartment["code"], apartment["number"]), ("PH-1", 1))

    def test_repeated_code_in_the_same_tower_is_rejected_but_not_in_another_tower(self):
        self.create_apartment(code="302", floor=3)

        repeated = self.create_apartment(code="302", floor=3)
        other_tower = self.call(
            "post", "/api/admin/apartments",
            json={"towerId": self.resident.apartment_ref.tower_id, "code": "302", "floor": 3},
        )

        self.assertEqual(repeated.status_code, 409)
        self.assertEqual(repeated.get_json()["error"], "El apartamento 302 ya existe en Torre 2.")
        self.assertEqual(other_tower.status_code, 201)

    def test_invalid_apartment_data_is_rejected(self):
        cases = {
            "piso fuera de la torre": {"code": "902", "floor": 9},
            "piso cero": {"code": "002", "floor": 0},
            "sin código": {"floor": 3},
            "piso en texto": {"code": "302", "floor": "tres"},
        }
        for case, body in cases.items():
            with self.subTest(case=case):
                self.assertEqual(self.create_apartment(**body).status_code, 400)
        missing_tower = self.call("post", "/api/admin/apartments", json={"towerId": 9999, "code": "101", "floor": 1})
        self.assertEqual(missing_tower.status_code, 404)

    def test_apartment_can_change_code_and_floor(self):
        apartment = self.create_apartment(code="302", floor=3).get_json()["apartment"]

        response = self.call("put", f"/api/admin/apartments/{apartment['id']}", json={"code": "303", "floor": 3})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["apartment"]["label"], "Torre 2 · Apto 303")
        self.create_apartment(code="304", floor=3)
        clash = self.call("put", f"/api/admin/apartments/{apartment['id']}", json={"code": "304"})
        self.assertEqual(clash.status_code, 409)
        moved = self.call("put", f"/api/admin/apartments/{apartment['id']}", json={"towerId": 1})
        self.assertEqual(moved.status_code, 400)

    def test_list_filters_by_tower_and_search_and_paginates(self):
        for code in ("101", "102", "201"):
            self.create_apartment(code=code)

        by_tower = self.call("get", f"/api/admin/apartments?towerId={self.tower['id']}").get_json()
        self.assertEqual([a["code"] for a in by_tower["apartments"]], ["101", "102", "201"])
        searched = self.call("get", "/api/admin/apartments?search=Torre 2 · Apto 10").get_json()
        self.assertEqual([a["code"] for a in searched["apartments"]], ["101", "102"])
        page = self.call("get", f"/api/admin/apartments?towerId={self.tower['id']}&page=2&pageSize=2").get_json()
        self.assertEqual(([a["code"] for a in page["apartments"]], page["total"], page["totalPages"]),
                         (["201"], 3, 2))
        self.assertEqual(self.call("get", "/api/admin/apartments?towerId=abc").status_code, 400)
        self.assertEqual(self.call("get", "/api/admin/apartments?pageSize=0").status_code, 400)

    def test_apartment_with_active_residents_cannot_be_retired(self):
        response = self.call("delete", f"/api/admin/apartments/{self.resident.apartment_id}")

        self.assertEqual(response.status_code, 409)
        self.assertIn("1 residente activo", response.get_json()["error"])
        self.assertIsNone(self.resident.apartment_ref.retired_at)

    def test_retiring_an_apartment_frees_its_parking_and_retires_its_household(self):
        apartment = apartment_in("Torre 2", "301")
        parking_spot("P-301", apartment=apartment)
        storage_room("C-301", apartment=apartment)
        db.session.add(Vehicle(
            unit_id=apartment.unit.id, plate="KLM456", vehicle_type="carro",
            make_model="Marca Modelo", year=2020, registered_owner="Dueño",
        ))
        db.session.commit()

        response = self.call("delete", f"/api/admin/apartments/{apartment.id}")

        self.assertEqual(response.status_code, 200)
        db.session.expire_all()
        retired = db.session.get(Apartment, apartment.id)
        self.assertIsNotNone(retired.retired_at)
        self.assertEqual(retired.retired_by_id, self.admin.id)
        self.assertIsNone(ParkingSpot.query.filter_by(code="P-301").one().apartment_id)
        self.assertIsNone(StorageRoom.query.filter_by(code="C-301").one().apartment_id)
        self.assertIsNotNone(Vehicle.query.filter_by(plate="KLM456").one().retired_at)
        # Nada se borró y la anotación dice qué se liberó.
        self.assertEqual(Apartment.query.filter_by(code="301").count(), 1)
        details = AuditLog.query.filter_by(entity_type="apartment", action="retired").one().details
        self.assertIn("P-301", details)
        # El código vuelve a estar libre para un apartamento nuevo.
        self.assertEqual(self.create_apartment(code="301", floor=3).status_code, 201)

    def test_user_with_a_retired_apartment_cannot_be_reactivated_into_it(self):
        apartment = apartment_in("Torre 2", "301")
        neighbor = self.make_user("RESIDENT", "vecino-estructura@test.local", apartment_ref=apartment)
        db.session.commit()
        self.call("put", f"/api/users/{neighbor.id}", json={"isActive": False})
        self.assertEqual(self.call("delete", f"/api/admin/apartments/{apartment.id}").status_code, 200)

        response = self.call("put", f"/api/users/{neighbor.id}", json={"isActive": True})

        self.assertEqual(response.status_code, 400)
        self.assertIn("ya no existe", response.get_json()["error"])
        db.session.rollback()  # una solicitud rechazada no guarda nada
        self.assertFalse(db.session.get(User, neighbor.id).is_active)


class FloorBatchTests(StructureTestCase):
    def setUp(self):
        super().setUp()
        self.tower = self.create_tower("Torre 2", 8)

    def batch(self, **body):
        return self.call("post", "/api/admin/apartments/batch", json={"towerId": self.tower["id"], **body})

    def test_a_floor_is_created_at_once_with_consecutive_codes(self):
        response = self.batch(floor=3, count=4)

        self.assertEqual(response.status_code, 201)
        codes = [a["code"] for a in response.get_json()["apartments"]]
        self.assertEqual(codes, ["301", "302", "303", "304"])
        self.assertIn("4 apartamentos en el piso 3 de Torre 2", response.get_json()["message"])
        created = Apartment.query.filter_by(tower_id=self.tower["id"]).all()
        self.assertEqual({a.floor for a in created}, {3})
        self.assertTrue(all(a.unit is not None for a in created))
        self.assertIn("floor_created", self.audit_actions("tower"))

    def test_floors_from_ten_up_use_two_digit_floor_prefix(self):
        tower = self.create_tower("Torre Alta", 12)

        response = self.call(
            "post", "/api/admin/apartments/batch", json={"towerId": tower["id"], "floor": 12, "count": 2}
        )

        self.assertEqual([a["code"] for a in response.get_json()["apartments"]], ["1201", "1202"])

    def test_batch_accepts_from_and_to_instead_of_count(self):
        response = self.batch(floor=2, **{"from": 3, "to": 5})

        self.assertEqual([a["code"] for a in response.get_json()["apartments"]], ["203", "204", "205"])

    def test_if_one_code_already_exists_none_is_created_and_the_message_names_it(self):
        self.call("post", "/api/admin/apartments", json={"towerId": self.tower["id"], "code": "303", "floor": 3})

        response = self.batch(floor=3, count=4)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.get_json()["error"],
            "No se creó ninguno: el apartamento 303 ya existe en Torre 2.",
        )
        self.assertEqual(Apartment.query.filter_by(tower_id=self.tower["id"]).count(), 1)

    def test_the_message_lists_several_repeated_codes(self):
        self.batch(floor=3, count=3)

        response = self.batch(floor=3, count=5)

        self.assertEqual(response.status_code, 409)
        self.assertIn("los apartamentos 301, 302 y 303 ya existen en Torre 2", response.get_json()["error"])
        self.assertEqual(Apartment.query.filter_by(tower_id=self.tower["id"]).count(), 3)

    def test_invalid_batch_data_is_rejected(self):
        cases = {
            "piso fuera de la torre": {"floor": 9, "count": 2},
            "sin cantidad": {"floor": 3},
            "cantidad cero": {"floor": 3, "count": 0},
            "demasiados": {"floor": 3, "count": 100},
            "cantidad y hasta a la vez": {"floor": 3, "count": 2, "to": 2},
            "hasta menor que desde": {"floor": 3, "from": 5, "to": 2},
            "sin piso": {"count": 2},
        }
        for case, body in cases.items():
            with self.subTest(case=case):
                self.assertEqual(self.batch(**body).status_code, 400)
        self.assertEqual(Apartment.query.filter_by(tower_id=self.tower["id"]).count(), 0)


class ParkingTests(StructureTestCase):
    def create_spot(self, **body):
        return self.call("post", "/api/admin/parking-spots", json=body)

    def test_resident_parking_can_be_assigned_to_an_apartment(self):
        response = self.create_spot(
            code="P-101", type="residente", location="Sótano 1", apartmentId=self.resident.apartment_id
        )

        self.assertEqual(response.status_code, 201)
        spot = response.get_json()["parkingSpot"]
        self.assertEqual((spot["code"], spot["type"], spot["apartment"]), ("P-101", "residente", "Torre 1 · Apto 101"))
        self.assertIn("created", self.audit_actions("parking_spot"))

    def test_visitor_parking_starts_free_and_cannot_be_assigned(self):
        response = self.create_spot(code="V-01", type="visitante", location="Frente a la portería")

        self.assertEqual(response.status_code, 201)
        spot = response.get_json()["parkingSpot"]
        self.assertEqual((spot["isOccupied"], spot["apartment"]), (False, None))
        assigned = self.create_spot(
            code="V-02", type="visitante", location="Entrada", apartmentId=self.resident.apartment_id
        )
        self.assertEqual(assigned.status_code, 400)
        self.assertEqual(ParkingSpot.query.count(), 1)

    def test_repeated_parking_code_is_rejected(self):
        self.create_spot(code="P-101", type="residente", location="Sótano 1")

        for code in ("P-101", "p-101"):
            with self.subTest(code=code):
                response = self.create_spot(code=code, type="visitante", location="Entrada")
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.get_json()["error"], "El parqueadero P-101 ya existe.")
        self.assertEqual(ParkingSpot.query.count(), 1)

    def test_invalid_parking_data_is_rejected(self):
        cases = {
            "sin ubicación": {"code": "P-1", "type": "residente"},
            "tipo inválido": {"code": "P-1", "type": "moto", "location": "Sótano"},
            "sin tipo": {"code": "P-1", "location": "Sótano"},
            "sin código": {"type": "residente", "location": "Sótano"},
            "apartamento inexistente": {
                "code": "P-1", "type": "residente", "location": "Sótano", "apartmentId": 9999,
            },
        }
        for case, body in cases.items():
            with self.subTest(case=case):
                self.assertIn(self.create_spot(**body).status_code, (400, 404))
        self.assertEqual(ParkingSpot.query.count(), 0)

    def test_parking_can_be_assigned_changed_and_released(self):
        spot = self.create_spot(code="P-101", type="residente", location="Sótano 1").get_json()["parkingSpot"]
        path = f"/api/admin/parking-spots/{spot['id']}"

        assigned = self.call("put", path, json={"apartmentId": self.resident.apartment_id})
        self.assertEqual(assigned.get_json()["parkingSpot"]["apartment"], "Torre 1 · Apto 101")
        relocated = self.call("put", path, json={"location": "Sótano 2", "code": "p-102"})
        self.assertEqual(
            (relocated.get_json()["parkingSpot"]["location"], relocated.get_json()["parkingSpot"]["code"]),
            ("Sótano 2", "P-102"),
        )
        self.assertEqual(self.call("put", path, json={"type": "visitante"}).status_code, 400)
        released = self.call("put", path, json={"apartmentId": None})
        self.assertIsNone(released.get_json()["parkingSpot"]["apartmentId"])
        self.assertEqual(self.call("put", path, json={"type": "visitante"}).status_code, 200)

    def test_list_filters_by_type_assignment_and_search(self):
        self.create_spot(code="P-101", type="residente", location="Sótano 1", apartmentId=self.resident.apartment_id)
        self.create_spot(code="P-102", type="residente", location="Sótano 1")
        self.create_spot(code="V-01", type="visitante", location="Entrada")

        def codes(query):
            body = self.call("get", f"/api/admin/parking-spots?{query}").get_json()
            return [spot["code"] for spot in body["parkingSpots"]]

        self.assertEqual(codes(""), ["P-101", "P-102", "V-01"])
        self.assertEqual(codes("type=visitante"), ["V-01"])
        self.assertEqual(codes("assigned=true"), ["P-101"])
        self.assertEqual(codes("assigned=false&type=residente"), ["P-102"])
        self.assertEqual(codes("occupied=false&search=entrada"), ["V-01"])
        self.assertEqual(self.call("get", "/api/admin/parking-spots?type=moto").status_code, 400)
        self.assertEqual(self.call("get", "/api/admin/parking-spots?assigned=quizas").status_code, 400)

    def test_occupied_parking_cannot_be_retired_and_a_free_one_frees_its_code(self):
        spot = self.create_spot(code="V-01", type="visitante", location="Entrada").get_json()["parkingSpot"]
        db.session.get(ParkingSpot, spot["id"]).occupied = True
        db.session.commit()
        path = f"/api/admin/parking-spots/{spot['id']}"

        self.assertEqual(self.call("delete", path).status_code, 409)
        db.session.get(ParkingSpot, spot["id"]).occupied = False
        db.session.commit()
        self.assertEqual(self.call("delete", path).status_code, 200)
        self.assertIsNotNone(db.session.get(ParkingSpot, spot["id"]).retired_at)
        self.assertEqual(self.create_spot(code="V-01", type="visitante", location="Entrada").status_code, 201)


class StorageRoomTests(StructureTestCase):
    def create_room(self, **body):
        return self.call("post", "/api/admin/storage-rooms", json=body)

    def test_storage_room_is_registered_and_assigned_to_an_apartment(self):
        response = self.create_room(code="C-101", apartmentId=self.resident.apartment_id)

        self.assertEqual(response.status_code, 201)
        room = response.get_json()["storageRoom"]
        self.assertEqual((room["code"], room["apartment"]), ("C-101", "Torre 1 · Apto 101"))

    def test_repeated_storage_code_is_rejected(self):
        self.create_room(code="C-101")

        response = self.create_room(code="c-101")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "El cuarto útil C-101 ya existe.")

    def test_storage_room_can_be_reassigned_and_retired(self):
        room = self.create_room(code="C-101").get_json()["storageRoom"]
        path = f"/api/admin/storage-rooms/{room['id']}"

        assigned = self.call("put", path, json={"apartmentId": self.resident.apartment_id})
        self.assertEqual(assigned.get_json()["storageRoom"]["apartment"], "Torre 1 · Apto 101")
        self.assertEqual(self.call("put", path, json={"apartmentId": 9999}).status_code, 404)
        self.assertEqual(self.call("delete", path).status_code, 200)
        self.assertIsNotNone(db.session.get(StorageRoom, room["id"]).retired_at)
        self.assertEqual(self.create_room(code="C-101").status_code, 201)

    def test_list_filters_by_assignment(self):
        self.create_room(code="C-101", apartmentId=self.resident.apartment_id)
        self.create_room(code="C-102")

        free = self.call("get", "/api/admin/storage-rooms?assigned=false").get_json()["storageRooms"]

        self.assertEqual([room["code"] for room in free], ["C-102"])


class ResidentLinkTests(StructureTestCase):
    def setUp(self):
        super().setUp()
        self.apartment = apartment_in("Torre 2", "202")
        db.session.commit()

    def body(self, **extra):
        return {
            "name": "Nuevo", "lastName": "Residente", "email": "nuevo-estructura@test.local",
            "password": "NewUser123*", "role": "RESIDENT", "dataProcessingConsent": True,
            "occupancyType": "arrendatario", **extra,
        }

    def create_resident(self, **extra):
        return self.call("post", "/api/users", json=self.body(**extra))

    def test_resident_is_linked_by_apartment_id_and_sees_apartment_and_occupancy(self):
        response = self.create_resident(apartmentId=self.apartment.id)

        self.assertEqual(response.status_code, 201)
        created = User.query.filter_by(email="nuevo-estructura@test.local").one()
        self.assertEqual(created.apartment_id, self.apartment.id)
        # CA-HU-017-03: el residente ve su apartamento y su tipo de ocupación en su perfil.
        profile = self.call("get", "/api/profile", user=created).get_json()["user"]
        self.assertEqual(
            (profile["apartment"], profile["apartmentId"], profile["occupancyType"]),
            ("Torre 2 · Apto 202", self.apartment.id, "arrendatario"),
        )

    def test_resident_can_still_be_linked_by_the_apartment_text(self):
        for index, text in enumerate(("Torre 2 · Apto 202", "Torre 2 Apto 202", "torre 2, apto 202")):
            with self.subTest(text=text):
                response = self.create_resident(apartment=text, email=f"texto{index}@test.local")
                self.assertEqual(response.status_code, 201)
                self.assertEqual(response.get_json()["user"]["apartmentId"], self.apartment.id)

    def test_occupancy_type_is_required_to_link_a_resident(self):
        body = self.body(apartmentId=self.apartment.id)
        del body["occupancyType"]

        missing = self.call("post", "/api/users", json=body)
        invalid = self.create_resident(apartmentId=self.apartment.id, occupancyType="visitante")

        self.assertEqual(missing.status_code, 400)
        self.assertIn("tipo de ocupación", missing.get_json()["error"])
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(User.query.filter_by(email="nuevo-estructura@test.local").count(), 0)

    def test_resident_can_only_be_linked_to_an_apartment_that_exists(self):
        retired = apartment_in("Torre 2", "999")
        db.session.commit()
        self.assertEqual(self.call("delete", f"/api/admin/apartments/{retired.id}").status_code, 200)

        cases = {
            "id inexistente": {"apartmentId": 99999},
            "texto inexistente": {"apartment": "Torre 7 · Apto 707"},
            "apartamento retirado": {"apartmentId": retired.id},
        }
        for case, extra in cases.items():
            with self.subTest(case=case):
                self.assertEqual(self.create_resident(**extra).status_code, 404)
        self.assertEqual(self.create_resident(apartmentId="uno").status_code, 400)
        self.assertEqual(self.create_resident().status_code, 400)
        self.assertEqual(User.query.filter_by(email="nuevo-estructura@test.local").count(), 0)

    def test_resident_can_be_moved_to_another_apartment_and_unlinked_when_not_resident(self):
        moved = self.call("put", f"/api/users/{self.resident.id}", json={"apartmentId": self.apartment.id})

        self.assertEqual(moved.status_code, 200)
        self.assertEqual(moved.get_json()["user"]["apartment"], "Torre 2 · Apto 202")
        cleared = self.call("put", f"/api/users/{self.resident.id}", json={"apartmentId": None})
        self.assertEqual(cleared.status_code, 400)  # un residente necesita apartamento
        guard = self.call("put", f"/api/users/{self.resident.id}", json={"role": "GUARD"})
        self.assertEqual(guard.status_code, 200)
        self.assertIsNone(guard.get_json()["user"]["apartment"])
        self.assertIsNone(db.session.get(User, self.resident.id).apartment_id)

    def test_promoting_to_resident_needs_occupancy_type_and_apartment(self):
        base = {"role": "RESIDENT", "dataProcessingConsent": True}

        no_occupancy = self.call("put", f"/api/users/{self.guard.id}", json={**base, "apartmentId": self.apartment.id})
        no_apartment = self.call("put", f"/api/users/{self.guard.id}", json={**base, "occupancyType": "propietario"})
        valid = self.call(
            "put", f"/api/users/{self.guard.id}",
            json={**base, "occupancyType": "propietario", "apartmentId": self.apartment.id},
        )

        self.assertEqual((no_occupancy.status_code, no_apartment.status_code, valid.status_code), (400, 400, 200))

    def test_users_can_be_searched_and_filtered_by_apartment_data(self):
        parking_spot("P-101", apartment=self.resident.apartment_ref)
        db.session.commit()

        by_text = self.call("get", "/api/users?search=Apto 101").get_json()["users"]
        with_parking = self.call("get", "/api/users?hasParking=true").get_json()["users"]
        without_storage = self.call("get", "/api/users?hasStorage=false&role=RESIDENT").get_json()["users"]
        in_range = self.call("get", "/api/users?apartmentFrom=100&apartmentTo=150").get_json()["users"]

        self.assertEqual([u["id"] for u in by_text], [self.resident.id])
        self.assertEqual([u["id"] for u in with_parking], [self.resident.id])
        self.assertEqual([u["id"] for u in without_storage], [self.resident.id])
        self.assertEqual([u["id"] for u in in_range], [self.resident.id])

    def test_household_file_is_found_by_apartment_id_or_text(self):
        by_id = self.call("get", f"/api/admin/units?apartmentId={self.resident.apartment_id}")
        by_text = self.call("get", "/api/admin/units?apartment=Torre 1 · Apto 101")
        missing = self.call("get", "/api/admin/units?apartment=Torre 9 · Apto 909")

        self.assertEqual((by_id.status_code, by_text.status_code, missing.status_code), (200, 200, 404))
        unit = by_id.get_json()["unit"]
        self.assertEqual((unit["apartmentId"], unit["apartment"]), (self.resident.apartment_id, "Torre 1 · Apto 101"))
        self.assertEqual(by_id.get_json(), by_text.get_json())

    def test_resident_reads_the_household_file_of_their_own_apartment_with_parking(self):
        parking_spot("P-101", apartment=self.resident.apartment_ref)
        parking_spot("V-01", kind="visitante")
        storage_room("C-101", apartment=self.resident.apartment_ref)
        db.session.commit()

        unit = self.call("get", "/api/profile/unit", user=self.resident).get_json()["unit"]

        self.assertEqual((unit["parkingIdentifier"], unit["storageIdentifier"]), ("P-101", "C-101"))


class DuplicateAndDatabaseTests(StructureTestCase):
    """RN-008 también se cumple en la base: aunque una ruta falle, no entran duplicados."""

    def test_email_duplicate_message_says_which_data_is_repeated(self):
        response = self.call("post", "/api/users", json={
            "name": "Otro", "email": "Residente-Estructura@test.local", "password": "NewUser123*",
            "role": "GUARD",
        })

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "Ese correo ya está registrado")

    def test_database_rejects_a_second_active_tower_with_the_same_name(self):
        db.session.add(Tower(name="Torre 1", floors=3))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_database_rejects_a_second_active_apartment_code_in_a_tower_but_not_in_another(self):
        tower = self.resident.apartment_ref.tower
        db.session.add(Apartment(tower=tower, code="101", floor=1))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        db.session.add(Apartment(tower=tower_named("Torre 2"), code="101", floor=1))
        db.session.commit()

    def test_database_rejects_duplicate_parking_and_storage_codes_but_allows_retired_ones(self):
        parking_spot("P-1")
        storage_room("C-1")
        db.session.commit()

        db.session.add(ParkingSpot(code="P-1", kind="visitante", location="Entrada"))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        db.session.add(StorageRoom(code="C-1"))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        ParkingSpot.query.filter_by(code="P-1").one().retire(self.admin)
        db.session.commit()
        db.session.add(ParkingSpot(code="P-1", kind="visitante", location="Entrada"))
        db.session.commit()

    def test_one_household_file_per_apartment(self):
        db.session.add(ResidentialUnit(apartment_id=self.resident.apartment_id))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()


class StructurePermissionTests(StructureTestCase):
    def test_only_the_admin_reaches_the_structure_endpoints(self):
        tower_id = self.resident.apartment_ref.tower_id
        requests = [
            ("get", "/api/admin/towers", None),
            ("post", "/api/admin/towers", {"name": "Torre 9", "floors": 3}),
            ("put", f"/api/admin/towers/{tower_id}", {"floors": 9}),
            ("delete", f"/api/admin/towers/{tower_id}", None),
            ("get", "/api/admin/apartments", None),
            ("post", "/api/admin/apartments", {"towerId": tower_id, "code": "102", "floor": 1}),
            ("post", "/api/admin/apartments/batch", {"towerId": tower_id, "floor": 2, "count": 2}),
            ("put", f"/api/admin/apartments/{self.resident.apartment_id}", {"floor": 2}),
            ("delete", f"/api/admin/apartments/{self.resident.apartment_id}", None),
            ("get", "/api/admin/parking-spots", None),
            ("post", "/api/admin/parking-spots", {"code": "P-1", "type": "residente", "location": "Sótano"}),
            ("get", "/api/admin/storage-rooms", None),
            ("post", "/api/admin/storage-rooms", {"code": "C-1"}),
        ]
        for method, path, body in requests:
            kwargs = {"json": body} if body is not None else {}
            for user in (self.guard, self.resident):
                with self.subTest(method=method, path=path, role=user.role):
                    self.assertEqual(self.call(method, path, user=user, **kwargs).status_code, 403)
            with self.subTest(method=method, path=path, role="sin sesión"):
                self.assertEqual(getattr(self.client, method)(path, **kwargs).status_code, 401)
        self.assertEqual((Tower.query.count(), Apartment.query.count(), ParkingSpot.query.count()), (1, 1, 0))


class ApartmentTextTests(StructureTestCase):
    def test_the_text_of_an_apartment_is_understood_in_its_usual_forms(self):
        cases = {
            "Torre 1 · Apto 101": ("Torre 1", "101"),
            "Torre 1 Apto 101": ("Torre 1", "101"),
            "torre 2, apartamento 202": ("torre 2", "202"),
            "  Torre   3 ·  Apto #303 ": ("Torre 3", "303"),
            "Torre Norte - Apto A-12": ("Torre Norte", "A-12"),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_apartment_text(text), expected)
        for text in ("Apto 101", "101", "", "Torre 1"):
            with self.subTest(text=text):
                self.assertIsNone(parse_apartment_text(text))

    def test_a_bare_code_only_works_when_the_unit_has_a_single_tower(self):
        self.assertEqual(apartment_by_text("Apto 101").id, self.resident.apartment_id)
        self.assertEqual(apartment_by_text("101").id, self.resident.apartment_id)
        apartment_in("Torre 2", "101")
        db.session.commit()
        self.assertIsNone(apartment_by_text("101"))
        self.assertEqual(apartment_by_text("1 · Apto 101").id, self.resident.apartment_id)
        self.assertIsNone(apartment_by_text(None))


class CensusImportStructureTests(StructureTestCase):
    def csv(self, *rows, header="Apartamento,Nombre,Correo,Parqueadero,Cuarto_Util"):
        return (header + "\n" + "\n".join(rows) + "\n").encode("utf-8")

    def test_census_rows_need_an_apartment_that_exists(self):
        result = import_census_from_bytes(
            self.csv("Torre 1 Apto 101,Ana,ana@test.local,,", "Torre 5 Apto 505,Luis,luis@test.local,,"),
            "censo.csv", self.admin,
        )

        self.assertEqual((result["createdUsers"], result["unitsProcessed"]), (1, 1))
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("Torre 5 Apto 505", result["errors"][0])
        self.assertIn("no existe", result["errors"][0])
        self.assertIsNone(User.query.filter_by(email="luis@test.local").first())

    def test_census_assigns_parking_and_storage_and_never_reassigns_another_apartments(self):
        other = apartment_in("Torre 1", "102")
        parking_spot("P-102", apartment=other)
        parking_spot("V-01", kind="visitante")
        db.session.commit()

        result = import_census_from_bytes(
            self.csv(
                'Torre 1 Apto 101,Ana,ana@test.local,"P-101, P-103",C-101',
                "Torre 1 Apto 101,Ana,ana2@test.local,P-102,",
                "Torre 1 Apto 101,Ana,ana3@test.local,V-01,",
            ),
            "censo.csv", self.admin,
        )

        assigned = {spot.code: spot.apartment.label for spot in ParkingSpot.query.filter(ParkingSpot.apartment_id.isnot(None))}
        self.assertEqual(assigned["P-101"], "Torre 1 · Apto 101")
        self.assertEqual(assigned["P-103"], "Torre 1 · Apto 101")
        self.assertEqual(assigned["P-102"], "Torre 1 · Apto 102")
        self.assertEqual(StorageRoom.query.filter_by(code="C-101").one().apartment_id, self.resident.apartment_id)
        self.assertEqual(result["createdUsers"], 1)
        self.assertEqual(len(result["errors"]), 2)
        self.assertIn("ya está asignado a Torre 1 · Apto 102", result["errors"][0])
        self.assertIn("visitantes", result["errors"][1])
        # Las filas con error no dejaron nada a medias.
        self.assertIsNone(User.query.filter_by(email="ana2@test.local").first())

    def test_new_census_accounts_do_not_share_a_known_password(self):
        import_census_from_bytes(
            self.csv("Torre 1 Apto 101,Ana,ana@test.local,,", "Torre 1 Apto 101,Luis,luis@test.local,,"),
            "censo.csv", self.admin,
        )

        ana = User.query.filter_by(email="ana@test.local").one()
        luis = User.query.filter_by(email="luis@test.local").one()

        self.assertNotEqual(ana.password_hash, luis.password_hash)
        for guess in ("password", "12345678", "Domux2026", "Clave-de-prueba-1*"):
            self.assertFalse(check_password_hash(ana.password_hash, guess))
        login = self.client.post("/api/auth/login", json={"email": "ana@test.local", "password": "password"})
        self.assertEqual(login.status_code, 401)

    def test_import_endpoint_reminds_the_admin_that_new_residents_have_no_password(self):
        import base64
        response = self.call("post", "/api/admin/import-census", json={
            "fileBase64": base64.b64encode(self.csv("Torre 1 Apto 101,Ana,ana@test.local,,")).decode(),
            "fileName": "censo.csv",
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn("aún no tienen contraseña", response.get_json()["message"])


if __name__ == "__main__":
    unittest.main()
