// MainActivity.kt — punto de entrada de la app. Usa Navigation Compose con TODAS
// las rutas declaradas inline, exactamente como en GA2-GA3.

package com.dracknoval.domux

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.NavType
import androidx.navigation.navArgument
import com.dracknoval.domux.ui.theme.DomuxAppTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        DomuxLocalNotifications.createChannel(this)
        setContent {
            DomuxAppTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    val navController = rememberNavController()
                    NavHost(navController = navController, startDestination = "login") {
                        composable("login") { LoginScreen(navController) }
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
                        composable("registry") { RegistryScreen(navController) }
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
    }
}
