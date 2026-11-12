package com.dracknoval.domux

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.dracknoval.domux.data.Announcement
import com.dracknoval.domux.data.CreateAnnouncementRequest
import com.dracknoval.domux.data.Session

private const val TAB_CURRENT = "Vigentes"
private const val TAB_ARCHIVED = "Archivados"
private const val TAB_PUBLISH = "Publicar"

/**
 * Comunicados de la unidad (HU-058 a HU-062). Todos ven los vigentes y los archivados; el
 * residente los marca como leídos al abrirlos y la administración los publica con categoría,
 * torre y vencimiento. La pantalla solo dibuja lo que le da [AnnouncementsViewModel].
 */
@Composable
fun AnnouncementsScreen(navController: NavController, viewModel: AnnouncementsViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()
    val tabs = if (Session.isAdmin) listOf(TAB_CURRENT, TAB_ARCHIVED, TAB_PUBLISH) else listOf(TAB_CURRENT, TAB_ARCHIVED)
    var selectedTab by rememberSaveable { mutableStateOf(0) }
    val tab = selectedTab.coerceIn(tabs.indices)
    var retiring by remember { mutableStateOf<Announcement?>(null) }

    // La pestaña de publicar no cambia la lista que se estaba viendo.
    LaunchedEffect(tab) {
        if (tabs[tab] != TAB_PUBLISH) viewModel.setArchived(tabs[tab] == TAB_ARCHIVED)
    }

    DomuxScreenScaffold(title = "Anuncios de la unidad", navController = navController) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            DomuxSectionTabs(tabs, tab) { selectedTab = it }
            if (state.message.isNotBlank()) {
                DomuxMessageBanner(state.message, state.messageIsError) { viewModel.dismissMessage() }
            }
            if (tabs[tab] == TAB_PUBLISH) {
                AnnouncementForm(
                    modifier = Modifier.weight(1f),
                    state = state,
                    onPublish = { viewModel.publish(it) },
                    onNotice = { viewModel.showNotice(it) },
                    onPublished = { selectedTab = 0 }
                )
            } else {
                AnnouncementList(
                    modifier = Modifier.weight(1f),
                    state = state,
                    archived = tabs[tab] == TAB_ARCHIVED,
                    onCategory = { viewModel.setCategory(it) },
                    onUnreadOnly = { viewModel.setUnreadOnly(it) },
                    onOpen = { viewModel.markRead(it) },
                    onRetire = { retiring = it },
                    onLoadMore = { viewModel.loadMore() },
                    onRefresh = { viewModel.refresh() }
                )
            }
        }
    }

    // Retirar no borra (TT-029): el comunicado deja de verse, pero queda en el historial.
    retiring?.let { item ->
        DomuxConfirmDialog(
            title = "Retirar comunicado",
            message = "“${item.title}” dejará de verse en la app. No se borra: queda guardado en el historial.",
            confirmLabel = "Retirar",
            danger = true,
            onConfirm = {
                retiring = null
                viewModel.retire(item)
            },
            onDismiss = { retiring = null }
        )
    }
}

// ---------------------------------------------------------------------------
// Lista de vigentes y archivados
// ---------------------------------------------------------------------------

@Composable
private fun AnnouncementList(
    modifier: Modifier,
    state: AnnouncementsUiState,
    archived: Boolean,
    onCategory: (String?) -> Unit,
    onUnreadOnly: (Boolean) -> Unit,
    onOpen: (Announcement) -> Unit,
    onRetire: (Announcement) -> Unit,
    onLoadMore: () -> Unit,
    onRefresh: () -> Unit
) {
    var expandedId by rememberSaveable { mutableStateOf<Int?>(null) }
    val filtered = state.category != null || state.unreadOnly
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Row(
            modifier = Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            FilterChip(
                selected = state.category == null,
                onClick = { onCategory(null) },
                label = { Text("Todas") }
            )
            announcementCategories.forEach { option ->
                FilterChip(
                    selected = state.category == option.key,
                    onClick = { onCategory(option.key) },
                    label = { Text(option.label) }
                )
            }
        }
        // Solo el residente tiene comunicados sin leer, y solo entre los vigentes (HU-059).
        if (Session.isResident && !archived) {
            FilterChip(
                selected = state.unreadOnly,
                onClick = { onUnreadOnly(!state.unreadOnly) },
                label = { Text("Sin leer (${state.unreadCount})") }
            )
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                if (state.page.total > 0) "Mostrando ${state.items.size} de ${state.page.total}" else "",
                style = MaterialTheme.typography.bodySmall
            )
            TextButton(onClick = onRefresh) { Text("Actualizar") }
        }
        if (state.loading) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            if (state.items.isEmpty() && !state.loading) {
                item {
                    Text(
                        when {
                            filtered -> "No hay comunicados con esos filtros."
                            archived -> "No hay comunicados archivados."
                            else -> "No hay comunicados vigentes."
                        }
                    )
                }
            }
            items(state.items, key = { "announcement-${it.id}" }) { announcement ->
                AnnouncementCard(
                    announcement = announcement,
                    expanded = expandedId == announcement.id,
                    archived = archived,
                    busy = state.busy,
                    onToggle = {
                        val opening = expandedId != announcement.id
                        expandedId = if (opening) announcement.id else null
                        // Abrirlo es leerlo (HU-059).
                        if (opening) onOpen(announcement)
                    },
                    onRetire = { onRetire(announcement) }
                )
            }
            if (state.page.page < state.page.totalPages) {
                item {
                    TextButton(
                        onClick = onLoadMore,
                        enabled = !state.loadingMore,
                        modifier = Modifier.fillMaxWidth()
                    ) { Text(if (state.loadingMore) "Cargando..." else "Ver más comunicados") }
                }
            }
        }
    }
}

@Composable
private fun AnnouncementCard(
    announcement: Announcement,
    expanded: Boolean,
    archived: Boolean,
    busy: Boolean,
    onToggle: () -> Unit,
    onRetire: () -> Unit
) {
    val unread = Session.isResident && !announcement.isRead
    val audience = announcement.towerName?.let { "Solo $it" } ?: "Toda la unidad"
    val validity = when {
        announcement.expiresAt == null -> null
        archived || announcement.isExpired -> "Venció el ${humanDate(announcement.expiresAt)}"
        else -> "Vigente hasta el ${humanDate(announcement.expiresAt)}"
    }
    DomuxCard(Modifier.fillMaxWidth().clickable(onClick = onToggle)) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                announcement.categoryLabel?.let { CategoryChip(it, urgent = announcement.category == "urgente") }
                if (unread) DomuxStatusBadge("Nuevo", DomuxBadgeTone.PROGRESS)
            }
            Text(announcement.title, style = MaterialTheme.typography.titleMedium)
            Text(
                announcement.message,
                maxLines = if (expanded) Int.MAX_VALUE else 3,
                overflow = TextOverflow.Ellipsis
            )
            if (announcement.eventDate != null || announcement.eventTime != null) {
                Text("Evento: ${announcement.eventDate.orEmpty()} ${announcement.eventTime.orEmpty()}".trim())
            }
            MediaAttachmentChip(announcement.mediaUrl, announcement.mediaType, "Foto del comunicado")
            Text(
                "Por ${announcement.authorName ?: "Administración"} · ${announcement.createdAt.orEmpty()}",
                style = MaterialTheme.typography.bodySmall
            )
            Text(
                listOfNotNull(audience, validity).joinToString(" · "),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.secondary
            )
            // La administración ve cuántos apartamentos lo han leído (HU-062).
            if (Session.isAdmin && announcement.totalApartments != null) {
                Text(
                    "Leído por ${announcement.readApartments ?: 0} de ${announcement.totalApartments} apartamentos",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.secondary
                )
            }
            if (Session.isAdmin) {
                RetireAnnouncementButton(enabled = !busy, onClick = onRetire)
            }
        }
    }
}

@Composable
private fun CategoryChip(label: String, urgent: Boolean) {
    Surface(
        color = if (urgent) Color(0xFF450A0A) else MaterialTheme.colorScheme.surfaceVariant,
        contentColor = if (urgent) Color(0xFFF87171) else MaterialTheme.colorScheme.secondary,
        shape = RoundedCornerShape(50),
        border = BorderStroke(1.dp, if (urgent) Color(0xFF7F1D1D) else MaterialTheme.colorScheme.outline)
    ) {
        Text(
            label,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
            style = MaterialTheme.typography.labelMedium
        )
    }
}

// ---------------------------------------------------------------------------
// Publicar un comunicado (solo la administración)
// ---------------------------------------------------------------------------

@Composable
private fun AnnouncementForm(
    modifier: Modifier,
    state: AnnouncementsUiState,
    onPublish: (CreateAnnouncementRequest) -> Unit,
    onNotice: (String) -> Unit,
    onPublished: () -> Unit
) {
    var title by rememberSaveable { mutableStateOf("") }
    var detail by rememberSaveable { mutableStateOf("") }
    var category by rememberSaveable { mutableStateOf<String?>(null) }
    var towerId by rememberSaveable { mutableStateOf<Int?>(null) }
    var expiresAt by rememberSaveable { mutableStateOf("") }
    var eventDate by rememberSaveable { mutableStateOf("") }
    var eventTime by rememberSaveable { mutableStateOf("") }
    var attempted by rememberSaveable { mutableStateOf(false) }
    // El adjunto va en base64 y puede pesar varios MB: no se guarda con el estado de la pantalla.
    var mediaUrl by remember { mutableStateOf<String?>(null) }
    var mediaType by remember { mutableStateOf<String?>(null) }
    var mediaName by remember { mutableStateOf<String?>(null) }
    var handled by rememberSaveable { mutableStateOf(state.published) }

    // Cuando el servidor acepta el comunicado, el formulario queda limpio y se vuelve a la lista.
    LaunchedEffect(state.published) {
        if (state.published != handled) {
            handled = state.published
            title = ""
            detail = ""
            category = null
            towerId = null
            expiresAt = ""
            eventDate = ""
            eventTime = ""
            attempted = false
            mediaUrl = null
            mediaType = null
            mediaName = null
            onPublished()
        }
    }

    val selectedTower = state.towers.firstOrNull { it.id == towerId }

    Column(
        modifier = modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        DomuxCard(Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text("Publicar comunicado", style = MaterialTheme.typography.titleMedium)
                OutlinedTextField(
                    value = title,
                    onValueChange = { title = it },
                    label = { Text("Título *") },
                    isError = attempted && title.isBlank(),
                    supportingText = { if (attempted && title.isBlank()) Text("El título es obligatorio") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(
                    value = detail,
                    onValueChange = { detail = it },
                    label = { Text("Mensaje *") },
                    isError = attempted && detail.isBlank(),
                    supportingText = { if (attempted && detail.isBlank()) Text("El mensaje es obligatorio") },
                    modifier = Modifier.fillMaxWidth()
                )
                Text("Categoría *", style = MaterialTheme.typography.labelLarge)
                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    announcementCategories.forEach { option ->
                        FilterChip(
                            selected = category == option.key,
                            onClick = { category = option.key },
                            label = { Text(option.label) }
                        )
                    }
                }
                if (attempted && category == null) {
                    Text(
                        "Elige la categoría: sin ella el comunicado no se publica.",
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
                Text("¿A quién va dirigido?", style = MaterialTheme.typography.labelLarge)
                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    FilterChip(
                        selected = towerId == null,
                        onClick = { towerId = null },
                        label = { Text("Toda la unidad") }
                    )
                    state.towers.forEach { tower ->
                        FilterChip(
                            selected = towerId == tower.id,
                            onClick = { towerId = tower.id },
                            label = { Text(tower.name) }
                        )
                    }
                }
                Text(
                    if (selectedTower == null) "Lo verán todos los residentes."
                    else "Solo lo verán los residentes de ${selectedTower.name}.",
                    style = MaterialTheme.typography.bodySmall
                )
                DatePickerField(
                    label = "Vence el (opcional)",
                    value = expiresAt,
                    onValueChange = { expiresAt = it },
                    allowPastDates = false
                )
                if (expiresAt.isNotBlank()) {
                    TextButton(onClick = { expiresAt = "" }) { Text("Quitar la fecha de vencimiento") }
                }
                Text(
                    "Después de esa fecha el comunicado pasa a «Archivados». Sin fecha, no vence.",
                    style = MaterialTheme.typography.bodySmall
                )
                DatePickerField("Fecha del evento", eventDate, { eventDate = it })
                TimePickerField("Hora del evento", eventTime, { eventTime = it })
                MediaAttachmentPicker(mediaName, { url, type, name ->
                    mediaUrl = url
                    mediaType = type
                    mediaName = name
                }, { onNotice(it) })
                Button(
                    enabled = !state.busy,
                    onClick = {
                        attempted = true
                        val chosenCategory = category
                        if (title.isBlank() || detail.isBlank() || chosenCategory == null) {
                            onNotice("Escribe el título y el mensaje, y elige la categoría.")
                        } else {
                            onPublish(
                                CreateAnnouncementRequest(
                                    title = title.trim(),
                                    message = detail.trim(),
                                    category = chosenCategory,
                                    towerId = towerId,
                                    expiresAt = expiresAt.ifBlank { null },
                                    eventDate = eventDate.ifBlank { null },
                                    eventTime = eventTime.ifBlank { null },
                                    mediaUrl = mediaUrl,
                                    mediaType = mediaType
                                )
                            )
                        }
                    },
                    modifier = Modifier.fillMaxWidth()
                ) { Text(if (state.busy) "Publicando..." else "Publicar") }
            }
        }
    }
}

@Composable
private fun RetireAnnouncementButton(enabled: Boolean, onClick: () -> Unit) {
    Surface(
        modifier = Modifier.semantics { contentDescription = "Retirar comunicado" },
        onClick = onClick,
        enabled = enabled,
        color = Color(0xFF450A0A),
        contentColor = Color(0xFFF87171),
        shape = RoundedCornerShape(12.dp),
        border = BorderStroke(1.dp, Color(0xFF7F1D1D))
    ) {
        Canvas(Modifier.padding(10.dp).size(20.dp)) {
            val strokeWidth = 1.8.dp.toPx()
            drawRoundRect(
                color = Color(0xFFF87171),
                topLeft = Offset(size.width * 0.25f, size.height * 0.3f),
                size = Size(size.width * 0.5f, size.height * 0.58f),
                cornerRadius = androidx.compose.ui.geometry.CornerRadius(2.dp.toPx()),
                style = Stroke(strokeWidth)
            )
            drawLine(
                color = Color(0xFFF87171),
                start = Offset(size.width * 0.17f, size.height * 0.22f),
                end = Offset(size.width * 0.83f, size.height * 0.22f),
                strokeWidth = strokeWidth
            )
            drawLine(
                color = Color(0xFFF87171),
                start = Offset(size.width * 0.38f, size.height * 0.12f),
                end = Offset(size.width * 0.62f, size.height * 0.12f),
                strokeWidth = strokeWidth
            )
            drawLine(
                color = Color(0xFFF87171),
                start = Offset(size.width * 0.43f, size.height * 0.43f),
                end = Offset(size.width * 0.43f, size.height * 0.72f),
                strokeWidth = strokeWidth
            )
            drawLine(
                color = Color(0xFFF87171),
                start = Offset(size.width * 0.57f, size.height * 0.43f),
                end = Offset(size.width * 0.57f, size.height * 0.72f),
                strokeWidth = strokeWidth
            )
        }
    }
}
