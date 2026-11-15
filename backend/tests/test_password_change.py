"""Pruebas del cambio de contraseña propio y de la confirmación antes de descargar (SEC-001).

* Cuando el administrador le restablece la contraseña a alguien, esa contraseña es temporal: al
  entrar, la persona solo puede cambiarla por una propia; lo demás responde 403 hasta que lo haga.
* La web pide otra vez la contraseña del administrador antes de descargar copias y archivos.
"""

import time

from werkzeug.security import check_password_hash

from auth import generate_token
from extensions import db
from models import AuditLog, User
from web_testing import PASSWORD, WebTestCase

TEMPORARY = "Temporal-de-prueba-3*"
OWN = "Propia-de-prueba-4*"


class PasswordApiTestCase(WebTestCase):
    def bearer(self, user_or_token):
        token = user_or_token if isinstance(user_or_token, str) else generate_token(user_or_token)
        return {"Authorization": f"Bearer {token}"}

    def reset(self, user, password=TEMPORARY):
        return self.client.put(
            f"/api/admin/users/{user.id}/password", headers=self.bearer(self.admin), json={"password": password},
        )

    def login(self, user, password):
        return self.client.post("/api/auth/login", json={"email": user.email, "password": password})

    def change(self, token, current, new):
        return self.client.put(
            "/api/auth/password", headers=self.bearer(token), json={"currentPassword": current, "newPassword": new},
        )


class ForcedPasswordChangeTests(PasswordApiTestCase):
    def test_despues_de_restablecer_la_persona_solo_puede_cambiar_su_contrasena(self):
        self.assertEqual(self.reset(self.resident).status_code, 200)

        login = self.login(self.resident, TEMPORARY)

        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.get_json()["user"]["mustChangePassword"])
        token = login.get_json()["token"]
        blocked = self.client.get("/api/announcements", headers=self.bearer(token))
        self.assertEqual(blocked.status_code, 403)
        self.assertTrue(blocked.get_json()["passwordChangeRequired"])
        self.assertIn("cambiar tu contraseña", blocked.get_json()["error"])
        session = self.client.get("/api/auth/session", headers=self.bearer(token))
        self.assertEqual(session.status_code, 200)
        self.assertTrue(session.get_json()["user"]["mustChangePassword"])

    def test_al_poner_una_contrasena_propia_todo_vuelve_a_funcionar(self):
        self.reset(self.resident)
        token = self.login(self.resident, TEMPORARY).get_json()["token"]

        response = self.change(token, TEMPORARY, OWN)

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertFalse(body["user"]["mustChangePassword"])
        self.assertEqual(self.client.get("/api/announcements", headers=self.bearer(body["token"])).status_code, 200)
        # La sesión con la contraseña temporal se cerró y la temporal ya no abre nada.
        self.assertEqual(self.client.get("/api/auth/session", headers=self.bearer(token)).status_code, 401)
        self.assertEqual(self.login(self.resident, TEMPORARY).status_code, 401)
        self.assertEqual(self.login(self.resident, OWN).status_code, 200)
        log = AuditLog.query.filter_by(action="password_changed").one()
        self.assertEqual(log.actor_id, self.resident.id)
        self.assertNotIn(OWN, log.details or "")

    def test_una_cuenta_nueva_nace_con_contrasena_temporal(self):
        created = self.client.post("/api/users", headers=self.bearer(self.admin), json={
            "name": "Nora", "lastName": "Paz", "email": "nueva-cuenta@test.local", "password": TEMPORARY,
            "role": "GUARD",
        })
        self.assertEqual(created.status_code, 201, created.get_json())
        self.assertTrue(created.get_json()["user"]["mustChangePassword"])

        token = self.client.post(
            "/api/auth/login", json={"email": "nueva-cuenta@test.local", "password": TEMPORARY},
        ).get_json()["token"]

        self.assertEqual(self.client.get("/api/announcements", headers=self.bearer(token)).status_code, 403)
        changed = self.change(token, TEMPORARY, OWN)
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(
            self.client.get("/api/announcements", headers=self.bearer(changed.get_json()["token"])).status_code, 200,
        )

    def test_el_administrador_que_cambia_la_suya_no_queda_obligado(self):
        self.reset(self.admin)

        self.assertFalse(db.session.get(User, self.admin.id).must_change_password)

    def test_las_cuentas_que_no_se_restablecieron_no_se_tocan(self):
        login = self.login(self.resident, PASSWORD)

        self.assertFalse(login.get_json()["user"]["mustChangePassword"])
        token = login.get_json()["token"]
        self.assertEqual(self.client.get("/api/announcements", headers=self.bearer(token)).status_code, 200)


class OwnPasswordChangeTests(PasswordApiTestCase):
    def test_pide_la_contrasena_actual_correcta(self):
        response = self.change(generate_token(self.resident), "No-es-la-mia-9*", OWN)

        self.assertEqual(response.status_code, 400)
        self.assertIn("actual no es correcta", response.get_json()["error"])
        self.assertTrue(check_password_hash(db.session.get(User, self.resident.id).password_hash, PASSWORD))

    def test_la_nueva_debe_ser_fuerte_y_distinta(self):
        token = generate_token(self.resident)

        weak = self.change(token, PASSWORD, "corta")
        same = self.change(token, PASSWORD, PASSWORD)

        self.assertEqual(weak.status_code, 400)
        self.assertIn("mínimo 8 caracteres", weak.get_json()["error"])
        self.assertEqual(same.status_code, 400)
        self.assertIn("distinta de la actual", same.get_json()["error"])

    def test_faltan_datos(self):
        response = self.client.put(
            "/api/auth/password", headers=self.bearer(self.resident), json={"newPassword": OWN},
        )

        self.assertEqual(response.status_code, 400)

    def test_sin_sesion_no_se_puede(self):
        response = self.client.put("/api/auth/password", json={"currentPassword": PASSWORD, "newPassword": OWN})

        self.assertEqual(response.status_code, 401)

    def test_cinco_fallos_seguidos_bloquean_15_minutos(self):
        token = generate_token(self.resident)
        for _ in range(5):
            last = self.change(token, "No-es-la-mia-9*", OWN)

        self.assertEqual(last.status_code, 429)
        self.assertEqual(self.change(token, PASSWORD, OWN).status_code, 429)


class WebPasswordTests(PasswordApiTestCase):
    def test_confirmar_con_una_contrasena_mala_no_deja_descargar(self):
        self.log_in()

        response = self.confirm_password("No-es-la-mia-9*", "/web/respaldo")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/web/confirmar-contrasena", response.headers["Location"])
        self.assertEqual(self.client.get("/web/respaldo/descargar").status_code, 302)
        self.assertEqual(AuditLog.query.filter_by(action="web_password_confirm_failed").count(), 1)

    def test_confirmar_bien_vuelve_a_la_pagina_y_deja_descargar(self):
        self.log_in()

        response = self.confirm_password(next_url="/web/respaldo")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/web/respaldo"))
        self.assertEqual(self.client.get("/web/respaldo/descargar").status_code, 200)

    def test_la_confirmacion_no_manda_a_otro_sitio(self):
        self.log_in()

        response = self.confirm_password(next_url="https://ejemplo.invalid/robo")

        self.assertNotIn("ejemplo.invalid", response.headers["Location"])

    def test_la_confirmacion_vence_a_los_10_minutos(self):
        self.log_in()
        self.confirm_password()
        with self.client.session_transaction() as session:
            session["pwd_at"] = int(time.time()) - 11 * 60

        self.assertEqual(self.client.get("/web/respaldo/descargar").status_code, 302)

    def test_cinco_fallos_al_confirmar_cierran_la_sesion(self):
        self.log_in()
        for _ in range(5):
            self.confirm_password("No-es-la-mia-9*")

        response = self.confirm_password()

        self.assertIn("/web/login", response.headers["Location"])
        self.assertEqual(self.client.get("/web/respaldo").status_code, 302)

    def test_la_pagina_de_confirmar_necesita_sesion(self):
        response = self.client.get("/web/confirmar-contrasena")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/web/login", response.headers["Location"])

    def test_el_administrador_con_contrasena_temporal_va_a_cambiarla(self):
        self.admin.must_change_password = True
        db.session.commit()
        self.log_in()

        response = self.client.get("/web/usuarios")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/web/cambiar-contrasena", response.headers["Location"])
        self.assertIn("Otro administrador te restableció la contraseña", self.page("/web/cambiar-contrasena"))

    def test_cambia_su_contrasena_en_la_web_y_sigue_con_la_sesion(self):
        self.admin.must_change_password = True
        db.session.commit()
        self.log_in()
        # El inicio manda a cambiar la contraseña: el código contra CSRF se toma de esa página.
        self._token = self.token_of("/web/cambiar-contrasena")

        response = self.post("/web/cambiar-contrasena", {
            "currentPassword": PASSWORD, "newPassword": OWN, "newPassword2": OWN,
        }, follow=True)

        self.assertIn("Contraseña cambiada", self.text(response))
        self.assertEqual(self.client.get("/web/usuarios").status_code, 200)
        self.assertTrue(check_password_hash(db.session.get(User, self.admin.id).password_hash, OWN))

    def test_en_la_web_las_dos_contrasenas_nuevas_deben_coincidir(self):
        self.log_in()

        response = self.post("/web/cambiar-contrasena", {
            "currentPassword": PASSWORD, "newPassword": OWN, "newPassword2": OWN + "x",
        }, follow=True)

        self.assertIn("no coinciden", self.text(response))
        self.assertTrue(check_password_hash(db.session.get(User, self.admin.id).password_hash, PASSWORD))

    def test_restablecer_desde_la_web_avisa_que_es_temporal(self):
        self.log_in()

        response = self.post(f"/web/usuarios/{self.resident.id}/clave", {
            "password": TEMPORARY, "password2": TEMPORARY,
        }, follow=True)

        self.assertIn("tendrá que cambiarla", self.text(response))
        self.assertTrue(db.session.get(User, self.resident.id).must_change_password)
