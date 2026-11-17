package com.dracknoval.domux.pantallas

import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import org.junit.Test
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * La pantalla de Documentos de la unidad (DEC-032) tocada como lo haría cada persona: qué documentos ve cada
 * rol y cómo se abre uno. El celular es «muy alto» (411 × 2000 dp) para que toda la lista quede dibujada y
 * se pueda comprobar lo que hay y lo que no hay en ella. Además de comprobar, deja fotos.
 */
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w411dp-h2000dp-xhdpi")
class PantallaDeDocumentosTest : BaseDeFotos() {

    private fun abrirDocumentos() {
        abrir("documents")
        compose.mainClock.advanceTimeBy(1000)
        compose.waitForIdle()
    }

    @Test
    fun el_residente_ve_solo_los_documentos_que_le_marcaron_y_abre_uno() {
        entrarComo(Roles.RESIDENTE)
        abrirDocumentos()
        // María es propietaria: ve lo marcado para propietarios, agrupado por tipo.
        compose.onNodeWithText("Manual de convivencia 2027").assertIsDisplayed()
        compose.onNodeWithText("Reglas de la piscina").assertExists()
        compose.onNodeWithText("Presupuesto aprobado 2027").assertExists()
        compose.onNodeWithText("Gastos del primer semestre").assertExists()
        compose.onNodeWithText("Acta de la asamblea de marzo").assertExists()
        // No ve lo de la portería ni el borrador que solo ve la administración.
        compose.onNodeWithText("Protocolo de portería").assertDoesNotExist()
        compose.onNodeWithText("Borrador del reglamento de mascotas").assertDoesNotExist()
        // Y tampoco sabe a quién se lo muestra la administración.
        compose.onAllNodesWithText("Lo ven:", substring = true).assertCountEquals(0)
        sacarFoto("documentos-01-residente")

        // Al tocar uno se descarga y se abre dentro de la app; el botón «Cerrar» lo cierra.
        compose.onNodeWithText("Reglas de la piscina").performClick()
        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithContentDescription("Cerrar").fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithContentDescription("Cerrar").performClick()
        compose.waitForIdle()
        compose.onAllNodesWithContentDescription("Cerrar").assertCountEquals(0)
    }

    @Test
    fun la_administracion_ve_todos_los_documentos_y_a_quien_se_los_muestra() {
        entrarComo(Roles.ADMINISTRACION)
        abrirDocumentos()
        compose.onNodeWithText("Borrador del reglamento de mascotas").assertExists()
        compose.onNodeWithText("Protocolo de portería").assertExists()
        compose.onNodeWithText("Solo la administración lo ve").assertExists()
        compose.onAllNodesWithText("Lo ven: Propietarios", substring = true).onFirst().assertExists()
        compose.onNodeWithText("Lo ven: Portería").assertExists()
        sacarFoto("documentos-02-administracion")
    }

    @Test
    fun la_porteria_ve_solo_los_documentos_marcados_para_ella() {
        entrarComo(Roles.PORTERIA)
        abrirDocumentos()
        compose.onNodeWithText("Protocolo de portería").assertExists()
        compose.onNodeWithText("Manual de convivencia 2027").assertExists()
        compose.onNodeWithText("Reglas de la piscina").assertExists()
        compose.onNodeWithText("Presupuesto aprobado 2027").assertDoesNotExist()
        compose.onNodeWithText("Borrador del reglamento de mascotas").assertDoesNotExist()
        sacarFoto("documentos-03-porteria")
    }
}
