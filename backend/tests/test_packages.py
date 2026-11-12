"""Pruebas de los paquetes: transportadora y guía, código de entrega y alertas (HU-047, HU-048 y HU-049).

Cubren lo que el guardia anota al registrar el paquete, los colores de las
48 y 72 horas sin reclamar (RN-018), el código de entrega que genera el
residente (QR y PIN), su validación al entregar —un código usado, anulado o de
otro paquete no entrega— y que cinco PIN errados anulan el código.
"""

import unittest
from datetime import timedelta
from unittest import mock

import env_setup  # noqa: F401  (va antes de importar la app)

from sqlalchemy import event, update
from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from auth import generate_token
from errors import ApiError
from extensions import db
from models import AuditLog, Notification, PackageItem, PackagePickupCode, User
from services import package_service
from structure_fixtures import apartment_for
from time_utils import utc_now

QR_PREFIX = "DOMUX-PKG:"


class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.apartment = apartment_for("Torre 1 · Apto 101")
        self.other_apartment = apartment_for("Torre 2 · Apto 202")
        self.admin = self.user("Admin", "admin", "ADMIN")
        self.guard = self.user("Guardia", "guard", "GUARD")
        self.resident = self.user("Residente", "resident", "RESIDENT", self.apartment)
        self.housemate = self.user("Compañero", "housemate", "RESIDENT", self.apartment)
        self.neighbor = self.user("Vecino", "neighbor", "RESIDENT", self.other_apartment)
        db.session.add_all([self.admin, self.guard, self.resident, self.housemate, self.neighbor])
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def user(self, name, key, role, apartment=None):
        return User(
            name=name, email=f"{key}@paquetes.test", role=role, is_active=True,
            password_hash=generate_password_hash("Prueba123*"), apartment_ref=apartment,
        )

    def auth(self, user):
        return {"Authorization": f"Bearer {generate_token(user)}"}

    def make_package(self, resident=None, status="pendiente", arrived_minutes_ago=0, **fields):
        """Crea un paquete directo en la base; arrived_minutes_ago son los minutos desde que llegó."""
        fields.setdefault("description", "Caja")
        arrived = None
        if status in ("pendiente", "entregado"):
            arrived = utc_now() - timedelta(minutes=arrived_minutes_ago)
        package = PackageItem(
            resident_id=(resident or self.resident).id, registered_by=self.guard.id,
            status=status, arrived_at=arrived, **fields,
        )
        db.session.add(package)
        db.session.commit()
        return package

    def register(self, **fields):
        body = {"residentId": self.resident.id, "description": "Caja"}
        body.update(fields)
        return self.client.post("/api/packages", headers=self.auth(self.guard), json=body)

    def set_status(self, package_id, status):
        return self.client.put(
            f"/api/packages/{package_id}/status", headers=self.auth(self.guard), json={"status": status}
        )

    def list_packages(self, query="", user=None):
        response = self.client.get(f"/api/packages?{query}", headers=self.auth(user or self.guard))
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["packages"]

    def generate(self, package, user=None):
        """El residente genera el código de entrega; devuelve {'qrData': ..., 'pin': ...}."""
        response = self.client.post(
            f"/api/packages/{package.id}/pickup-code", headers=self.auth(user or self.resident)
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["pickupCode"]

    def lookup(self, code, user=None):
        return self.client.post(
            "/api/packages/pickup-lookup", headers=self.auth(user or self.guard), json={"code": code}
        )

    def deliver(self, package, receiver="Tercero Pérez", **fields):
        body = {"receivedBy": receiver}
        body.update(fields)
        return self.client.put(
            f"/api/packages/{package.id}/deliver", headers=self.auth(self.guard), json=body
        )

    def stored_code(self, package=None):
        query = PackagePickupCode.query
        if package is not None:
            query = query.filter_by(package_id=package.id)
        return query.order_by(PackagePickupCode.id.desc()).first()

    # --- Transportadora y guía (HU-047) -------------------------------------

    def test_registering_with_carrier_and_guide_shows_them_and_names_the_carrier_in_the_notice(self):
        response = self.register(carrier="Servientrega", trackingNumber="SV-12345")

        self.assertEqual(response.status_code, 201)
        package = response.get_json()["packageItem"]
        self.assertEqual(package["carrier"], "Servientrega")
        self.assertEqual(package["trackingNumber"], "SV-12345")
        stored = PackageItem.query.one()
        self.assertEqual((stored.carrier, stored.tracking_number), ("Servientrega", "SV-12345"))
        notice = Notification.query.filter_by(user_id=self.resident.id).one()
        self.assertIn("Servientrega", notice.message)

    def test_carrier_and_guide_are_optional_and_cleaned_up(self):
        plain = self.register().get_json()["packageItem"]
        self.assertIsNone(plain["carrier"])
        self.assertIsNone(plain["trackingNumber"])
        explicit_nulls = self.register(carrier=None, trackingNumber=None)
        self.assertEqual(explicit_nulls.status_code, 201)

        spaced = self.register(carrier="  Inter   Rapidísimo ", trackingNumber=" 99 ")

        self.assertEqual(spaced.get_json()["packageItem"]["carrier"], "Inter Rapidísimo")
        self.assertEqual(spaced.get_json()["packageItem"]["trackingNumber"], "99")

    def test_an_invalid_carrier_or_guide_is_refused(self):
        for field in ("carrier", "trackingNumber"):
            for value in ("x" * 61, 5, ["a"], "   "):
                with self.subTest(field=field, value=value):
                    self.assertEqual(self.register(**{field: value}).status_code, 400)
        self.assertEqual(PackageItem.query.count(), 0)
        self.assertEqual(self.register(carrier="x" * 60, trackingNumber="y" * 60).status_code, 201)

    def test_search_finds_packages_by_carrier_or_guide(self):
        self.make_package(description="Libros", carrier="Servientrega", tracking_number="SV-777")
        self.make_package(description="Ropa", carrier="Coordinadora", tracking_number="CO-123")

        def found(term, user=None):
            return [item["description"] for item in self.list_packages(f"search={term}", user)]

        self.assertEqual(found("servi"), ["Libros"])
        self.assertEqual(found("CO-12"), ["Ropa"])
        self.assertEqual(found("zzz"), [])
        self.assertEqual(found("servi", self.resident), ["Libros"])
        self.assertEqual(found("servi", self.neighbor), [])

    # --- Alertas de 48 y 72 horas (HU-049, RN-018) --------------------------

    def test_the_alert_turns_orange_after_48_hours_and_red_after_72(self):
        package = self.make_package()
        arrived = package.arrived_at
        cases = [
            (0, None),
            (48 * 60, None),  # justo 48 horas todavía no es «más de 48»
            (48 * 60 + 1, "naranja"),
            (72 * 60, "naranja"),
            (72 * 60 + 1, "rojo"),
        ]
        for minutes, expected in cases:
            with self.subTest(minutes=minutes):
                self.assertEqual(package.claim_alert(arrived + timedelta(minutes=minutes)), expected)

    def test_the_list_marks_each_package_with_its_alert_and_hours_waiting(self):
        self.make_package(description="Nuevo", arrived_minutes_ago=30 * 60)
        self.make_package(description="Naranja", arrived_minutes_ago=50 * 60)
        self.make_package(description="Rojo", arrived_minutes_ago=80 * 60)

        items = {item["description"]: item for item in self.list_packages()}

        self.assertEqual((items["Nuevo"]["claimAlert"], items["Nuevo"]["hoursWaiting"]), (None, 30))
        self.assertEqual((items["Naranja"]["claimAlert"], items["Naranja"]["hoursWaiting"]), ("naranja", 50))
        self.assertEqual((items["Rojo"]["claimAlert"], items["Rojo"]["hoursWaiting"]), ("rojo", 80))
        mine = self.list_packages(user=self.resident)
        self.assertEqual({item["claimAlert"] for item in mine}, {None, "naranja", "rojo"})

    def test_only_packages_waiting_in_the_porteria_have_an_alert(self):
        long_ago = 100 * 60
        delivered = self.make_package(
            status="entregado", arrived_minutes_ago=long_ago, delivered_at=utc_now(), delivered_to="Ana"
        )
        coming = self.make_package(status="por_llegar")
        trashed = self.make_package(arrived_minutes_ago=long_ago, is_deleted=True, deleted_at=utc_now())

        for package in (delivered, coming, trashed):
            with self.subTest(package=package.id):
                self.assertIsNone(package.waiting_minutes())
                self.assertIsNone(package.claim_alert())
                self.assertIsNone(package.to_dict()["hoursWaiting"])

    def test_the_arrival_time_starts_when_the_package_reaches_the_porteria(self):
        coming = self.register(status="por_llegar").get_json()["packageItem"]
        self.assertIsNone(coming["arrivedAt"])
        self.assertIsNone(coming["hoursWaiting"])

        arrived = self.set_status(coming["id"], "pendiente").get_json()["packageItem"]
        self.assertIsNotNone(arrived["arrivedAt"])
        self.assertEqual(arrived["hoursWaiting"], 0)

        back = self.set_status(coming["id"], "por_llegar").get_json()["packageItem"]
        self.assertIsNone(back["arrivedAt"])
        self.assertIsNone(back["hoursWaiting"])

        direct = self.register().get_json()["packageItem"]
        self.assertIsNotNone(direct["arrivedAt"])

    def test_confirming_the_same_status_does_not_restart_the_clock(self):
        package = self.make_package(arrived_minutes_ago=50 * 60)
        before = package.arrived_at

        self.assertEqual(self.set_status(package.id, "pendiente").status_code, 200)

        self.assertEqual(db.session.get(PackageItem, package.id).arrived_at, before)
        self.assertEqual(self.list_packages()[0]["claimAlert"], "naranja")

    def test_a_delivered_package_cannot_go_back_to_another_status(self):
        package = self.make_package(status="entregado", delivered_at=utc_now(), delivered_to="Ana")

        response = self.set_status(package.id, "pendiente")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(db.session.get(PackageItem, package.id).status, "entregado")

    # --- Generar el código de entrega (HU-048) ------------------------------

    def test_the_resident_generates_a_code_with_qr_and_pin(self):
        package = self.make_package()

        response = self.client.post(
            f"/api/packages/{package.id}/pickup-code", headers=self.auth(self.resident)
        )

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        code = body["pickupCode"]
        self.assertTrue(code["qrData"].startswith(QR_PREFIX))
        self.assertRegex(code["pin"], r"^\d{6}$")
        self.assertTrue(body["packageItem"]["hasPickupCode"])
        stored = self.stored_code()
        self.assertEqual(code["qrData"], QR_PREFIX + stored.token)
        self.assertEqual((stored.package_id, stored.created_by_id), (package.id, self.resident.id))
        # El PIN no queda guardado: solo su hash.
        self.assertNotEqual(stored.pin_hash, code["pin"])
        self.assertTrue(check_password_hash(stored.pin_hash, code["pin"]))
        self.assertEqual(AuditLog.query.filter_by(action="pickup_code_created").count(), 1)

    def test_the_pin_keeps_its_leading_zeros(self):
        package = self.make_package()

        with mock.patch.object(package_service.secrets, "randbelow", return_value=42):
            code = self.generate(package)

        self.assertEqual(code["pin"], "000042")
        self.assertEqual(self.deliver(package, pickupCode="000042").status_code, 200)

    def test_only_the_owner_resident_generates_the_code(self):
        package = self.make_package()
        url = f"/api/packages/{package.id}/pickup-code"

        for user in (self.housemate, self.neighbor, self.guard, self.admin):
            with self.subTest(user=user.email):
                self.assertEqual(self.client.post(url, headers=self.auth(user)).status_code, 403)

        self.assertEqual(PackagePickupCode.query.count(), 0)
        missing = self.client.post("/api/packages/9999/pickup-code", headers=self.auth(self.resident))
        self.assertEqual(missing.status_code, 404)

    def test_the_code_is_only_generated_while_the_package_waits_in_the_porteria(self):
        coming = self.make_package(status="por_llegar")
        delivered = self.make_package(status="entregado", delivered_at=utc_now(), delivered_to="Ana")
        trashed = self.make_package(is_deleted=True, deleted_at=utc_now())

        for package in (coming, delivered, trashed):
            with self.subTest(status=package.status, deleted=package.is_deleted):
                response = self.client.post(
                    f"/api/packages/{package.id}/pickup-code", headers=self.auth(self.resident)
                )
                self.assertEqual(response.status_code, 409)
        self.assertEqual(PackagePickupCode.query.count(), 0)

    def test_a_new_code_cancels_the_previous_one(self):
        package = self.make_package()
        first = self.generate(package)
        second = self.generate(package)

        self.assertNotEqual(first["qrData"], second["qrData"])
        codes = PackagePickupCode.query.order_by(PackagePickupCode.id).all()
        self.assertEqual(len(codes), 2)
        self.assertIsNotNone(codes[0].revoked_at)
        self.assertIsNone(codes[1].revoked_at)
        old = self.lookup(first["qrData"])
        self.assertEqual(old.status_code, 409)
        self.assertIn("anulado", old.get_json()["error"])
        self.assertEqual(self.lookup(second["qrData"]).status_code, 200)

    # --- Escanear el QR (HU-048) --------------------------------------------

    def test_the_guard_scans_the_qr_and_sees_whose_package_it_is(self):
        package = self.make_package(description="Cajón", carrier="Servientrega")
        code = self.generate(package)

        for scanned in (code["qrData"], code["qrData"][len(QR_PREFIX):], f"  {code['qrData']}  "):
            with self.subTest(scanned=scanned[:14]):
                response = self.lookup(scanned)
                self.assertEqual(response.status_code, 200)
                item = response.get_json()["packageItem"]
                self.assertEqual(item["id"], package.id)
                self.assertEqual(item["carrier"], "Servientrega")
                self.assertEqual(item["residentName"], self.resident.full_name)
                self.assertEqual(item["apartment"], "Torre 1 · Apto 101")
        self.assertEqual(self.lookup(code["qrData"], self.admin).status_code, 200)

    def test_the_lookup_refuses_unknown_missing_and_resident_requests(self):
        package = self.make_package()
        code = self.generate(package)

        self.assertEqual(self.lookup(QR_PREFIX + "inventado").status_code, 404)
        self.assertEqual(self.lookup(code["pin"]).status_code, 404)  # el PIN no abre la búsqueda
        no_code = self.client.post("/api/packages/pickup-lookup", headers=self.auth(self.guard), json={})
        self.assertEqual(no_code.status_code, 400)
        not_text = self.client.post(
            "/api/packages/pickup-lookup", headers=self.auth(self.guard), json={"code": 123456}
        )
        self.assertEqual(not_text.status_code, 400)
        self.assertEqual(self.lookup(code["qrData"], self.resident).status_code, 403)

    def test_the_code_of_a_delivered_or_trashed_package_does_not_open_the_lookup(self):
        package = self.make_package()
        code = self.generate(package)

        package.is_deleted = True
        db.session.commit()
        trashed = self.lookup(code["qrData"])
        self.assertEqual(trashed.status_code, 409)
        self.assertIn("papelera", trashed.get_json()["error"])

        package.is_deleted = False
        package.status = "entregado"
        db.session.commit()
        delivered = self.lookup(code["qrData"])
        self.assertEqual(delivered.status_code, 409)
        self.assertIn("entregado", delivered.get_json()["error"])

    # --- Entregar con el código (HU-048) ------------------------------------

    def test_delivering_with_the_qr_marks_the_code_as_used(self):
        package = self.make_package()
        code = self.generate(package)

        response = self.deliver(package, receiver="Tercero Pérez", pickupCode=code["qrData"])

        self.assertEqual(response.status_code, 200, response.get_json())
        item = response.get_json()["packageItem"]
        self.assertEqual(item["status"], "entregado")
        self.assertEqual(item["deliveredTo"], "Tercero Pérez")
        self.assertFalse(item["hasPickupCode"])
        stored = self.stored_code()
        self.assertIsNotNone(stored.used_at)
        self.assertIsNone(stored.revoked_at)
        notice = Notification.query.filter_by(user_id=self.resident.id, title="Paquete entregado").one()
        self.assertIn("con tu código de entrega", notice.message)
        self.assertEqual(AuditLog.query.filter_by(action="pickup_code_used").count(), 1)

    def test_delivering_with_the_pin_works_too(self):
        package = self.make_package()
        code = self.generate(package)

        response = self.deliver(package, pickupCode=code["pin"])

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(db.session.get(PackageItem, package.id).status, "entregado")
        self.assertIsNotNone(self.stored_code().used_at)

    def test_a_used_code_does_not_deliver_anything_else(self):
        first = self.make_package(description="Primero")
        second = self.make_package(description="Segundo")
        used = self.generate(first)
        self.generate(second)
        self.assertEqual(self.deliver(first, pickupCode=used["qrData"]).status_code, 200)

        lookup = self.lookup(used["qrData"])
        self.assertEqual(lookup.status_code, 409)
        self.assertIn("ya se usó", lookup.get_json()["error"])
        rejected = self.deliver(second, pickupCode=used["qrData"])
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(db.session.get(PackageItem, second.id).status, "pendiente")

    def test_a_code_from_another_package_is_refused_without_counting(self):
        first = self.make_package(description="Primero")
        second = self.make_package(description="Segundo")
        first_code = self.generate(first)
        self.generate(second)

        response = self.deliver(second, pickupCode=first_code["qrData"])

        self.assertEqual(response.status_code, 409)
        self.assertIn("otro paquete", response.get_json()["error"])
        self.assertEqual(self.stored_code(second).failed_attempts, 0)
        self.assertEqual(db.session.get(PackageItem, second.id).status, "pendiente")
        self.assertEqual(db.session.get(PackageItem, first.id).status, "pendiente")

    def test_five_wrong_pins_cancel_the_code(self):
        package = self.make_package()
        code = self.generate(package)
        wrong = "000000" if code["pin"] != "000000" else "111111"

        for attempt in range(1, 5):
            response = self.deliver(package, pickupCode=wrong)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(self.stored_code().failed_attempts, attempt)
        locked = self.deliver(package, pickupCode=wrong)

        self.assertEqual(locked.status_code, 409)
        self.assertIn("anuló", locked.get_json()["error"])
        self.assertIsNotNone(self.stored_code().revoked_at)
        # Ni siquiera el PIN correcto sirve ya, y el paquete sigue en portería.
        self.assertEqual(self.deliver(package, pickupCode=code["pin"]).status_code, 409)
        self.assertEqual(db.session.get(PackageItem, package.id).status, "pendiente")
        # El residente genera un código nuevo y ese sí entrega.
        fresh = self.generate(package)
        self.assertEqual(self.deliver(package, pickupCode=fresh["pin"]).status_code, 200)

    def test_a_pin_with_the_wrong_length_is_a_typing_mistake_and_does_not_count(self):
        package = self.make_package()
        self.generate(package)

        for typed in ("1", "12345", "1234567"):
            with self.subTest(typed=typed):
                response = self.deliver(package, pickupCode=typed)
                self.assertEqual(response.status_code, 400)
                self.assertIn("6 dígitos", response.get_json()["error"])

        self.assertEqual(self.stored_code().failed_attempts, 0)

    def test_a_code_cannot_be_used_if_the_package_has_none(self):
        package = self.make_package()

        response = self.deliver(package, pickupCode="123456")

        self.assertEqual(response.status_code, 409)
        self.assertIn("no tiene un código", response.get_json()["error"])
        self.assertEqual(db.session.get(PackageItem, package.id).status, "pendiente")

    def test_delivering_without_the_code_still_works_and_closes_the_code(self):
        package = self.make_package()
        self.generate(package)

        response = self.deliver(package)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["packageItem"]["hasPickupCode"])
        stored = self.stored_code()
        self.assertIsNotNone(stored.revoked_at)
        self.assertIsNone(stored.used_at)
        notice = Notification.query.filter_by(user_id=self.resident.id, title="Paquete entregado").one()
        self.assertNotIn("código de entrega", notice.message)

    def test_a_resident_cannot_deliver_even_with_the_code(self):
        package = self.make_package()
        code = self.generate(package)

        response = self.client.put(
            f"/api/packages/{package.id}/deliver", headers=self.auth(self.resident),
            json={"receivedBy": "Yo", "pickupCode": code["pin"]},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(db.session.get(PackageItem, package.id).status, "pendiente")

    def test_a_code_used_at_the_same_time_by_another_request_is_refused(self):
        package = self.make_package()
        code = self.generate(package)
        package = db.session.get(PackageItem, package.id)
        self.assertIsNotNone(package.active_pickup_code)  # esta solicitud ya lo leyó vigente
        # Otra solicitud lo marca usado justo antes de que esta intente reclamarlo.
        db.session.execute(update(PackagePickupCode).values(used_at=utc_now()))

        with self.assertRaises(ApiError) as caught:
            package_service.check_pickup_code(package, code["pin"], self.guard)

        self.assertEqual(caught.exception.status, 409)
        self.assertIn("ya se usó", caught.exception.message)

    # --- Lo que se muestra y cuánto cuesta ----------------------------------

    def test_the_lists_say_a_code_exists_but_never_show_it(self):
        package = self.make_package()
        code = self.generate(package)
        token = code["qrData"][len(QR_PREFIX):]

        for user in (self.resident, self.guard, self.admin):
            with self.subTest(user=user.email):
                response = self.client.get("/api/packages", headers=self.auth(user))
                item = response.get_json()["packages"][0]
                self.assertTrue(item["hasPickupCode"])
                self.assertNotIn("pin", item)
                self.assertNotIn("token", item)
                self.assertNotIn(token, response.get_data(as_text=True))

    def test_the_list_does_not_query_more_as_packages_grow(self):
        extra = [self.user(f"Extra {n}", f"extra{n}", "RESIDENT", self.apartment) for n in range(4)]
        db.session.add_all(extra)
        db.session.commit()

        def list_with_count():
            statements = []

            def count(connection, cursor, statement, parameters, context, executemany):
                statements.append(statement)

            event.listen(db.engine, "before_cursor_execute", count)
            try:
                response = self.client.get("/api/packages", headers=self.auth(self.guard))
            finally:
                event.remove(db.engine, "before_cursor_execute", count)
            self.assertEqual(response.status_code, 200)
            return len(statements), len(response.get_json()["packages"])

        def add_one_of_each(resident):
            package = self.make_package(resident, carrier="Servientrega")
            self.generate(package, resident)
            self.make_package(
                resident, status="entregado", delivered_at=utc_now(), delivered_to="Ana",
                delivered_by_id=self.guard.id,
            )

        # Con uno de cada tipo ya se hacen todas las consultas posibles; de ahí en
        # adelante, más paquetes no deben sumar ninguna.
        add_one_of_each(extra[0])
        few = list_with_count()
        for resident in extra[1:]:
            add_one_of_each(resident)
        many = list_with_count()

        self.assertGreater(many[1], few[1])
        self.assertEqual(many[0], few[0])


if __name__ == "__main__":
    unittest.main()
