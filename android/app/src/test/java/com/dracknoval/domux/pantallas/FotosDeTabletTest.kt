package com.dracknoval.domux.pantallas

import org.junit.Test
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * Las mismas fotos, pero en una tablet (1280 × 800 dp): ahí el menú va a la izquierda y las
 * pantallas se reparten distinto. Se sacan solo las más importantes de cada rol.
 */
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w1280dp-h800dp-mdpi")
class FotosDeTabletTest : BaseDeFotos() {

    @Test
    fun administracion_inicio() {
        entrarComo(Roles.ADMINISTRACION)
        foto("tablet-administracion-01-inicio", "home")
    }

    @Test
    fun administracion_pqrs() {
        entrarComo(Roles.ADMINISTRACION)
        foto("tablet-administracion-02-pqrs", "pqrs")
    }

    @Test
    fun administracion_estructura() {
        entrarComo(Roles.ADMINISTRACION)
        foto("tablet-administracion-03-estructura", "structure")
    }

    @Test
    fun porteria_inicio() {
        entrarComo(Roles.PORTERIA)
        foto("tablet-porteria-01-inicio", "home")
    }

    @Test
    fun porteria_visitas() {
        entrarComo(Roles.PORTERIA)
        foto("tablet-porteria-02-visitas", "registry?tab=visitas")
    }

    @Test
    fun residente_inicio() {
        entrarComo(Roles.RESIDENTE)
        foto("tablet-residente-01-inicio", "home")
    }

    @Test
    fun residente_reservas() {
        entrarComo(Roles.RESIDENTE)
        foto("tablet-residente-02-reservas", "reservations")
    }
}
