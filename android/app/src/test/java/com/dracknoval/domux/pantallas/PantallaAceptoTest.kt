package com.dracknoval.domux.pantallas

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.dracknoval.domux.data.Session
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * La pantalla «Acepto» tocada como lo haría una persona que entra por primera vez: ve los textos, no puede
 * continuar sin marcar que los leyó y, al aceptar, la sesión queda al día. Además de comprobar, deja fotos.
 */
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w411dp-h2000dp-xhdpi")
class PantallaAceptoTest : BaseDeFotos() {

    private fun abrirAcepto() {
        entrarComo(Roles.RESIDENTE)
        Session.legalAcceptanceRequired = true
        abrir("acepto")
        compose.mainClock.advanceTimeBy(1000)
        compose.waitForIdle()
    }

    @Test
    fun muestra_los_textos_y_no_deja_continuar_sin_marcar() {
        abrirAcepto()

        compose.onNodeWithText("Antes de continuar, lee y acepta").assertIsDisplayed()
        compose.onNodeWithText("Ley 1581 de 2012", substring = true).assertExists()
        compose.onNodeWithText("Términos y condiciones de uso").assertExists()
        compose.onNodeWithText("Política de privacidad").assertExists()
        compose.onNodeWithText("Si soy menor de edad, acepta mi representante legal.", substring = true).assertExists()
        compose.onNodeWithText("Acepto y continuar").assertIsNotEnabled()
        sacarFoto("acepto-01-antes-de-marcar")
    }

    @Test
    fun se_puede_leer_un_texto_completo() {
        abrirAcepto()

        compose.onNodeWithText("1. Quién cuida tus datos").assertDoesNotExist()
        compose.onAllNodesWithText("Leer el texto completo").onFirst().performClick()
        compose.waitForIdle()
        compose.onNodeWithText("1. Quién cuida tus datos").assertExists()
        sacarFoto("acepto-02-texto-abierto")
    }

    @Test
    fun al_aceptar_la_sesion_queda_al_dia() {
        abrirAcepto()
        assertTrue(Session.legalAcceptanceRequired)

        compose.onNodeWithText("Leí los textos y los acepto.", substring = true).performClick()
        compose.waitForIdle()
        compose.onNodeWithText("Acepto y continuar").assertIsEnabled()
        sacarFoto("acepto-03-marcado")

        compose.onNodeWithText("Acepto y continuar").performClick()
        compose.waitUntil(timeoutMillis = 5_000) { !Session.legalAcceptanceRequired }
        assertFalse(Session.legalAcceptanceRequired)
    }

    @Test
    fun quien_no_acepta_puede_cerrar_la_sesion() {
        abrirAcepto()

        compose.onNodeWithText("No acepto, cerrar sesión").performClick()
        compose.waitForIdle()

        assertTrue(Session.token.isNullOrBlank())
        assertFalse(Session.legalAcceptanceRequired)
    }
}
