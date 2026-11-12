package com.dracknoval.domux

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
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
import androidx.core.content.ContextCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.dracknoval.domux.data.ComplexInfoStore
import com.dracknoval.domux.data.NotificationItem
import com.dracknoval.domux.data.Session
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive

private data class HomeModule(
    val title: String,
    val detail: String,
    val icon: String,
    val route: String
)

/** true si el celular no deja mostrar avisos: desde Android 13 hay que pedir el permiso. */
private fun notificationPermissionMissing(context: Context): Boolean =
    Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
        ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
        PackageManager.PERMISSION_GRANTED

/**
 * Inicio de la app (HU-002 y HU-065). La pantalla dibuja y lleva el reloj de la revisión cada 30
 * segundos mientras está a la vista; los datos están en [HomeViewModel].
 */
@Composable
fun HomeScreen(navController: NavController, viewModel: HomeViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()
    var permissionRequested by rememberSaveable { mutableStateOf(false) }
    val context = LocalContext.current
    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        viewModel.setPermissionMissing(!granted)
    }
    val backStackEntry by navController.currentBackStackEntryFlow.collectAsState(
        initial = navController.currentBackStackEntry
    )
    val currentRoute = backStackEntry?.destination?.route
    val userName = Session.userName?.trim().orEmpty().ifBlank { "usuario" }
    val lastName = Session.lastName?.trim().orEmpty()
    val greetingName = if (lastName.isNotBlank() && userName.contains(lastName, ignoreCase = true)) {
        userName
    } else {
        listOf(userName, lastName).filter(String::isNotBlank).joinToString(" ")
    }

    // Los datos de la unidad (HU-077) se piden al abrir el inicio: si la administración los
    // cambió en la web, aquí se ven la próxima vez que se entra.
    LaunchedEffect(currentRoute, Session.userId) {
        if (currentRoute == "home" && Session.token != null) ComplexInfoStore.refresh()
    }

    // Mientras el inicio está a la vista se revisa cada 30 segundos si llegó algo nuevo; lo nuevo se
    // muestra como aviso del celular.
    LaunchedEffect(currentRoute, Session.userId) {
        if (currentRoute != "home") return@LaunchedEffect
        // El permiso se pide una sola vez; si ya se pidió, solo se recuerda (y se quita el
        // recordatorio si la persona lo activó desde los ajustes del celular).
        if (!notificationPermissionMissing(context)) {
            viewModel.setPermissionMissing(false)
        } else if (!permissionRequested) {
            permissionRequested = true
            permissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else {
            viewModel.setPermissionMissing(true)
        }
        while (isActive) {
            viewModel.refresh().forEach { notification ->
                if (DomuxLocalNotifications.show(context, notification)) viewModel.setPermissionMissing(false)
                else if (notificationPermissionMissing(context)) viewModel.setPermissionMissing(true)
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
            add(HomeModule("Vehículos", "Parqueaderos y placas", "◧", "vehicles"))
            add(HomeModule("Usuarios", "Administración", "♙", "createUser"))
            add(HomeModule("Estructura", "Torres y apartamentos", "▦", "structure"))
        } else if (Session.isResident) {
            add(HomeModule("Mi perfil", "Mis datos y hogar", "♙", "profile"))
            add(HomeModule("Mis PQRS", "Solicitudes y respuestas", "◎", "pqrs"))
            add(HomeModule("Reservas", "Zonas comunes", "◷", "reservations"))
            add(HomeModule("Paquetería y visitas", "Mis registros", "▣", "registry"))
        } else if (Session.isGuard) {
            add(HomeModule("Paquetería y visitas", "Control de portería", "▣", "registry"))
            add(HomeModule("Vehículos", "Parqueaderos y placas", "◧", "vehicles"))
        }
    }

    DomuxScreenScaffold(
        title = "DOMUX",
        navController = navController,
        showBackButton = false,
        actions = {
            Box(modifier = Modifier.padding(end = 8.dp)) {
                Surface(
                    modifier = Modifier
                        .size(42.dp)
                        .semantics { contentDescription = "Notificaciones, ${state.unreadCount} sin leer" },
                    color = Color(0xFF152C4A),
                    shape = CircleShape,
                    onClick = { viewModel.openNotifications() }
                ) {
                    Box(contentAlignment = Alignment.Center) { Text("🔔", fontSize = 18.sp) }
                }
                if (state.unreadCount > 0) {
                    Surface(
                        modifier = Modifier.align(Alignment.TopEnd),
                        color = Color(0xFF450A0A),
                        contentColor = Color(0xFFF87171),
                        shape = CircleShape
                    ) {
                        Text(
                            state.unreadCount.coerceAtMost(99).toString(),
                            modifier = Modifier.padding(horizontal = 5.dp, vertical = 2.dp),
                            fontSize = 9.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 18.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp)
        ) {

        Surface(
            modifier = Modifier.fillMaxWidth(),
            color = Color(0xFF091426),
            shape = RoundedCornerShape(24.dp),
            border = BorderStroke(1.dp, Color(0xFF1E334D))
        ) {
            Column(
                modifier = Modifier.padding(20.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Text("CENTRO DE CONTROL", color = Color(0xFF38BDF8), fontSize = 11.sp, letterSpacing = 1.5.sp)
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    if (ComplexInfoStore.logo != null) ComplexLogo(size = 56.dp, describe = false)
                    Text(
                        ComplexInfoStore.displayName,
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold
                    )
                }
                Text(
                    "Hola, $greetingName",
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
                // Dirección y NIT de la unidad, y el teléfono de portería para llamar con un toque.
                val complexDetails = listOfNotNull(
                    ComplexInfoStore.info?.address,
                    ComplexInfoStore.info?.nit?.let { "NIT $it" }
                )
                if (complexDetails.isNotEmpty()) {
                    Text(
                        complexDetails.joinToString(" · "),
                        color = Color(0xFF94A3B8),
                        style = MaterialTheme.typography.bodySmall
                    )
                }
                val portalPhone = ComplexInfoStore.info?.portalPhone
                if (portalPhone != null && !Session.isGuard) {
                    TextButton(onClick = { dialPortal(context, portalPhone) }) {
                        Text("Llamar a portería · $portalPhone")
                    }
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
                        modifier = Modifier.weight(1f),
                        badge = if (module.route == "announcements") state.unreadAnnouncements else 0
                    ) { navController.navigate(module.route) }
                }
                if (rowModules.size == 1) Spacer(Modifier.weight(1f))
            }
        }

        // Avisos pequeños: no tapan nada y se quitan solos cuando el problema se arregla.
        if (state.permissionMissing) {
            Text(
                "Activa el permiso de notificaciones del celular para recibir avisos de DOMUX.",
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall
            )
        }
        state.syncProblem?.let {
            Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
        }
        }

        if (state.showNotifications) {
            NotificationsDialog(
                state = state,
                onMarkRead = viewModel::markRead,
                onDismissMessage = viewModel::dismissMessage,
                onOpenInbox = {
                    viewModel.closeNotifications()
                    navController.navigate("notifications")
                },
                onClose = viewModel::closeNotifications
            )
        }
    }
}

/** Vista rápida de las notificaciones desde la campana del inicio (HU-064). */
@Composable
private fun NotificationsDialog(
    state: HomeUiState,
    onMarkRead: (NotificationItem) -> Unit,
    onDismissMessage: () -> Unit,
    onOpenInbox: () -> Unit,
    onClose: () -> Unit
) {
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp),
            color = Color(0xFF091426),
            shape = RoundedCornerShape(24.dp),
            border = BorderStroke(1.dp, Color(0xFF1E334D))
        ) {
            Column(
                modifier = Modifier.padding(20.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Text("Notificaciones", style = MaterialTheme.typography.titleLarge)
                Text(
                    if (state.unreadCount == 0) "Todo al día" else "${state.unreadCount} sin leer",
                    color = Color(0xFF94A3B8),
                    style = MaterialTheme.typography.bodySmall
                )
                DomuxMessageBanner(state.message, state.messageIsError, onDismiss = onDismissMessage)
                if (state.notifications.isEmpty()) {
                    Text("No tienes notificaciones todavía.", color = Color(0xFFCBD5E1))
                } else {
                    LazyColumn(Modifier.heightIn(max = 380.dp)) {
                        items(state.notifications, key = { it.id }) { item ->
                            Surface(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 4.dp),
                                color = Color(0xFF0F1E33),
                                shape = RoundedCornerShape(16.dp),
                                border = BorderStroke(1.dp, Color(0xFF1E334D))
                            ) {
                                Column(
                                    modifier = Modifier.padding(14.dp),
                                    verticalArrangement = Arrangement.spacedBy(5.dp)
                                ) {
                                    Text(item.title, fontWeight = FontWeight.SemiBold)
                                    Text(item.message, color = Color(0xFFCBD5E1))
                                    Text(
                                        item.createdAt.orEmpty(),
                                        color = Color(0xFF94A3B8),
                                        style = MaterialTheme.typography.bodySmall
                                    )
                                    if (!item.isRead) {
                                        TextButton(onClick = { onMarkRead(item) }, enabled = !state.busy) {
                                            Text("Marcar como leída")
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    TextButton(onClick = onOpenInbox) { Text("Ver bandeja completa") }
                    TextButton(onClick = onClose) { Text("Cerrar") }
                }
            }
        }
    }
}
