package com.dracknoval.domux

import androidx.compose.foundation.clickable
import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.dracknoval.domux.data.CreatePqrsRequest
import com.dracknoval.domux.data.Pqrs
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
fun PqrsScreen(navController: NavController) {
    var items by remember { mutableStateOf<List<Pqrs>>(emptyList()) }
    var residents by remember { mutableStateOf<List<ResidentSummary>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var message by remember { mutableStateOf("") }
    var search by remember { mutableStateOf("") }
    var statusFilter by remember { mutableStateOf<String?>(null) }
    var categoryFilter by remember { mutableStateOf<String?>(null) }
    var expandedId by remember { mutableStateOf<Int?>(null) }
    var subject by remember { mutableStateOf("") }
    var detail by remember { mutableStateOf("") }
    var category by remember { mutableStateOf(pqrsCategories.first()) }
    var incidentDate by remember { mutableStateOf("") }
    var incidentTime by remember { mutableStateOf("") }
    var mediaUrl by remember { mutableStateOf<String?>(null) }
    var mediaType by remember { mutableStateOf<String?>(null) }
    var mediaName by remember { mutableStateOf<String?>(null) }
    var selectedResident by remember { mutableStateOf<ResidentSummary?>(null) }
    var sending by remember { mutableStateOf(false) }
    var attemptedSubmit by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    suspend fun load() {
        loading = true
        try {
            val response = RetrofitClient.api.getPqrs(
                Session.bearer(), statusFilter, categoryFilter, search.trim().ifEmpty { null }
            )
            if (response.isSuccessful) items = response.body()?.pqrs.orEmpty()
            else message = mensajeDeError(response.code(), response.errorBody()?.string())
            if (Session.isAdmin && residents.isEmpty()) {
                val residentResponse = RetrofitClient.api.getResidents(Session.bearer())
                if (residentResponse.isSuccessful) {
                    residents = residentResponse.body()?.residents.orEmpty()
                    if (selectedResident == null) selectedResident = residents.firstOrNull()
                }
            }
        } catch (exception: Exception) {
            message = "No se pudieron cargar las PQRS: ${exception.message}"
        } finally {
            loading = false
        }
    }

    LaunchedEffect(statusFilter, categoryFilter, search) { load() }

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
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            pqrsStates.forEach { (label, value) ->
                FilterChip(
                    selected = statusFilter == value,
                    onClick = { statusFilter = value },
                    label = { Text(label) }
                )
            }
            Row(
                Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                listOf("Todas" to null).plus(pqrsCategories.map { it to it }).forEach { (label, value) ->
                    FilterChip(
                        selected = categoryFilter == value,
                        onClick = { categoryFilter = value },
                        label = { Text(label) }
                    )
                }
            }
        }

        if (Session.isResident || Session.isAdmin) {
            DomuxCard(Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
                Column(Modifier.padding(12.dp)) {
                    Text(if (Session.isAdmin) "Crear PQRS para un residente" else "Nueva PQRS", style = MaterialTheme.typography.titleMedium)
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
                        supportingText = { if (attemptedSubmit && subject.trim().isEmpty()) Text("El asunto es obligatorio") },
                        singleLine = true, modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        detail, { detail = it }, label = { Text("Descripción *") },
                        isError = attemptedSubmit && detail.trim().isEmpty(),
                        supportingText = { if (attemptedSubmit && detail.trim().isEmpty()) Text("La descripción es obligatoria") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
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
                        mediaUrl = url; mediaType = type; mediaName = name
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
                                        subject = ""; detail = ""; incidentDate = ""; incidentTime = ""
                                        mediaUrl = null; mediaType = null; mediaName = null
                                        attemptedSubmit = false
                                        message = "PQRS enviada."
                                        load()
                                    } else message = mensajeDeError(response.code(), response.errorBody()?.string())
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

        if (loading) CircularProgressIndicator()
        else LazyColumn(Modifier.weight(1f)) {
            items(items, key = { it.id }) { pqrs ->
                val expanded = expandedId == pqrs.id
                val badgeColor = when (pqrs.status) {
                    "resuelta" -> Color(0xFF22C55E)
                    "en_proceso" -> Color(0xFFF59E0B)
                    else -> Color(0xFFEF4444)
                }
                DomuxCard(Modifier.fillMaxWidth().padding(vertical = 5.dp)) {
                    Column(
                        Modifier.fillMaxWidth().clickable {
                            expandedId = if (expanded) null else pqrs.id
                        }.animateContentSize().padding(12.dp)
                    ) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(pqrs.category ?: "Petición", color = MaterialTheme.colorScheme.secondary)
                            Surface(color = badgeColor.copy(alpha = 0.18f), shape = MaterialTheme.shapes.small) {
                                Text(
                                    pqrs.status.replace('_', ' '),
                                    color = badgeColor,
                                    modifier = Modifier.padding(horizontal = 9.dp, vertical = 4.dp)
                                )
                            }
                        }
                        Text(pqrs.subject, style = MaterialTheme.typography.titleMedium)
                        Text(
                            "${pqrs.residentName ?: "Residente"} · ${pqrs.apartment.orEmpty()}",
                            style = MaterialTheme.typography.bodySmall
                        )
                        Text(pqrs.createdAt.orEmpty(), style = MaterialTheme.typography.bodySmall)
                        if (expanded) {
                            HorizontalDivider(Modifier.padding(vertical = 8.dp))
                            Text(pqrs.message)
                            if (pqrs.incidentDate != null || pqrs.incidentTime != null) {
                                Text("Incidente: ${pqrs.incidentDate.orEmpty()} ${pqrs.incidentTime.orEmpty()}")
                            }
                            MediaAttachmentChip(pqrs.mediaUrl, pqrs.mediaType)
                            if (!pqrs.adminResponse.isNullOrBlank()) Text("Respuesta: ${pqrs.adminResponse}")
                            if (Session.isAdmin) {
                                var responseText by remember(pqrs.id, pqrs.adminResponse) {
                                    mutableStateOf(pqrs.adminResponse.orEmpty())
                                }
                                var newStatus by remember(pqrs.id, pqrs.status) { mutableStateOf(pqrs.status) }
                                OutlinedTextField(
                                    responseText, { responseText = it },
                                    label = { Text("Respuesta administrativa *") },
                                    isError = responseText.isNotEmpty() && responseText.trim().isEmpty(),
                                    modifier = Modifier.fillMaxWidth()
                                )
                                Row {
                                    listOf("abierta", "en_proceso", "resuelta").forEach { state ->
                                        FilterChip(
                                            selected = newStatus == state,
                                            onClick = { newStatus = state },
                                            label = { Text(state.replace('_', ' ')) }
                                        )
                                    }
                                }
                                Button(
                                    onClick = {
                                        if (responseText.trim().isEmpty()) {
                                            message = "Escribe una respuesta antes de guardar."
                                            return@Button
                                        }
                                        scope.launch {
                                            try {
                                                val result = RetrofitClient.api.respondPqrs(
                                                    Session.bearer(), pqrs.id,
                                                    RespondPqrsRequest(newStatus, responseText.trim())
                                                )
                                                message = if (result.isSuccessful) "PQRS actualizada."
                                                else mensajeDeError(result.code(), result.errorBody()?.string())
                                                if (result.isSuccessful) load()
                                            } catch (exception: Exception) {
                                                message = "No se pudo actualizar la PQRS: ${exception.message}"
                                            }
                                        }
                                    }
                                ) { Text("Guardar respuesta") }
                            }
                        }
                    }
                }
            }
        }
        TextButton(onClick = { navController.popBackStack() }) { Text("Volver") }
    }
}
