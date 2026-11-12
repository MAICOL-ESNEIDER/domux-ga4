package com.dracknoval.domux

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.core.content.ContextCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.dracknoval.domux.data.AdminSummaryResponse
import com.dracknoval.domux.data.ComplexInfoStore
import com.dracknoval.domux.data.NotificationItem
import com.dracknoval.domux.data.Reservation
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.Visit
import com.dracknoval.domux.ui.theme.DomuxColor
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive

/** true si el celular no deja mostrar avisos: desde Android 13 hay que pedir el permiso. */
private fun notificationPermissionMissing(context: Context): Boolean =
    Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
        ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
        PackageManager.PERMISSION_GRANTED

/**
 * Inicio de cada rol (HU-002, HU-065 y HU-081): el residente ve lo que le espera, la administración
 * lo que hay por atender hoy y la portería sus acciones y quién está en la unidad. La pantalla dibuja
 * y lleva el reloj de la revisión cada 30 segundos mientras está a la vista; los datos están en
 * [HomeViewModel].
 */
@Composable
fun HomeScreen(navController: NavController, viewModel: HomeViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()
    var permissionRequested by rememberSaveable { mutableStateOf(false) }
    var showGuardShift by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        viewModel.setPermissionMissing(!granted)
    }
    val backStackEntry by navController.currentBackStackEntryFlow.collectAsState(
        initial = navController.currentBackStackEntry
    )
    val currentRoute = backStackEntry?.destination?.route

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

    DomuxScreenScaffold(
        title = if (Session.isGuard) "Portería" else "Inicio",
        navController = navController,
        showBackButton = false,
        actions = { NotificationBell(state.unreadCount) { viewModel.openNotifications() } }
    ) { innerPadding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(innerPadding)
        ) {
            DomuxMessageBanner(
                state.message, state.messageIsError,
                Modifier.padding(start = 16.dp, end = 16.dp, top = 12.dp)
            ) { viewModel.dismissMessage() }
            Column(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState())
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp)
            ) {
                WelcomeCard(context)
                when {
                    Session.isAdmin -> AdminHome(state.adminSummary, state.dashboardLoading, navController)
                    Session.isGuard -> GuardHome(state, navController) { showGuardShift = true }
                    else -> ResidentHome(state, navController, viewModel::decideVisit)
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

    if (showGuardShift) {
        GuardShiftDialog(
            onDismiss = { showGuardShift = false },
            onShiftDone = { shiftMessage ->
                showGuardShift = false
                viewModel.showNotice(shiftMessage, isError = false)
            }
        )
    }
}

/** La campana de la barra de arriba con cuántas notificaciones faltan por leer. */
@Composable
private fun NotificationBell(unread: Int, onClick: () -> Unit) {
    Box(modifier = Modifier.padding(end = 8.dp)) {
        Surface(
            modifier = Modifier
                .size(44.dp)
                .semantics { contentDescription = "Notificaciones, $unread sin leer" },
            color = DomuxColor.Selected,
            shape = CircleShape,
            onClick = onClick
        ) {
            Box(contentAlignment = Alignment.Center) {
                Icon(painterResource(R.drawable.ic_notifications), contentDescription = null, modifier = Modifier.size(22.dp))
            }
        }
        if (unread > 0) {
            Surface(
                modifier = Modifier.align(Alignment.TopEnd),
                color = DomuxColor.BadBackground,
                contentColor = DomuxColor.Bad,
                shape = CircleShape
            ) {
                Text(
                    unread.coerceAtMost(99).toString(),
                    modifier = Modifier.padding(horizontal = 5.dp, vertical = 2.dp),
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold
                )
            }
        }
    }
}

/** Saludo con la unidad, el nombre, el rol y el teléfono de portería para llamar con un toque. */
@Composable
private fun WelcomeCard(context: Context) {
    val userName = Session.userName?.trim().orEmpty().ifBlank { "usuario" }
    val lastName = Session.lastName?.trim().orEmpty()
    val greetingName = if (lastName.isNotBlank() && userName.contains(lastName, ignoreCase = true)) {
        userName
    } else {
        listOf(userName, lastName).filter(String::isNotBlank).joinToString(" ")
    }
    val roleLine = when {
        Session.isAdmin -> "Administración"
        Session.isGuard -> "Portería · turno de ${Session.userName.orEmpty()}"
        else -> listOfNotNull("Residente", Session.apartment?.takeIf { it.isNotBlank() }).joinToString(" · ")
    }
    DomuxCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                ComplexLogo(size = 44.dp, describe = false)
                Column(Modifier.weight(1f)) {
                    Text(ComplexInfoStore.displayName, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    val details = listOfNotNull(ComplexInfoStore.info?.address, ComplexInfoStore.info?.nit?.let { "NIT $it" })
                    if (details.isNotEmpty()) {
                        Text(details.joinToString(" · "), color = DomuxColor.TextMuted, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            Text("Hola, $greetingName", style = MaterialTheme.typography.headlineSmall)
            Text(roleLine, color = DomuxColor.TextSoft, style = MaterialTheme.typography.bodyMedium)
            val portalPhone = ComplexInfoStore.info?.portalPhone
            if (portalPhone != null && !Session.isGuard) {
                TextButton(onClick = { dialPortal(context, portalPhone) }) {
                    Text("Llamar a portería · $portalPhone")
                }
            }
        }
    }
}

/** Título de una sección; el lector de pantalla lo anuncia como título. */
@Composable
private fun SectionTitle(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.titleMedium,
        fontWeight = FontWeight.SemiBold,
        modifier = Modifier.semantics { heading() }
    )
}

/** Una tarjeta de «pendiente» con ícono, título, detalle y, si aplica, botones al final. */
@Composable
private fun TodoCard(
    icon: Int,
    title: String,
    detail: String?,
    onClick: (() -> Unit)? = null,
    actions: @Composable () -> Unit = {}
) {
    DomuxCard(
        Modifier
            .fillMaxWidth()
            .then(if (onClick != null) Modifier.clickable(role = Role.Button, onClick = onClick) else Modifier)
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Box(
                    Modifier
                        .size(42.dp)
                        .background(DomuxColor.Selected, CircleShape),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(painterResource(icon), contentDescription = null, tint = DomuxColor.Primary, modifier = Modifier.size(22.dp))
                }
                Column(Modifier.weight(1f)) {
                    Text(title, style = MaterialTheme.typography.titleSmall)
                    if (!detail.isNullOrBlank()) {
                        Text(detail, color = DomuxColor.TextMuted, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            actions()
        }
    }
}

// --- Residente ------------------------------------------------------------------------------

@Composable
private fun ResidentHome(
    state: HomeUiState,
    navController: NavController,
    onDecideVisit: (Visit, Boolean) -> Unit
) {
    SectionTitle("Lo que te espera")
    if (state.dashboardLoading) LinearProgressIndicator(Modifier.fillMaxWidth())
    state.pendingVisits.forEach { visit ->
        TodoCard(
            icon = R.drawable.ic_person,
            title = "${visit.visitorName} está en la portería",
            detail = listOfNotNull(visitTypeLabel(visit.type), visit.createdAt?.let { "llegó $it" }).joinToString(" · ") +
                ". ¿Lo dejas entrar?"
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(
                    onClick = { onDecideVisit(visit, false) },
                    enabled = !state.busy,
                    modifier = Modifier.weight(1f).heightIn(min = 48.dp)
                ) { Text("No autorizar") }
                Button(
                    onClick = { onDecideVisit(visit, true) },
                    enabled = !state.busy,
                    modifier = Modifier.weight(1f).heightIn(min = 48.dp)
                ) { Text("Dejar entrar") }
            }
        }
    }
    if (state.waitingPackagesTotal > 0) {
        val first = state.waitingPackages.firstOrNull()
        TodoCard(
            icon = R.drawable.ic_package,
            title = if (state.waitingPackagesTotal == 1) "Tienes un paquete en portería"
            else "Tienes ${state.waitingPackagesTotal} paquetes en portería",
            detail = listOfNotNull(first?.carrier, first?.arrivedAt?.let { "llegó $it" }).joinToString(" · "),
            onClick = { navController.navigate("registry?tab=paquetes") }
        ) {
            TextButton(onClick = { navController.navigate("registry?tab=paquetes") }) { Text("Ver código de entrega") }
        }
    }
    if (state.unreadAnnouncementsTotal > 0) {
        val first = state.unreadAnnouncements.firstOrNull()
        TodoCard(
            icon = R.drawable.ic_campaign,
            title = first?.title ?: "Comunicados nuevos",
            detail = if (state.unreadAnnouncementsTotal == 1) "Comunicado nuevo"
            else "${state.unreadAnnouncementsTotal} comunicados sin leer",
            onClick = { navController.openMainDestination("announcements") }
        ) {
            TextButton(onClick = { navController.openMainDestination("announcements") }) { Text("Leer") }
        }
    }
    val nothingPending = state.pendingVisits.isEmpty() && state.waitingPackagesTotal == 0 && state.unreadAnnouncementsTotal == 0
    if (!state.dashboardLoading && nothingPending) {
        TodoCard(
            icon = R.drawable.ic_check_circle,
            title = "Todo al día",
            detail = "No tienes visitas, paquetes ni comunicados pendientes."
        )
    }

    SectionTitle("Mis próximas reservas")
    if (!state.dashboardLoading && state.upcomingReservations.isEmpty()) {
        Text("No tienes reservas próximas.", color = DomuxColor.TextMuted)
    }
    state.upcomingReservations.forEach { reservation ->
        ReservationCard(reservation) { navController.openMainDestination("reservations") }
    }
    OutlinedButton(
        onClick = { navController.openMainDestination("reservations") },
        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
    ) { Text("Reservar una zona común") }
}

@Composable
private fun ReservationCard(reservation: Reservation, onClick: () -> Unit) {
    val approved = reservation.status == "aprobada"
    TodoCard(
        icon = R.drawable.ic_event,
        title = reservation.commonAreaName ?: "Zona común",
        detail = "${humanDate(reservation.date)} · ${reservation.timeSlot}",
        onClick = onClick
    ) {
        DomuxStatusBadge(
            if (approved) "Aprobada" else "Pendiente",
            if (approved) DomuxBadgeTone.SUCCESS else DomuxBadgeTone.PROGRESS
        )
    }
}

/** El tipo de visita en palabras. */
private fun visitTypeLabel(type: String): String = when (type) {
    "visitante" -> "Visitante"
    "domiciliario" -> "Domiciliario"
    "contratista" -> "Contratista"
    else -> type.replaceFirstChar { it.uppercase() }
}

// --- Administración -------------------------------------------------------------------------

@Composable
private fun AdminHome(summary: AdminSummaryResponse?, loading: Boolean, navController: NavController) {
    SectionTitle("Esto es lo que hay por atender hoy")
    if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())
    val counts = summary?.counts
    CountCard(
        icon = R.drawable.ic_forum,
        count = counts?.pqrsOpen ?: 0,
        label = "PQRS abiertas",
        note = when {
            (counts?.pqrsOverdue ?: 0) > 0 -> "${counts?.pqrsOverdue} vencidas" to DomuxBadgeTone.ALERT
            (counts?.pqrsDueSoon ?: 0) > 0 -> "${counts?.pqrsDueSoon} por vencer" to DomuxBadgeTone.PROGRESS
            else -> null
        }
    ) { navController.openMainDestination("pqrs") }
    CountCard(
        icon = R.drawable.ic_event,
        count = counts?.reservationsPending ?: 0,
        label = "Reservas por aprobar",
        note = if ((counts?.reservationsPending ?: 0) > 0) "Esperan tu decisión" to DomuxBadgeTone.PROGRESS else null
    ) { navController.openMainDestination("reservations") }
    CountCard(
        icon = R.drawable.ic_package,
        count = counts?.packagesOver48 ?: 0,
        label = "Paquetes con más de 48 h",
        note = if ((counts?.packagesOver72 ?: 0) > 0) "${counts?.packagesOver72} con más de 72 h" to DomuxBadgeTone.ALERT
        else null
    ) { navController.openMainDestination("registry") }

    val reservations = summary?.pendingReservations.orEmpty()
    if (reservations.isNotEmpty()) {
        SectionTitle("Reservas por aprobar")
        reservations.take(3).forEach { item ->
            TodoCard(
                icon = R.drawable.ic_event,
                title = "${item.commonAreaName ?: "Zona común"} · ${humanDate(item.date)} · ${item.timeSlot.orEmpty()}",
                detail = listOfNotNull(item.residentName, item.apartment, item.attendees?.let { "$it personas" })
                    .joinToString(" · "),
                onClick = { navController.openMainDestination("reservations") }
            )
        }
    }
    val urgent = summary?.urgentPqrs.orEmpty()
    if (urgent.isNotEmpty()) {
        SectionTitle("PQRS más urgentes")
        urgent.take(3).forEach { item ->
            val days = item.daysRemaining ?: 0
            TodoCard(
                icon = R.drawable.ic_forum,
                title = item.subject?.takeIf { it.isNotBlank() } ?: "PQRS ${item.radicado.orEmpty()}",
                detail = listOfNotNull(item.radicado, item.residentName, item.apartment).joinToString(" · "),
                onClick = { navController.openMainDestination("pqrs") }
            ) {
                DomuxStatusBadge(
                    when {
                        days < 0 -> "Vencida"
                        days == 0 -> "Vence hoy"
                        else -> "Le quedan ${businessDaysText(days)}"
                    },
                    when (item.semaphore) {
                        "rojo" -> DomuxBadgeTone.ALERT
                        "amarillo" -> DomuxBadgeTone.PROGRESS
                        else -> DomuxBadgeTone.SUCCESS
                    }
                )
            }
        }
    }
}

/** Un contador grande del inicio de la administración; se toca para ir a la lista. */
@Composable
private fun CountCard(
    icon: Int,
    count: Int,
    label: String,
    note: Pair<String, DomuxBadgeTone>?,
    onClick: () -> Unit
) {
    DomuxCard(
        Modifier
            .fillMaxWidth()
            .clickable(role = Role.Button, onClickLabel = "Ver $label", onClick = onClick)
    ) {
        Row(
            Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            Box(
                Modifier
                    .size(42.dp)
                    .background(DomuxColor.Selected, CircleShape),
                contentAlignment = Alignment.Center
            ) {
                Icon(painterResource(icon), contentDescription = null, tint = DomuxColor.Primary, modifier = Modifier.size(22.dp))
            }
            Text(count.toString(), style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(label, style = MaterialTheme.typography.titleSmall)
                note?.let { (text, tone) -> DomuxStatusBadge(text, tone) }
            }
        }
    }
}

// --- Portería -------------------------------------------------------------------------------

private class GuardAction(val icon: Int, val title: String, val detail: String, val route: String)

private val guardActions = listOf(
    GuardAction(R.drawable.ic_person, "Registrar visita", "Visitante, domiciliario o contratista", "registry?tab=registrar-visita"),
    GuardAction(R.drawable.ic_qr_scan, "Escanear QR", "Visita invitada por el residente", "registry?tab=qr"),
    GuardAction(R.drawable.ic_package, "Recibir paquete", "Con foto y transportadora", "registry?tab=registrar-paquete"),
    GuardAction(R.drawable.ic_check_circle, "Entregar paquete", "Con el código de entrega", "registry?tab=paquetes"),
    GuardAction(R.drawable.ic_car, "Entrada de vehículo", "Placa y parqueadero", "vehicles"),
    GuardAction(R.drawable.ic_car, "Salida de vehículo", "Libera el parqueadero", "vehicles")
)

@Composable
private fun GuardHome(state: HomeUiState, navController: NavController, onShift: () -> Unit) {
    OutlinedButton(onClick = onShift, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
        Icon(painterResource(R.drawable.ic_swap), contentDescription = null, modifier = Modifier.size(20.dp))
        Spacer(Modifier.size(8.dp))
        Text("Entregar el turno a otro guardia")
    }
    // En la tablet caben tres botones por fila; en el celular, dos.
    val columns = if (LocalConfiguration.current.screenWidthDp >= 600) 3 else 2
    guardActions.chunked(columns).forEach { row ->
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            row.forEach { action ->
                DomuxCard(
                    Modifier
                        .weight(1f)
                        .heightIn(min = 112.dp)
                        .clickable(role = Role.Button) { navController.navigate(action.route) }
                ) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Icon(painterResource(action.icon), contentDescription = null, tint = DomuxColor.Primary, modifier = Modifier.size(28.dp))
                        Text(action.title, style = MaterialTheme.typography.titleSmall)
                        Text(action.detail, color = DomuxColor.TextMuted, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            repeat(columns - row.size) { Spacer(Modifier.weight(1f)) }
        }
    }

    SectionTitle("Esperando autorización (${state.guardPending.size})")
    if (state.dashboardLoading) LinearProgressIndicator(Modifier.fillMaxWidth())
    if (!state.dashboardLoading && state.guardPending.isEmpty()) {
        Text("Nadie está esperando autorización.", color = DomuxColor.TextMuted)
    }
    state.guardPending.forEach { visit ->
        TodoCard(
            icon = R.drawable.ic_schedule,
            title = visit.visitorName,
            detail = listOfNotNull(visit.apartment?.let { "Para $it" }, visit.createdAt?.let { "llegó $it" }).joinToString(" · "),
            onClick = { navController.navigate("registry?tab=visitas") }
        )
    }

    SectionTitle("Dentro ahora (${state.guardInsideTotal})")
    if (!state.dashboardLoading && state.guardInside.isEmpty()) {
        Text("No hay visitas dentro de la unidad.", color = DomuxColor.TextMuted)
    }
    state.guardInside.forEach { visit ->
        TodoCard(
            icon = R.drawable.ic_person,
            title = visit.visitorName,
            detail = listOfNotNull(visit.apartment, visit.insideMinutes?.let { "lleva ${durationText(it)}" }).joinToString(" · "),
            onClick = { navController.navigate("registry?tab=visitas") }
        ) {
            if (visit.isOverstay) DomuxStatusBadge("Pasó lo previsto", DomuxBadgeTone.ALERT)
        }
    }
    if (state.guardInsideTotal > state.guardInside.size) {
        TextButton(onClick = { navController.navigate("registry?tab=visitas") }) { Text("Ver todas las visitas") }
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
            color = DomuxColor.Surface,
            shape = RoundedCornerShape(24.dp),
            border = BorderStroke(1.dp, DomuxColor.Line)
        ) {
            Column(
                modifier = Modifier.padding(20.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Text("Notificaciones", style = MaterialTheme.typography.titleLarge)
                Text(
                    if (state.unreadCount == 0) "Todo al día" else "${state.unreadCount} sin leer",
                    color = DomuxColor.TextMuted,
                    style = MaterialTheme.typography.bodySmall
                )
                DomuxMessageBanner(state.message, state.messageIsError, onDismiss = onDismissMessage)
                if (state.notifications.isEmpty()) {
                    Text("No tienes notificaciones todavía.", color = DomuxColor.TextSoft)
                } else {
                    LazyColumn(Modifier.heightIn(max = 380.dp)) {
                        items(state.notifications, key = { it.id }) { item ->
                            Surface(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 4.dp),
                                color = DomuxColor.Card,
                                shape = RoundedCornerShape(16.dp),
                                border = BorderStroke(1.dp, DomuxColor.Line)
                            ) {
                                Column(
                                    modifier = Modifier.padding(14.dp),
                                    verticalArrangement = Arrangement.spacedBy(5.dp)
                                ) {
                                    Text(item.title, fontWeight = FontWeight.SemiBold)
                                    Text(item.message, color = DomuxColor.TextSoft)
                                    Text(
                                        item.createdAt.orEmpty(),
                                        color = DomuxColor.TextMuted,
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
