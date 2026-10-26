package com.dracknoval.domux

import android.util.Log
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.navigation.NavController
import com.dracknoval.domux.data.NotificationItem
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.PushRegistration
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

private data class HomeModule(
    val title: String,
    val detail: String,
    val icon: String,
    val route: String
)

@Composable
fun HomeScreen(navController: NavController) {
    var unreadCount by remember { mutableIntStateOf(0) }
    var notifications by remember { mutableStateOf<List<NotificationItem>>(emptyList()) }
    var notificationError by remember { mutableStateOf<String?>(null) }
    var notificationActionMessage by remember { mutableStateOf<String?>(null) }
    var showNotifications by remember { mutableStateOf(false) }
    var permissionRequested by remember { mutableStateOf(false) }
    val knownNotificationIds = remember(Session.userId) { mutableStateOf<Set<Int>?>(null) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
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
                    val currentNotifications = response.body()?.notifications.orEmpty()
                    notifications = currentNotifications
                    unreadCount = currentNotifications.count { !it.isRead }
                    val currentIds = currentNotifications.mapTo(mutableSetOf()) { it.id }
                    val previousIds = knownNotificationIds.value
                    if (previousIds != null) {
                        currentNotifications
                            .filter { !it.isRead && it.id !in previousIds }
                            .distinctBy { it.id }
                            .forEach { notification ->
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
                    knownNotificationIds.value = knownNotificationIds.value.orEmpty() + currentIds
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

    val modules = buildList {
        add(HomeModule("Anuncios", "Comunicados", "▤", "announcements"))
        if (Session.isAdmin) {
            add(HomeModule("PQRS", "Gestión de solicitudes", "◎", "pqrs"))
            add(HomeModule("Reservas", "Zonas comunes", "◷", "reservations"))
            add(HomeModule("Paquetería y visitas", "Control de portería", "▣", "registry"))
            add(HomeModule("Usuarios", "Administración", "♙", "createUser"))
        } else if (Session.isResident) {
            add(HomeModule("Mi perfil", "Mis datos y hogar", "♙", "profile"))
            add(HomeModule("Mis PQRS", "Solicitudes y respuestas", "◎", "pqrs"))
            add(HomeModule("Reservas", "Zonas comunes", "◷", "reservations"))
            add(HomeModule("Paquetería y visitas", "Mis registros", "▣", "registry"))
        } else if (Session.isGuard) {
            add(HomeModule("Paquetería y visitas", "Control de portería", "▣", "registry"))
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 18.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            DomuxBrandMark(size = 44.dp)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text("DOMUX", fontWeight = FontWeight.Bold, letterSpacing = 2.sp)
                Text("Residential Security OS", color = Color(0xFF94A3B8), fontSize = 11.sp)
            }
            Box {
                Surface(
                    modifier = Modifier
                        .size(46.dp)
                        .semantics { contentDescription = "Notificaciones, $unreadCount sin leer" },
                    color = Color(0xFF152C4A),
                    shape = CircleShape,
                    onClick = { showNotifications = true }
                ) {
                    Box(contentAlignment = Alignment.Center) { Text("🔔", fontSize = 18.sp) }
                }
                if (unreadCount > 0) {
                    Surface(
                        modifier = Modifier.align(Alignment.TopEnd),
                        color = Color(0xFF450A0A),
                        contentColor = Color(0xFFF87171),
                        shape = CircleShape
                    ) {
                        Text(
                            unreadCount.coerceAtMost(99).toString(),
                            modifier = Modifier.padding(horizontal = 5.dp, vertical = 2.dp),
                            fontSize = 9.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }
        }

        Surface(
            modifier = Modifier.fillMaxWidth(),
            color = Color(0xFF091426),
            shape = RoundedCornerShape(24.dp),
            border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFF1E334D))
        ) {
            Column(
                modifier = Modifier.padding(20.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Text("CENTRO DE CONTROL", color = Color(0xFF38BDF8), fontSize = 11.sp, letterSpacing = 1.5.sp)
                Text("Altos de DOMUX", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                Text(
                    "Hola, ${Session.userName ?: "usuario"}${Session.lastName?.let { " $it" }.orEmpty()}",
                    color = Color(0xFFCBD5E1)
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(
                        when {
                            Session.isAdmin -> "Administrador"
                            Session.isResident -> "Residente${Session.apartment?.let { " · $it" }.orEmpty()}"
                            Session.isGuard -> "Guardia de seguridad"
                            else -> "Usuario"
                        },
                        color = Color(0xFF94A3B8),
                        style = MaterialTheme.typography.bodySmall
                    )
                    DomuxStatusBadge("Operación estable")
                }
            }
        }

        Text("Módulos operativos", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        modules.chunked(2).forEach { rowModules ->
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                rowModules.forEach { module ->
                    DomuxBentoCard(
                        title = module.title,
                        detail = module.detail,
                        icon = module.icon,
                        modifier = Modifier.weight(1f)
                    ) { navController.navigate(module.route) }
                }
                if (rowModules.size == 1) Spacer(Modifier.weight(1f))
            }
        }

        notificationError?.let {
            Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
        }
        Button(
            onClick = {
                scope.launch {
                    try {
                        PushRegistration.removeCurrentDevice(context)
                    } catch (exception: Exception) {
                        Log.e("DomuxPush", "Could not unregister FCM token during logout.", exception)
                    }
                    try {
                        Session.clear(context)
                        navController.navigate("login") { popUpTo(0) }
                    } catch (exception: Exception) {
                        notificationError = "No se pudo borrar la sesión segura: ${exception.message}"
                    }
                }
            },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Cerrar sesión")
        }
    }

    if (showNotifications) {
        Dialog(
            onDismissRequest = { showNotifications = false },
            properties = DialogProperties(usePlatformDefaultWidth = false)
        ) {
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 20.dp),
                color = Color(0xFF091426),
                shape = RoundedCornerShape(24.dp),
                border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFF1E334D))
            ) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Text("Notificaciones", style = MaterialTheme.typography.titleLarge)
                    Text(
                        if (unreadCount == 0) "Todo al día" else "$unreadCount sin leer",
                        color = Color(0xFF94A3B8),
                        style = MaterialTheme.typography.bodySmall
                    )
                    if (notifications.isEmpty()) {
                        Text("No tienes notificaciones todavía.", color = Color(0xFFCBD5E1))
                    } else {
                        LazyColumn(Modifier.heightIn(max = 380.dp)) {
                            items(notifications, key = { it.id }) { item ->
                                Surface(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(vertical = 4.dp),
                                    color = Color(0xFF0F1E33),
                                    shape = RoundedCornerShape(16.dp),
                                    border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFF1E334D))
                                ) {
                                    Column(
                                        modifier = Modifier.padding(14.dp),
                                        verticalArrangement = Arrangement.spacedBy(5.dp)
                                    ) {
                                        Text(item.title, fontWeight = FontWeight.SemiBold)
                                        Text(item.message, color = Color(0xFFCBD5E1))
                                        Text(
                                            "${item.type} · ${item.createdAt.orEmpty()}",
                                            color = Color(0xFF94A3B8),
                                            style = MaterialTheme.typography.bodySmall
                                        )
                                        if (!item.isRead) {
                                            TextButton(
                                                onClick = {
                                                    scope.launch {
                                                        try {
                                                            val response = RetrofitClient.api.markNotificationRead(
                                                                Session.bearer(),
                                                                item.id
                                                            )
                                                            if (response.isSuccessful) {
                                                                notifications = notifications.map {
                                                                    if (it.id == item.id) it.copy(isRead = true) else it
                                                                }
                                                                unreadCount = notifications.count { !it.isRead }
                                                                notificationActionMessage = null
                                                            } else {
                                                                notificationActionMessage = mensajeDeError(
                                                                    response.code(),
                                                                    response.errorBody()?.string()
                                                                )
                                                            }
                                                        } catch (exception: Exception) {
                                                            notificationActionMessage =
                                                                "No se pudo marcar como leída: ${exception.message}"
                                                        }
                                                    }
                                                }
                                            ) {
                                                Text("Marcar como leída")
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    notificationActionMessage?.let {
                        Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        TextButton(
                            onClick = {
                                showNotifications = false
                                navController.navigate("notifications")
                            }
                        ) { Text("Ver bandeja completa") }
                        TextButton(onClick = { showNotifications = false }) { Text("Cerrar") }
                    }
                }
            }
        }
    }
}
