package com.dracknoval.domux

import android.util.Log
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationDrawerItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.rememberDrawerState
import androidx.compose.material3.DrawerValue
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.navigation.NavController
import com.dracknoval.domux.data.PushRegistration
import com.dracknoval.domux.data.ResidentSummary
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@Composable
fun MediaAttachmentChip(mediaUrl: String?, mediaType: String?) {
    if (mediaUrl.isNullOrBlank()) return
    val (icon, label) = when (mediaType?.lowercase()) {
        "image" -> "IMG" to "Imagen adjunta"
        "video" -> "VID" to "Video adjunto"
        "audio" -> "AUD" to "Audio adjunto"
        else -> "FILE" to "Archivo adjunto"
    }
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        contentColor = MaterialTheme.colorScheme.secondary,
        shape = RoundedCornerShape(50),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline)
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 11.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(icon, fontSize = 10.sp)
            Spacer(Modifier.width(7.dp))
            Text(label, style = MaterialTheme.typography.labelMedium)
        }
    }
}

@Composable
fun DomuxConfirmDialog(
    title: String,
    message: String,
    confirmLabel: String = "Confirmar",
    danger: Boolean = false,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit
) {
    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 24.dp),
            shape = RoundedCornerShape(24.dp),
            color = Color(0xFF091426),
            border = BorderStroke(1.dp, Color(0xFF1E334D))
        ) {
            Column(
                modifier = Modifier.padding(22.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Text(title, style = MaterialTheme.typography.titleLarge)
                Text(message, color = Color(0xFFCBD5E1), style = MaterialTheme.typography.bodyMedium)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    TextButton(onClick = onDismiss) { Text("Cancelar") }
                    Button(
                        onClick = onConfirm,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (danger) Color(0xFF450A0A) else Color(0xFF152C4A),
                            contentColor = if (danger) Color(0xFFF87171) else Color(0xFF38BDF8)
                        )
                    ) {
                        Text(confirmLabel)
                    }
                }
            }
        }
    }
}

@Composable
fun DomuxBentoCard(
    title: String,
    detail: String,
    icon: String,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    Surface(
        modifier = modifier.clickable(onClick = onClick),
        color = Color(0xFF0F1E33),
        shape = RoundedCornerShape(20.dp),
        border = BorderStroke(1.dp, Color(0xFF1E334D))
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Box(
                modifier = Modifier
                    .size(42.dp)
                    .background(Color(0xFF152C4A), RoundedCornerShape(13.dp)),
                contentAlignment = Alignment.Center
            ) {
                Text(icon, color = Color(0xFF38BDF8), fontSize = 19.sp)
            }
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(title, color = Color(0xFF94A3B8), style = MaterialTheme.typography.labelMedium)
                Text(detail, color = Color(0xFFF8FAFC), style = MaterialTheme.typography.titleSmall)
            }
        }
    }
}

@Composable
fun DomuxStatusBadge(label: String, tone: DomuxBadgeTone = DomuxBadgeTone.SUCCESS) {
    val (background, foreground, outline) = when (tone) {
        DomuxBadgeTone.SUCCESS -> Triple(Color(0xFF064E3B), Color(0xFF34D399), Color(0xFF065F46))
        DomuxBadgeTone.PROGRESS -> Triple(Color(0xFF451A03), Color(0xFFFBBF24), Color(0xFF78350F))
        DomuxBadgeTone.ALERT -> Triple(Color(0xFF450A0A), Color(0xFFF87171), Color(0xFF7F1D1D))
    }
    Surface(
        color = background,
        contentColor = foreground,
        shape = CircleShape,
        border = BorderStroke(1.dp, outline)
    ) {
        Text(label, modifier = Modifier.padding(horizontal = 11.dp, vertical = 6.dp), fontSize = 11.sp)
    }
}

enum class DomuxBadgeTone { SUCCESS, PROGRESS, ALERT }

@Composable
fun DomuxBrandMark(size: Dp = 54.dp) {
    Surface(
        modifier = Modifier.size(size),
        shape = RoundedCornerShape(17.dp),
        color = Color.Transparent
    ) {
        Box(
            modifier = Modifier.background(
                Brush.linearGradient(
                    listOf(Color(0xFF22D3EE), Color(0xFF818CF8), Color(0xFFA855F7))
                )
            ),
            contentAlignment = Alignment.Center
        ) {
            Text(
                "D",
                color = Color.White,
                fontSize = (size.value * 0.52f).sp,
                fontWeight = FontWeight.Bold
            )
        }
    }
}

@Composable
fun DomuxFeedbackBanner(message: String, onDismiss: (() -> Unit)? = null) {
        if (message.isBlank()) return

        val errorPrefixes = listOf(
            "No se", "Error", "Falta", "Completa", "Escribe", "Selecciona", "Elige",
            "Revisa", "Confirma", "La contraseña", "El ", "Sin conexión", "Ocurrió", "❌", "⚠"
        )
        val confirmations = listOf(
            "creado", "actualizado", "actualizada", "actualizadas", "publicado", "eliminado",
            "enviada", "enviado", "guardada", "guardado", "registrado", "registrada",
            "entregado", "restaurado", "restablecida", "revocado", "autorizado",
            "aprobada", "vinculado", "papelera"
        )
        val isSuccess = errorPrefixes.none { message.startsWith(it, ignoreCase = true) } &&
            confirmations.any { message.contains(it, ignoreCase = true) }
        val background = if (isSuccess) Color(0xFF052E16) else Color(0xFF450A0A)
        val foreground = if (isSuccess) Color(0xFF34D399) else Color(0xFFF87171)
        val outline = if (isSuccess) Color(0xFF10B981) else Color(0xFFEF4444)

        Surface(
            modifier = Modifier.fillMaxWidth(),
            color = background,
            contentColor = foreground,
            shape = RoundedCornerShape(16.dp),
            border = BorderStroke(1.dp, outline)
        ) {
            Row(
                modifier = Modifier.padding(start = 14.dp, top = 10.dp, bottom = 10.dp, end = 6.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    "${if (isSuccess) "✓" else "⚠"} $message",
                    modifier = Modifier.weight(1f),
                    color = foreground,
                    style = MaterialTheme.typography.bodyMedium
                )
                if (onDismiss != null) {
                    TextButton(onClick = onDismiss) {
                        Text("✕", color = foreground)
                    }
                }
            }
        }
    }

@Composable
fun DomuxSectionTabs(tabs: List<String>, selectedIndex: Int, onSelect: (Int) -> Unit) {
        Surface(
            modifier = Modifier.fillMaxWidth(),
            color = Color(0xFF091426),
            shape = RoundedCornerShape(18.dp),
            border = BorderStroke(1.dp, Color(0xFF1E334D))
        ) {
            Row(
                modifier = Modifier
                    .horizontalScroll(rememberScrollState())
                    .padding(6.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                tabs.forEachIndexed { index, tab ->
                    val selected = index == selectedIndex
                    Surface(
                        modifier = Modifier.clickable { onSelect(index) },
                        color = if (selected) Color(0xFF152C4A) else Color.Transparent,
                        contentColor = if (selected) Color(0xFFF8FAFC) else Color(0xFF94A3B8),
                        shape = RoundedCornerShape(13.dp),
                        border = BorderStroke(
                            1.dp,
                            if (selected) Color(0xFF38BDF8) else Color.Transparent
                        )
                    ) {
                        Text(
                            tab,
                            modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                            style = MaterialTheme.typography.labelLarge,
                            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal
                        )
                    }
                }
            }
        }
    }

@Composable
fun DomuxResidentSearchField(
        selectedResident: ResidentSummary?,
        onSelectResident: (ResidentSummary?) -> Unit,
        label: String = "Residente destinatario *"
    ) {
        var searchQuery by remember { mutableStateOf("") }
        var results by remember { mutableStateOf<List<ResidentSummary>>(emptyList()) }
        var searching by remember { mutableStateOf(false) }
        var searchError by remember { mutableStateOf<String?>(null) }

        LaunchedEffect(searchQuery) {
            delay(300)
            searching = true
            searchError = null
            try {
                val response = RetrofitClient.api.getResidents(
                    Session.bearer(),
                    searchQuery.trim().ifEmpty { null }
                )
                if (response.isSuccessful) {
                    results = response.body()?.residents.orEmpty()
                } else {
                    searchError = mensajeDeError(response.code(), response.errorBody()?.string())
                    results = emptyList()
                }
            } catch (exception: CancellationException) {
                throw exception
            } catch (exception: Exception) {
                if (exception.message?.contains("left the composition", ignoreCase = true) == true) {
                    return@LaunchedEffect
                }
                searchError = "No se pudieron buscar residentes: ${exception.message.orEmpty()}"
                results = emptyList()
            } finally {
                searching = false
            }
        }

        if (selectedResident != null) {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                color = Color(0xFF0F1E33),
                shape = RoundedCornerShape(18.dp),
                border = BorderStroke(1.dp, Color(0xFF1E334D))
            ) {
                Row(
                    modifier = Modifier.padding(start = 16.dp, top = 12.dp, bottom = 12.dp, end = 8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(
                        modifier = Modifier.weight(1f),
                        verticalArrangement = Arrangement.spacedBy(3.dp)
                    ) {
                        Text(selectedResident.name, fontWeight = FontWeight.SemiBold)
                        Text(
                            selectedResident.apartment ?: "Apartamento sin asignar",
                            color = Color(0xFF94A3B8),
                            style = MaterialTheme.typography.bodySmall
                        )
                        Text(
                            selectedResident.phone?.takeIf { it.isNotBlank() } ?: "Sin teléfono",
                            color = Color(0xFF94A3B8),
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    TextButton(onClick = { onSelectResident(null) }) {
                        Text("Cambiar", color = Color(0xFF38BDF8))
                    }
                }
            }
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = searchQuery,
                    onValueChange = { searchQuery = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text(label) },
                    placeholder = { Text("Nombre, documento o apartamento") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                    trailingIcon = {
                        if (searching) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(20.dp),
                                color = Color(0xFF38BDF8),
                                strokeWidth = 2.dp
                            )
                        }
                    },
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = Color(0xFF38BDF8),
                        unfocusedBorderColor = Color(0xFF1E334D),
                        focusedLabelColor = Color(0xFF38BDF8),
                        cursorColor = Color(0xFF38BDF8)
                    )
                )
                searchError?.let {
                    Text(it, color = Color(0xFFF87171), style = MaterialTheme.typography.bodySmall)
                }
                if (results.isNotEmpty()) {
                    Surface(
                        modifier = Modifier.fillMaxWidth(),
                        color = Color(0xFF091426),
                        shape = RoundedCornerShape(16.dp),
                        border = BorderStroke(1.dp, Color(0xFF1E334D))
                    ) {
                        Column(modifier = Modifier.padding(6.dp)) {
                            results.take(6).forEach { resident ->
                                Surface(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clickable {
                                            onSelectResident(resident)
                                            searchQuery = ""
                                            results = emptyList()
                                        },
                                    color = Color.Transparent,
                                    shape = RoundedCornerShape(12.dp)
                                ) {
                                    Column(
                                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
                                        verticalArrangement = Arrangement.spacedBy(2.dp)
                                    ) {
                                        Text(resident.name, fontWeight = FontWeight.Medium)
                                        Text(
                                            listOfNotNull(resident.apartment, resident.phone?.takeIf(String::isNotBlank))
                                                .joinToString(" · ")
                                                .ifBlank { "Sin apartamento ni teléfono" },
                                            color = Color(0xFF94A3B8),
                                            style = MaterialTheme.typography.bodySmall
                                        )
                                    }
                                }
                            }
                        }
                    }
                } else if (searchQuery.isNotBlank() && !searching && searchError == null) {
                    Text(
                        "No se encontraron residentes.",
                        color = Color(0xFF94A3B8),
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        }
    }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DomuxScreenScaffold(
        title: String,
        navController: NavController,
        showBackButton: Boolean = true,
        actions: @Composable RowScope.() -> Unit = {},
        content: @Composable (PaddingValues) -> Unit
    ) {
        val drawerState = rememberDrawerState(initialValue = DrawerValue.Closed)
        val scope = rememberCoroutineScope()
        val context = LocalContext.current
        var logoutError by remember { mutableStateOf<String?>(null) }
        val destinations = buildList {
            add("Inicio" to "home")
            add("Anuncios" to "announcements")
            add("Notificaciones" to "notifications")
            if (Session.isAdmin) {
                add("PQRS" to "pqrs")
                add("Reservas" to "reservations")
                add("Paquetería y visitas" to "registry")
                add("Gestión de usuarios" to "createUser")
            } else if (Session.isResident) {
                add("Mi perfil" to "profile")
                add("Mis PQRS" to "pqrs")
                add("Reservas" to "reservations")
                add("Paquetería y visitas" to "registry")
            } else if (Session.isGuard) {
                add("Paquetería y visitas" to "registry")
            }
        }
        val currentRoute = navController.currentBackStackEntry?.destination?.route?.substringBefore("?")

        ModalNavigationDrawer(
            drawerState = drawerState,
            drawerContent = {
                ModalDrawerSheet(
                    modifier = Modifier.fillMaxSize(),
                    drawerContainerColor = Color(0xFF07111F),
                    drawerContentColor = Color(0xFFF8FAFC)
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(20.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            DomuxBrandMark(size = 48.dp)
                            Spacer(Modifier.width(12.dp))
                            Column {
                                Text(
                                    Session.userName?.takeIf { it.isNotBlank() } ?: "Usuario",
                                    fontWeight = FontWeight.SemiBold
                                )
                                Text(
                                    when {
                                        Session.isAdmin -> "Administrador"
                                        Session.isResident -> "Residente"
                                        Session.isGuard -> "Guardia"
                                        else -> Session.role.orEmpty()
                                    },
                                    color = Color(0xFF94A3B8),
                                    style = MaterialTheme.typography.bodySmall
                                )
                                Session.apartment?.takeIf { it.isNotBlank() }?.let {
                                    Text(it, color = Color(0xFF94A3B8), style = MaterialTheme.typography.bodySmall)
                                }
                            }
                        }
                    }
                    androidx.compose.material3.HorizontalDivider(
                        modifier = Modifier.padding(horizontal = 16.dp),
                        color = Color(0xFF1E334D)
                    )
                    Column(
                        modifier = Modifier
                            .weight(1f)
                            .padding(horizontal = 12.dp, vertical = 10.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        destinations.forEach { (label, route) ->
                            NavigationDrawerItem(
                                label = { Text(label) },
                                selected = currentRoute == route,
                                onClick = {
                                    scope.launch {
                                        drawerState.close()
                                        if (currentRoute != route) {
                                            navController.navigate(route) { launchSingleTop = true }
                                        }
                                    }
                                },
                                colors = androidx.compose.material3.NavigationDrawerItemDefaults.colors(
                                    selectedContainerColor = Color(0xFF152C4A),
                                    selectedTextColor = Color(0xFFF8FAFC),
                                    unselectedTextColor = Color(0xFFCBD5E1)
                                )
                            )
                        }
                    }
                    logoutError?.let {
                        Text(
                            it,
                            modifier = Modifier.padding(horizontal = 20.dp, vertical = 6.dp),
                            color = Color(0xFFF87171),
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    androidx.compose.material3.HorizontalDivider(
                        modifier = Modifier.padding(horizontal = 16.dp),
                        color = Color(0xFF1E334D)
                    )
                    TextButton(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 12.dp, vertical = 8.dp),
                        onClick = {
                            scope.launch {
                                logoutError = null
                                try {
                                    PushRegistration.removeCurrentDevice(context.applicationContext)
                                } catch (exception: Exception) {
                                    Log.e("DomuxPush", "Could not unregister FCM token during logout.", exception)
                                }
                                try {
                                    Session.clear(context)
                                    drawerState.close()
                                    navController.navigate("login") { popUpTo(0) }
                                } catch (exception: Exception) {
                                    Log.e("DomuxSession", "Could not clear the session during logout.", exception)
                                    logoutError = "No se pudo borrar la sesión segura: ${exception.message.orEmpty()}"
                                }
                            }
                        }
                    ) {
                        Text("Cerrar sesión", color = Color(0xFFF87171))
                    }
                }
            }
        ) {
            Scaffold(
                containerColor = Color(0xFF07111F),
                topBar = {
                    TopAppBar(
                        title = { Text(title, color = Color(0xFFF8FAFC)) },
                        navigationIcon = {
                            Row(
                                modifier = Modifier.padding(start = 8.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(6.dp)
                            ) {
                                if (showBackButton) {
                                    Surface(
                                        modifier = Modifier.size(40.dp),
                                        color = Color(0xFF091426),
                                        shape = CircleShape,
                                        border = BorderStroke(1.dp, Color(0xFF1E334D)),
                                        onClick = { navController.popBackStack() }
                                    ) {
                                        Box(contentAlignment = Alignment.Center) {
                                            Text("←", color = Color(0xFFF8FAFC), fontSize = 21.sp)
                                        }
                                    }
                                }
                                Surface(
                                    modifier = Modifier.size(40.dp),
                                    color = Color(0xFF091426),
                                    shape = CircleShape,
                                    border = BorderStroke(1.dp, Color(0xFF1E334D)),
                                    onClick = { scope.launch { drawerState.open() } }
                                ) {
                                    Box(contentAlignment = Alignment.Center) {
                                        Text("☰", color = Color(0xFF38BDF8), fontSize = 18.sp)
                                    }
                                }
                            }
                        },
                        actions = actions,
                        colors = androidx.compose.material3.TopAppBarDefaults.topAppBarColors(
                            containerColor = Color(0xFF07111F),
                            titleContentColor = Color(0xFFF8FAFC)
                        )
                    )
                }
            ) { innerPadding ->
                content(innerPadding)
            }
        }
    }
