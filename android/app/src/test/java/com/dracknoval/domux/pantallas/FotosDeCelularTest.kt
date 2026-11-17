package com.dracknoval.domux.pantallas

import android.net.Uri
import com.dracknoval.domux.SearchScreen
import com.dracknoval.domux.SearchViewModel
import org.junit.Test
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * Las fotos de pantalla de la app en un celular. Cada prueba dibuja una pantalla de verdad (la misma
 * que ve la persona) con datos de mentira ([DatosDeMentira]) y le saca una foto.
 *
 * Solo corren en GitHub (no hay Gradle en el computador). Con «-Proborazzi.test.record=true» las
 * fotos quedan en android/app/build/fotos-de-pantallas; sin eso, las pruebas solo revisan que cada
 * pantalla se pueda dibujar sin errores.
 *
 * Celular simulado: 411 × 891 dp, como un Pixel 7.
 */
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w411dp-h891dp-xxhdpi")
class FotosDeCelularTest : BaseDeFotos() {

    private val apartamento101 = "unitProfile/" + Uri.encode("Torre 1 · Apto 101")

    // --- Administración -----------------------------------------------------------------------

    @Test
    fun administracion_inicio() {
        entrarComo(Roles.ADMINISTRACION)
        foto("administracion-01-inicio", "home")
    }

    @Test
    fun administracion_buscador() {
        entrarComo(Roles.ADMINISTRACION)
        // Se escribe y se busca de una vez (sin esperar el instante de «dejó de escribir»).
        val buscador = SearchViewModel().apply {
            setText("maria")
            searchNow()
        }
        fotoConContenido("administracion-02-buscador", "search") { SearchScreen(it, buscador) }
    }

    @Test
    fun administracion_mas() {
        entrarComo(Roles.ADMINISTRACION)
        foto("administracion-03-mas", "more")
    }

    @Test
    fun administracion_preferencias() {
        entrarComo(Roles.ADMINISTRACION)
        foto("administracion-04-preferencias", "preferences")
    }

    @Test
    fun administracion_pqrs() {
        entrarComo(Roles.ADMINISTRACION)
        foto("administracion-05-pqrs", "pqrs")
    }

    @Test
    fun administracion_pqrs_nueva() {
        entrarComo(Roles.ADMINISTRACION)
        foto("administracion-06-pqrs-nueva", "pqrs?tab=nueva")
    }

    @Test
    fun administracion_reservas() {
        entrarComo(Roles.ADMINISTRACION)
        foto("administracion-07-reservas", "reservations")
    }

    @Test
    fun administracion_porteria() {
        entrarComo(Roles.ADMINISTRACION)
        foto("administracion-08-porteria", "registry")
    }

    @Test
    fun administracion_porteria_visitas() {
        entrarComo(Roles.ADMINISTRACION)
        foto("administracion-09-porteria-visitas", "registry?tab=visitas")
    }

    @Test
    fun administracion_comunicados() {
        entrarComo(Roles.ADMINISTRACION)
        foto("administracion-10-comunicados", "announcements")
    }

    @Test
    fun administracion_comunicado_nuevo() {
        entrarComo(Roles.ADMINISTRACION)
        foto("administracion-11-comunicado-nuevo", "announcements?tab=publicar")
    }

    @Test
    fun administracion_vehiculos() {
        entrarComo(Roles.ADMINISTRACION)
        foto("administracion-12-vehiculos", "vehicles")
    }

    @Test
    fun administracion_vehiculos_historial() {
        entrarComo(Roles.ADMINISTRACION)
        foto("administracion-13-vehiculos-historial", "vehicles?tab=historial")
    }

    @Test
    fun administracion_usuarios() {
        entrarComo(Roles.ADMINISTRACION)
        foto("administracion-14-usuarios", "createUser")
    }

    @Test
    fun administracion_usuario_nuevo() {
        entrarComo(Roles.ADMINISTRACION)
        foto("administracion-15-usuario-nuevo", "createUser?tab=crear")
    }

    @Test
    fun administracion_estructura() {
        entrarComo(Roles.ADMINISTRACION)
        foto("administracion-16-estructura", "structure")
    }

    @Test
    fun administracion_torre_nueva() {
        entrarComo(Roles.ADMINISTRACION)
        foto("administracion-17-torre-nueva", "structure?action=torre")
    }

    @Test
    fun administracion_apartamento() {
        entrarComo(Roles.ADMINISTRACION)
        foto("administracion-18-apartamento", apartamento101)
    }

    @Test
    fun administracion_notificaciones() {
        entrarComo(Roles.ADMINISTRACION)
        foto("administracion-19-notificaciones", "notifications")
    }

    @Test
    fun administracion_legal() {
        entrarComo(Roles.ADMINISTRACION)
        foto("administracion-20-legal", "legal")
    }

    @Test
    fun administracion_legal_documento() {
        entrarComo(Roles.ADMINISTRACION)
        foto("administracion-21-legal-documento", "legal?slug=politica-de-privacidad")
    }

    // --- Portería -------------------------------------------------------------------------------

    @Test
    fun porteria_inicio() {
        entrarComo(Roles.PORTERIA)
        foto("porteria-01-inicio", "home")
    }

    @Test
    fun porteria_buscador() {
        entrarComo(Roles.PORTERIA)
        fotoConContenido("porteria-02-buscador", "search") { SearchScreen(it) }
    }

    @Test
    fun porteria_visitas() {
        entrarComo(Roles.PORTERIA)
        foto("porteria-03-visitas", "registry?tab=visitas")
    }

    @Test
    fun porteria_paquetes() {
        entrarComo(Roles.PORTERIA)
        foto("porteria-04-paquetes", "registry?tab=paquetes")
    }

    @Test
    fun porteria_registrar_visita() {
        entrarComo(Roles.PORTERIA)
        foto("porteria-05-registrar-visita", "registry?tab=registrar-visita")
    }

    @Test
    fun porteria_registrar_paquete() {
        entrarComo(Roles.PORTERIA)
        foto("porteria-06-registrar-paquete", "registry?tab=registrar-paquete")
    }

    @Test
    fun porteria_escanear_qr() {
        entrarComo(Roles.PORTERIA)
        foto("porteria-07-escanear-qr", "registry?tab=qr")
    }

    @Test
    fun porteria_vehiculos() {
        entrarComo(Roles.PORTERIA)
        foto("porteria-08-vehiculos", "vehicles")
    }

    @Test
    fun porteria_entrada_de_vehiculo() {
        entrarComo(Roles.PORTERIA)
        foto("porteria-09-entrada-de-vehiculo", "vehicles?tab=registrar-entrada")
    }

    @Test
    fun porteria_comunicados() {
        entrarComo(Roles.PORTERIA)
        foto("porteria-10-comunicados", "announcements")
    }

    @Test
    fun porteria_mas() {
        entrarComo(Roles.PORTERIA)
        foto("porteria-11-mas", "more")
    }

    @Test
    fun porteria_notificaciones() {
        entrarComo(Roles.PORTERIA)
        foto("porteria-12-notificaciones", "notifications")
    }

    // --- Residente ------------------------------------------------------------------------------

    @Test
    fun residente_inicio() {
        entrarComo(Roles.RESIDENTE)
        foto("residente-01-inicio", "home")
    }

    @Test
    fun residente_perfil() {
        entrarComo(Roles.RESIDENTE)
        foto("residente-02-perfil", "profile")
    }

    @Test
    fun residente_mi_apartamento() {
        entrarComo(Roles.RESIDENTE)
        foto("residente-03-mi-apartamento", apartamento101)
    }

    @Test
    fun residente_pqrs() {
        entrarComo(Roles.RESIDENTE)
        foto("residente-04-pqrs", "pqrs")
    }

    @Test
    fun residente_pqrs_nueva() {
        entrarComo(Roles.RESIDENTE)
        foto("residente-05-pqrs-nueva", "pqrs?tab=nueva")
    }

    @Test
    fun residente_reservas() {
        entrarComo(Roles.RESIDENTE)
        foto("residente-06-reservas", "reservations")
    }

    @Test
    fun residente_comunicados() {
        entrarComo(Roles.RESIDENTE)
        foto("residente-07-comunicados", "announcements")
    }

    @Test
    fun residente_mis_paquetes() {
        entrarComo(Roles.RESIDENTE)
        foto("residente-08-mis-paquetes", "registry?tab=paquetes")
    }

    @Test
    fun residente_mis_visitas() {
        entrarComo(Roles.RESIDENTE)
        foto("residente-09-mis-visitas", "registry?tab=visitas")
    }

    @Test
    fun residente_mi_qr() {
        entrarComo(Roles.RESIDENTE)
        foto("residente-10-mi-qr", "registry?tab=qr")
    }

    @Test
    fun residente_mi_hogar() {
        entrarComo(Roles.RESIDENTE)
        foto("residente-11-mi-hogar", "more")
    }

    @Test
    fun residente_notificaciones() {
        entrarComo(Roles.RESIDENTE)
        foto("residente-12-notificaciones", "notifications")
    }

    // --- Sin sesión -----------------------------------------------------------------------------

    @Test
    fun inicio_de_sesion() {
        foto("login-01-inicio-de-sesion", "login")
    }
}
