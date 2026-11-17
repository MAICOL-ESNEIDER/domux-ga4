package com.dracknoval.domux.pantallas

import org.junit.Test
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * Las ventanas que se abren encima de una pantalla (diálogos de crear): son otra «ventana» y la
 * foto se saca distinto que en el resto (ver [BaseDeFotos.fotoDeVentana]). Celular de 411 × 891 dp.
 */
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w411dp-h891dp-xhdpi")
class FotosDeVentanasTest : BaseDeFotos() {

    @Test
    fun administracion_torre_nueva() {
        entrarComo(Roles.ADMINISTRACION)
        fotoDeVentana("ventana-administracion-01-torre-nueva", "structure?action=torre")
    }

    @Test
    fun administracion_apartamento_nuevo() {
        entrarComo(Roles.ADMINISTRACION)
        fotoDeVentana("ventana-administracion-02-apartamento-nuevo", "structure?action=apartamento")
    }
}
