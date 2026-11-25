package com.dracknoval.domux

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.dracknoval.domux.data.AddPqrsMessageRequest
import com.dracknoval.domux.data.BatchRespondPqrsRequest
import com.dracknoval.domux.data.CreatePqrsRequest
import com.dracknoval.domux.data.Pqrs
import com.dracknoval.domux.data.RatePqrsRequest
import com.dracknoval.domux.data.RespondPqrsRequest
import com.dracknoval.domux.data.ResidentSummary
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.foundation.text.KeyboardOptions

private fun getDaysAgo(dateString: String?): Long {
    if (dateString.isNullOrBlank()) return 0
    return try {
        val format = java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US)
        val date = format.parse(dateString.take(10))
        if (date != null) {
            val diff = System.currentTimeMillis() - date.time
            java.util.concurrent.TimeUnit.MILLISECONDS.toDays(diff)
        } else 0
    } catch(e: Exception) { 0 }
}

private val pqrsCategories = listOf("Petición", "Queja", "Reclamo", "Sugerencia", "Daño")
private val pqrsStates = listOf(
    "Todas" to null,
    "Abiertas" to "abierta",
    "En proceso" to "en_proceso",
    "Resueltas" to "resuelta"
)

@Composable
fun PqrsScreen(navController: NavController, targetResidentId: Int? = null) {
    var allItems by remember { mutableStateOf<List<Pqrs>>(emptyList()) }
    var residents by remember { mutableStateOf<List<ResidentSummary>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var sending by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var messageIsError by remember { mutableStateOf(false) }
    var search by remember { mutableStateOf("") }
    var statusFilter by remember { mutableStateOf<String?>(null) }
    var categoryFilter by remember { mutableStateOf<String?>(null) }
    var residentStatusFilter by remember { mutableStateOf("Activas") }
    var sortOrder by remember { mutableStateOf("recientes") }
    var expandedId by remember { mutableStateOf<Int?>(null) }
    var selectedIds by remember { mutableStateOf<Set<Int>>(emptySet()) }
    var selectedCategory by remember { mutableStateOf<String?>(null) }
    var batchDialog by remember { mutableStateOf(false) }
    var batchMessage by remember { mutableStateOf("") }
    var batchStatus by remember { mutableStateOf("en_proceso") }
    var batchMediaUrl by remember { mutableStateOf<String?>(null) }
    var batchMediaType by remember { mutableStateOf<String?>(null) }
    var batchMediaName by remember { mutableStateOf<String?>(null) }
    var subject by remember { mutableStateOf("") }
    var detail by remember { mutableStateOf("") }
    var category by remember { mutableStateOf(pqrsCategories.first()) }
    var incidentDate by remember { mutableStateOf("") }
    var incidentTime by remember { mutableStateOf("") }
    var mediaUrl by remember { mutableStateOf<String?>(null) }
    var mediaType by remember { mutableStateOf<String?>(null) }
    var mediaName by remember { mutableStateOf<String?>(null) }
    var selectedResident by remember { mutableStateOf<ResidentSummary?>(null) }
    var attemptedSubmit by remember { mutableStateOf(false) }
    var selectedTab by remember {
        mutableIntStateOf(if (targetResidentId != null) 1 else 0)
    }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    suspend fun load() {
        loading = true
        try {
            val response = RetrofitClient.api.getPqrs(
                Session.bearer(), null, null, search.trim().ifEmpty { null },
                targetResidentId.takeIf { Session.isAdmin },
                null
            )
            if (response.isSuccessful) {
                allItems = response.body()?.pqrs.orEmpty()
                selectedIds = selectedIds.intersect(allItems.map { it.id }.toSet())
                if (selectedIds.isEmpty()) selectedCategory = null
            } else {
                message = mensajeDeError(response.code(), response.errorBody()?.string())
            }
            if (Session.isAdmin && residents.isEmpty()) {
                val residentResponse = RetrofitClient.api.getResidents(Session.bearer())
                if (residentResponse.isSuccessful) {
                    residents = residentResponse.body()?.residents.orEmpty()
                    selectedResident = residents.firstOrNull { it.id == targetResidentId }
                        ?: selectedResident?.takeIf { current ->
                            residents.any { it.id == current.id }
                        }
                        ?: residents.firstOrNull()
                }
            }
        } catch (exception: Exception) {
            if (exception is CancellationException) throw exception
            message = "No se pudieron cargar las PQRS: ${exception.message}"
        } finally {
            loading = false
        }
    }

    LaunchedEffect(search) {
        selectedIds = emptySet()
        selectedCategory = null
        load()
    }

    val visibleItems = allItems.filter { pqrs ->
        if (Session.isResident) {
            (if (residentStatusFilter == "Activas") pqrs.status in listOf("abierta", "en_proceso") else pqrs.status == "resuelta") &&
            (categoryFilter == null || pqrs.category == categoryFilter)
        } else {
            (statusFilter == null || pqrs.status == statusFilter) &&
            (categoryFilter == null || pqrs.category == categoryFilter)
        }
    }
    val sortedItems = if (sortOrder == "antiguas") visibleItems.sortedBy { it.createdAt } else visibleItems.sortedByDescending { it.createdAt }
    val groupedItems = sortedItems.groupBy { it.category ?: "Petición" }.toSortedMap()
    val selectedVisibleCount = sortedItems.count { it.id in selectedIds }

    DomuxScreenScaffold(title = "PQRS", navController = navController) { padding ->
    Column(Modifier.fillMaxSize().padding(padding).padding(horizontal = 18.dp, vertical = 12.dp)) {
        DomuxSectionTabs(
            listOf("Solicitudes PQRS", "Nueva PQRS"),
            selectedTab
        ) { selectedTab = it }
        DomuxFeedbackBanner(message, isError = messageIsError) { message = "" }
        if (selectedTab == 0) {
        OutlinedTextField(
            value = search,
            onValueChange = { search = it },
            label = { Text("Buscar PQRS") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            if (Session.isResident) {
                listOf("Activas", "Resueltas / Historial").forEach { label ->
                    FilterChip(
                        selected = residentStatusFilter == label,
                        onClick = { residentStatusFilter = label },
                        label = { Text(label) }
                    )
                }
            } else {
                pqrsStates.forEach { (label, value) ->
                    FilterChip(
                        selected = statusFilter == value,
                        onClick = { statusFilter = value },
                        label = { Text(label) }
                    )
                }
            }
        }
        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            listOf("Todas" to null).plus(pqrsCategories.map { it to it }).forEach { (label, value) ->
                FilterChip(
                    selected = categoryFilter == value,
                    onClick = {
                        categoryFilter = value
                        selectedIds = emptySet()
                        selectedCategory = null
                    },
                    label = { Text(label) }
                )
            }
        }
        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            listOf("Más recientes" to "recientes", "Más antiguas primero" to "antiguas").forEach { (label, value) ->
                FilterChip(
                    selected = sortOrder == value,
                    onClick = { sortOrder = value },
                    label = { Text(label) }
                )
            }
        }
        }

        if ((Session.isAdmin || Session.isResident) && selectedTab == 1) {
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
            DomuxCard(Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
                Column(Modifier.padding(12.dp)) {
                    if (Session.isResident && Session.isMinor && !Session.parentalConsent) {
                        Text(
                            "Tu cuenta de menor de edad está en Modo Consulta. Puedes ver anuncios, paquetes y notificaciones, pero para radicar PQRS necesitas autorización parental registrada por la administración.",
                            color = MaterialTheme.colorScheme.error,
                            modifier = Modifier.padding(bottom = 10.dp)
                        )
                    }
                    Text(
                        if (Session.isAdmin) "Crear PQRS para un residente" else "Nueva PQRS",
                        style = MaterialTheme.typography.titleMedium
                    )
                    if (Session.isAdmin) {
                        DomuxResidentSearchField(
                            selectedResident = selectedResident,
                            onSelectResident = { selectedResident = it }
                        )
                    }
                    OutlinedTextField(
                        subject, { subject = it }, label = { Text("Asunto *") },
                        isError = attemptedSubmit && subject.trim().isEmpty(),
                        supportingText = {
                            if (attemptedSubmit && subject.trim().isEmpty()) Text("El asunto es obligatorio")
                        },
                        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
                        minLines = 3, maxLines = 6, modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        detail, { detail = it }, label = { Text("Descripción *") },
                        isError = attemptedSubmit && detail.trim().isEmpty(),
                        supportingText = {
                            if (attemptedSubmit && detail.trim().isEmpty()) Text("La descripción es obligatoria")
                        },
                        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
                        minLines = 3, maxLines = 6, modifier = Modifier.fillMaxWidth()
                    )
                    @OptIn(ExperimentalLayoutApi::class)
                    FlowRow(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        pqrsCategories.forEach { value ->
                            FilterChip(
                                selected = category == value,
                                onClick = { category = value },
                                label = { Text(value) }
                            )
                        }
                    }
                    DatePickerField(
                        "Fecha del incidente",
                        incidentDate,
                        { incidentDate = it },
                        allowPastDates = true,
                        maxDate = java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US).format(java.util.Date())
                    )
                    TimePickerField("Hora del incidente", incidentTime, { incidentTime = it })
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.padding(top = 8.dp)) {
                        MediaAttachmentPicker(mediaName, { url, type, name ->
                            mediaUrl = url
                            mediaType = type
                            mediaName = name
                        }, { message = it; messageIsError = true })
                        Button(
                            enabled = !sending &&
                                !(Session.isResident && Session.isMinor && !Session.parentalConsent),
                            onClick = {
                                attemptedSubmit = true
                                if (subject.trim().isEmpty() || detail.trim().isEmpty() ||
                                    (Session.isAdmin && selectedResident == null)
                                ) {
                                    message = "Asunto, descripción y residente son obligatorios."
                                    messageIsError = true
                                    return@Button
                                }
                                sending = true
                                scope.launch {
                                    try {
                                        val response = RetrofitClient.api.createPqrs(
                                            Session.bearer(),
                                            CreatePqrsRequest(
                                                subject.trim(), detail.trim(), category,
                                                incidentDate.ifBlank { null }, incidentTime.ifBlank { null },
                                                mediaUrl, mediaType, if (Session.isAdmin) selectedResident?.id else null
                                            )
                                        )
                                        if (response.isSuccessful) {
                                            subject = ""
                                            detail = ""
                                            incidentDate = ""
                                            incidentTime = ""
                                            mediaUrl = null
                                            mediaType = null
                                            mediaName = null
                                            attemptedSubmit = false
                                            message = "PQRS enviada exitosamente."
                                            messageIsError = false
                                            selectedTab = 0
                                            load()
                                        } else {
                                            message = mensajeDeError(response.code(), response.errorBody()?.string())
                                            messageIsError = true
                                        }
                                    } catch (exception: Exception) {
                                        if (exception is CancellationException) throw exception
                                        message = "No se pudo enviar la PQRS: ${exception.message}"
                                        messageIsError = true
                                    } finally {
                                        sending = false
                                    }
                                }
                            },
                            modifier = Modifier.fillMaxWidth()
                        ) { Text(if (sending) "Enviando..." else "Enviar PQRS") }
                    }
                }
            }
            }
        }

        if (selectedTab == 0) {
        if (Session.isAdmin && selectedVisibleCount > 0) {
            Button(
                onClick = { batchDialog = true },
                modifier = Modifier.fillMaxWidth()
            ) { Text("Responder seleccionadas ($selectedVisibleCount)") }
        }

        if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            LazyColumn(Modifier.weight(1f)) {
                groupedItems.forEach { (groupCategory, group) ->
                    item(key = "category-$groupCategory") {
                        Row(
                            Modifier.fillMaxWidth().padding(top = 12.dp, bottom = 4.dp),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(
                                "$groupCategory · pendientes: ${
                                    allItems.count {
                                        (it.category ?: "Petición") == groupCategory &&
                                            it.status != "resuelta"
                                    }
                                }",
                                style = MaterialTheme.typography.titleMedium
                            )
                            if (Session.isAdmin) {
                                val allSelected = group.isNotEmpty() && group.all { it.id in selectedIds }
                                Checkbox(
                                    checked = allSelected,
                                    onCheckedChange = { checked ->
                                        selectedIds = if (checked) {
                                            if (selectedCategory != groupCategory) {
                                                group.map { it.id }.toSet()
                                            } else {
                                                selectedIds + group.map { it.id }
                                            }
                                        } else {
                                            selectedIds - group.map { it.id }.toSet()
                                        }
                                        selectedCategory = if (selectedIds.isEmpty()) null else groupCategory
                                    }
                                )
                            }
                        }
                    }
                    items(group, key = { it.id }) { pqrs ->
                        PqrsCard(
                            pqrs = pqrs,
                            expanded = expandedId == pqrs.id,
                            selected = pqrs.id in selectedIds,
                            onToggleExpanded = {
                                expandedId = if (expandedId == pqrs.id) null else pqrs.id
                            },
                            onToggleSelected = { checked ->
                                selectedIds = if (checked) {
                                    if (selectedCategory != groupCategory) setOf(pqrs.id)
                                    else selectedIds + pqrs.id
                                } else {
                                    selectedIds - pqrs.id
                                }
                                selectedCategory = if (selectedIds.isEmpty()) null else groupCategory
                            },
                            onRefresh = {
                                scope.launch { load() }
                            },
                            onMessage = { text, isError ->
                                message = text
                                messageIsError = isError
                            }
                        )
                    }
                }
                if (visibleItems.isEmpty()) {
                    item { Text("No hay PQRS que coincidan con esos filtros.", Modifier.padding(16.dp)) }
                }
        }
        }
    }
    }

    if (batchDialog) {
        AlertDialog(
            onDismissRequest = { batchDialog = false },
            title = {
                Text(if (selectedIds.size == 1) "Responder PQRS" else "Respuesta por lotes")
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        if (selectedIds.size == 1) "Escribe la respuesta para esta solicitud."
                        else "Vas a responder $selectedVisibleCount PQRS de la categoría seleccionada."
                    )
                    OutlinedTextField(
                        value = batchMessage,
                        onValueChange = { batchMessage = it },
                        label = { Text("Respuesta *") },
                        isError = batchMessage.isNotEmpty() && batchMessage.isBlank(),
                        modifier = Modifier.fillMaxWidth()
                    )
                    Row(
                        modifier = Modifier.horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        listOf("en_proceso", "resuelta").forEach { value ->
                            FilterChip(
                                selected = batchStatus == value,
                                onClick = { batchStatus = value },
                                label = { Text(value.toDomuxDisplayLabel()) }
                            )
                        }
                    }
                    MediaAttachmentPicker(batchMediaName, { url, type, name ->
                        batchMediaUrl = url
                        batchMediaType = type
                        batchMediaName = name
                    }, { message = it; messageIsError = true })
                }
            },
            confirmButton = {
                TextButton(
                    enabled = batchMessage.isNotBlank() && selectedVisibleCount > 0 && !sending,
                    onClick = {
                        sending = true
                        scope.launch {
                            try {
                                val response = RetrofitClient.api.respondPqrsBatch(
                                    Session.bearer(),
                                    BatchRespondPqrsRequest(
                                        sortedItems.filter { it.id in selectedIds }.map { it.id },
                                        batchStatus,
                                        batchMessage.trim(),
                                        batchMediaUrl,
                                        batchMediaType
                                    )
                                )
                                if (response.isSuccessful) {
                                    message = response.body()?.message ?: "PQRS actualizadas."
                                    messageIsError = false
                                    selectedIds = emptySet()
                                    selectedCategory = null
                                    batchMessage = ""
                                    batchMediaUrl = null
                                    batchMediaType = null
                                    batchMediaName = null
                                    batchDialog = false
                                    load()
                                } else {
                                    message = mensajeDeError(response.code(), response.errorBody()?.string())
                                    messageIsError = true
                                }
                            } catch (exception: Exception) {
                                if (exception is CancellationException) throw exception
                                message = "No se pudieron responder las PQRS: ${exception.message}"
                                messageIsError = true
                            } finally {
                                sending = false
                            }
                        }
                    }
                ) {
                    Text(
                        if (sending) "Enviando..."
                        else if (selectedIds.size == 1) "Enviar respuesta"
                        else "Enviar a $selectedVisibleCount"
                    )
                }
            },
            dismissButton = {
                TextButton(onClick = { batchDialog = false }) { Text("Cancelar") }
            }
        )
    }
}

@Composable
private fun PqrsCard(
    pqrs: Pqrs,
    expanded: Boolean,
    selected: Boolean,
    onToggleExpanded: () -> Unit,
    onToggleSelected: (Boolean) -> Unit,
    onRefresh: () -> Unit,
    onMessage: (String, Boolean) -> Unit
) {
    val scope = rememberCoroutineScope()
    var responseText by remember(pqrs.id, pqrs.adminResponse) {
        mutableStateOf(pqrs.adminResponse.orEmpty())
    }
    var responseStatus by remember(pqrs.id, pqrs.status) { mutableStateOf(pqrs.status) }
    var responseMediaUrl by remember(pqrs.id) { mutableStateOf<String?>(null) }
    var responseMediaType by remember(pqrs.id) { mutableStateOf<String?>(null) }
    var responseMediaName by remember(pqrs.id) { mutableStateOf<String?>(null) }
    var replyText by remember(pqrs.id, pqrs.messages?.size) { mutableStateOf("") }
    var replyMediaUrl by remember(pqrs.id) { mutableStateOf<String?>(null) }
    var replyMediaType by remember(pqrs.id) { mutableStateOf<String?>(null) }
    var replyMediaName by remember(pqrs.id) { mutableStateOf<String?>(null) }
    var rating by remember(pqrs.id, pqrs.satisfactionRating) {
        mutableIntStateOf(pqrs.satisfactionRating ?: 5)
    }
    var ratingComment by remember(pqrs.id, pqrs.satisfactionComment) {
        mutableStateOf(pqrs.satisfactionComment.orEmpty())
    }
    var busy by remember(pqrs.id) { mutableStateOf(false) }
    val tone = when (pqrs.status) {
        "resuelta" -> DomuxBadgeTone.SUCCESS
        "en_proceso" -> DomuxBadgeTone.PROGRESS
        else -> DomuxBadgeTone.ALERT
    }

    DomuxCard(Modifier.fillMaxWidth().padding(vertical = 5.dp)) {
        Column(Modifier.fillMaxWidth().animateContentSize()) {
            Column(Modifier.fillMaxWidth().clickable(onClick = onToggleExpanded).padding(12.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(pqrs.subject, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                    if (Session.isAdmin) {
                        Checkbox(checked = selected, onCheckedChange = onToggleSelected)
                    }
                    DomuxStatusBadge(pqrs.status.toDomuxDisplayLabel(), tone)
                }
                Text("${pqrs.residentName ?: "Residente"} · ${pqrs.apartment.orEmpty()}", style = MaterialTheme.typography.bodySmall)
                if (pqrs.createdByAdministration) {
                    Text("Creada por administración", style = MaterialTheme.typography.labelSmall)
                }
                Text(pqrs.createdAt.orEmpty(), style = MaterialTheme.typography.bodySmall)
                val daysAgo = getDaysAgo(pqrs.createdAt)
                if (pqrs.status != "resuelta" && daysAgo > 0) {
                    Text("Hace $daysAgo días", color = if (daysAgo >= 3) Color(0xFFEF4444) else Color(0xFFF59E0B), style = MaterialTheme.typography.labelSmall)
                }
            }
            if (expanded) {
                Column(Modifier.fillMaxWidth().padding(start = 12.dp, end = 12.dp, bottom = 12.dp)) {
                    HorizontalDivider(Modifier.padding(bottom = 8.dp))
                    val messages = pqrs.messages.orEmpty()
                    if (messages.isEmpty()) {
                        Text(pqrs.message)
                        DomuxAttachmentPreview(pqrs.mediaUrl, pqrs.mediaType)
                        if (!pqrs.adminResponse.isNullOrBlank()) Text("Respuesta anterior: ${pqrs.adminResponse}")
                    } else {
                        messages.forEach { item ->
                            Text(
                                "${item.authorName ?: item.authorRole} · ${item.createdAt.orEmpty()}",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.secondary
                            )
                            if (!item.message.isNullOrBlank()) Text(item.message)
                            DomuxAttachmentPreview(item.mediaUrl, item.mediaType)
                            Spacer(Modifier.height(6.dp))
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
                    Row(Modifier.horizontalScroll(rememberScrollState())) {
                        listOf("abierta", "en_proceso", "resuelta").forEach { state ->
                            FilterChip(
                                selected = responseStatus == state,
                                onClick = { responseStatus = state },
                                label = { Text(state.toDomuxDisplayLabel()) }
                            )
                        }
                    }
                    MediaAttachmentPicker(responseMediaName, { url, type, name ->
                        responseMediaUrl = url
                        responseMediaType = type
                        responseMediaName = name
                    }, { onMessage(it, true) })
                    Button(
                        enabled = responseText.isNotBlank() && !busy,
                        onClick = {
                            busy = true
                            scope.launch {
                                try {
                                    val result = RetrofitClient.api.respondPqrs(
                                        Session.bearer(),
                                        pqrs.id,
                                        RespondPqrsRequest(
                                            responseStatus,
                                            responseText.trim(),
                                            responseMediaUrl,
                                            responseMediaType
                                        )
                                    )
                                    if (result.isSuccessful) {
                                        onMessage("PQRS actualizada.", false)
                                        onRefresh()
                                    } else {
                                        onMessage(mensajeDeError(result.code(), result.errorBody()?.string()), true)
                                    }
                                } catch (exception: Exception) {
                                    if (exception is CancellationException) throw exception
                                    onMessage("No se pudo actualizar la PQRS: ${exception.message}", true)
                                } finally {
                                    busy = false
                                }
                            }
                        }
                    ) { Text(if (busy) "Guardando..." else "Guardar respuesta") }
                } else if (Session.isResident) {
                    OutlinedTextField(
                        value = replyText,
                        onValueChange = { replyText = it },
                        label = { Text("Escribe un mensaje para continuar la conversación") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    MediaAttachmentPicker(replyMediaName, { url, type, name ->
                        replyMediaUrl = url
                        replyMediaType = type
                        replyMediaName = name
                    }, { onMessage(it, true) })
                    Button(
                        enabled = (replyText.isNotBlank() || replyMediaUrl != null) && !busy,
                        onClick = {
                            busy = true
                            scope.launch {
                                try {
                                    val result = RetrofitClient.api.addPqrsMessage(
                                        Session.bearer(),
                                        pqrs.id,
                                        AddPqrsMessageRequest(
                                            replyText.trim().ifEmpty { null },
                                            replyMediaUrl,
                                            replyMediaType
                                        )
                                    )
                                    if (result.isSuccessful) {
                                        onMessage("Mensaje enviado.", false)
                                        onRefresh()
                                    } else {
                                        onMessage(mensajeDeError(result.code(), result.errorBody()?.string()), true)
                                    }
                                } catch (exception: Exception) {
                                    if (exception is CancellationException) throw exception
                                    onMessage("No se pudo enviar el mensaje: ${exception.message}", true)
                                } finally {
                                    busy = false
                                }
                            }
                        }
                    ) { Text(if (busy) "Enviando..." else "Enviar mensaje") }

                    if (pqrs.status == "resuelta") {
                        HorizontalDivider(Modifier.padding(vertical = 8.dp))
                        Text("¿Qué tan satisfecho estás con la solución?")
                        Row(
                            modifier = Modifier.horizontalScroll(rememberScrollState()),
                            horizontalArrangement = Arrangement.spacedBy(4.dp)
                        ) {
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
                                busy = true
                                scope.launch {
                                    try {
                                        val result = RetrofitClient.api.ratePqrs(
                                            Session.bearer(),
                                            pqrs.id,
                                            RatePqrsRequest(rating, ratingComment.trim().ifEmpty { null })
                                        )
                                        if (result.isSuccessful) {
                                            onMessage("Calificación guardada.", false)
                                            onRefresh()
                                        } else {
                                            onMessage(mensajeDeError(result.code(), result.errorBody()?.string()), true)
                                        }
                                    } catch (exception: Exception) {
                                        if (exception is CancellationException) throw exception
                                        onMessage("No se pudo guardar la calificación: ${exception.message}", true)
                                    } finally {
                                        busy = false
                                    }
                                }
                            }
                        ) { Text("Guardar calificación") }
                    }
                }
            }
        }
    }
}
}
