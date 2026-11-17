package com.dracknoval.domux.pantallas

import org.junit.Test
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * Las pantallas con mucho contenido en un celular «muy alto» (411 × 2000 dp): así la foto muestra
 * la lista completa y no solo lo que cabe en una pantalla. Sirven para comprobar que dividir los
 * archivos grandes no cambia nada de lo que está más abajo.
 */
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w411dp-h2000dp-xhdpi")
class FotosLargasTest : BaseDeFotos() {

    @Test
    fun administracion_inicio() {
        entrarComo(Roles.ADMINISTRACION)
        foto("larga-administracion-01-inicio", "home")
    }

    @Test
    fun administracion_pqrs() {
        entrarComo(Roles.ADMINISTRACION)
        foto("larga-administracion-02-pqrs", "pqrs")
    }

    @Test
    fun administracion_reservas() {
        entrarComo(Roles.ADMINISTRACION)
        foto("larga-administracion-03-reservas", "reservations")
    }

    @Test
    fun administracion_paquetes() {
        entrarComo(Roles.ADMINISTRACION)
        foto("larga-administracion-04-paquetes", "registry")
    }

    @Test
    fun administracion_usuarios() {
        entrarComo(Roles.ADMINISTRACION)
        foto("larga-administracion-05-usuarios", "createUser")
    }

    @Test
    fun administracion_apartamentos() {
        entrarComo(Roles.ADMINISTRACION)
        foto("larga-administracion-06-apartamento", "unitProfile/Torre%201%20%C2%B7%20Apto%20101")
    }

    @Test
    fun administracion_comunicados() {
        entrarComo(Roles.ADMINISTRACION)
        foto("larga-administracion-07-comunicados", "announcements")
    }

    @Test
    fun porteria_inicio() {
        entrarComo(Roles.PORTERIA)
        foto("larga-porteria-01-inicio", "home")
    }

    @Test
    fun porteria_visitas() {
        entrarComo(Roles.PORTERIA)
        foto("larga-porteria-02-visitas", "registry?tab=visitas")
    }

    @Test
    fun residente_inicio() {
        entrarComo(Roles.RESIDENTE)
        foto("larga-residente-01-inicio", "home")
    }

    @Test
    fun residente_reservas() {
        entrarComo(Roles.RESIDENTE)
        foto("larga-residente-02-reservas", "reservations")
    }

    @Test
    fun residente_perfil() {
        entrarComo(Roles.RESIDENTE)
        foto("larga-residente-03-perfil", "profile")
    }
}
