package com.dracknoval.domux.pantallas

import android.net.Uri
import com.dracknoval.domux.data.SearchResult
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.TextSize
import com.dracknoval.domux.hasQuickActions
import com.dracknoval.domux.mainDestinations
import com.dracknoval.domux.moreDestinations
import com.dracknoval.domux.quickCreateItems
import com.dracknoval.domux.searchResultRoute
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Comprueba la lógica de lo nuevo de esta versión (buscador, «+ Nuevo», menú y Preferencias) sin
 * dibujar nada: a qué lleva cada resultado, qué puede crear cada rol y qué lleva cada menú.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class NovedadesDeLaVersionTest {

    @After
    fun cerrarSesion() {
        Session.clear()
    }

    private fun como(rol: Rol) = Session.updateFrom(rol.usuario)

    private fun resultado(tipo: String, titulo: String, apartamento: String? = null, clase: String? = null) =
        SearchResult(tipo, 1, titulo, null, 1, apartamento, clase)

    // --- «+ Nuevo» ---

    @Test
    fun nuevo_de_administracion_tiene_los_cinco_atajos() {
        como(Roles.ADMINISTRACION)
        assertTrue(hasQuickActions())
        assertEquals(
            listOf("Comunicado", "Usuario", "Torre", "Apartamento", "PQRS para un residente"),
            quickCreateItems().map { it.label }
        )
        assertEquals(
            listOf(
                "announcements?tab=publicar", "createUser?tab=crear", "structure?action=torre",
                "structure?action=apartamento", "pqrs?tab=nueva"
            ),
            quickCreateItems().map { it.route }
        )
    }

    @Test
    fun nuevo_de_porteria_tiene_los_tres_registros() {
        como(Roles.PORTERIA)
        assertTrue(hasQuickActions())
        assertEquals(listOf("Visita", "Paquete", "Entrada de vehículo"), quickCreateItems().map { it.label })
        assertEquals(
            listOf("registry?tab=registrar-visita", "registry?tab=registrar-paquete", "vehicles?tab=registrar-entrada"),
            quickCreateItems().map { it.route }
        )
    }

    @Test
    fun el_residente_no_tiene_nuevo() {
        como(Roles.RESIDENTE)
        assertFalse(hasQuickActions())
        assertTrue(quickCreateItems().isEmpty())
    }

    // --- Menús de cada rol ---

    @Test
    fun menu_principal_de_cada_rol() {
        como(Roles.ADMINISTRACION)
        assertEquals(listOf("Inicio", "PQRS", "Reservas", "Portería", "Más"), mainDestinations().map { it.label })
        como(Roles.PORTERIA)
        assertEquals(listOf("Portería", "Visitas", "Paquetes", "Vehículos", "Más"), mainDestinations().map { it.label })
        como(Roles.RESIDENTE)
        assertEquals(listOf("Inicio", "Comunicados", "Reservas", "PQRS", "Mi hogar"), mainDestinations().map { it.label })
    }

    @Test
    fun mas_de_cada_rol_incluye_preferencias_y_legal() {
        como(Roles.ADMINISTRACION)
        assertEquals(
            listOf(
                "Comunicados", "Vehículos", "Usuarios", "Estructura de la unidad", "Documentos", "Reglas de la unidad", "Notificaciones",
                "Preferencias", "Legal y privacidad"
            ),
            moreDestinations().map { it.label }
        )
        como(Roles.PORTERIA)
        assertEquals(
            listOf("Comunicados", "Documentos", "Notificaciones", "Preferencias", "Legal y privacidad"),
            moreDestinations().map { it.label }
        )
        como(Roles.RESIDENTE)
        assertEquals(
            listOf(
                "Mi perfil", "Mis paquetes", "Mis visitas y mi QR", "Documentos", "Notificaciones", "Preferencias",
                "Legal y privacidad"
            ),
            moreDestinations().map { it.label }
        )
    }

    @Test
    fun cada_menu_tiene_cinco_botones_y_el_ultimo_abre_mas() {
        listOf(Roles.ADMINISTRACION, Roles.PORTERIA, Roles.RESIDENTE).forEach { rol ->
            como(rol)
            assertEquals(5, mainDestinations().size)
            assertEquals("more", mainDestinations().last().route)
        }
    }

    // --- A dónde lleva cada resultado del buscador ---

    @Test
    fun resultados_del_buscador_para_administracion() {
        como(Roles.ADMINISTRACION)
        assertEquals(
            "createUser?search=" + Uri.encode("María Gómez"),
            searchResultRoute(resultado("personas", "María Gómez"))
        )
        assertEquals(
            "unitProfile/" + Uri.encode("Torre 1 · Apto 101"),
            searchResultRoute(resultado("apartamentos", "Torre 1 · Apto 101", apartamento = "Torre 1 · Apto 101"))
        )
        assertEquals(
            "vehicles?tab=residentes&search=MAR123",
            searchResultRoute(resultado("vehiculos", "MAR123", clase = "residente"))
        )
        assertEquals("vehicles", searchResultRoute(resultado("vehiculos", "KLM456", clase = "visitante")))
        assertEquals(
            "pqrs?search=PQRS-2026-000012",
            searchResultRoute(resultado("pqrs", "PQRS-2026-000012 · Ruido en la torre 2"))
        )
        assertEquals(
            "registry?tab=paquetes&search=" + Uri.encode("Caja mediana"),
            searchResultRoute(resultado("paquetes", "Caja mediana"))
        )
        assertEquals(
            "registry?tab=visitas&search=" + Uri.encode("Laura Restrepo"),
            searchResultRoute(resultado("visitas", "Laura Restrepo"))
        )
    }

    @Test
    fun la_porteria_no_abre_usuarios_ni_apartamentos() {
        como(Roles.PORTERIA)
        assertNull(searchResultRoute(resultado("personas", "María Gómez")))
        assertNull(searchResultRoute(resultado("apartamentos", "Torre 1 · Apto 101", apartamento = "Torre 1 · Apto 101")))
        // Lo demás sí lo abre.
        assertEquals("vehicles", searchResultRoute(resultado("vehiculos", "KLM456", clase = "visitante")))
    }

    @Test
    fun un_apartamento_sin_nombre_o_un_tipo_raro_no_lleva_a_ningun_lado() {
        como(Roles.ADMINISTRACION)
        assertNull(searchResultRoute(resultado("apartamentos", "Torre 1 · Apto 101", apartamento = "  ")))
        assertNull(searchResultRoute(resultado("otra-cosa", "algo")))
    }

    // --- Tamaño del texto ---

    @Test
    fun el_tamano_del_texto_se_reconoce_por_su_clave() {
        assertEquals(TextSize.NORMAL, TextSize.fromKey("normal"))
        assertEquals(TextSize.LARGE, TextSize.fromKey("grande"))
        assertEquals(TextSize.EXTRA_LARGE, TextSize.fromKey("muy-grande"))
        // Si no se reconoce, queda el normal.
        assertEquals(TextSize.NORMAL, TextSize.fromKey(null))
        assertEquals(TextSize.NORMAL, TextSize.fromKey("enorme"))
    }

    @Test
    fun cada_tamano_agranda_lo_que_dice() {
        assertEquals(1f, TextSize.NORMAL.factor, 0.0001f)
        assertEquals(1.125f, TextSize.LARGE.factor, 0.0001f)
        assertEquals(1.25f, TextSize.EXTRA_LARGE.factor, 0.0001f)
    }
}
