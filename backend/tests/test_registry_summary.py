"""Pruebas de la consulta de paquetería y visitas para la web (HU-088): la lista liviana de paquetes y de
visitas (GET /api/packages y GET /api/visits con view=summary), la lectura de un solo paquete o una sola
visita, la lectura de sus fotos y los números de la lista de vehículos visitantes."""

import base64
import unittest
from datetime import timedelta

import env_setup  # noqa: F401  (va antes de importar la app)

from app import create_app
from auth import generate_token
from extensions import db
from models import PackageItem, User, Visit, VisitEvent, VisitorVehicleEntry
from services import package_view, visit_view
from structure_fixtures import apartment_for
from time_utils import colombia_today, utc_now
from werkzeug.security import generate_password_hash

#: Una foto de mentira bastante grande como para notar si viaja donde no debe.
JPEG = b"\xff\xd8\xff" + b"x" * 5000
PHOTO = "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()
SVG = "data:image/svg+xml;base64," + base64.b64encode(b"<svg xmlns='http://www.w3.org/2000/svg'/>").decode()


class RegistryTestCase(unittest.TestCase):
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
        self.apartment = apartment_for("Torre 1 · Apto 101")
        self.other_apartment = apartment_for("Torre 2 · Apto 202")
        self.admin = self.user("Admin", "admin", "ADMIN")
        self.guard = self.user("Guardia", "guard", "GUARD", last_name="Portería")
        self.resident = self.user("Marta", "resident", "RESIDENT", self.apartment, last_name="Gómez")
        self.housemate = self.user("Luis", "housemate", "RESIDENT", self.apartment, last_name="Gómez")
        self.neighbor = self.user("Pedro", "neighbor", "RESIDENT", self.other_apartment, last_name="Ramos")
        db.session.add_all([self.admin, self.guard, self.resident, self.housemate, self.neighbor])
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def user(self, name, key, role, apartment=None, last_name=None):
        return User(
            name=name, last_name=last_name, email=f"{key}@consulta.test", role=role, is_active=True,
            password_hash=generate_password_hash("Prueba123*"), apartment_ref=apartment,
        )

    def headers(self, user):
        return {"Authorization": f"Bearer {generate_token(user)}"}

    def get(self, path, user=None, **params):
        return self.client.get(path, headers=self.headers(user or self.admin), query_string=params)

    def day(self, offset):
        """La fecha de hoy (en Colombia) más ``offset`` días, como AAAA-MM-DD."""
        return (colombia_today() + timedelta(days=offset)).isoformat()


# ---------------------------------------------------------------------------
# Paquetes
# ---------------------------------------------------------------------------

class PackageTestCase(RegistryTestCase):
    def package(self, resident=None, status="pendiente", arrived_hours_ago=0, created_minutes_ago=None, **fields):
        """Crea un paquete directo en la base; llegó a la portería hace ``arrived_hours_ago`` horas."""
        now = utc_now()
        item = PackageItem(
            resident_id=(resident or self.resident).id, registered_by=self.guard.id, status=status,
            arrived_at=now - timedelta(hours=arrived_hours_ago) if status in ("pendiente", "entregado") else None,
            **{"description": "Caja", **fields},
        )
        if created_minutes_ago is not None:
            item.created_at = now - timedelta(minutes=created_minutes_ago)
        db.session.add(item)
        db.session.commit()
        return item

    def trash(self, package, by=None):
        package.is_deleted = True
        package.deleted_at = utc_now()
        package.deleted_by_id = (by or self.admin).id
        db.session.commit()
        return package

    def summary(self, user=None, **params):
        response = self.get("/api/packages", user, view="summary", **params)
        return response, response.get_json()

    def ids(self, body):
        return [row["id"] for row in body["packages"]]


class PackageSummaryListTests(PackageTestCase):
    def test_rows_are_light_and_carry_what_the_list_shows(self):
        delivered_at = utc_now() - timedelta(hours=2)
        package = self.package(
            status="entregado", arrived_hours_ago=30, description="Caja de libros", carrier="Servientrega",
            tracking_number="SV-123", media_url=PHOTO, media_type="image",
            delivered_at=delivered_at, delivered_to="Tercero Pérez", delivered_by_id=self.admin.id,
        )

        response, body = self.summary(status="entregado")

        self.assertEqual(response.status_code, 200)
        self.assertEqual((body["page"], body["pageSize"], body["total"], body["totalPages"]), (1, 25, 1, 1))
        row = body["packages"][0]
        self.assertEqual(row["id"], package.id)
        self.assertEqual((row["residentId"], row["residentName"]), (self.resident.id, "Marta Gómez"))
        self.assertEqual(row["apartment"], "Torre 1 · Apto 101")
        self.assertEqual((row["description"], row["carrier"], row["trackingNumber"]), ("Caja de libros", "Servientrega", "SV-123"))
        self.assertEqual((row["status"], row["isDeleted"]), ("entregado", False))
        self.assertEqual((row["deliveredTo"], row["deliveredByName"]), ("Tercero Pérez", "Admin"))
        self.assertEqual(row["registeredByName"], "Guardia Portería")
        self.assertEqual((row["mediaType"], row["hasMedia"]), ("image", True))
        self.assertRegex(row["arrivedAt"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
        self.assertRegex(row["deliveredAt"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
        # Lo que pesa no viaja: ni en la fila ni en ninguna otra parte de la respuesta.
        self.assertNotIn("mediaUrl", row)
        self.assertNotIn(PHOTO[30:130], response.get_data(as_text=True))

    def test_a_row_without_photo_or_shipping_data_says_so(self):
        self.package(description="Sobre")

        _response, body = self.summary()

        row = body["packages"][0]
        self.assertFalse(row["hasMedia"])
        self.assertIsNone(row["mediaType"])
        self.assertIsNone(row["carrier"])
        self.assertIsNone(row["trackingNumber"])
        self.assertIsNone(row["deliveredAt"])
        self.assertIsNone(row["deliveredByName"])

    def test_the_full_list_still_carries_the_photo(self):
        # La app depende de esta respuesta: no cambia.
        self.package(media_url=PHOTO, media_type="image")

        body = self.get("/api/packages", self.guard).get_json()

        self.assertEqual(body["packages"][0]["mediaUrl"], PHOTO)
        self.assertNotIn("counts", body)
        self.assertNotIn("page", body)
        self.assertNotIn("hasMedia", body["packages"][0])

    def test_an_unknown_view_is_refused(self):
        response = self.get("/api/packages", view="todo")

        self.assertEqual(response.status_code, 400)
        self.assertIn("solo acepta el valor 'summary'", response.get_json()["error"])

    def test_the_hours_and_the_color_of_the_alert_are_the_ones_of_the_full_list(self):
        self.package(arrived_hours_ago=80, description="Rojo")
        self.package(arrived_hours_ago=50, description="Naranja")
        self.package(arrived_hours_ago=5, description="Reciente")
        self.package(status="por_llegar", description="Por llegar")
        self.package(status="entregado", arrived_hours_ago=90, description="Entregado")

        _response, light = self.summary(status="todos")
        full = {item["id"]: item for item in self.get("/api/packages", self.guard).get_json()["packages"]}

        self.assertEqual(len(light["packages"]), 5)
        for row in light["packages"]:
            self.assertEqual(row["hoursWaiting"], full[row["id"]]["hoursWaiting"], row["description"])
            self.assertEqual(row["claimAlert"], full[row["id"]]["claimAlert"], row["description"])
        by_description = {row["description"]: row for row in light["packages"]}
        self.assertEqual(by_description["Rojo"]["claimAlert"], "rojo")
        self.assertEqual(by_description["Naranja"]["claimAlert"], "naranja")
        self.assertIsNone(by_description["Reciente"]["claimAlert"])
        # Uno entregado ya no espera: no tiene horas ni color.
        self.assertIsNone(by_description["Entregado"]["hoursWaiting"])
        self.assertIsNone(by_description["Entregado"]["claimAlert"])

    def test_those_waiting_come_first_the_longest_waiting_on_top(self):
        newest = self.package(arrived_hours_ago=1)
        oldest = self.package(arrived_hours_ago=60)
        middle = self.package(arrived_hours_ago=20)

        _response, body = self.summary(status="pendiente")

        self.assertEqual(self.ids(body), [oldest.id, middle.id, newest.id])

    def test_everything_else_comes_newest_first(self):
        first = self.package(status="por_llegar", created_minutes_ago=300)
        second = self.package(status="por_llegar", created_minutes_ago=200)
        third = self.package(status="por_llegar", created_minutes_ago=100)

        _response, body = self.summary(status="por_llegar")
        _response, everything = self.summary(status="todos")

        self.assertEqual(self.ids(body), [third.id, second.id, first.id])
        self.assertEqual(self.ids(everything), [third.id, second.id, first.id])

    def test_delivered_come_with_the_latest_delivery_first(self):
        old = self.package(status="entregado", delivered_at=utc_now() - timedelta(days=3))
        recent = self.package(status="entregado", delivered_at=utc_now() - timedelta(hours=1))

        _response, body = self.summary(status="entregado")

        self.assertEqual(self.ids(body), [recent.id, old.id])

    def test_paginated(self):
        made = [self.package(status="por_llegar", created_minutes_ago=10 * number) for number in range(5)]

        _response, first = self.summary(pageSize=2)
        _response, third = self.summary(pageSize=2, page=3)

        self.assertEqual(self.ids(first), [made[0].id, made[1].id])
        self.assertEqual(self.ids(third), [made[4].id])
        self.assertEqual((first["total"], first["totalPages"], third["page"]), (5, 3, 3))

    def test_a_page_outside_the_limits_is_refused(self):
        self.assertEqual(self.summary(pageSize=500)[0].status_code, 400)
        self.assertEqual(self.summary(page=0)[0].status_code, 400)


class PackageSummaryFilterTests(PackageTestCase):
    def setUp(self):
        super().setUp()
        self.waiting = self.package(
            arrived_hours_ago=60, description="Caja grande", carrier="Servientrega", tracking_number="SV-100",
        )
        self.waiting_housemate = self.package(self.housemate, arrived_hours_ago=2, description="Sobre")
        self.incoming = self.package(self.neighbor, status="por_llegar", description="Televisor")
        self.delivered = self.package(
            status="entregado", description="Libros", delivered_to="Tercero Pérez",
            delivered_at=utc_now() - timedelta(days=1),
        )
        self.in_trash = self.trash(self.package(
            self.neighbor, status="entregado", description="Perdido", delivered_to="Alguien",
            delivered_at=utc_now() - timedelta(days=9),
        ))

    def test_without_a_status_the_trash_does_not_show(self):
        _response, body = self.summary()

        self.assertEqual(
            sorted(self.ids(body)),
            sorted([self.waiting.id, self.waiting_housemate.id, self.incoming.id, self.delivered.id]),
        )

    def test_each_status_shows_only_its_own(self):
        self.assertEqual(sorted(self.ids(self.summary(status="pendiente")[1])), sorted([self.waiting.id, self.waiting_housemate.id]))
        self.assertEqual(self.ids(self.summary(status="por_llegar")[1]), [self.incoming.id])
        self.assertEqual(self.ids(self.summary(status="entregado")[1]), [self.delivered.id])
        self.assertEqual(self.ids(self.summary(status="papelera")[1]), [self.in_trash.id])

    def test_all_includes_the_trash(self):
        _response, body = self.summary(status="todos")

        self.assertEqual(len(body["packages"]), 5)
        self.assertIn(self.in_trash.id, self.ids(body))
        trashed = next(row for row in body["packages"] if row["id"] == self.in_trash.id)
        self.assertTrue(trashed["isDeleted"])
        self.assertEqual(trashed["status"], "entregado")

    def test_a_package_in_the_trash_never_counts_as_waiting(self):
        self.trash(self.waiting)

        _response, body = self.summary(status="todos")

        row = next(row for row in body["packages"] if row["id"] == self.waiting.id)
        self.assertIsNone(row["hoursWaiting"])
        self.assertIsNone(row["claimAlert"])

    def test_todos_only_exists_in_the_light_view(self):
        response = self.get("/api/packages", self.guard, status="todos")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Estado de paquete inválido")

    def test_an_invalid_status_is_refused_in_both_views(self):
        self.assertEqual(self.summary(status="perdido")[0].status_code, 400)
        self.assertEqual(self.get("/api/packages", self.guard, status="perdido").status_code, 400)

    def test_the_numbers_of_each_status(self):
        _response, body = self.summary()

        self.assertEqual(body["counts"], {"waiting": 2, "incoming": 1, "delivered": 1, "trash": 1, "all": 5})

    def test_the_numbers_do_not_depend_on_the_status_asked_for(self):
        _response, waiting = self.summary(status="pendiente")
        _response, trash = self.summary(status="papelera")

        self.assertEqual(waiting["counts"], trash["counts"])
        self.assertEqual(waiting["total"], 2)
        self.assertEqual(trash["total"], 1)

    def test_the_search_narrows_the_list_and_the_numbers(self):
        _response, body = self.summary(q="servientrega")

        self.assertEqual(self.ids(body), [self.waiting.id])
        self.assertEqual(body["counts"], {"waiting": 1, "incoming": 0, "delivered": 0, "trash": 0, "all": 1})

    def test_the_search_finds_by_each_of_these_things(self):
        searches = {
            "Marta": {self.waiting.id, self.delivered.id},            # el residente
            "gómez": {self.waiting.id, self.waiting_housemate.id, self.delivered.id},  # el apellido
            "Torre 2": {self.incoming.id, self.in_trash.id},          # el apartamento (con el de la papelera)
            "Apto 101": {self.waiting.id, self.waiting_housemate.id, self.delivered.id},
            "SV-100": {self.waiting.id},                              # la guía
            "Televisor": {self.incoming.id},                          # la descripción
            "Tercero": {self.delivered.id},                           # quien recibió
        }
        for text, expected in searches.items():
            with self.subTest(text):
                _response, body = self.summary(q=text, status="todos")
                self.assertEqual(set(self.ids(body)), expected)
        # «search» es lo mismo que «q».
        _response, body = self.summary(search="Televisor")
        self.assertEqual(self.ids(body), [self.incoming.id])

    def test_the_search_also_reaches_the_trash_when_asked_for_everything(self):
        _response, body = self.summary(q="Perdido", status="todos")

        self.assertEqual(self.ids(body), [self.in_trash.id])

    def test_filtering_by_resident(self):
        _response, body = self.summary(residentId=self.neighbor.id, status="todos")

        self.assertEqual(set(self.ids(body)), {self.incoming.id, self.in_trash.id})

    def test_the_guard_can_also_use_the_light_view(self):
        response, body = self.summary(self.guard, status="pendiente")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(body["packages"]), 2)


class PackageSummaryPermissionTests(PackageTestCase):
    def test_a_resident_only_sees_their_own_packages_in_the_light_view(self):
        mine = self.package()
        self.package(self.housemate)
        self.package(self.neighbor)

        response, body = self.summary(self.resident, status="todos")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.ids(body), [mine.id])
        self.assertEqual(body["counts"]["all"], 1)

    def test_a_resident_cannot_ask_for_the_packages_of_another(self):
        response, _body = self.summary(self.resident, residentId=self.neighbor.id)

        self.assertEqual(response.status_code, 403)

    def test_without_a_session_there_is_nothing(self):
        response = self.client.get("/api/packages?view=summary")

        self.assertEqual(response.status_code, 401)


class SinglePackageTests(PackageTestCase):
    def single(self, package_id, user=None, **params):
        response = self.get(f"/api/packages/{package_id}", user, **params)
        return response, response.get_json()

    def test_the_administration_reads_one_without_the_photo(self):
        package = self.package(
            description="Caja", carrier="Coordinadora", tracking_number="CO-9", media_url=PHOTO, media_type="image",
        )

        response, body = self.single(package.id, view="summary")

        self.assertEqual(response.status_code, 200)
        data = body["packageItem"]
        self.assertEqual((data["id"], data["carrier"], data["trackingNumber"]), (package.id, "Coordinadora", "CO-9"))
        self.assertEqual((data["residentName"], data["apartment"]), ("Marta Gómez", "Torre 1 · Apto 101"))
        self.assertTrue(data["hasMedia"])
        self.assertNotIn("mediaUrl", data)
        self.assertNotIn(PHOTO[30:130], response.get_data(as_text=True))
        self.assertIsNone(data["deletedByName"])

    def test_the_complete_version_still_carries_the_photo(self):
        package = self.package(media_url=PHOTO, media_type="image")

        _response, body = self.single(package.id)

        self.assertEqual(body["packageItem"]["mediaUrl"], PHOTO)
        self.assertNotIn("hasMedia", body["packageItem"])

    def test_one_in_the_trash_says_who_sent_it_there(self):
        package = self.trash(self.package(status="entregado"), by=self.guard)

        _response, body = self.single(package.id, view="summary")

        self.assertTrue(body["packageItem"]["isDeleted"])
        self.assertEqual(body["packageItem"]["deletedByName"], "Guardia Portería")
        self.assertIsNotNone(body["packageItem"]["deletedAt"])

    def test_it_says_if_it_has_a_delivery_code(self):
        package = self.package()

        _response, body = self.single(package.id, view="summary")

        self.assertFalse(body["packageItem"]["hasPickupCode"])

    def test_the_guard_reads_any_package(self):
        package = self.package(self.neighbor)

        response, _body = self.single(package.id, self.guard)

        self.assertEqual(response.status_code, 200)

    def test_a_resident_reads_theirs_but_not_those_of_others(self):
        mine = self.package()
        other = self.package(self.neighbor)

        self.assertEqual(self.single(mine.id, self.resident)[0].status_code, 200)
        response, body = self.single(other.id, self.resident)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(body["error"], "Paquete no encontrado")

    def test_a_package_that_does_not_exist_is_a_404(self):
        response, body = self.single(9999)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(body["error"], "Paquete no encontrado")

    def test_an_unknown_view_is_refused(self):
        package = self.package()

        response, _body = self.single(package.id, view="todo")

        self.assertEqual(response.status_code, 400)


class PackagePhotoTests(PackageTestCase):
    def test_the_photo_is_read_as_bytes_and_type(self):
        package = self.package(media_url=PHOTO, media_type="image")

        self.assertEqual(package_view.attachment(package.id), (JPEG, "image/jpeg"))

    def test_one_in_the_trash_still_has_its_photo(self):
        package = self.trash(self.package(media_url=PHOTO, media_type="image"))

        self.assertEqual(package_view.attachment(package.id), (JPEG, "image/jpeg"))

    def test_there_is_nothing_to_read_without_a_photo_or_for_an_unknown_package(self):
        package = self.package()

        self.assertIsNone(package_view.attachment(package.id))
        self.assertIsNone(package_view.attachment(9999))

    def test_something_that_is_not_an_image_is_not_shown(self):
        package = self.package(media_url=SVG, media_type="image")

        self.assertIsNone(package_view.attachment(package.id))


# ---------------------------------------------------------------------------
# Visitas
# ---------------------------------------------------------------------------

class VisitTestCase(RegistryTestCase):
    def visit(
        self, resident=None, name="Visita", status="aprobada", entered_minutes_ago=None, exited_minutes_ago=None,
        created_minutes_ago=None, stay=None, **fields,
    ):
        """Crea una visita directo en la base; los minutos cuentan desde ahora hacia atrás."""
        now = utc_now()
        item = Visit(
            resident_id=(resident or self.resident).id, registered_by=self.guard.id, visitor_name=name,
            type=fields.pop("type", "visitante"), approval_status=status,
            authorization_method="app" if status != "pendiente" else None, expected_stay_minutes=stay,
            entered_at=now - timedelta(minutes=entered_minutes_ago) if entered_minutes_ago is not None else None,
            exited_at=now - timedelta(minutes=exited_minutes_ago) if exited_minutes_ago is not None else None,
            **fields,
        )
        if created_minutes_ago is not None:
            item.created_at = now - timedelta(minutes=created_minutes_ago)
        db.session.add(item)
        db.session.commit()
        return item

    def summary(self, user=None, **params):
        response = self.get("/api/visits", user, view="summary", **params)
        return response, response.get_json()

    def names(self, body):
        return [row["visitorName"] for row in body["visits"]]


class VisitSummaryListTests(VisitTestCase):
    def test_rows_are_light_and_carry_what_the_list_shows(self):
        visit = self.visit(
            name="Carlos Ruiz", entered_minutes_ago=90, stay=60, visitor_document="123456",
            visitor_photo_url=PHOTO, visitor_photo_type="image", media_consent=True,
            description="Domicilio de comida",
        )
        visit.events.append(VisitEvent(event_type="solicitud", method="app", actor_id=self.guard.id))
        db.session.commit()

        response, body = self.summary()

        self.assertEqual(response.status_code, 200)
        self.assertEqual((body["page"], body["pageSize"], body["total"], body["totalPages"]), (1, 50, 1, 1))
        row = body["visits"][0]
        self.assertEqual((row["id"], row["visitorName"], row["type"]), (visit.id, "Carlos Ruiz", "visitante"))
        self.assertEqual((row["residentName"], row["apartment"]), ("Marta Gómez", "Torre 1 · Apto 101"))
        self.assertEqual((row["approvalStatus"], row["authorizationMethod"]), ("aprobada", "app"))
        self.assertEqual(row["registeredByName"], "Guardia Portería")
        self.assertEqual(row["description"], "Domicilio de comida")
        self.assertTrue(row["hasPhoto"])
        self.assertRegex(row["enteredAt"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
        self.assertIsNone(row["exitedAt"])
        self.assertEqual((row["isInside"], row["expectedStayMinutes"], row["isOverstay"]), (True, 60, True))
        self.assertGreaterEqual(row["insideMinutes"], 90)
        # Lo que pesa o es delicado no viaja en la lista: ni la foto, ni el documento, ni los eventos.
        for forbidden in ("visitorPhotoUrl", "visitorDocument", "events"):
            self.assertNotIn(forbidden, row)
        self.assertNotIn(PHOTO[30:130], response.get_data(as_text=True))

    def test_a_visit_that_has_not_entered_is_not_inside(self):
        self.visit(status="pendiente")

        _response, body = self.summary()

        row = body["visits"][0]
        self.assertEqual((row["isInside"], row["insideMinutes"], row["isOverstay"]), (False, None, False))
        self.assertFalse(row["hasPhoto"])
        self.assertIsNone(row["authorizationMethod"])

    def test_a_photo_without_the_consent_of_the_visitor_is_not_announced(self):
        self.visit(visitor_photo_url=PHOTO, visitor_photo_type="image", media_consent=False)

        response, body = self.summary()

        self.assertFalse(body["visits"][0]["hasPhoto"])
        self.assertNotIn(PHOTO[30:130], response.get_data(as_text=True))

    def test_one_that_already_left_is_not_inside_even_if_it_overstayed(self):
        self.visit(entered_minutes_ago=300, exited_minutes_ago=100, stay=30)

        _response, body = self.summary()

        row = body["visits"][0]
        self.assertEqual((row["isInside"], row["insideMinutes"], row["isOverstay"]), (False, None, False))
        self.assertIsNotNone(row["exitedAt"])

    def test_the_inside_data_is_the_one_of_the_full_list(self):
        self.visit(name="A", entered_minutes_ago=200, stay=60)
        self.visit(name="B", entered_minutes_ago=20, stay=60)
        self.visit(name="C", entered_minutes_ago=20)
        self.visit(name="D", entered_minutes_ago=200, exited_minutes_ago=10, stay=30)
        self.visit(name="E", status="pendiente")

        _response, light = self.summary()
        full = {
            item["id"]: item for item in self.get("/api/visits").get_json()["visits"]
        }

        self.assertEqual(len(light["visits"]), 5)
        for row in light["visits"]:
            expected = full[row["id"]]
            self.assertEqual(row["insideMinutes"], expected["insideMinutes"], row["visitorName"])
            self.assertEqual(row["isOverstay"], expected["isOverstay"], row["visitorName"])
        by_name = {row["visitorName"]: row for row in light["visits"]}
        self.assertTrue(by_name["A"]["isOverstay"])
        self.assertFalse(by_name["B"]["isOverstay"])
        self.assertFalse(by_name["C"]["isOverstay"])

    def test_the_full_list_still_carries_the_photo_and_the_events(self):
        # La app depende de esta respuesta: no cambia.
        visit = self.visit(visitor_photo_url=PHOTO, visitor_photo_type="image", media_consent=True)
        visit.events.append(VisitEvent(event_type="solicitud", method="app", actor_id=self.guard.id))
        db.session.commit()

        body = self.get("/api/visits").get_json()

        self.assertEqual(body["visits"][0]["visitorPhotoUrl"], PHOTO)
        self.assertEqual(len(body["visits"][0]["events"]), 1)
        self.assertNotIn("counts", body)
        self.assertNotIn("hasPhoto", body["visits"][0])

    def test_an_unknown_view_is_refused(self):
        response = self.get("/api/visits", view="todo")

        self.assertEqual(response.status_code, 400)

    def test_newest_first_and_paginated(self):
        made = [self.visit(name=f"Visita {number}", created_minutes_ago=10 * number) for number in range(5)]

        _response, first = self.summary(pageSize=2)
        _response, third = self.summary(pageSize=2, page=3)

        self.assertEqual(self.names(first), [made[0].visitor_name, made[1].visitor_name])
        self.assertEqual(self.names(third), [made[4].visitor_name])
        self.assertEqual((first["total"], first["totalPages"], third["page"]), (5, 3, 3))

    def test_those_inside_come_with_the_longest_inside_first(self):
        self.visit(name="Reciente", entered_minutes_ago=10)
        self.visit(name="Antigua", entered_minutes_ago=300)
        self.visit(name="Media", entered_minutes_ago=100)
        self.visit(name="Ya salió", entered_minutes_ago=400, exited_minutes_ago=300)

        _response, body = self.summary(inside="true")

        self.assertEqual(self.names(body), ["Antigua", "Media", "Reciente"])

    def test_a_page_outside_the_limits_is_refused(self):
        self.assertEqual(self.summary(pageSize=500)[0].status_code, 400)
        self.assertEqual(self.summary(page=0)[0].status_code, 400)


class VisitSummaryFilterTests(VisitTestCase):
    def setUp(self):
        super().setUp()
        self.inside = self.visit(name="Ana Dentro", entered_minutes_ago=60, created_minutes_ago=60)
        # Dos días atrás: así las pruebas de fechas no dependen de la hora del día en que se corran.
        two_days = 60 * 24 * 2
        self.left = self.visit(
            name="Beto Salió", entered_minutes_ago=two_days, exited_minutes_ago=two_days - 100,
            created_minutes_ago=two_days,
        )
        self.pending = self.visit(self.neighbor, name="Carla Pendiente", status="pendiente", created_minutes_ago=30)
        self.rejected = self.visit(self.housemate, name="Dani Rechazado", status="rechazada", created_minutes_ago=20)
        self.old = self.visit(name="Eva Antigua", entered_minutes_ago=60 * 24 * 10 + 5, exited_minutes_ago=60 * 24 * 10, created_minutes_ago=60 * 24 * 10 + 10)

    def test_the_numbers_of_each_tab(self):
        _response, body = self.summary()

        self.assertEqual(body["counts"], {"inside": 1, "pending": 1, "approved": 3, "rejected": 1, "all": 5})

    def test_the_numbers_do_not_depend_on_the_status_nor_on_inside(self):
        _response, rejected = self.summary(status="rechazada")
        _response, inside = self.summary(inside="true")

        self.assertEqual(rejected["counts"], inside["counts"])
        self.assertEqual(rejected["counts"]["all"], 5)
        self.assertEqual(self.names(rejected), ["Dani Rechazado"])
        self.assertEqual(self.names(inside), ["Ana Dentro"])

    def test_each_status_shows_only_its_own(self):
        self.assertEqual(self.names(self.summary(status="pendiente")[1]), ["Carla Pendiente"])
        self.assertEqual(self.names(self.summary(status="rechazada")[1]), ["Dani Rechazado"])
        self.assertEqual(
            set(self.names(self.summary(status="aprobada")[1])), {"Ana Dentro", "Beto Salió", "Eva Antigua"},
        )

    def test_an_invalid_status_is_refused(self):
        response, body = self.summary(status="perdida")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(body["error"], "Estado de visita inválido.")

    def test_the_search_narrows_the_list_and_the_numbers(self):
        _response, body = self.summary(search="beto")

        self.assertEqual(self.names(body), ["Beto Salió"])
        self.assertEqual(body["counts"], {"inside": 0, "pending": 0, "approved": 1, "rejected": 0, "all": 1})

    def test_the_search_also_finds_by_resident_and_apartment(self):
        _response, by_resident = self.summary(search="Pedro")
        _response, by_apartment = self.summary(search="Torre 2")

        self.assertEqual(self.names(by_resident), ["Carla Pendiente"])
        self.assertEqual(self.names(by_apartment), ["Carla Pendiente"])

    def test_the_dates_narrow_the_list_and_the_numbers(self):
        _response, recent = self.summary(**{"from": self.day(-3)})
        _response, old = self.summary(**{"to": self.day(-5)})

        self.assertEqual(self.names(old), ["Eva Antigua"])
        self.assertEqual(old["counts"]["all"], 1)
        self.assertEqual(
            set(self.names(recent)), {"Ana Dentro", "Beto Salió", "Carla Pendiente", "Dani Rechazado"},
        )
        self.assertEqual(recent["counts"]["all"], 4)

    def test_a_single_day_includes_the_visits_of_that_day(self):
        self.visit(name="Hoy mismo", created_minutes_ago=0)

        _response, today = self.summary(**{"from": self.day(0), "to": self.day(0)})

        self.assertIn("Hoy mismo", self.names(today))
        self.assertNotIn("Eva Antigua", self.names(today))
        self.assertNotIn("Beto Salió", self.names(today))
        self.assertEqual(today["counts"]["all"], len(today["visits"]))

    def test_filtering_by_apartment(self):
        _response, body = self.summary(apartmentId=self.other_apartment.id)

        self.assertEqual(self.names(body), ["Carla Pendiente"])

    def test_a_wrong_date_or_a_reversed_range_is_refused(self):
        self.assertEqual(self.summary(**{"from": "ayer"})[0].status_code, 400)
        self.assertEqual(self.summary(**{"from": self.day(0), "to": self.day(-3)})[0].status_code, 400)


class VisitSummaryPermissionTests(VisitTestCase):
    def test_a_resident_only_sees_the_visits_of_their_apartment(self):
        self.visit(name="De mi casa")
        self.visit(self.housemate, name="De mi compañero")
        self.visit(self.neighbor, name="Del vecino")

        response, body = self.summary(self.resident)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(self.names(body)), {"De mi casa", "De mi compañero"})
        self.assertEqual(body["counts"]["all"], 2)

    def test_the_guard_sees_all_of_them(self):
        self.visit(name="Uno")
        self.visit(self.neighbor, name="Dos")

        _response, body = self.summary(self.guard)

        self.assertEqual(set(self.names(body)), {"Uno", "Dos"})

    def test_without_a_session_there_is_nothing(self):
        self.assertEqual(self.client.get("/api/visits?view=summary").status_code, 401)


class SingleVisitTests(VisitTestCase):
    def single(self, visit_id, user=None, **params):
        response = self.get(f"/api/visits/{visit_id}", user, **params)
        return response, response.get_json()

    def make_complete_visit(self):
        visit = self.visit(
            name="Carlos Ruiz", entered_minutes_ago=30, visitor_document="123456",
            visitor_photo_url=PHOTO, visitor_photo_type="image", media_consent=True,
        )
        visit.events.extend([
            VisitEvent(event_type="solicitud", method="app", actor_id=self.guard.id),
            VisitEvent(event_type="aprobada", method="app", actor_id=self.resident.id),
            VisitEvent(event_type="entrada", method="app", actor_id=self.guard.id),
        ])
        db.session.commit()
        return visit

    def test_the_administration_reads_one_with_its_events_but_without_the_photo(self):
        visit = self.make_complete_visit()

        response, body = self.single(visit.id, view="summary")

        self.assertEqual(response.status_code, 200)
        data = body["visit"]
        self.assertEqual((data["id"], data["visitorName"], data["visitorDocument"]), (visit.id, "Carlos Ruiz", "123456"))
        self.assertEqual([event["type"] for event in data["events"]], ["solicitud", "aprobada", "entrada"])
        self.assertEqual(data["events"][1]["actorName"], "Marta Gómez")
        self.assertTrue(data["hasPhoto"])
        self.assertTrue(data["mediaConsent"])
        self.assertTrue(data["isInside"])
        self.assertNotIn("visitorPhotoUrl", data)
        self.assertNotIn(PHOTO[30:130], response.get_data(as_text=True))

    def test_a_visit_that_is_not_inside_says_so(self):
        waiting = self.visit(status="pendiente")
        left = self.visit(entered_minutes_ago=120, exited_minutes_ago=60)

        self.assertFalse(self.single(waiting.id, view="summary")[1]["visit"]["isInside"])
        self.assertFalse(self.single(left.id, view="summary")[1]["visit"]["isInside"])

    def test_a_photo_without_the_consent_of_the_visitor_is_not_announced_in_the_detail(self):
        visit = self.visit(visitor_photo_url=PHOTO, visitor_photo_type="image", media_consent=False)

        response, body = self.single(visit.id, view="summary")

        self.assertFalse(body["visit"]["hasPhoto"])
        self.assertNotIn("visitorPhotoUrl", body["visit"])
        self.assertNotIn(PHOTO[30:130], response.get_data(as_text=True))

    def test_the_complete_version_still_carries_the_photo(self):
        visit = self.make_complete_visit()

        _response, body = self.single(visit.id)

        self.assertEqual(body["visit"]["visitorPhotoUrl"], PHOTO)
        self.assertNotIn("hasPhoto", body["visit"])

    def test_the_guard_reads_any_visit(self):
        visit = self.visit(self.neighbor)

        self.assertEqual(self.single(visit.id, self.guard)[0].status_code, 200)

    def test_a_resident_reads_those_of_their_apartment_but_not_others(self):
        mine = self.visit()
        housemates = self.visit(self.housemate)
        other = self.visit(self.neighbor)

        self.assertEqual(self.single(mine.id, self.resident)[0].status_code, 200)
        self.assertEqual(self.single(housemates.id, self.resident)[0].status_code, 200)
        response, body = self.single(other.id, self.resident)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(body["error"], "Visita no encontrada.")

    def test_a_visit_that_does_not_exist_is_a_404(self):
        response, body = self.single(9999)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(body["error"], "Visita no encontrada.")


class VisitPhotoTests(VisitTestCase):
    def test_the_photo_is_read_as_bytes_and_type(self):
        visit = self.visit(visitor_photo_url=PHOTO, visitor_photo_type="image", media_consent=True)

        self.assertEqual(visit_view.photo(visit.id), (JPEG, "image/jpeg"))

    def test_without_the_consent_of_the_visitor_it_is_not_shown(self):
        visit = self.visit(visitor_photo_url=PHOTO, visitor_photo_type="image", media_consent=False)

        self.assertIsNone(visit_view.photo(visit.id))

    def test_there_is_nothing_to_read_without_a_photo_or_for_an_unknown_visit(self):
        visit = self.visit(media_consent=True)

        self.assertIsNone(visit_view.photo(visit.id))
        self.assertIsNone(visit_view.photo(9999))

    def test_something_that_is_not_an_image_is_not_shown(self):
        visit = self.visit(visitor_photo_url=SVG, visitor_photo_type="image", media_consent=True)

        self.assertIsNone(visit_view.photo(visit.id))


# ---------------------------------------------------------------------------
# Vehículos de visitantes
# ---------------------------------------------------------------------------

class VehicleCountsTests(RegistryTestCase):
    def entry(self, plate, days_ago, exited=False, resident=None):
        visit = Visit(
            resident_id=(resident or self.resident).id, registered_by=self.guard.id, visitor_name="Visitante",
            type="visitante", approval_status="aprobada", authorization_method="app", entered_at=utc_now(),
        )
        db.session.add(visit)
        db.session.flush()
        now = utc_now()
        entry = VisitorVehicleEntry(
            plate=plate, visit_id=visit.id, apartment_id=(resident or self.resident).apartment_id,
            entered_at=now - timedelta(days=days_ago), registered_by=self.guard.id,
            exited_at=now - timedelta(days=days_ago, hours=-3) if exited else None,
        )
        db.session.add(entry)
        db.session.commit()
        return entry

    def listing(self, **params):
        response = self.get("/api/vehicle-entries", **params)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def test_the_numbers_come_only_when_asked_for(self):
        self.entry("ABC123", days_ago=1)

        self.assertNotIn("counts", self.listing())
        self.assertIn("counts", self.listing(counts="true"))

    def test_the_numbers_of_each_situation(self):
        self.entry("ABC123", days_ago=1)                       # adentro
        self.entry("XYZ789", days_ago=5)                       # adentro y vencido (más de 3 días)
        self.entry("DEF456", days_ago=8, exited=True)          # ya salió
        self.entry("GHI111", days_ago=2, exited=True, resident=self.neighbor)

        body = self.listing(counts="true")

        self.assertEqual(body["counts"], {"inside": 2, "overdue": 1, "exited": 2, "all": 4})
        self.assertEqual(body["total"], 4)

    def test_the_numbers_do_not_depend_on_the_state_asked_for_but_on_the_plate(self):
        self.entry("ABC123", days_ago=1)
        self.entry("ABC123", days_ago=9, exited=True)
        self.entry("XYZ789", days_ago=5)

        everything = self.listing(counts="true", inside="true")
        by_plate = self.listing(counts="true", plate="abc")

        self.assertEqual(everything["total"], 2)
        self.assertEqual(everything["counts"], {"inside": 2, "overdue": 1, "exited": 1, "all": 3})
        self.assertEqual(by_plate["counts"], {"inside": 1, "overdue": 0, "exited": 1, "all": 2})

    def test_the_numbers_follow_the_apartment(self):
        self.entry("ABC123", days_ago=1)
        self.entry("GHI111", days_ago=1, resident=self.neighbor)

        body = self.listing(counts="true", apartmentId=self.other_apartment.id)

        self.assertEqual(body["counts"], {"inside": 1, "overdue": 0, "exited": 0, "all": 1})

    def test_a_wrong_flag_is_refused(self):
        response = self.get("/api/vehicle-entries", counts="quizás")

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
