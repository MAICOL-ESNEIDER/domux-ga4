"""Pruebas de los datos de prueba que se agregan a los de la semilla (demo_data.py).

Revisan que se agreguen las 13 cuentas que faltan para llegar a 17 sin cambiar lo que ya había,
que cada rol use la contraseña de su variable, que se carguen una sola vez y nunca en una base
sin las cuentas de prueba, y que lo agregado se use desde la API como cualquier dato de la app.
"""

import os
import unittest
from unittest import mock

import env_setup  # noqa: F401  (va antes de importar la app)

from werkzeug.security import check_password_hash

import app as app_module
import demo_data
import seed
from app import create_app
from extensions import db
from models import (
    Announcement,
    AuditLog,
    CommonArea,
    ComplexProfile,
    PackageItem,
    ParkingSpot,
    Pqrs,
    Reservation,
    StorageRoom,
    User,
    Vehicle,
    VehicleMovement,
    VisitorVehicleEntry,
    VisitQrPass,
)

ON = {"DOMUX_DEMO_DATA": "1"}


def environment_without(*names, **values):
    """Copia el entorno actual sin algunas variables y con otras cambiadas."""
    env = {key: value for key, value in os.environ.items() if key not in names}
    env.update(values)
    return env


class DemoDataTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.addClassCleanup(env_setup.release_app, cls.app)
        cls.client = cls.app.test_client()

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        seed.seed_if_empty()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def add(self, **env):
        with mock.patch.dict(os.environ, dict(ON, **env)):
            return demo_data.add_demo_data()

    def login(self, email, var="SEED_RESIDENT_PASSWORD"):
        response = self.client.post(
            "/api/auth/login", json={"email": email, "password": os.environ[var]}
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        return {"Authorization": f"Bearer {response.get_json()['token']}"}

    def get(self, path, headers):
        response = self.client.get(path, headers=headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()


class AddsWhatIsMissingTests(DemoDataTestCase):
    def test_quedan_17_usuarios_sin_cambiar_los_que_ya_habia(self):
        before = {user.email: (user.password_hash, user.apartment_id, user.occupancy_type) for user in User.query}
        self.assertTrue(self.add())
        counts = {role: User.query.filter_by(role=role).count() for role in ("ADMIN", "GUARD", "RESIDENT")}
        self.assertEqual(counts, {"ADMIN": 1, "GUARD": 4, "RESIDENT": 12})
        after = {user.email: (user.password_hash, user.apartment_id, user.occupancy_type) for user in User.query}
        for email, data in before.items():
            self.assertEqual(after[email], data, email)

    def test_no_cambia_nada_de_la_semilla(self):
        def snapshot():
            return {
                "spots": sorted((s.code, s.kind, s.location, s.apartment_id, s.occupied) for s in ParkingSpot.query),
                "rooms": sorted((r.code, r.apartment_id) for r in StorageRoom.query),
                "areas": sorted((a.name, a.open_time, a.close_time, a.capacity) for a in CommonArea.query),
                "packages": sorted((p.id, p.status, p.description) for p in PackageItem.query),
                "announcements": sorted((a.id, a.title) for a in Announcement.query),
            }
        before = snapshot()
        self.add()
        after = snapshot()
        for key, rows in before.items():
            self.assertTrue(set(rows) <= set(after[key]), key)

    def test_cada_rol_usa_la_contrasena_de_su_variable(self):
        self.add()
        for email in demo_data.NEW_ACCOUNT_VARS:
            user = User.query.filter_by(email=email).one()
            var = demo_data.NEW_ACCOUNT_VARS[email]
            self.assertTrue(check_password_hash(user.password_hash, os.environ[var]), email)
        self.login("guardia3@domux.com", "SEED_GUARD_PASSWORD")
        self.login("hernan@domux.com")

    def test_los_guardias_nuevos_empiezan_sin_pin(self):
        self.add()
        for guard in demo_data.NEW_GUARDS:
            self.assertIsNone(User.query.filter_by(email=guard["email"]).one().pin_hash)

    def test_los_hogares(self):
        self.add()

        def home(email):
            user = User.query.filter_by(email=email).one()
            return sorted(
                (resident.email, resident.occupancy_type)
                for resident in User.query.filter_by(apartment_id=user.apartment_id, role="RESIDENT")
            )

        self.assertEqual(home("maria@domux.com"), [
            ("jorge@domux.com", "residente"), ("maria@domux.com", "propietario"), ("samuel@domux.com", "residente"),
        ])
        self.assertEqual(home("carlos@domux.com"), [
            ("carlos@domux.com", "arrendatario"), ("diana@domux.com", "residente"),
            ("hernan@domux.com", "propietario"), ("sara@domux.com", "residente"),
        ])
        self.assertEqual(home("natalia@domux.com"), [
            ("marta@domux.com", "propietario"), ("natalia@domux.com", "arrendatario"), ("tomas@domux.com", "residente"),
        ])
        self.assertEqual(home("gustavo@domux.com"), [
            ("gloria@domux.com", "propietario"), ("gustavo@domux.com", "propietario"),
        ])
        samuel, sara, tomas = (User.query.filter_by(email=e).one() for e in
                               ("samuel@domux.com", "sara@domux.com", "tomas@domux.com"))
        self.assertTrue(samuel.is_minor and samuel.parental_consent)
        self.assertTrue(sara.is_minor and not sara.parental_consent)
        self.assertFalse(tomas.is_minor)

    def test_se_carga_una_sola_vez(self):
        self.assertTrue(self.add())
        users, pqrs = User.query.count(), Pqrs.query.count()
        self.assertFalse(self.add())
        self.assertEqual((User.query.count(), Pqrs.query.count()), (users, pqrs))
        marker = AuditLog.query.filter_by(entity_type=demo_data.MARKER_ENTITY).one()
        self.assertEqual(marker.action, demo_data.MARKER_ACTION)

    def test_si_ya_existe_una_cuenta_no_la_repite(self):
        db.session.add(User(name="Jorge", email="jorge@domux.com", password_hash="x", role="RESIDENT"))
        db.session.commit()
        self.assertTrue(self.add())
        self.assertEqual(User.query.filter_by(email="jorge@domux.com").count(), 1)
        self.assertEqual(User.query.count(), 17)


class WhenItDoesNotLoadTests(DemoDataTestCase):
    def test_no_se_carga_en_una_base_sin_las_cuentas_de_prueba(self):
        db.drop_all()
        db.create_all()
        self.assertFalse(self.add())
        self.assertEqual(User.query.count(), 0)

    def test_apagado_con_la_variable(self):
        self.assertFalse(self.add(DOMUX_DEMO_DATA="0"))
        self.assertEqual(User.query.count(), 4)

    def test_en_produccion_sin_contrasena_no_carga_y_dice_cual_falta(self):
        env = environment_without("SEED_GUARD_PASSWORD", RENDER="true", **ON)
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertLogs("demo_data", level="WARNING") as logs:
                self.assertFalse(demo_data.add_demo_data())
        self.assertIn("SEED_GUARD_PASSWORD", logs.output[0])
        self.assertEqual(User.query.count(), 4)
        self.assertEqual(AuditLog.query.filter_by(entity_type=demo_data.MARKER_ENTITY).count(), 0)

    def test_en_desarrollo_sin_contrasenas_las_crea_y_solo_anota_las_nuevas(self):
        env = environment_without("SEED_GUARD_PASSWORD", "SEED_RESIDENT_PASSWORD", "RENDER", "APP_ENV", **ON)
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch.object(seed, "_save_generated_credentials") as save:
                self.assertTrue(demo_data.add_demo_data())
        saved = save.call_args.args[0]
        self.assertEqual(set(saved), set(demo_data.NEW_ACCOUNT_VARS))
        for email, password in saved.items():
            user = User.query.filter_by(email=email).one()
            self.assertTrue(check_password_hash(user.password_hash, password), email)

    def test_si_algo_falla_no_queda_nada_a_medias(self):
        with mock.patch.object(demo_data._DemoBuilder, "add_visits", side_effect=RuntimeError("falla")):
            with self.assertLogs("demo_data", level="ERROR"):
                self.assertFalse(self.add())
        self.assertEqual(User.query.count(), 4)
        self.assertEqual(Pqrs.query.count(), 0)


class StartupTests(DemoDataTestCase):
    def test_el_servidor_los_agrega_al_arrancar_despues_de_la_semilla(self):
        calls = []
        with mock.patch.object(app_module, "seed_if_empty", side_effect=lambda: calls.append("semilla")), \
                mock.patch.object(app_module, "add_demo_data", side_effect=lambda: calls.append("datos")), \
                mock.patch.object(app_module, "sync_demo_passwords", side_effect=lambda: calls.append("claves")):
            env_setup.release_app(create_app())
        self.assertEqual(calls, ["semilla", "datos", "claves"])

    def test_cambiar_la_variable_cambia_la_contrasena_de_todo_el_rol(self):
        self.add()
        new_password = "Nueva-clave-2026*"
        with mock.patch.dict(os.environ, {"SEED_RESIDENT_PASSWORD": new_password}):
            seed.sync_demo_passwords()
        for email in ("maria@domux.com", "carlos@domux.com", "sara@domux.com", "gloria@domux.com"):
            user = User.query.filter_by(email=email).one()
            self.assertTrue(check_password_hash(user.password_hash, new_password), email)
        guard = User.query.filter_by(email="guardia2@domux.com").one()
        self.assertTrue(check_password_hash(guard.password_hash, os.environ["SEED_GUARD_PASSWORD"]))


class UsableFromTheApiTests(DemoDataTestCase):
    def setUp(self):
        super().setUp()
        self.add()

    def test_la_menor_sin_autorizacion_solo_consulta(self):
        headers = self.login("sara@domux.com")
        self.get("/api/pqrs", headers)
        response = self.client.post(
            "/api/pqrs", headers=headers, json={"subject": "Balón", "message": "Se perdió un balón.", "category": "Petición"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("autorización parental", response.get_json()["error"])

    def test_pqrs_con_su_semaforo(self):
        headers = self.login("admin@domux.com", "SEED_ADMIN_PASSWORD")
        body = self.get("/api/pqrs", headers)
        colors = {item["semaphore"] for item in body["pqrs"]}
        self.assertTrue({"verde", "amarillo", "rojo"} <= colors)
        resolved = [item for item in body["pqrs"] if item["status"] == "resuelta"]
        self.assertEqual(resolved[0]["satisfactionRating"], 5)
        self.assertTrue(any(item["createdByAdministration"] for item in body["pqrs"]))

    def test_paquetes_con_alertas_de_48_y_72_horas(self):
        headers = self.login("guardia2@domux.com", "SEED_GUARD_PASSWORD")
        body = self.get("/api/packages", headers)
        alerts = {item["claimAlert"] for item in body["packages"]}
        self.assertTrue({"naranja", "rojo"} <= alerts)

    def test_visitas_adentro_y_una_esperando(self):
        headers = self.login("guardia2@domux.com", "SEED_GUARD_PASSWORD")
        visits = self.get("/api/visits", headers)["visits"]
        inside = {visit["visitorName"] for visit in visits if visit["enteredAt"] and not visit["exitedAt"]}
        self.assertEqual(inside, {"Ana María Vélez", "Pedro Gómez"})
        entries = self.get("/api/vehicle-entries", headers)
        open_entries = [entry for entry in entries["vehicleEntries"] if entry["isInside"]]
        self.assertEqual([(entry["plate"], entry["spotCode"]) for entry in open_entries], [("VIS123", "V-06")])
        diana = self.login("diana@domux.com")
        waiting = [v for v in self.get("/api/visits", diana)["visits"] if v["approvalStatus"] == "pendiente"]
        self.assertEqual(len(waiting), 1)
        response = self.client.put(
            f"/api/visits/{waiting[0]['id']}/decision", headers=diana, json={"decision": "aprobada"}
        )
        self.assertEqual(response.status_code, 200, response.get_json())

    def test_ficha_del_hogar_con_integrantes_mascotas_y_vehiculos(self):
        headers = self.login("jorge@domux.com")
        unit = self.get("/api/profile/unit", headers)
        unit = unit.get("unit", unit)
        self.assertEqual([member["name"] for member in unit["members"]], ["Valentina"])
        self.assertEqual([pet["name"] for pet in unit["pets"]], ["Luna"])
        self.assertEqual([vehicle["plate"] for vehicle in unit["vehicles"]], ["DMX101"])
        self.assertEqual(unit["parkingIdentifier"], "P-101")

    def test_reservas_en_cada_estado(self):
        statuses = {reservation.status for reservation in Reservation.query}
        self.assertTrue({"aprobada", "pendiente", "rechazada", "cancelada"} <= statuses)
        headers = self.login("tomas@domux.com")
        mine = self.get("/api/reservations", headers)["reservations"]
        self.assertEqual([item["status"] for item in mine], ["pendiente"])

    def test_lo_demas(self):
        self.assertEqual(Vehicle.query.count(), 4)
        self.assertEqual({v.vehicle_type for v in Vehicle.query}, {"carro", "moto"})
        self.assertGreater(VehicleMovement.query.count(), 0)
        self.assertEqual(VisitQrPass.query.count(), 3)
        self.assertEqual(VisitorVehicleEntry.query.filter_by(exited_at=None).count(), 1)
        self.assertEqual(CommonArea.query.filter_by(name="Piscina").one().maintenance_weekday, 0)
        profile = db.session.get(ComplexProfile, ComplexProfile.SINGLE_ID)
        self.assertEqual(profile.name, "Conjunto Residencial Mirador del Norte P.H.")
        headers = self.login("admin@domux.com", "SEED_ADMIN_PASSWORD")
        self.assertEqual(self.get("/api/unit-info", headers)["unit"]["nit"], demo_data.UNIT_PROFILE["nit"])
        notifications = self.get("/api/notifications", self.login("natalia@domux.com"))
        self.assertGreaterEqual(len(notifications["notifications"]), 2)


if __name__ == "__main__":
    unittest.main()
