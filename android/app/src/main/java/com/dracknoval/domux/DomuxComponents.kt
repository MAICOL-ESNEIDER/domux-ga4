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
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.selection.selectable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.NavigationRailItemDefaults
import androidx.compose.material3.NavigationRailItem
import androidx.compose.material3.NavigationRail
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBar
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.res.painterResource
import androidx.compose.material3.IconButton
import androidx.compose.material3.Icon
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
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
import com.dracknoval.domux.ui.theme.DomuxColor

/**
 * Un adjunto que llegó del servidor, ya visible: la foto en miniatura (se abre en grande), el
 * video para reproducir y el audio con su reproductor (ver MediaViewer.kt).
 */
@Composable
fun MediaAttachmentChip(mediaUrl: String?, mediaType: String?, description: String = "Foto adjunta") {
    MediaAttachment(mediaUrl, mediaType, description)
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
            color = DomuxColor.Surface,
            border = BorderStroke(1.dp, DomuxColor.Line)
        ) {
            Column(
                modifier = Modifier.padding(22.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Text(title, style = MaterialTheme.typography.titleLarge)
                Text(message, color = DomuxColor.TextSoft, style = MaterialTheme.typography.bodyMedium)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    TextButton(onClick = onDismiss) { Text("Cancelar") }
                    Button(
                        onClick = onConfirm,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (danger) DomuxColor.BadBackground else DomuxColor.Selected,
                            contentColor = if (danger) DomuxColor.Bad else DomuxColor.Primary
                        )
                    ) {
                        Text(confirmLabel)
                    }
                }
            }
        }
    }
}

/**
 * Tarjeta de un módulo del inicio. [badge] es un número pendiente (por ejemplo, los comunicados
 * sin leer): si es mayor que cero se dibuja en la esquina de la tarjeta.
 */
/**
 * Estado con color, ícono y palabra (nunca solo el color): verde con chulo para lo hecho, amarillo
 * con reloj para lo pendiente y rojo con signo de admiración para lo vencido o rechazado.
 */
@Composable
fun DomuxStatusBadge(label: String, tone: DomuxBadgeTone = DomuxBadgeTone.SUCCESS) {
    val (background, foreground, outline) = when (tone) {
        DomuxBadgeTone.SUCCESS -> Triple(DomuxColor.OkBackground, DomuxColor.Ok, DomuxColor.OkLine)
        DomuxBadgeTone.PROGRESS -> Triple(DomuxColor.WarnBackground, DomuxColor.Warn, DomuxColor.WarnLine)
        DomuxBadgeTone.ALERT -> Triple(DomuxColor.BadBackground, DomuxColor.Bad, DomuxColor.BadLine)
    }
    Surface(
        color = background,
        contentColor = foreground,
        shape = CircleShape,
        border = BorderStroke(1.dp, outline)
    ) {
        Row(
            modifier = Modifier.padding(start = 8.dp, end = 11.dp, top = 5.dp, bottom = 5.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            Icon(painterResource(tone.icon), contentDescription = null, modifier = Modifier.size(14.dp))
            Text(label, fontSize = 12.sp)
        }
    }
}

enum class DomuxBadgeTone(val icon: Int) {
    SUCCESS(R.drawable.ic_check),
    PROGRESS(R.drawable.ic_schedule),
    ALERT(R.drawable.ic_warning)
}

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
                    listOf(DomuxColor.Cyan, DomuxColor.Violet, DomuxColor.Purple)
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

/**
 * Casilla con su texto: se marca tocando cualquiera de los dos (no solo el cuadrito) y el lector
 * de pantalla los anuncia juntos como una casilla.
 */
@Composable
fun DomuxCheckRow(label: String, checked: Boolean, onCheckedChange: (Boolean) -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .toggleable(value = checked, role = Role.Checkbox, onValueChange = onCheckedChange)
            .padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Checkbox(checked = checked, onCheckedChange = null)
        Text(label, Modifier.padding(start = 8.dp))
    }
}

/**
 * Aviso verde (acierto) o rojo (error); quien lo usa ya sabe de cuál de los dos se trata.
 * En las pantallas largas va fuera de la parte que se desplaza, para que siempre se vea.
 */
@Composable
fun DomuxMessageBanner(
    message: String,
    isError: Boolean,
    modifier: Modifier = Modifier,
    onDismiss: (() -> Unit)? = null
) {
        if (message.isBlank()) return

        val background = if (isError) DomuxColor.BadBackground else DomuxColor.OkNotice
        val foreground = if (isError) DomuxColor.Bad else DomuxColor.Ok
        val outline = if (isError) DomuxColor.BadNoticeLine else DomuxColor.OkNoticeLine

        Surface(
            // El lector de pantalla lo anuncia apenas aparece; un error interrumpe, un acierto espera su turno.
            modifier = modifier
                .fillMaxWidth()
                .semantics { liveRegion = if (isError) LiveRegionMode.Assertive else LiveRegionMode.Polite },
            color = background,
            contentColor = foreground,
            shape = RoundedCornerShape(16.dp),
            border = BorderStroke(1.dp, outline)
        ) {
            Row(
                modifier = Modifier.padding(start = 14.dp, top = 10.dp, bottom = 10.dp, end = 6.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    painterResource(if (isError) R.drawable.ic_warning else R.drawable.ic_check_circle),
                    contentDescription = if (isError) "Error:" else "Listo:",
                    tint = foreground,
                    modifier = Modifier.size(22.dp)
                )
                Spacer(Modifier.width(10.dp))
                Text(
                    message,
                    modifier = Modifier.weight(1f),
                    color = foreground,
                    style = MaterialTheme.typography.bodyMedium
                )
                if (onDismiss != null) {
                    IconButton(onClick = onDismiss) {
                        Icon(
                            painterResource(R.drawable.ic_close),
                            contentDescription = "Cerrar el aviso",
                            tint = foreground,
                            modifier = Modifier.size(20.dp)
                        )
                    }
                }
            }
        }
    }

@Composable
fun DomuxSectionTabs(tabs: List<String>, selectedIndex: Int, onSelect: (Int) -> Unit) {
        Surface(
            modifier = Modifier.fillMaxWidth(),
            color = DomuxColor.Surface,
            shape = RoundedCornerShape(18.dp),
            border = BorderStroke(1.dp, DomuxColor.Line)
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
                        // Es una pestaña: el lector de pantalla dice cuál está elegida. Mide al menos 48 de alto.
                        modifier = Modifier
                            .heightIn(min = 48.dp)
                            .selectable(selected = selected, role = Role.Tab) { onSelect(index) },
                        color = if (selected) DomuxColor.Selected else Color.Transparent,
                        contentColor = if (selected) DomuxColor.TextBright else DomuxColor.TextMuted,
                        shape = RoundedCornerShape(13.dp),
                        border = BorderStroke(
                            1.dp,
                            if (selected) DomuxColor.Primary else Color.Transparent
                        )
                    ) {
                        Box(Modifier.heightIn(min = 48.dp), contentAlignment = Alignment.Center) {
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
                color = DomuxColor.Card,
                shape = RoundedCornerShape(18.dp),
                border = BorderStroke(1.dp, DomuxColor.Line)
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
                            color = DomuxColor.TextMuted,
                            style = MaterialTheme.typography.bodySmall
                        )
                        Text(
                            selectedResident.phone?.takeIf { it.isNotBlank() } ?: "Sin teléfono",
                            color = DomuxColor.TextMuted,
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    TextButton(onClick = { onSelectResident(null) }) {
                        Text("Cambiar", color = DomuxColor.Primary)
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
                                color = DomuxColor.Primary,
                                strokeWidth = 2.dp
                            )
                        }
                    },
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = DomuxColor.Primary,
                        unfocusedBorderColor = DomuxColor.FieldBorder,
                        focusedLabelColor = DomuxColor.Primary,
                        cursorColor = DomuxColor.Primary
                    )
                )
                searchError?.let {
                    Text(it, color = DomuxColor.Bad, style = MaterialTheme.typography.bodySmall)
                }
                if (results.isNotEmpty()) {
                    Surface(
                        modifier = Modifier.fillMaxWidth(),
                        color = DomuxColor.Surface,
                        shape = RoundedCornerShape(16.dp),
                        border = BorderStroke(1.dp, DomuxColor.Line)
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
                                            color = DomuxColor.TextMuted,
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
                        color = DomuxColor.TextMuted,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        }
    }

/**
 * El marco de cada pantalla: barra de arriba con el título (y «Volver» cuando la pantalla no es
 * del menú principal) y el menú del rol: abajo en el celular y a la izquierda en la tablet.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DomuxScreenScaffold(
    title: String,
    navController: NavController,
    showBackButton: Boolean = true,
    actions: @Composable RowScope.() -> Unit = {},
    content: @Composable (PaddingValues) -> Unit
) {
    // Se lee para que el menú se vuelva a dibujar si cambian los datos de la sesión (por ejemplo,
    // cuando otro guardia recibe el turno).
    @Suppress("UNUSED_VARIABLE")
    val sessionVersion = Session.changeCount
    val entry by navController.currentBackStackEntryAsState()
    val destinations = mainDestinations()
    val selected = destinations.firstOrNull { it.matches(entry) }
    val canGoBack = showBackButton && selected == null && navController.previousBackStackEntry != null
    // Desde 600 dp de ancho (tablet o celular acostado grande) el menú va a la izquierda.
    val wide = LocalConfiguration.current.screenWidthDp >= 600

    Scaffold(
        containerColor = DomuxColor.Background,
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        title,
                        color = DomuxColor.TextBright,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.semantics { heading() }
                    )
                },
                navigationIcon = {
                    if (canGoBack) {
                        IconButton(onClick = { navController.popBackStack() }) {
                            Icon(painterResource(R.drawable.ic_arrow_back), contentDescription = "Volver")
                        }
                    }
                },
                actions = actions,
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = DomuxColor.Deep,
                    titleContentColor = DomuxColor.TextBright,
                    navigationIconContentColor = DomuxColor.TextBright,
                    actionIconContentColor = DomuxColor.TextBright
                )
            )
        },
        bottomBar = {
            if (!wide) DomuxBottomBar(destinations, selected, navController)
        }
    ) { innerPadding ->
        if (wide) {
            Row(Modifier.fillMaxSize()) {
                DomuxRail(destinations, selected, navController, Modifier.padding(top = innerPadding.calculateTopPadding()))
                Box(Modifier.weight(1f)) { content(innerPadding) }
            }
        } else {
            content(innerPadding)
        }
    }
}

/** El menú de abajo del celular: cinco botones con ícono y nombre. */
@Composable
private fun DomuxBottomBar(
    destinations: List<DomuxDestination>,
    selected: DomuxDestination?,
    navController: NavController
) {
    NavigationBar(containerColor = DomuxColor.Deep, tonalElevation = 0.dp) {
        destinations.forEach { destination ->
            NavigationBarItem(
                selected = destination == selected,
                onClick = { if (destination != selected) navController.openMainDestination(destination.route) },
                icon = { Icon(painterResource(destination.icon), contentDescription = null) },
                label = { Text(destination.label, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = DomuxColor.Primary,
                    selectedTextColor = DomuxColor.TextBright,
                    indicatorColor = DomuxColor.Selected,
                    unselectedIconColor = DomuxColor.TextMuted,
                    unselectedTextColor = DomuxColor.TextMuted
                )
            )
        }
    }
}

/** El menú de la tablet: los mismos botones, en una columna a la izquierda. */
@Composable
private fun DomuxRail(
    destinations: List<DomuxDestination>,
    selected: DomuxDestination?,
    navController: NavController,
    modifier: Modifier = Modifier
) {
    NavigationRail(
        modifier = modifier.fillMaxHeight(),
        containerColor = DomuxColor.Deep,
        header = { ComplexLogo(size = 40.dp) }
    ) {
        Spacer(Modifier.height(8.dp))
        destinations.forEach { destination ->
            NavigationRailItem(
                selected = destination == selected,
                onClick = { if (destination != selected) navController.openMainDestination(destination.route) },
                icon = { Icon(painterResource(destination.icon), contentDescription = null) },
                label = { Text(destination.label, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                colors = NavigationRailItemDefaults.colors(
                    selectedIconColor = DomuxColor.Primary,
                    selectedTextColor = DomuxColor.TextBright,
                    indicatorColor = DomuxColor.Selected,
                    unselectedIconColor = DomuxColor.TextMuted,
                    unselectedTextColor = DomuxColor.TextMuted
                )
            )
        }
    }
}
