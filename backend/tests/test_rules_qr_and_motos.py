"""Las dos reglas de la unidad que faltaban conectar (decisión del 27/11/2026).

* «QR automático para estadías largas»: si una visita se va a quedar los días de la regla o más, al
  registrar su entrada DOMUX le crea un QR al residente para ese visitante.
* «Motos por cupo de carro»: un parqueadero de visitantes marcado «para motos» recibe hasta ese número
  de motos; con el cupo lleno queda ocupado y vuelve a quedar libre cuando sale una.
"""

import unittest

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import generate_password_hash

from app import create_app
from auth import generate_token
from extensions import db
from models import Notification, ParkingSpot, UnitSettings, User, Visit, VisitQrPass
from services.unit_rules import forget_rules
from structure_fixtures import apartment_for, parking_spot
from time_utils import utc_now


class RulesTests(unittest.TestCase):
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
        forget_rules()
        apartment = apartment_for("Torre 1 · Apto 101")
        self.admin = self.user("Admin", "admin", "ADMIN")
        self.guard = self.user("Guardia", "guard", "GUARD")
        self.resident = self.user("Residente", "resident", "RESIDENT", apartment)
        db.session.add_all([self.admin, self.guard, self.resident])
        self.moto_spot = parking_spot("V-M1", kind="visitante", location="Entrada")
        self.moto_spot.for_motos = True
        self.car_spot = parking_spot("V-01", kind="visitante", location="Entrada")
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        forget_rules()
        db.session.remove()
        self.context.pop()

    def user(self, name, key, role, apartment=None):
        return User(
            name=name, email=f"{key}@reglas.test", role=role, is_active=True,
            password_hash=generate_password_hash("Prueba123*"), apartment_ref=apartment,
        )

    def auth(self, user):
        return {"Authorization": f"Bearer {generate_token(user)}"}

    def visit(self, name="Tía Rosa", inside=False):
        visit = Visit(
            resident_id=self.resident.id, registered_by=self.guard.id, visitor_name=name, type="visitante",
            approval_status="aprobada", authorization_method="app", entered_at=utc_now() if inside else None,
        )
        db.session.add(visit)
        db.session.commit()
        return visit

    # --- QR automático --------------------------------------------------------------------------

    def test_una_estadia_larga_crea_el_qr_solo(self):
        visit = self.visit()
        response = self.client.post(
            f"/api/visits/{visit.id}/entry", json={"expectedStayMinutes": 3 * 24 * 60}, headers=self.auth(self.guard)
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        passes = VisitQrPass.query.filter_by(resident_id=self.resident.id).all()
        self.assertEqual(len(passes), 1)
        self.assertEqual(passes[0].names, ["Tía Rosa"])
        self.assertEqual(passes[0].max_people, 1)
        self.assertTrue(Notification.query.filter_by(user_id=self.resident.id, title="QR creado para tu visita").first())

    def test_una_estadia_corta_no_crea_qr(self):
        visit = self.visit()
        self.client.post(f"/api/visits/{visit.id}/entry", json={"expectedStayMinutes": 120}, headers=self.auth(self.guard))
        self.assertEqual(VisitQrPass.query.count(), 0)

    def test_la_regla_cambia_desde_cuantos_dias(self):
        db.session.add(UnitSettings(id=1, auto_qr_min_stay_days=5))
        db.session.commit()
        forget_rules()
        visit = self.visit()
        self.client.post(
            f"/api/visits/{visit.id}/entry", json={"expectedStayMinutes": 3 * 24 * 60}, headers=self.auth(self.guard)
        )
        self.assertEqual(VisitQrPass.query.count(), 0)

    # --- Motos por cupo de carro --------------------------------------------------------------------

    def enter(self, plate, vehicle_type="moto", **extra):
        body = {"plate": plate, "visitId": self.visit(name=f"Visita {plate}", inside=True).id, "vehicleType": vehicle_type, **extra}
        return self.client.post("/api/vehicle-entries", json=body, headers=self.auth(self.guard))

    def test_las_motos_comparten_el_parqueadero_hasta_el_cupo(self):
        db.session.add(UnitSettings(id=1, motos_per_car_spot=2))
        db.session.commit()
        forget_rules()
        first = self.enter("ABC12D")
        self.assertEqual(first.status_code, 201, first.get_json())
        self.assertEqual(first.get_json()["vehicleEntry"]["spotCode"], "V-M1")
        self.assertFalse(db.session.get(ParkingSpot, self.moto_spot.id).occupied)
        second = self.enter("XYZ34E")
        self.assertEqual(second.get_json()["vehicleEntry"]["spotCode"], "V-M1")
        db.session.expire_all()
        self.assertTrue(db.session.get(ParkingSpot, self.moto_spot.id).occupied)
        # La tercera ya no cabe: va al parqueadero normal libre.
        third = self.enter("QWE56F")
        self.assertEqual(third.get_json()["vehicleEntry"]["spotCode"], "V-01")
        # Sale una moto: vuelve a haber cupo.
        self.client.put(f"/api/vehicle-entries/{first.get_json()['vehicleEntry']['id']}/exit", headers=self.auth(self.guard))
        db.session.expire_all()
        self.assertFalse(db.session.get(ParkingSpot, self.moto_spot.id).occupied)
        board = self.client.get("/api/parking/visitor-spots", headers=self.auth(self.guard)).get_json()
        moto = [spot for spot in board["spots"] if spot["code"] == "V-M1"][0]
        self.assertEqual((moto["motosInside"], moto["motosCapacity"]), (1, 2))

    def test_un_carro_no_entra_al_parqueadero_de_motos(self):
        response = self.enter("CAR123", vehicle_type="carro", spotId=self.moto_spot.id)
        self.assertEqual(response.status_code, 400)
        car = self.enter("CAR124", vehicle_type="carro")
        self.assertEqual(car.get_json()["vehicleEntry"]["spotCode"], "V-01")

    def test_la_administracion_marca_un_parqueadero_para_motos(self):
        response = self.client.put(
            f"/api/admin/parking-spots/{self.car_spot.id}", json={"forMotos": True}, headers=self.auth(self.admin)
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertTrue(response.get_json()["parkingSpot"]["forMotos"])
        resident_spot = parking_spot("P-1", kind="residente")
        db.session.commit()
        refused = self.client.put(
            f"/api/admin/parking-spots/{resident_spot.id}", json={"forMotos": True}, headers=self.auth(self.admin)
        )
        self.assertEqual(refused.status_code, 400)


class QrVisitorsTests(RulesTests):
    """El QR del residente lleva nombre y documento revisados de cada persona (máximo las de la regla)."""

    def create(self, visitors, max_people=None):
        from time_utils import colombia_today

        today = colombia_today().isoformat()
        return self.client.post("/api/visits/qr-passes", headers=self.auth(self.resident), json={
            "validFrom": today, "validUntil": today, "maxPeople": max_people or len(visitors), "visitors": visitors,
        })

    def test_nombre_y_documento_quedan_en_el_qr_y_en_la_visita(self):
        response = self.create([{"name": "Laura Gómez", "document": "1.020.304.050"}])
        self.assertEqual(response.status_code, 201, response.get_json())
        qr = response.get_json()["qrPass"]
        self.assertEqual(qr["visitors"], [{"name": "Laura Gómez", "document": "1020304050"}])
        inspected = self.client.get(f"/api/visits/qr/{qr['token']}", headers=self.auth(self.guard)).get_json()
        self.assertEqual(inspected["pendingVisitors"][0]["document"], "1020304050")
        entry = self.client.post(f"/api/visits/qr/{qr['token']}/entry", json={"visitorName": "Laura Gómez"},
                                 headers=self.auth(self.guard))
        self.assertEqual(entry.status_code, 201, entry.get_json())
        self.assertEqual(entry.get_json()["visit"]["visitorDocument"], "1020304050")

    def test_validaciones(self):
        self.assertEqual(self.create([{"name": "Laura", "document": "1020304050"}]).status_code, 400)
        self.assertEqual(self.create([{"name": "Laura Gómez", "document": "12"}]).status_code, 400)
        self.assertEqual(self.create([{"name": "Laura G0mez", "document": "1020304050"}]).status_code, 400)
        twins = [{"name": "Laura Gómez", "document": "1020304050"}, {"name": "Ana Ruiz", "document": "1020304050"}]
        self.assertEqual(self.create(twins).status_code, 400)
        six = [{"name": f"Persona Número{chr(65 + i)}", "document": f"10203040{i}"} for i in range(6)]
        self.assertEqual(self.create(six, max_people=6).status_code, 400)


class QrVehicleTests(QrVisitorsTests):
    """El QR puede decir en qué vehículo llegan; el guardia lo ve al leerlo y registra su entrada."""

    def test_el_qr_guarda_el_vehiculo_y_la_porteria_lo_ve(self):
        from time_utils import colombia_today

        today = colombia_today().isoformat()
        response = self.client.post("/api/visits/qr-passes", headers=self.auth(self.resident), json={
            "validFrom": today, "validUntil": today, "maxPeople": 1,
            "visitors": [{"name": "Laura Gómez", "document": "1020304050"}],
            "vehicle": {"type": "carro", "plate": "abc 123", "brand": "Mazda", "color": "Rojo"},
        })
        self.assertEqual(response.status_code, 201, response.get_json())
        qr = response.get_json()["qrPass"]
        self.assertEqual(qr["vehicle"], {"type": "carro", "plate": "ABC123", "brand": "Mazda", "color": "Rojo"})
        inspected = self.client.get(f"/api/visits/qr/{qr['token']}", headers=self.auth(self.guard)).get_json()
        self.assertEqual(inspected["qrPass"]["vehicle"]["plate"], "ABC123")

    def test_placa_invalida_y_sin_vehiculo(self):
        from time_utils import colombia_today

        today = colombia_today().isoformat()
        body = {"validFrom": today, "validUntil": today, "maxPeople": 1,
                "visitors": [{"name": "Laura Gómez", "document": "1020304050"}]}
        bad = self.client.post("/api/visits/qr-passes", headers=self.auth(self.resident),
                               json={**body, "vehicle": {"type": "carro", "plate": "12-ABC"}})
        self.assertEqual(bad.status_code, 400)
        plain = self.client.post("/api/visits/qr-passes", headers=self.auth(self.resident), json=body)
        self.assertIsNone(plain.get_json()["qrPass"]["vehicle"])

    def test_la_administracion_verifica_el_contacto_cambiado(self):
        self.resident.contact_unverified = True
        db.session.commit()
        response = self.client.put(f"/api/users/{self.resident.id}", json={"contactVerified": True}, headers=self.auth(self.admin))
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertFalse(db.session.get(User, self.resident.id).contact_unverified)
