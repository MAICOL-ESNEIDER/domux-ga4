package com.dracknoval.domux.pantallas

import android.Manifest
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onRoot
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.dracknoval.domux.AnnouncementsScreen
import com.dracknoval.domux.CreateUserScreen
import com.dracknoval.domux.HomeScreen
import com.dracknoval.domux.LegalScreen
import com.dracknoval.domux.LoginScreen
import com.dracknoval.domux.MoreScreen
import com.dracknoval.domux.NotificationsScreen
import com.dracknoval.domux.PqrsScreen
import com.dracknoval.domux.PreferencesScreen
import com.dracknoval.domux.RegistryScreen
import com.dracknoval.domux.ReservationsScreen
import com.dracknoval.domux.ResidentProfileScreen
import com.dracknoval.domux.SearchScreen
import com.dracknoval.domux.StructureScreen
import com.dracknoval.domux.UnitProfileScreen
import com.dracknoval.domux.VehiclesScreen
import com.dracknoval.domux.data.AppPreferences
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.TextSize
import com.dracknoval.domux.data.UnitRules
import com.dracknoval.domux.data.UserData
import com.dracknoval.domux.ui.theme.DomuxAppTheme
import com.github.takahirom.roborazzi.captureRoboImage
import org.junit.After
import org.junit.Before
import org.junit.Rule
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf

/** Quién tiene la sesión abierta en la foto. */
class Rol(val usuario: UserData)

/** Las tres personas de las fotos (las mismas de los datos de mentira). */
object Roles {
    val ADMINISTRACION = Rol(
        UserData(
            id = 1, name = "Administración", email = "admin@domux.com", role = "ADMIN", apartment = null,
            lastName = "Domux"
        )
    )
    val PORTERIA = Rol(
        UserData(
            id = 2, name = "Guardia", email = "guardia@domux.com", role = "GUARD", apartment = null,
            lastName = "Principal"
        )
    )
    val RESIDENTE = Rol(
        UserData(
            id = 6, name = "María", email = "maria@domux.com", role = "RESIDENT",
            apartment = "Torre 1 · Apto 101", lastName = "Gómez"
        )
    )
}

/** Dónde quedan las fotos (Roborazzi las guarda relativas a la carpeta «app»). */
private const val CARPETA_DE_FOTOS = "build/fotos-de-pantallas"

private val tabArg = navArgument("tab") {
    type = NavType.StringType
    defaultValue = ""
}
private val searchArg = navArgument("search") {
    type = NavType.StringType
    defaultValue = ""
}

/**
 * Lo que tienen en común las pruebas de fotos: la conexión de mentira, la sesión de cada rol y
 * la manera de dibujar una pantalla (con las mismas rutas de la app) y sacarle la foto.
 */
@RunWith(RobolectricTestRunner::class)
abstract class BaseDeFotos {

    @get:Rule
    val compose = createComposeRule()

    @Before
    fun prepararConexionDeMentira() {
        RetrofitClient.api = DatosDeMentira.api()
        RetrofitClient.structureApi = DatosDeMentira.estructura()
        // Sin este permiso el inicio pediría el de las notificaciones y taparía la foto.
        shadowOf(RuntimeEnvironment.getApplication()).grantPermissions(Manifest.permission.POST_NOTIFICATIONS)
    }

    @After
    fun cerrarSesion() {
        Session.clear()
        DatosDeMentira.reglasDeLaUnidad = UnitRules()
        AppPreferences.saveTextSize(RuntimeEnvironment.getApplication(), TextSize.NORMAL)
    }

    /** Pone el texto de la app en el tamaño que la persona elige en Preferencias. */
    protected fun conTamanoDeTexto(tamano: TextSize) {
        AppPreferences.saveTextSize(RuntimeEnvironment.getApplication(), tamano)
    }

    protected fun entrarComo(rol: Rol) {
        Session.token = "token-de-prueba"
        Session.updateFrom(rol.usuario)
    }

    /** Dibuja la pantalla de esa ruta (la misma que abre la app) y le saca la foto. */
    protected fun foto(nombre: String, ruta: String) {
        abrir(ruta)
        sacarFoto(nombre)
    }

    /** Solo dibuja la pantalla de esa ruta; sirve para tocar cosas antes de sacar la foto. */
    protected fun abrir(ruta: String) {
        compose.setContent { Marco { navegacion -> GrafoDeLaApp(navegacion, ruta) } }
        compose.waitForIdle()
    }

    /** La ruta en la que está la pantalla ahora (por ejemplo, después de tocar un resultado del buscador). */
    protected fun rutaActual(): String? = navegacionActual?.currentBackStackEntry?.destination?.route

    /** Un valor de la ruta actual, como «tab» o «search». */
    protected fun argumentoActual(nombre: String): String? =
        navegacionActual?.currentBackStackEntry?.arguments?.getString(nombre)

    /** Para las pantallas que necesitan algo especial (por ejemplo, el buscador ya con un texto escrito). */
    protected fun fotoConContenido(nombre: String, ruta: String, pantalla: @Composable (NavHostController) -> Unit) {
        compose.setContent {
            Marco { navegacion ->
                NavHost(navController = navegacion, startDestination = ruta) {
                    composable(ruta) { pantalla(navegacion) }
                }
            }
        }
        sacarFoto(nombre)
    }

    private var navegacionActual: NavHostController? = null

    @Composable
    private fun Marco(contenido: @Composable (NavHostController) -> Unit) {
        DomuxAppTheme {
            Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                val navegacion = rememberNavController()
                SideEffect { navegacionActual = navegacion }
                contenido(navegacion)
            }
        }
    }

    protected fun sacarFoto(nombre: String) {
        compose.waitForIdle()
        // Deja terminar la animación de entrada de la pantalla antes de la foto.
        compose.mainClock.advanceTimeBy(500)
        compose.waitForIdle()
        compose.onRoot().captureRoboImage("$CARPETA_DE_FOTOS/$nombre.png")
    }
}

/**
 * Las mismas rutas de MainActivity. La primera pantalla solo manda a la ruta pedida: así cada foto
 * sale con la pestaña y los datos que tendría la persona al abrirla desde el menú o desde un atajo.
 */
@Composable
private fun GrafoDeLaApp(navegacion: NavHostController, rutaPedida: String) {
    NavHost(navController = navegacion, startDestination = "foto-inicio") {
        composable("foto-inicio") {
            LaunchedEffect(Unit) {
                navegacion.navigate(rutaPedida) { popUpTo("foto-inicio") { inclusive = true } }
            }
        }
        composable("login") { LoginScreen(navegacion) }
        composable("home") { HomeScreen(navegacion) }
        composable("announcements?tab={tab}", arguments = listOf(tabArg)) { entry ->
            AnnouncementsScreen(navegacion, initialTab = entry.arguments?.getString("tab").orEmpty())
        }
        composable(
            "pqrs?residentId={residentId}&tab={tab}&search={search}",
            arguments = listOf(
                navArgument("residentId") {
                    type = NavType.IntType
                    defaultValue = -1
                },
                tabArg,
                searchArg
            )
        ) { entry ->
            PqrsScreen(
                navegacion,
                entry.arguments?.getInt("residentId")?.takeIf { it > 0 },
                initialTab = entry.arguments?.getString("tab").orEmpty(),
                initialSearch = entry.arguments?.getString("search").orEmpty()
            )
        }
        composable(
            "reservations?residentId={residentId}",
            arguments = listOf(navArgument("residentId") {
                type = NavType.IntType
                defaultValue = -1
            })
        ) { entry ->
            ReservationsScreen(navegacion, entry.arguments?.getInt("residentId")?.takeIf { it > 0 })
        }
        composable("registry?tab={tab}&search={search}", arguments = listOf(tabArg, searchArg)) { entry ->
            RegistryScreen(
                navegacion,
                initialTab = entry.arguments?.getString("tab").orEmpty(),
                initialSearch = entry.arguments?.getString("search").orEmpty()
            )
        }
        composable("vehicles?tab={tab}&search={search}", arguments = listOf(tabArg, searchArg)) { entry ->
            VehiclesScreen(
                navegacion,
                initialTab = entry.arguments?.getString("tab").orEmpty(),
                initialSearch = entry.arguments?.getString("search").orEmpty()
            )
        }
        composable("createUser?tab={tab}&search={search}", arguments = listOf(tabArg, searchArg)) { entry ->
            CreateUserScreen(
                navegacion,
                initialTab = entry.arguments?.getString("tab").orEmpty(),
                initialSearch = entry.arguments?.getString("search").orEmpty()
            )
        }
        composable(
            "structure?action={action}",
            arguments = listOf(navArgument("action") {
                type = NavType.StringType
                defaultValue = ""
            })
        ) { entry ->
            StructureScreen(navegacion, initialAction = entry.arguments?.getString("action").orEmpty())
        }
        composable("profile") { ResidentProfileScreen(navegacion) }
        composable(
            "unitProfile/{apartment}",
            arguments = listOf(navArgument("apartment") { type = NavType.StringType })
        ) { entry ->
            UnitProfileScreen(navegacion, entry.arguments?.getString("apartment").orEmpty())
        }
        composable("notifications") { NotificationsScreen(navegacion) }
        composable(
            "legal?slug={slug}",
            arguments = listOf(navArgument("slug") {
                type = NavType.StringType
                defaultValue = ""
            })
        ) { entry ->
            LegalScreen(navegacion, slug = entry.arguments?.getString("slug").orEmpty())
        }
        composable("more") { MoreScreen(navegacion) }
        composable("search") { SearchScreen(navegacion) }
        composable("preferences") { PreferencesScreen(navegacion) }
    }
}
