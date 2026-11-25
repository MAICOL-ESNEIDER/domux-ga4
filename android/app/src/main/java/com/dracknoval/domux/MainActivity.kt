package com.dracknoval.domux

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.dracknoval.domux.data.AppPreferences
import com.dracknoval.domux.data.AppTempFiles
import com.dracknoval.domux.data.PushRegistration
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.ui.theme.DomuxAppTheme
import kotlinx.coroutines.launch

// Los atajos del buscador y de «+ Nuevo» abren una pantalla ya en una pestaña («tab») o con un texto
// de búsqueda puesto («search»). Sin ellos, cada pantalla abre como siempre.
private val tabArg = navArgument("tab") {
    type = NavType.StringType
    defaultValue = ""
}
private val searchArg = navArgument("search") {
    type = NavType.StringType
    defaultValue = ""
}

class MainActivity : ComponentActivity() {
    private lateinit var appNavController: NavHostController
    private var pendingNotificationRoute: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Al abrir la app se borra lo temporal que haya quedado de la vez anterior (adjuntos abiertos, QR compartido).
        if (savedInstanceState == null) AppTempFiles.clearAll(this)
        Session.restore(this)
        // El tamaño del texto que la persona eligió en Preferencias.
        AppPreferences.load(this)
        pendingNotificationRoute = intent.notificationRoute()
        markNotificationOpened(intent)
        DomuxLocalNotifications.createChannel(this)
        setContent {
            DomuxAppTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    val navController = rememberNavController()
                    appNavController = navController
                    NavHost(navController = navController, startDestination = "session") {
                        composable("session") {
                            SessionStartupScreen(navController, ::navigateAfterAuthentication)
                        }
                        composable("login") {
                            LoginScreen(navController, ::navigateAfterAuthentication)
                        }
                        composable("home") { HomeScreen(navController) }
                        composable("announcements?tab={tab}", arguments = listOf(tabArg)) { entry ->
                            AnnouncementsScreen(navController, initialTab = entry.arguments?.getString("tab").orEmpty())
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
                                navController,
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
                            ReservationsScreen(
                                navController,
                                entry.arguments?.getInt("residentId")?.takeIf { it > 0 }
                            )
                        }
                        // «tab» abre portería en una pestaña: «paquetes» o «visitas» (los botones del guardia).
                        composable("registry?tab={tab}&search={search}", arguments = listOf(tabArg, searchArg)) { entry ->
                            RegistryScreen(
                                navController,
                                initialTab = entry.arguments?.getString("tab").orEmpty(),
                                initialSearch = entry.arguments?.getString("search").orEmpty()
                            )
                        }
                        composable("vehicles?tab={tab}&search={search}", arguments = listOf(tabArg, searchArg)) { entry ->
                            VehiclesScreen(
                                navController,
                                initialTab = entry.arguments?.getString("tab").orEmpty(),
                                initialSearch = entry.arguments?.getString("search").orEmpty()
                            )
                        }
                        composable("createUser?tab={tab}&search={search}", arguments = listOf(tabArg, searchArg)) { entry ->
                            CreateUserScreen(
                                navController,
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
                            StructureScreen(navController, initialAction = entry.arguments?.getString("action").orEmpty())
                        }
                        composable("profile") { ResidentProfileScreen(navController) }
                        composable(
                            "unitProfile/{apartment}",
                            arguments = listOf(navArgument("apartment") { type = NavType.StringType })
                        ) { entry ->
                            UnitProfileScreen(
                                navController,
                                entry.arguments?.getString("apartment").orEmpty()
                            )
                        }
                        composable("notifications") { NotificationsScreen(navController) }
                        composable("documents") { DocumentsScreen(navController) }
                        // Documentos legales (públicos): sin «slug» es la lista; con «slug», el texto de ese documento.
                        composable(
                            "legal?slug={slug}",
                            arguments = listOf(navArgument("slug") {
                                type = NavType.StringType
                                defaultValue = ""
                            })
                        ) { entry ->
                            LegalScreen(navController, slug = entry.arguments?.getString("slug").orEmpty())
                        }
                        composable("more") { MoreScreen(navController) }
                        composable("search") { SearchScreen(navController) }
                        composable("preferences") { PreferencesScreen(navController) }
                    }
                    // Con una contraseña temporal (se la restableció el administrador) esta pantalla
                    // tapa todo lo demás hasta que la persona ponga una propia.
                    if (Session.mustChangePassword) {
                        PasswordChangeScreen(
                            onChanged = { navController.navigate("home") { popUpTo(0) } },
                            onLoggedOut = { navController.navigate("login") { popUpTo(0) } }
                        )
                    } else if (Session.legalAcceptanceRequired) {
                        // Pantalla «Acepto»: la primera vez que entra (y cuando cambian los textos legales)
                        // la persona lee y acepta cómo se usan sus datos. Va después de la contraseña.
                        LegalAcceptScreen(
                            onAccepted = { navController.navigate("home") { popUpTo(0) } },
                            onLoggedOut = { navController.navigate("login") { popUpTo(0) } }
                        )
                    }
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        markNotificationOpened(intent)
        pendingNotificationRoute = intent.notificationRoute() ?: return
        if (
            ::appNavController.isInitialized &&
            appNavController.currentDestination?.route !in setOf("session", "login")
        ) {
            navigateAfterAuthentication()
        }
    }

    private fun navigateAfterAuthentication() {
        val route = pendingNotificationRoute
        pendingNotificationRoute = null
        if (route != null) appNavController.navigate(route)
    }

    private fun markNotificationOpened(intent: Intent) {
        val notificationId = intent.getStringExtra("notificationId")?.toIntOrNull()
            ?: intent.getIntExtra("notification_id", -1).takeIf { it > 0 }
        if (notificationId != null) DomuxLocalNotifications.markSeen(this, notificationId)
    }

    private fun Intent.notificationRoute(): String? {
        val route = getStringExtra(EXTRA_NOTIFICATION_ROUTE) ?: getStringExtra("route")
        return route?.takeIf {
            it in setOf("pqrs", "reservations", "registry", "vehicles", "announcements", "notifications")
        }
    }

    companion object {
        const val EXTRA_NOTIFICATION_ROUTE = "domux_notification_route"
    }
}

@Composable
private fun SessionStartupScreen(
    navController: NavHostController,
    onAuthenticated: () -> Unit
) {
    var error by remember { mutableStateOf<String?>(null) }
    var validating by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    fun validateSession() {
        scope.launch {
            if (Session.token.isNullOrBlank()) {
                navController.navigate("login") { popUpTo("session") { inclusive = true } }
                return@launch
            }
            validating = true
            error = null
            try {
                val response = RetrofitClient.api.currentSession(Session.bearer())
                if (response.isSuccessful) {
                    val user = response.body()?.user
                    if (user == null) {
                        error = "El servidor no envió los datos de la sesión."
                    } else {
                        Session.updateFrom(user)
                        Session.persist(context)
                        PushRegistration.registerAfterAuthentication(context.applicationContext)
                        navController.navigate("home") { popUpTo("session") { inclusive = true } }
                        onAuthenticated()
                    }
                } else if (response.code() == 401) {
                    Session.clear(context)
                    navController.navigate("login") { popUpTo("session") { inclusive = true } }
                } else {
                    error = "No se pudo validar la sesión (${response.code()}). Revisa tu conexión."
                }
            } catch (exception: Exception) {
                error = "No se pudo validar la sesión: ${exception.message}"
            } finally {
                validating = false
            }
        }
    }

    LaunchedEffect(Unit) { validateSession() }
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        if (validating) CircularProgressIndicator()
        else if (error != null) {
            Text(error.orEmpty(), color = MaterialTheme.colorScheme.error)
            Button(onClick = ::validateSession) { Text("Reintentar") }
            Button(onClick = {
                Session.clear(context)
                navController.navigate("login") { popUpTo("session") { inclusive = true } }
            }) { Text("Iniciar sesión") }
        } else CircularProgressIndicator()
    }
}
