package com.dracknoval.domux

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.dracknoval.domux.data.Pqrs
import com.dracknoval.domux.data.Session
import kotlinx.coroutines.delay

private const val PQRS_TAB_LIST = "Solicitudes PQRS"
private const val PQRS_TAB_NEW = "Nueva PQRS"

private val pqrsCategories = listOf("Petición", "Queja", "Reclamo", "Sugerencia", "Daño")
private val pqrsStates = listOf(
    "Todas" to null,
    "Abiertas" to "abierta",
    "En proceso" to "en_proceso",
    "Resueltas" to "resuelta"
)

/**
 * Peticiones, quejas, reclamos y sugerencias (HU-072 y HU-073). Cada PQRS muestra su radicado y,
 * mientras no esté resuelta, el semáforo de su plazo de 15 días hábiles. La pantalla solo dibuja
 * lo que le da [PqrsViewModel].
 */
@Composable
fun PqrsScreen(
    navController: NavController,
    targetResidentId: Int? = null,
    viewModel: PqrsViewModel = viewModel()
) {
    val state by viewModel.state.collectAsState()
    val canCreate = Session.isAdmin || Session.isResident
    val tabs = if (canCreate) listOf(PQRS_TAB_LIST, PQRS_TAB_NEW) else listOf(PQRS_TAB_LIST)
    // Si la administración llega desde el perfil de un residente, abre directo la PQRS nueva.
    var selectedTab by rememberSaveable { mutableStateOf(if (targetResidentId != null && canCreate) 1 else 0) }
    val tab = selectedTab.coerceIn(tabs.indices)
    var batchDialog by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) { viewModel.start(targetResidentId) }

    DomuxScreenScaffold(title = "PQRS", navController = navController) { padding ->
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
            if (tabs[tab] == PQRS_TAB_NEW) {
                PqrsForm(
                    modifier = Modifier.weight(1f),
                    state = state,
                    viewModel = viewModel,
                    onCreated = { selectedTab = 0 }
                )
            } else {
                PqrsList(
                    modifier = Modifier.weight(1f),
                    state = state,
                    viewModel = viewModel,
                    onBatch = { batchDialog = true }
                )
            }
        }
    }

    if (batchDialog) {
        PqrsBatchDialog(state = state, viewModel = viewModel, onClose = { batchDialog = false })
    }
}

// ---------------------------------------------------------------------------
// Lista de PQRS
// ---------------------------------------------------------------------------

@Composable
private fun PqrsList(
    modifier: Modifier,
    state: PqrsUiState,
    viewModel: PqrsViewModel,
    onBatch: () -> Unit
) {
    var searchText by rememberSaveable { mutableStateOf(state.search) }
    var expandedId by rememberSaveable { mutableStateOf<Int?>(null) }

    // La búsqueda espera un instante a que termines de escribir antes de preguntarle al servidor.
    LaunchedEffect(searchText) {
        delay(300)
        viewModel.setSearch(searchText.trim())
    }

    val visible = state.visibleItems
    val grouped = visible.groupBy { it.category ?: PQRS_DEFAULT_CATEGORY }.toSortedMap()

    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        OutlinedTextField(
            value = searchText,
            onValueChange = { searchText = it },
            label = { Text("Buscar por asunto, residente o radicado") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Row(
            modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            pqrsStates.forEach { (label, value) ->
                FilterChip(
                    selected = state.statusFilter == value,
                    onClick = { viewModel.setStatusFilter(value) },
                    label = { Text(label) }
                )
            }
        }
        Row(
            modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            FilterChip(
                selected = state.categoryFilter == null,
                onClick = { viewModel.setCategoryFilter(null) },
                label = { Text("Todas las categorías") }
            )
            pqrsCategories.forEach { value ->
                FilterChip(
                    selected = state.categoryFilter == value,
                    onClick = { viewModel.setCategoryFilter(value) },
                    label = { Text(value) }
                )
            }
        }
        if (Session.isAdmin && state.selectedVisibleCount > 0) {
            Button(onClick = onBatch, modifier = Modifier.fillMaxWidth()) {
                Text("Responder seleccionadas (${state.selectedVisibleCount})")
            }
        }
        if (state.loading) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            // Las archivadas se ven aquí; el respaldo en Excel y archivar se hacen en la web, desde el computador.
            if (Session.isAdmin) {
                item {
                    FilterChip(
                        selected = state.includeArchived,
                        onClick = { viewModel.setIncludeArchived(!state.includeArchived) },
                        label = { Text("Ver archivadas") }
                    )
                }
            }
            if (state.residentFilterId != null) {
                item {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            "Mostrando solo las PQRS de ${state.resident?.name ?: "este residente"}.",
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.weight(1f)
                        )
                        TextButton(onClick = { viewModel.clearResidentFilter() }) { Text("Ver todas") }
                    }
                }
            }
            grouped.forEach { (groupCategory, group) ->
                item(key = "category-$groupCategory") {
                    val pending = state.items.count {
                        (it.category ?: PQRS_DEFAULT_CATEGORY) == groupCategory && it.status != "resuelta"
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            "$groupCategory · pendientes: $pending",
                            style = MaterialTheme.typography.titleMedium
                        )
                        if (Session.isAdmin) {
                            val allSelected = group.isNotEmpty() && group.all { it.id in state.selectedIds }
                            Checkbox(
                                checked = allSelected,
                                onCheckedChange = { checked ->
                                    viewModel.toggleCategory(groupCategory, group, checked)
                                }
                            )
                        }
                    }
                }
                items(group, key = { it.id }) { pqrs ->
                    PqrsCard(
                        pqrs = pqrs,
                        expanded = expandedId == pqrs.id,
                        selected = pqrs.id in state.selectedIds,
                        busy = state.busy,
                        viewModel = viewModel,
                        onToggleExpanded = {
                            expandedId = if (expandedId == pqrs.id) null else pqrs.id
                        }
                    )
                }
            }
            if (visible.isEmpty() && !state.loading) {
                item { Text("No hay PQRS que coincidan con esos filtros.") }
            }
        }
    }
}

/** Qué tan urgente es el plazo: verde, amarillo o rojo (HU-073). */
private fun semaphoreTone(color: String?): DomuxBadgeTone = when (color) {
    "rojo" -> DomuxBadgeTone.ALERT
    "amarillo" -> DomuxBadgeTone.PROGRESS
    else -> DomuxBadgeTone.SUCCESS
}

/** El plazo escrito para leerlo rápido: cuántos días hábiles quedan, o cuántos lleva vencido. */
private fun semaphoreLabel(pqrs: Pqrs): String? {
    // Sin semáforo es porque la PQRS ya está resuelta: no hay plazo que mostrar.
    if (pqrs.semaphore == null) return null
    val due = humanDate(pqrs.dueDate)
    val days = pqrs.daysRemaining
        ?: return if (due.isBlank()) "Plazo de 15 días hábiles" else "Vence el $due"
    val dueNote = if (due.isBlank()) "" else " · vence el $due"
    return when {
        days < 0 -> "Plazo vencido hace ${businessDaysText(-days)}" + if (due.isBlank()) "" else " · era el $due"
        days == 0 -> "Vence hoy"
        else -> "Quedan ${businessDaysText(days)}$dueNote"
    }
}

@Composable
private fun PqrsCard(
    pqrs: Pqrs,
    expanded: Boolean,
    selected: Boolean,
    busy: Boolean,
    viewModel: PqrsViewModel,
    onToggleExpanded: () -> Unit
) {
    var responseText by remember(pqrs.id, pqrs.adminResponse) { mutableStateOf(pqrs.adminResponse.orEmpty()) }
    var responseStatus by remember(pqrs.id, pqrs.status) { mutableStateOf(pqrs.status) }
    // Cuando el servidor acepta una respuesta o un mensaje, la lista trae uno más y los adjuntos se limpian.
    val thread = pqrs.messages?.size
    var responseMediaUrl by remember(pqrs.id, thread) { mutableStateOf<String?>(null) }
    var responseMediaType by remember(pqrs.id, thread) { mutableStateOf<String?>(null) }
    var responseMediaName by remember(pqrs.id, thread) { mutableStateOf<String?>(null) }
    var replyText by remember(pqrs.id, thread) { mutableStateOf("") }
    var replyMediaUrl by remember(pqrs.id, thread) { mutableStateOf<String?>(null) }
    var replyMediaType by remember(pqrs.id, thread) { mutableStateOf<String?>(null) }
    var replyMediaName by remember(pqrs.id, thread) { mutableStateOf<String?>(null) }
    var rating by remember(pqrs.id, pqrs.satisfactionRating) { mutableIntStateOf(pqrs.satisfactionRating ?: 5) }
    var ratingComment by remember(pqrs.id, pqrs.satisfactionComment) {
        mutableStateOf(pqrs.satisfactionComment.orEmpty())
    }
    val tone = when (pqrs.status) {
        "resuelta" -> DomuxBadgeTone.SUCCESS
        "en_proceso" -> DomuxBadgeTone.PROGRESS
        else -> DomuxBadgeTone.ALERT
    }

    DomuxCard(Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.fillMaxWidth().animateContentSize().padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f).clickable(onClick = onToggleExpanded)) {
                    pqrs.radicado?.let { radicado ->
                        Text(
                            radicado,
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.secondary
                        )
                    }
                    Text(pqrs.subject, style = MaterialTheme.typography.titleMedium)
                }
                if (Session.isAdmin) {
                    Checkbox(
                        checked = selected,
                        onCheckedChange = { checked -> viewModel.toggleSelected(pqrs, checked) }
                    )
                }
                DomuxStatusBadge(pqrs.status.replace('_', ' '), tone)
            }
            semaphoreLabel(pqrs)?.let { label ->
                DomuxStatusBadge(label, semaphoreTone(pqrs.semaphore))
            }
            Text(
                "${pqrs.residentName ?: "Residente"} · ${pqrs.apartment.orEmpty()}",
                style = MaterialTheme.typography.bodySmall
            )
            if (pqrs.createdByAdministration) {
                Text("Creada por administración", style = MaterialTheme.typography.labelSmall)
            }
            if (pqrs.isArchived) {
                Text("Archivada", style = MaterialTheme.typography.labelSmall)
            }
            Text(pqrs.createdAt.orEmpty(), style = MaterialTheme.typography.bodySmall)
            if (expanded) {
                HorizontalDivider(Modifier.padding(vertical = 8.dp))
                val messages = pqrs.messages.orEmpty()
                if (messages.isEmpty()) {
                    Text(pqrs.message)
                    MediaAttachmentChip(pqrs.mediaUrl, pqrs.mediaType)
                    if (!pqrs.adminResponse.isNullOrBlank()) Text("Respuesta anterior: ${pqrs.adminResponse}")
                } else {
                    messages.forEach { item ->
                        Text(
                            "${item.authorName ?: item.authorRole} · ${item.createdAt.orEmpty()}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.secondary
                        )
                        if (!item.message.isNullOrBlank()) Text(item.message)
                        MediaAttachmentChip(item.mediaUrl, item.mediaType)
                        Spacer(Modifier.height(4.dp))
                    }
                }
                if (pqrs.incidentDate != null || pqrs.incidentTime != null) {
                    Text("Incidente: ${pqrs.incidentDate.orEmpty()} ${pqrs.incidentTime.orEmpty()}")
                }
                if (Session.isAdmin) {
                    Text(
                        "Satisfacción: ${pqrs.satisfactionRating?.let { "$it/5" } ?: "Sin calificar"}" +
                            (pqrs.satisfactionComment?.let { " · $it" } ?: "")
                    )
                    OutlinedTextField(
                        value = responseText,
                        onValueChange = { responseText = it },
                        label = { Text("Respuesta administrativa *") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    if (responseText.isBlank()) {
                        Text(
                            "Escribe texto antes de responder o marcar como resuelta.",
                            color = MaterialTheme.colorScheme.error,
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    Row(modifier = Modifier.horizontalScroll(rememberScrollState())) {
                        listOf("abierta", "en_proceso", "resuelta").forEach { option ->
                            FilterChip(
                                selected = responseStatus == option,
                                onClick = { responseStatus = option },
                                label = { Text(option.replace('_', ' ')) }
                            )
                        }
                    }
                    MediaAttachmentPicker(
                        responseMediaName,
                        { url, type, name ->
                            responseMediaUrl = url
                            responseMediaType = type
                            responseMediaName = name
                        },
                        { viewModel.showNotice(it) },
                        kinds = AttachmentKinds.MEDIA_AND_PDF,
                        onClear = { responseMediaUrl = null; responseMediaType = null; responseMediaName = null }
                    )
                    Button(
                        enabled = responseText.isNotBlank() && !busy,
                        onClick = {
                            viewModel.respond(
                                pqrs,
                                responseStatus,
                                responseText.trim(),
                                responseMediaUrl,
                                responseMediaType
                            )
                        }
                    ) { Text(if (busy) "Guardando..." else "Guardar respuesta") }
                } else if (Session.isResident) {
                    OutlinedTextField(
                        value = replyText,
                        onValueChange = { replyText = it },
                        label = { Text("Escribe un mensaje para continuar la conversación") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    MediaAttachmentPicker(
                        replyMediaName,
                        { url, type, name ->
                            replyMediaUrl = url
                            replyMediaType = type
                            replyMediaName = name
                        },
                        { viewModel.showNotice(it) },
                        kinds = AttachmentKinds.MEDIA_AND_PDF,
                        onClear = { replyMediaUrl = null; replyMediaType = null; replyMediaName = null }
                    )
                    Button(
                        enabled = (replyText.isNotBlank() || replyMediaUrl != null) && !busy,
                        onClick = {
                            viewModel.reply(
                                pqrs,
                                replyText.trim().ifEmpty { null },
                                replyMediaUrl,
                                replyMediaType
                            )
                        }
                    ) { Text(if (busy) "Enviando..." else "Enviar mensaje") }

                    if (pqrs.status == "resuelta") {
                        HorizontalDivider(Modifier.padding(vertical = 8.dp))
                        Text("¿Qué tan satisfecho estás con la solución?")
                        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            (1..5).forEach { score ->
                                FilterChip(
                                    selected = rating == score,
                                    onClick = { rating = score },
                                    label = { Text("$score ★") }
                                )
                            }
                        }
                        OutlinedTextField(
                            value = ratingComment,
                            onValueChange = { ratingComment = it },
                            label = { Text("Comentario opcional") },
                            modifier = Modifier.fillMaxWidth()
                        )
                        Button(
                            enabled = !busy,
                            onClick = {
                                viewModel.rate(pqrs, rating, ratingComment.trim().ifEmpty { null })
                            }
                        ) { Text("Guardar calificación") }
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Respuesta por lotes (solo la administración)
// ---------------------------------------------------------------------------

@Composable
private fun PqrsBatchDialog(state: PqrsUiState, viewModel: PqrsViewModel, onClose: () -> Unit) {
    var text by rememberSaveable { mutableStateOf("") }
    var status by rememberSaveable { mutableStateOf("en_proceso") }
    // El adjunto va en base64 y puede pesar varios MB: no se guarda con el estado de la pantalla.
    var mediaUrl by remember { mutableStateOf<String?>(null) }
    var mediaType by remember { mutableStateOf<String?>(null) }
    var mediaName by remember { mutableStateOf<String?>(null) }
    var handled by rememberSaveable { mutableStateOf(state.batchDone) }
    val count = state.selectedVisibleCount

    // Cuando el servidor acepta la respuesta, el cuadro se cierra.
    LaunchedEffect(state.batchDone) {
        if (state.batchDone != handled) {
            handled = state.batchDone
            onClose()
        }
    }

    AlertDialog(
        onDismissRequest = onClose,
        title = { Text("Respuesta por lotes") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Vas a responder $count PQRS de la categoría seleccionada.")
                OutlinedTextField(
                    value = text,
                    onValueChange = { text = it },
                    label = { Text("Respuesta *") },
                    modifier = Modifier.fillMaxWidth()
                )
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    listOf("en_proceso", "resuelta").forEach { option ->
                        FilterChip(
                            selected = status == option,
                            onClick = { status = option },
                            label = { Text(option.replace('_', ' ')) }
                        )
                    }
                }
                MediaAttachmentPicker(
                    mediaName,
                    { url, type, name ->
                        mediaUrl = url
                        mediaType = type
                        mediaName = name
                    },
                    { viewModel.showNotice(it) },
                    kinds = AttachmentKinds.MEDIA_AND_PDF,
                    onClear = { mediaUrl = null; mediaType = null; mediaName = null }
                )
            }
        },
        confirmButton = {
            TextButton(
                enabled = text.isNotBlank() && count > 0 && !state.busy,
                onClick = { viewModel.respondBatch(status, text.trim(), mediaUrl, mediaType) }
            ) { Text(if (state.busy) "Enviando..." else "Enviar a $count") }
        },
        dismissButton = {
            TextButton(onClick = onClose) { Text("Cancelar") }
        }
    )
}

// ---------------------------------------------------------------------------
// PQRS nueva
// ---------------------------------------------------------------------------

@Composable
private fun PqrsForm(
    modifier: Modifier,
    state: PqrsUiState,
    viewModel: PqrsViewModel,
    onCreated: () -> Unit
) {
    var subject by rememberSaveable { mutableStateOf("") }
    var detail by rememberSaveable { mutableStateOf("") }
    var category by rememberSaveable { mutableStateOf(pqrsCategories.first()) }
    var incidentDate by rememberSaveable { mutableStateOf("") }
    var incidentTime by rememberSaveable { mutableStateOf("") }
    var attempted by rememberSaveable { mutableStateOf(false) }
    // El adjunto va en base64 y puede pesar varios MB: no se guarda con el estado de la pantalla.
    var mediaUrl by remember { mutableStateOf<String?>(null) }
    var mediaType by remember { mutableStateOf<String?>(null) }
    var mediaName by remember { mutableStateOf<String?>(null) }
    var handled by rememberSaveable { mutableStateOf(state.created) }

    // Cuando el servidor acepta la PQRS, el formulario queda limpio y se vuelve a la lista.
    LaunchedEffect(state.created) {
        if (state.created != handled) {
            handled = state.created
            subject = ""
            detail = ""
            category = pqrsCategories.first()
            incidentDate = ""
            incidentTime = ""
            attempted = false
            mediaUrl = null
            mediaType = null
            mediaName = null
            onCreated()
        }
    }

    val minorBlocked = Session.isResident && Session.isMinor && !Session.parentalConsent
    val admin = Session.isAdmin

    Column(
        modifier = modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        DomuxCard(Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                if (minorBlocked) {
                    Text(
                        "Tu cuenta de menor de edad está en Modo Consulta. Puedes ver anuncios, paquetes y notificaciones, pero para radicar PQRS necesitas autorización parental registrada por la administración.",
                        color = MaterialTheme.colorScheme.error
                    )
                }
                Text(
                    if (admin) "Crear PQRS para un residente" else "Nueva PQRS",
                    style = MaterialTheme.typography.titleMedium
                )
                if (admin) {
                    DomuxResidentSearchField(
                        selectedResident = state.resident,
                        onSelectResident = { viewModel.selectResident(it) }
                    )
                    if (attempted && state.resident == null) {
                        Text("Selecciona el residente.", color = MaterialTheme.colorScheme.error)
                    }
                }
                OutlinedTextField(
                    value = subject,
                    onValueChange = { subject = it },
                    label = { Text("Asunto *") },
                    isError = attempted && subject.isBlank(),
                    supportingText = { if (attempted && subject.isBlank()) Text("El asunto es obligatorio") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(
                    value = detail,
                    onValueChange = { detail = it },
                    label = { Text("Descripción *") },
                    isError = attempted && detail.isBlank(),
                    supportingText = { if (attempted && detail.isBlank()) Text("La descripción es obligatoria") },
                    modifier = Modifier.fillMaxWidth()
                )
                Row(
                    modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    pqrsCategories.forEach { value ->
                        FilterChip(
                            selected = category == value,
                            onClick = { category = value },
                            label = { Text(value) }
                        )
                    }
                }
                Text(
                    "Al radicarla recibe un número de radicado y tiene 15 días hábiles para ser respondida.",
                    style = MaterialTheme.typography.bodySmall
                )
                DatePickerField("Fecha del incidente", incidentDate, { incidentDate = it })
                TimePickerField("Hora del incidente", incidentTime, { incidentTime = it })
                MediaAttachmentPicker(
                    mediaName,
                    { url, type, name ->
                        mediaUrl = url
                        mediaType = type
                        mediaName = name
                    },
                    { viewModel.showNotice(it) },
                    kinds = AttachmentKinds.MEDIA_AND_PDF,
                    onClear = { mediaUrl = null; mediaType = null; mediaName = null }
                )
                Button(
                    enabled = !state.busy && !minorBlocked,
                    onClick = {
                        attempted = true
                        if (subject.isBlank() || detail.isBlank() || (admin && state.resident == null)) {
                            viewModel.showNotice(
                                if (admin) "Asunto, descripción y residente son obligatorios."
                                else "El asunto y la descripción son obligatorios."
                            )
                        } else {
                            viewModel.create(
                                subject.trim(),
                                detail.trim(),
                                category,
                                incidentDate.ifBlank { null },
                                incidentTime.ifBlank { null },
                                mediaUrl,
                                mediaType
                            )
                        }
                    },
                    modifier = Modifier.fillMaxWidth()
                ) { Text(if (state.busy) "Enviando..." else "Enviar PQRS") }
            }
        }
    }
}
