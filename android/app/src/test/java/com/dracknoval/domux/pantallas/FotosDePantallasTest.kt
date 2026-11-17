package com.dracknoval.domux.pantallas

import android.Manifest
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onRoot
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.dracknoval.domux.HomeScreen
import com.dracknoval.domux.MoreScreen
import com.dracknoval.domux.PreferencesScreen
import com.dracknoval.domux.SearchScreen
import com.dracknoval.domux.SearchViewModel
import com.dracknoval.domux.data.ComplexInfoStore
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.ui.theme.DomuxAppTheme
import com.github.takahirom.roborazzi.captureRoboImage
import org.junit.After
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * Las fotos de pantalla de la app. Cada prueba dibuja una pantalla de verdad (la misma que ve la
 * persona en el celular) con datos de mentira ([DatosDeMentira]) y le saca una foto.
 *
 * Solo corren en GitHub (no hay Gradle en el computador). Con «-Proborazzi.test.record=true» las
 * fotos quedan en android/app/build/fotos-de-pantallas; sin eso, las pruebas solo revisan que cada
 * pantalla se pueda dibujar sin errores.
 *
 * Celular simulado: 411 × 891 dp, como un Pixel 7.
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w411dp-h891dp-xxhdpi")
class FotosDePantallasTest {

    @get:Rule
    val compose = createComposeRule()

    @Before
    fun prepararConexionDeMentira() {
        RetrofitClient.api = DatosDeMentira.api()
        // Sin este permiso el inicio pediría el de las notificaciones y taparía la foto.
        shadowOf(RuntimeEnvironment.getApplication()).grantPermissions(Manifest.permission.POST_NOTIFICATIONS)
    }

    @After
    fun cerrarSesion() {
        Session.token = null
        Session.userId = null
        Session.userName = null
        Session.lastName = null
        Session.email = null
        Session.role = null
        Session.apartment = null
        ComplexInfoStore.clear()
    }

    // --- Inicio de cada rol ---

    @Test
    fun inicio_administracion() {
        entrarComo(ADMINISTRACION)
        foto("01-inicio-administracion", "home") { HomeScreen(it) }
    }

    @Test
    fun inicio_porteria() {
        entrarComo(PORTERIA)
        foto("02-inicio-porteria", "home") { HomeScreen(it) }
    }

    @Test
    fun inicio_residente() {
        entrarComo(RESIDENTE)
        foto("03-inicio-residente", "home") { HomeScreen(it) }
    }

    // --- Pantallas nuevas de esta versión ---

    @Test
    fun buscador_administracion_con_resultados() {
        entrarComo(ADMINISTRACION)
        // Se escribe y se busca de una vez (sin esperar el instante de «dejó de escribir»).
        val buscador = SearchViewModel().apply {
            setText("maria")
            searchNow()
        }
        foto("04-buscador-administracion", "search") { SearchScreen(it, buscador) }
    }

    @Test
    fun buscador_porteria_vacio() {
        entrarComo(PORTERIA)
        foto("05-buscador-porteria", "search") { SearchScreen(it) }
    }

    @Test
    fun mas_administracion() {
        entrarComo(ADMINISTRACION)
        foto("06-mas-administracion", "more") { MoreScreen(it) }
    }

    @Test
    fun preferencias_administracion() {
        entrarComo(ADMINISTRACION)
        foto("07-preferencias-administracion", "preferences") { PreferencesScreen(it) }
    }

    // --- Herramientas ---

    private fun entrarComo(rol: Rol) {
        Session.token = "token-de-prueba"
        Session.userId = rol.id
        Session.userName = rol.nombre
        Session.lastName = rol.apellido
        Session.email = rol.correo
        Session.role = rol.codigo
        Session.apartment = rol.apartamento
    }

    /** Dibuja la pantalla dentro de un NavHost que empieza en [ruta] (así el menú marca la opción de siempre) y le saca la foto. */
    private fun foto(nombre: String, ruta: String, pantalla: @Composable (NavHostController) -> Unit) {
        compose.setContent {
            DomuxAppTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    val navegacion = rememberNavController()
                    NavHost(navController = navegacion, startDestination = ruta) {
                        composable(ruta) { pantalla(navegacion) }
                    }
                }
            }
        }
        compose.waitForIdle()
        compose.onRoot().captureRoboImage("$CARPETA/$nombre.png")
    }

    private class Rol(
        val codigo: String,
        val id: Int,
        val nombre: String,
        val apellido: String,
        val correo: String,
        val apartamento: String?
    )

    private companion object {
        const val CARPETA = "build/fotos-de-pantallas"

        val ADMINISTRACION = Rol("ADMIN", 1, "Administración", "Domux", "admin@domux.com", null)
        val PORTERIA = Rol("GUARD", 2, "Guardia", "Principal", "guardia@domux.com", null)
        val RESIDENTE = Rol("RESIDENT", 6, "María", "Gómez", "maria@domux.com", "Torre 1 · Apto 101")
    }
}
