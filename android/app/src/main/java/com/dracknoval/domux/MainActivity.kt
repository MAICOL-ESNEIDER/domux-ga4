package com.dracknoval.domux

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.util.Log
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.dracknoval.domux.data.PushRegistration
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.ui.theme.DomuxAppTheme
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private lateinit var appNavController: NavHostController
    private var pendingNotificationRoute: String? = null
    private val notificationPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (!granted) {
                Log.i("DomuxNotifications", "Notification permission was not granted.")
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        RetrofitClient.initialize(this)
        Session.restore(this)
        pendingNotificationRoute = intent.notificationRoute()
        markNotificationOpened(intent)
        DomuxLocalNotifications.createChannel(this)
        DomuxNotifier.createNotificationChannel(this)
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
                            SessionStartupScreen(navController, ::onAuthenticationComplete)
                        }
                        composable("login") {
                            LoginScreen(navController, ::onAuthenticationComplete)
                        }
                        composable("force_password_change") {
                            ForcePasswordChangeScreen(navController)
                        }
                        composable("home") { HomeScreen(navController) }
                        composable("announcements") { AnnouncementsScreen(navController) }
                        composable(
                            "pqrs?residentId={residentId}",
                            arguments = listOf(navArgument("residentId") {
                                type = NavType.IntType
                                defaultValue = -1
                            })
                        ) { entry ->
                            PqrsScreen(
                                navController,
                                entry.arguments?.getInt("residentId")?.takeIf { it > 0 }
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
                        composable(
                            "registry?initialTab={initialTab}",
                            arguments = listOf(navArgument("initialTab") {
                                type = NavType.IntType
                                defaultValue = 0
                            })
                        ) { entry ->
                            RegistryScreen(
                                navController,
                                entry.arguments?.getInt("initialTab") ?: 0
                            )
                        }
                        composable("createUser") { CreateUserScreen(navController) }
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
                    }
                }
            }
        }
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                while (isActive) {
                    syncUnreadNotifications()
                    delay(NOTIFICATION_SYNC_INTERVAL_MS)
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
        if (Session.mustChangePassword) {
            pendingNotificationRoute = null
            return
        }
        val route = pendingNotificationRoute
        pendingNotificationRoute = null
        if (route != null) appNavController.navigate(route)
    }

    private fun onAuthenticationComplete() {
        requestNotificationPermission()
        DomuxNotificationWorker.enqueuePeriodic(applicationContext)
        lifecycleScope.launch { syncUnreadNotifications() }
        navigateAfterAuthentication()
    }

    private fun requestNotificationPermission() {
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    private suspend fun syncUnreadNotifications() {
        if (Session.token.isNullOrBlank()) return
        try {
            val responseCode = DomuxNotificationSync.fetchAndShow(applicationContext)
            if (responseCode >= 500) {
                Log.w("DomuxNotifications", "Notification sync returned HTTP $responseCode.")
            }
        } catch (exception: CancellationException) {
            throw exception
        } catch (exception: Exception) {
            Log.w("DomuxNotifications", "Notification sync failed.", exception)
        }
    }

    private fun markNotificationOpened(intent: Intent) {
        val notificationId = intent.getStringExtra("notificationId")?.toIntOrNull()
            ?: intent.getIntExtra("notification_id", -1).takeIf { it > 0 }
        if (notificationId != null) DomuxLocalNotifications.markSeen(this, notificationId)
    }

    private fun Intent.notificationRoute(): String? {
        val route = getStringExtra(EXTRA_NOTIFICATION_ROUTE) ?: getStringExtra("route")
        return route?.takeIf {
            it in setOf("pqrs", "reservations", "registry", "announcements", "notifications")
        }
    }

    companion object {
        const val EXTRA_NOTIFICATION_ROUTE = "domux_notification_route"
        private const val NOTIFICATION_SYNC_INTERVAL_MS = 60_000L
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
                        val destination = if (Session.mustChangePassword) {
                            "force_password_change"
                        } else {
                            "home"
                        }
                        navController.navigate(destination) {
                            popUpTo("session") { inclusive = true }
                            launchSingleTop = true
                        }
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

    LaunchedEffect(Unit) {
        RetrofitClient.resolveBestServerUrl(RetrofitClient.fallbackUrls)
        validateSession()
    }
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
