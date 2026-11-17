package com.dracknoval.domux.pantallas

import android.net.Uri
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onLast
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performImeAction
import androidx.compose.ui.test.performTextInput
import com.dracknoval.domux.data.AppPreferences
import com.dracknoval.domux.data.ComplexInfoStore
import com.dracknoval.domux.data.TextSize
import com.dracknoval.domux.data.UnitRules
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Test
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * Lo nuevo de esta versión tocado como lo haría una persona: escribir en el buscador, abrir «+ Nuevo»
 * y cambiar el tamaño del texto en Preferencias. Además de comprobar que funciona, deja fotos.
 * Celular de 411 × 891 dp.
 */
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w411dp-h891dp-xhdpi")
class InteraccionesTest : BaseDeFotos() {

    /** Una opción del menú «+ Nuevo»: el menú es una ventanita encima de la pantalla, la última en dibujarse. */
    private fun opcionDelMenu(texto: String) = compose.onAllNodesWithText(texto).onLast()

    @Test
    fun el_buscador_encuentra_y_abre_una_persona() {
        entrarComo(Roles.ADMINISTRACION)
        abrir("search")
        compose.onNode(hasSetTextAction()).performTextInput("maria")
        // La tecla «Buscar» del teclado busca de una vez, sin esperar el instante de «dejó de escribir».
        compose.onNode(hasSetTextAction()).performImeAction()
        compose.mainClock.advanceTimeBy(1000)
        compose.waitForIdle()
        compose.onNodeWithText("María Gómez").assertIsDisplayed()
        sacarFoto("interaccion-01-buscador-con-resultados")

        compose.onNodeWithText("María Gómez").performClick()
        compose.waitForIdle()
        assertEquals("createUser?tab={tab}&search={search}", rutaActual())
        assertEquals("María Gómez", Uri.decode(argumentoActual("search").orEmpty()))
    }

    @Test
    fun el_buscador_filtra_por_lugar() {
        entrarComo(Roles.ADMINISTRACION)
        abrir("search")
        compose.onNode(hasSetTextAction()).performTextInput("maria")
        compose.onNode(hasSetTextAction()).performImeAction()
        compose.mainClock.advanceTimeBy(1000)
        compose.waitForIdle()
        compose.onNodeWithText("Personas").performClick()
        compose.mainClock.advanceTimeBy(1000)
        compose.waitForIdle()
        sacarFoto("interaccion-02-buscador-en-personas")
    }

    @Test
    fun nuevo_de_administracion_abre_el_menu_y_lleva_a_publicar_un_comunicado() {
        entrarComo(Roles.ADMINISTRACION)
        abrir("home")
        compose.onNodeWithContentDescription("Nuevo: crear algo").performClick()
        compose.waitForIdle()
        listOf("Comunicado", "Usuario", "Torre", "Apartamento", "PQRS para un residente").forEach {
            opcionDelMenu(it).assertExists()
        }
        opcionDelMenu("Comunicado").performClick()
        compose.waitForIdle()
        assertEquals("announcements?tab={tab}", rutaActual())
        assertEquals("publicar", argumentoActual("tab"))
        sacarFoto("interaccion-03-nuevo-abre-publicar-comunicado")
    }

    @Test
    fun nuevo_de_porteria_abre_el_menu_y_lleva_a_registrar_una_visita() {
        entrarComo(Roles.PORTERIA)
        abrir("home")
        compose.onNodeWithContentDescription("Nuevo: crear algo").performClick()
        compose.waitForIdle()
        listOf("Visita", "Paquete", "Entrada de vehículo").forEach {
            opcionDelMenu(it).assertExists()
        }
        opcionDelMenu("Visita").performClick()
        compose.waitForIdle()
        assertEquals("registry?tab={tab}&search={search}", rutaActual())
        assertEquals("registrar-visita", argumentoActual("tab"))
        sacarFoto("interaccion-04-nuevo-abre-registrar-visita")
    }

    @Test
    fun la_lupa_abre_el_buscador() {
        entrarComo(Roles.ADMINISTRACION)
        abrir("home")
        compose.onNodeWithContentDescription("Buscar").performClick()
        compose.waitForIdle()
        assertEquals("search", rutaActual())
    }

    @Test
    fun una_zona_cerrada_muestra_el_motivo_y_no_deja_reservar() {
        entrarComo(Roles.RESIDENTE)
        abrir("reservations")
        compose.mainClock.advanceTimeBy(1000)
        compose.waitForIdle()
        compose.onAllNodesWithText("Nueva reserva").onFirst().performClick()
        compose.waitForIdle()
        // Con una zona abierta el formulario ofrece reservar; la zona cerrada lo dice en su botón.
        compose.onNodeWithText("Reservar").assertExists()
        compose.onNodeWithText("Cancha múltiple · Cerrada").performClick()
        compose.waitForIdle()
        compose.onNodeWithText("Cancha múltiple está cerrada por la administración", substring = true).assertIsDisplayed()
        compose.onNodeWithText("Motivo: Cambio del piso", substring = true).assertIsDisplayed()
        compose.onNodeWithText("Reservar").assertDoesNotExist()
        sacarFoto("interaccion-07-zona-cerrada")
    }

    @Test
    fun el_inicio_de_administracion_escribe_las_horas_de_paquetes_que_fijo_la_unidad() {
        DatosDeMentira.reglasDeLaUnidad = UnitRules(packageOrangeHours = 40, packageRedHours = 60)
        entrarComo(Roles.ADMINISTRACION)
        abrir("home")
        compose.mainClock.advanceTimeBy(1000)
        compose.waitForIdle()
        compose.onNodeWithText("Paquetes con más de 40 h").assertExists()
        compose.onNodeWithText("1 con más de 60 h").assertExists()
        compose.onNodeWithText("Paquetes con más de 48 h").assertDoesNotExist()
        sacarFoto("interaccion-08-horas-de-paquetes-de-la-unidad")
    }

    @Test
    fun el_plazo_de_una_pqrs_nueva_sigue_la_regla_de_su_tipo() {
        DatosDeMentira.reglasDeLaUnidad = UnitRules(pqrsTermDays = 20, pqrsTermsByCategory = mapOf("Daño" to 5))
        entrarComo(Roles.RESIDENTE)
        // En la app las reglas llegan al abrir el inicio; aquí se piden directamente.
        runBlocking { ComplexInfoStore.refresh() }
        abrir("pqrs?tab=nueva")
        compose.mainClock.advanceTimeBy(1000)
        compose.waitForIdle()
        // Una petición usa el plazo general de la unidad; un daño, el suyo propio.
        compose.onNodeWithText("tiene 20 días hábiles para ser respondida", substring = true).assertExists()
        compose.onAllNodesWithText("Daño").onLast().performClick()
        compose.waitForIdle()
        compose.onNodeWithText("tiene 5 días hábiles para ser respondida", substring = true).assertExists()
        sacarFoto("interaccion-09-plazo-de-pqrs-por-tipo")
    }

    @Test
    fun preferencias_cambia_el_tamano_del_texto() {
        entrarComo(Roles.ADMINISTRACION)
        abrir("preferences")
        assertEquals(TextSize.NORMAL, AppPreferences.textSize)

        compose.onNodeWithText("Grande").performClick()
        compose.waitForIdle()
        assertEquals(TextSize.LARGE, AppPreferences.textSize)
        sacarFoto("interaccion-05-preferencias-grande")

        compose.onNodeWithText("Muy grande").performClick()
        compose.waitForIdle()
        assertEquals(TextSize.EXTRA_LARGE, AppPreferences.textSize)
        sacarFoto("interaccion-06-preferencias-muy-grande")

        compose.onNodeWithText("Normal").performClick()
        compose.waitForIdle()
        assertEquals(TextSize.NORMAL, AppPreferences.textSize)
    }
}
