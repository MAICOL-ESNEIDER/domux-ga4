// HomeScreen.kt — el MENÚ que se ve después de iniciar sesión. Es UNA sola pantalla
// (mismo archivo para los 3 roles), y decide qué botones mostrar según Session.role.
// Es el mismo patrón de "if (Session.isAdmin)" de la GA3, extendido a 3 roles.

package com.dracknoval.domux

import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive

@Composable
fun HomeScreen(navController: NavController) {
    var unreadCount by remember { mutableIntStateOf(0) }
    var notificationError by remember { mutableStateOf<String?>(null) }
    var permissionRequested by remember { mutableStateOf(false) }
    val knownNotificationIds = remember(Session.userId) { mutableStateOf<Set<Int>?>(null) }
    val context = androidx.compose.ui.platform.LocalContext.current
    val permissionLauncher = androidx.activity.compose.rememberLauncherForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (!granted) notificationError = "Activa el permiso de notificaciones para recibir avisos locales."
    }
    val backStackEntry by navController.currentBackStackEntryFlow.collectAsState(
        initial = navController.currentBackStackEntry
    )
    val currentRoute = backStackEntry?.destination?.route

    LaunchedEffect(currentRoute, Session.userId) {
        if (currentRoute != "home") return@LaunchedEffect
        if (
            android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU &&
            androidx.core.content.ContextCompat.checkSelfPermission(
                context,
                android.Manifest.permission.POST_NOTIFICATIONS
            ) != android.content.pm.PackageManager.PERMISSION_GRANTED &&
            !permissionRequested
        ) {
            permissionRequested = true
            permissionLauncher.launch(android.Manifest.permission.POST_NOTIFICATIONS)
        }
        while (isActive) {
            try {
                val response = RetrofitClient.api.getNotifications(Session.bearer())
                if (response.isSuccessful) {
                    val notifications = response.body()?.notifications.orEmpty()
                    unreadCount = notifications.count { !it.isRead }
                    val currentIds = notifications.mapTo(mutableSetOf()) { it.id }
                    val previousIds = knownNotificationIds.value
                    if (previousIds != null) {
                        notifications.filter { !it.isRead && it.id !in previousIds }.forEach { notification ->
                            if (DomuxLocalNotifications.show(context, notification)) {
                                notificationError = null
                            } else if (
                                android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU &&
                                androidx.core.content.ContextCompat.checkSelfPermission(
                                    context,
                                    android.Manifest.permission.POST_NOTIFICATIONS
                                ) != android.content.pm.PackageManager.PERMISSION_GRANTED
                            ) {
                                notificationError = "Activa el permiso de notificaciones para recibir avisos locales."
                            }
                        }
                    }
                    knownNotificationIds.value = currentIds
                    if (notificationError?.startsWith("No se pudo") == true) notificationError = null
                } else {
                    notificationError = "No se pudo actualizar el contador de notificaciones."
                }
            } catch (exception: Exception) {
                notificationError = "Sin conexión para actualizar notificaciones: ${exception.message}"
            }
            delay(30_000)
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp)
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.Top,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text("Hola, ${Session.userName ?: "usuario"}", fontSize = 24.sp)
        Text(
            when {
                Session.isAdmin -> "Rol: Administrador"
                Session.isResident -> "Rol: Residente" + (Session.apartment?.let { " · $it" } ?: "")
                Session.isGuard -> "Rol: Guardia de seguridad"
                else -> "Rol: desconocido"
            }
        )
        Spacer(Modifier.height(32.dp))

        Button(onClick = { navController.navigate("announcements") }, modifier = Modifier.fillMaxWidth()) {
            Text("Anuncios de la unidad")
        }
        Spacer(Modifier.height(12.dp))
        Button(
            onClick = { navController.navigate("notifications") },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(if (unreadCount > 0) "Notificaciones · $unreadCount sin leer" else "Notificaciones")
        }
        notificationError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Spacer(Modifier.height(12.dp))

        if (Session.isAdmin) {
            Button(onClick = { navController.navigate("pqrs") }, modifier = Modifier.fillMaxWidth()) {
                Text("Ver PQRS de residentes")
            }
            Spacer(Modifier.height(12.dp))
            Button(onClick = { navController.navigate("reservations") }, modifier = Modifier.fillMaxWidth()) {
                Text("Ver reservas de zonas comunes")
            }
            Spacer(Modifier.height(12.dp))
            Button(onClick = { navController.navigate("registry") }, modifier = Modifier.fillMaxWidth()) {
                Text("Ver registros de portería")
            }
            Spacer(Modifier.height(12.dp))
            Button(onClick = { navController.navigate("createUser") }, modifier = Modifier.fillMaxWidth()) {
                Text("Crear usuario (residente o guardia)")
            }
            Spacer(Modifier.height(12.dp))
        }

        if (Session.isResident) {
            Button(onClick = { navController.navigate("pqrs") }, modifier = Modifier.fillMaxWidth()) {
                Text("Mis PQRS")
            }
            Spacer(Modifier.height(12.dp))
            Button(onClick = { navController.navigate("reservations") }, modifier = Modifier.fillMaxWidth()) {
                Text("Reservar zona común")
            }
            Spacer(Modifier.height(12.dp))
            Button(onClick = { navController.navigate("registry") }, modifier = Modifier.fillMaxWidth()) {
                Text("Mis notificaciones (paquetes y visitas)")
            }
            Spacer(Modifier.height(12.dp))
        }

        if (Session.isGuard) {
            Button(onClick = { navController.navigate("registry") }, modifier = Modifier.fillMaxWidth()) {
                Text("Registrar paquete / visitante")
            }
            Spacer(Modifier.height(12.dp))
        }

        Spacer(Modifier.height(20.dp))
        OutlinedButton(
            onClick = {
                Session.clear()
                navController.navigate("login") { popUpTo(0) }
            },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Cerrar sesión")
        }
    }
}
