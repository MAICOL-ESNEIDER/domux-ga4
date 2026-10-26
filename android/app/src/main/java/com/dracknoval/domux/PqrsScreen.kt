package com.dracknoval.domux

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
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
import kotlinx.coroutines.launch

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
    var search by remember { mutableStateOf("") }
    var statusFilter by remember { mutableStateOf<String?>(null) }
    var categoryFilter by remember { mutableStateOf<String?>(null) }
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
    val scope = rememberCoroutineScope()

    suspend fun load() {
        loading = true
        try {
            val response = RetrofitClient.api.getPqrs(
                Session.bearer(), null, null, search.trim().ifEmpty { null },
                targetResidentId.takeIf { Session.isAdmin }
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
        (statusFilter == null || pqrs.status == statusFilter) &&
            (categoryFilter == null || pqrs.category == categoryFilter)
    }
    val groupedItems = visibleItems.groupBy { it.category ?: "Petición" }.toSortedMap()
    val selectedVisibleCount = visibleItems.count { it.id in selectedIds }

    Column(Modifier.fillMaxSize().padding(horizontal = 18.dp, vertical = 12.dp)) {
        Text("Peticiones, quejas y reclamos", fontSize = 23.sp, color = MaterialTheme.colorScheme.primary)
        if (message.isNotBlank()) Text(message, color = MaterialTheme.colorScheme.error)
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
            pqrsStates.forEach { (label, value) ->
                FilterChip(
                    selected = statusFilter == value,
                    onClick = { statusFilter = value },
                    label = { Text(label) }
                )
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

        if (Session.isAdmin || Session.isResident) {
            DomuxCard(Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
                Column(Modifier.padding(12.dp)) {
                    Text(
                        if (Session.isAdmin) "Crear PQRS para un residente" else "Nueva PQRS",
                        style = MaterialTheme.typography.titleMedium
                    )
                    if (Session.isAdmin) {
                        residents.forEach { resident ->
                            FilterChip(
                                selected = selectedResident?.id == resident.id,
                                onClick = { selectedResident = resident },
                                label = { Text("${resident.name} · ${resident.apartment.orEmpty()}") }
                            )
                        }
                    }
                    OutlinedTextField(
                        subject, { subject = it }, label = { Text("Asunto *") },
                        isError = attemptedSubmit && subject.trim().isEmpty(),
                        supportingText = {
                            if (attemptedSubmit && subject.trim().isEmpty()) Text("El asunto es obligatorio")
                        },
                        singleLine = true, modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        detail, { detail = it }, label = { Text("Descripción *") },
                        isError = attemptedSubmit && detail.trim().isEmpty(),
                        supportingText = {
                            if (attemptedSubmit && detail.trim().isEmpty()) Text("La descripción es obligatoria")
                        },
                        modifier = Modifier.fillMaxWidth()
                    )
                    Row(
                        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        pqrsCategories.forEach { value ->
                            FilterChip(
                                selected = category == value,
                                onClick = { category = value },
                                label = { Text(value) }
                            )
                        }
                    }
                    DatePickerField("Fecha del incidente", incidentDate, { incidentDate = it })
                    TimePickerField("Hora del incidente", incidentTime, { incidentTime = it })
                    MediaAttachmentPicker(mediaName, { url, type, name ->
                        mediaUrl = url
                        mediaType = type
                        mediaName = name
                    }, { message = it })
                    Button(
                        enabled = !sending,
                        onClick = {
                            attemptedSubmit = true
                            if (subject.trim().isEmpty() || detail.trim().isEmpty() ||
                                (Session.isAdmin && selectedResident == null)
                            ) {
                                message = "Asunto, descripción y residente son obligatorios."
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
                                        message = "PQRS enviada."
                                        load()
                                    } else {
                                        message = mensajeDeError(response.code(), response.errorBody()?.string())
                                    }
                                } catch (exception: Exception) {
                                    message = "No se pudo enviar la PQRS: ${exception.message}"
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

        if (Session.isAdmin && selectedVisibleCount > 0) {
            Button(
                onClick = { batchDialog = true },
                modifier = Modifier.fillMaxWidth()
            ) { Text("Responder seleccionadas ($selectedVisibleCount)") }
        }

        if (loading) {
            CircularProgressIndicator()
        } else {
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
                            onMessage = { text ->
                                message = text
                            }
                        )
                    }
                }
                if (visibleItems.isEmpty()) {
                    item { Text("No hay PQRS que coincidan con esos filtros.", Modifier.padding(16.dp)) }
                }
            }
        }
        TextButton(onClick = { navController.popBackStack() }) { Text("Volver") }
    }

    if (batchDialog) {
        AlertDialog(
            onDismissRequest = { batchDialog = false },
            title = { Text("Respuesta por lotes") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Vas a responder $selectedVisibleCount PQRS de la categoría seleccionada.")
                    OutlinedTextField(
                        value = batchMessage,
                        onValueChange = { batchMessage = it },
                        label = { Text("Respuesta *") },
                        isError = batchMessage.isNotEmpty() && batchMessage.isBlank(),
                        modifier = Modifier.fillMaxWidth()
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        listOf("en_proceso", "resuelta").forEach { value ->
                            FilterChip(
                                selected = batchStatus == value,
                                onClick = { batchStatus = value },
                                label = { Text(value.replace('_', ' ')) }
                            )
                        }
                    }
                    MediaAttachmentPicker(batchMediaName, { url, type, name ->
                        batchMediaUrl = url
                        batchMediaType = type
                        batchMediaName = name
                    }, { message = it })
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
                                        visibleItems.filter { it.id in selectedIds }.map { it.id },
                                        batchStatus,
                                        batchMessage.trim(),
                                        batchMediaUrl,
                                        batchMediaType
                                    )
                                )
                                if (response.isSuccessful) {
                                    message = response.body()?.message ?: "PQRS actualizadas."
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
                                }
                            } catch (exception: Exception) {
                                message = "No se pudieron responder las PQRS: ${exception.message}"
                            } finally {
                                sending = false
                            }
                        }
                    }
                ) { Text(if (sending) "Enviando..." else "Enviar a $selectedVisibleCount") }
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
    onMessage: (String) -> Unit
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
        Column(Modifier.fillMaxWidth().animateContentSize().padding(12.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Row(Modifier.weight(1f).clickable(onClick = onToggleExpanded)) {
                    Text(pqrs.subject, style = MaterialTheme.typography.titleMedium)
                }
                if (Session.isAdmin) {
                    Checkbox(checked = selected, onCheckedChange = onToggleSelected)
                }
                DomuxStatusBadge(pqrs.status.replace('_', ' '), tone)
            }
            Text("${pqrs.residentName ?: "Residente"} · ${pqrs.apartment.orEmpty()}", style = MaterialTheme.typography.bodySmall)
            if (pqrs.createdByAdministration) {
                Text("Creada por administración", style = MaterialTheme.typography.labelSmall)
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
                                label = { Text(state.replace('_', ' ')) }
                            )
                        }
                    }
                    MediaAttachmentPicker(responseMediaName, { url, type, name ->
                        responseMediaUrl = url
                        responseMediaType = type
                        responseMediaName = name
                    }, onMessage)
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
                                    onMessage(
                                        if (result.isSuccessful) "PQRS actualizada."
                                        else mensajeDeError(result.code(), result.errorBody()?.string())
                                    )
                                    if (result.isSuccessful) onRefresh()
                                } catch (exception: Exception) {
                                    onMessage("No se pudo actualizar la PQRS: ${exception.message}")
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
                    }, onMessage)
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
                                    onMessage(
                                        if (result.isSuccessful) "Mensaje enviado."
                                        else mensajeDeError(result.code(), result.errorBody()?.string())
                                    )
                                    if (result.isSuccessful) onRefresh()
                                } catch (exception: Exception) {
                                    onMessage("No se pudo enviar el mensaje: ${exception.message}")
                                } finally {
                                    busy = false
                                }
                            }
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
                                busy = true
                                scope.launch {
                                    try {
                                        val result = RetrofitClient.api.ratePqrs(
                                            Session.bearer(),
                                            pqrs.id,
                                            RatePqrsRequest(rating, ratingComment.trim().ifEmpty { null })
                                        )
                                        onMessage(
                                            if (result.isSuccessful) "Calificación guardada."
                                            else mensajeDeError(result.code(), result.errorBody()?.string())
                                        )
                                        if (result.isSuccessful) onRefresh()
                                    } catch (exception: Exception) {
                                        onMessage("No se pudo guardar la calificación: ${exception.message}")
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
