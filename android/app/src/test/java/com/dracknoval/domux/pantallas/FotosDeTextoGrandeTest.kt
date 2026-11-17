package com.dracknoval.domux.pantallas

import com.dracknoval.domux.data.TextSize
import org.junit.Test
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * Las pantallas con el texto en «Muy grande» (Preferencias): sirven para ver que nada se corta ni
 * se encima cuando la persona agranda las letras. Celular de 411 × 891 dp.
 */
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w411dp-h891dp-xhdpi")
class FotosDeTextoGrandeTest : BaseDeFotos() {

    @Test
    fun administracion_inicio() {
        entrarComo(Roles.ADMINISTRACION)
        conTamanoDeTexto(TextSize.EXTRA_LARGE)
        foto("texto-muy-grande-administracion-01-inicio", "home")
    }

    @Test
    fun administracion_preferencias() {
        entrarComo(Roles.ADMINISTRACION)
        conTamanoDeTexto(TextSize.EXTRA_LARGE)
        foto("texto-muy-grande-administracion-02-preferencias", "preferences")
    }

    @Test
    fun administracion_pqrs() {
        entrarComo(Roles.ADMINISTRACION)
        conTamanoDeTexto(TextSize.EXTRA_LARGE)
        foto("texto-muy-grande-administracion-03-pqrs", "pqrs")
    }

    @Test
    fun porteria_inicio() {
        entrarComo(Roles.PORTERIA)
        conTamanoDeTexto(TextSize.EXTRA_LARGE)
        foto("texto-muy-grande-porteria-01-inicio", "home")
    }

    @Test
    fun residente_inicio() {
        entrarComo(Roles.RESIDENTE)
        conTamanoDeTexto(TextSize.EXTRA_LARGE)
        foto("texto-muy-grande-residente-01-inicio", "home")
    }

    @Test
    fun residente_documentos() {
        entrarComo(Roles.RESIDENTE)
        conTamanoDeTexto(TextSize.EXTRA_LARGE)
        foto("texto-muy-grande-residente-02-documentos", "documents")
    }

    @Test
    fun inicio_de_sesion() {
        conTamanoDeTexto(TextSize.EXTRA_LARGE)
        foto("texto-muy-grande-login-01-inicio-de-sesion", "login")
    }
}
