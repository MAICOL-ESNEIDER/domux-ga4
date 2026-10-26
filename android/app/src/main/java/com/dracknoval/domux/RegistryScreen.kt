package com.dracknoval.domux

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.dracknoval.domux.data.PackageItem
import com.dracknoval.domux.data.RegisterPackageRequest
import com.dracknoval.domux.data.RegisterVisitRequest
import com.dracknoval.domux.data.ResidentSummary
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.Visit
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.launch

private val packageFilters = listOf(
    "Todos" to null,
    "Por llegar" to "por_llegar",
    "En portería" to "pendiente",
    "Entregados" to "entregado"
)

@Composable
fun RegistryScreen(navController: NavController) {
    var packages by remember { mutableStateOf<List<PackageItem>>(emptyList()) }
    var visits by remember { mutableStateOf<List<Visit>>(emptyList()) }
    var residents by remember { mutableStateOf<List<ResidentSummary>>(emptyList()) }
    var selectedResident by remember { mutableStateOf<ResidentSummary?>(null) }
    var loading by remember { mutableStateOf(true) }
    var message by remember { mutableStateOf("") }
    var search by remember { mutableStateOf("") }
    var statusFilter by remember { mutableStateOf<String?>(null) }
    var description by remember { mutableStateOf("") }
    var packageDate by remember { mutableStateOf("") }
    var packageTime by remember { mutableStateOf("") }
    var mediaUrl by remember { mutableStateOf<String?>(null) }
    var mediaType by remember { mutableStateOf<String?>(null) }
    var mediaName by remember { mutableStateOf<String?>(null) }
    var visitorName by remember { mutableStateOf("") }
    var visitorDocument by remember { mutableStateOf("") }
    var visitorType by remember { mutableStateOf("visitante") }
    var confirmation by remember { mutableStateOf<Pair<String, () -> Unit>?>(null) }
    var attemptedPackage by remember { mutableStateOf(false) }
    var attemptedVisit by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val canRegister = Session.isGuard || Session.isAdmin

    suspend fun load() {
        loading = true
        try {
            val packageResponse = RetrofitClient.api.getPackages(
                Session.bearer(), statusFilter, search.trim().ifEmpty { null }
            )
            if (packageResponse.isSuccessful) packages = packageResponse.body()?.packages.orEmpty()
            else message = mensajeDeError(packageResponse.code(), packageResponse.errorBody()?.string())

            val visitsResponse = RetrofitClient.api.getVisits(Session.bearer())
            if (visitsResponse.isSuccessful) visits = visitsResponse.body()?.visits.orEmpty()
            else message = mensajeDeError(visitsResponse.code(), visitsResponse.errorBody()?.string())

            if (canRegister && residents.isEmpty()) {
                val residentResponse = RetrofitClient.api.getResidents(Session.bearer())
                if (residentResponse.isSuccessful) {
                    residents = residentResponse.body()?.residents.orEmpty()
                    if (selectedResident == null) selectedResident = residents.firstOrNull()
                } else message = mensajeDeError(residentResponse.code(), residentResponse.errorBody()?.string())
            }
        } catch (exception: Exception) {
            message = "No se pudieron cargar los registros: ${exception.message}"
        } finally {
            loading = false
        }
    }

    LaunchedEffect(statusFilter, search) { load() }

    Column(Modifier.fillMaxSize().padding(18.dp)) {
        Text(
            when {
                Session.isResident -> "Mis paquetes y visitas"
                Session.isGuard -> "Registro de portería"
                else -> "Paquetes y visitas"
            },
            fontSize = 23.sp,
            color = MaterialTheme.colorScheme.primary
        )
        if (message.isNotBlank()) Text(message, color = MaterialTheme.colorScheme.error)

        OutlinedTextField(
            search, { search = it }, label = { Text("Buscar residente, apartamento o paquete") },
            singleLine = true, modifier = Modifier.fillMaxWidth()
        )
        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            packageFilters.forEach { (label, value) ->
                FilterChip(selected = statusFilter == value, onClick = { statusFilter = value }, label = { Text(label) })
            }
        }

        if (canRegister) {
            DomuxCard(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                Column(Modifier.padding(12.dp)) {
                    Text("Registrar paquete", style = MaterialTheme.typography.titleMedium)
                    Row(
                        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        residents.forEach { resident ->
                            FilterChip(
                                selected = selectedResident?.id == resident.id,
                                onClick = { selectedResident = resident },
                                label = { Text("${resident.name} · ${resident.apartment.orEmpty()}") }
                            )
                        }
                    }
                    OutlinedTextField(
                        description, { description = it }, label = { Text("Descripción *") },
                        isError = attemptedPackage && description.trim().isEmpty(),
                        supportingText = { if (attemptedPackage && description.trim().isEmpty()) Text("La descripción es obligatoria") },
                        singleLine = true, modifier = Modifier.fillMaxWidth()
                    )
                    DatePickerField("Fecha del paquete", packageDate, { packageDate = it })
                    TimePickerField("Hora del paquete", packageTime, { packageTime = it })
                    MediaAttachmentPicker(mediaName, { url, type, name ->
                        mediaUrl = url; mediaType = type; mediaName = name
                    }, { message = it })
                    Button(onClick = {
                        attemptedPackage = true
                        if (selectedResident == null || description.trim().isEmpty()) {
                            message = "Selecciona residente y escribe la descripción del paquete."
                            return@Button
                        }
                        confirmation = "¿Estás seguro de guardar este paquete?" to {
                            scope.launch {
                                try {
                                    val response = RetrofitClient.api.registerPackage(
                                        Session.bearer(),
                                        RegisterPackageRequest(
                                            selectedResident!!.id, description.trim(),
                                            mediaUrl, mediaType,
                                            packageDate.ifBlank { null }, packageTime.ifBlank { null }
                                        )
                                    )
                                    message = if (response.isSuccessful) {
                                        description = ""; mediaUrl = null; mediaType = null; mediaName = null
                                        packageDate = ""; packageTime = ""
                                        attemptedPackage = false
                                        "Paquete registrado."
                                    } else mensajeDeError(response.code(), response.errorBody()?.string())
                                    if (response.isSuccessful) load()
                                } catch (exception: Exception) {
                                    message = "No se pudo registrar el paquete: ${exception.message}"
                                }
                            }
                        }
                    }, modifier = Modifier.fillMaxWidth()) { Text("Registrar paquete") }
                }
            }

            DomuxCard(Modifier.fillMaxWidth().padding(vertical = 5.dp)) {
                Column(Modifier.padding(12.dp)) {
                    Text("Registrar visita", style = MaterialTheme.typography.titleMedium)
                    Row(
                        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        residents.forEach { resident ->
                            FilterChip(
                                selected = selectedResident?.id == resident.id,
                                onClick = { selectedResident = resident },
                                label = { Text("${resident.name} · ${resident.apartment.orEmpty()}") }
                            )
                        }
                    }
                    OutlinedTextField(
                        visitorName, { visitorName = it }, label = { Text("Nombre del visitante *") },
                        isError = attemptedVisit && visitorName.trim().isEmpty(),
                        supportingText = { if (attemptedVisit && visitorName.trim().isEmpty()) Text("El nombre es obligatorio") },
                        singleLine = true, modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        visitorDocument, { visitorDocument = it }, label = { Text("Documento (opcional)") },
                        singleLine = true, modifier = Modifier.fillMaxWidth()
                    )
                    Row {
                        listOf("visitante", "domiciliario", "contratista").forEach { value ->
                            FilterChip(
                                selected = visitorType == value,
                                onClick = { visitorType = value },
                                label = { Text(value.replaceFirstChar(Char::uppercase)) }
                            )
                        }
                    }
                    Button(onClick = {
                        attemptedVisit = true
                        if (selectedResident == null || visitorName.trim().isEmpty()) {
                            message = "Selecciona residente y escribe el nombre del visitante."
                            return@Button
                        }
                        scope.launch {
                            try {
                                val response = RetrofitClient.api.registerVisit(
                                    Session.bearer(),
                                    RegisterVisitRequest(
                                        selectedResident!!.id, visitorName.trim(), visitorType,
                                        visitorDocument.trim().ifEmpty { null }
                                    )
                                )
                                message = if (response.isSuccessful) {
                                    visitorName = ""; visitorDocument = ""
                                    attemptedVisit = false
                                    "Visita registrada."
                                } else mensajeDeError(response.code(), response.errorBody()?.string())
                                if (response.isSuccessful) load()
                            } catch (exception: Exception) {
                                message = "No se pudo registrar la visita: ${exception.message}"
                            }
                        }
                    }, modifier = Modifier.fillMaxWidth()) { Text("Registrar visita") }
                }
            }
        }

        if (loading) CircularProgressIndicator()
        else LazyColumn(Modifier.weight(1f)) {
            item { Text("Paquetes", style = MaterialTheme.typography.titleLarge) }
            if (packages.isEmpty()) item { Text("No hay paquetes para estos filtros.") }
            items(packages, key = { "package-${it.id}" }) { item ->
                DomuxCard(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                    Column(Modifier.padding(12.dp)) {
                        Text(item.description.orEmpty(), style = MaterialTheme.typography.titleMedium)
                        Text("Para: ${item.residentName.orEmpty()} · ${item.apartment.orEmpty()}")
                        Text("Estado: ${when (item.status) {
                            "por_llegar" -> "Por llegar"
                            "pendiente" -> "En portería"
                            else -> "Entregado"
                        }} · ${item.createdAt.orEmpty()}")
                        if (item.eventDate != null || item.eventTime != null) {
                            Text("Registro: ${item.eventDate.orEmpty()} ${item.eventTime.orEmpty()}")
                        }
                        MediaAttachmentChip(item.mediaUrl, item.mediaType)
                        if (canRegister && item.status != "entregado") {
                            TextButton(onClick = {
                                confirmation = "¿Estás seguro de marcar el paquete como entregado?" to {
                                    scope.launch {
                                        try {
                                            val response = RetrofitClient.api.deliverPackage(Session.bearer(), item.id)
                                            message = if (response.isSuccessful) "Paquete entregado."
                                            else mensajeDeError(response.code(), response.errorBody()?.string())
                                            if (response.isSuccessful) load()
                                        } catch (exception: Exception) {
                                            message = "No se pudo entregar el paquete: ${exception.message}"
                                        }
                                    }
                                }
                            }) { Text("Marcar entregado") }
                        }
                    }
                }
            }
            item { Text("Visitas", style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(top = 12.dp)) }
            if (visits.isEmpty()) item { Text("No hay visitas registradas.") }
            items(visits, key = { "visit-${it.id}" }) { item ->
                DomuxCard(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                    Column(Modifier.padding(12.dp)) {
                        Text(item.visitorName, style = MaterialTheme.typography.titleMedium)
                        Text("${item.type} · ${item.createdAt.orEmpty()}")
                        Text("Para: ${item.residentName.orEmpty()} · ${item.apartment.orEmpty()}")
                    }
                }
            }
        }
        TextButton(onClick = { navController.popBackStack() }) { Text("Volver") }
    }

    confirmation?.let { (prompt, action) ->
        AlertDialog(
            onDismissRequest = { confirmation = null },
            title = { Text("Confirmar acción") },
            text = { Text(prompt) },
            confirmButton = {
                TextButton(onClick = { confirmation = null; action() }) { Text("Confirmar") }
            },
            dismissButton = { TextButton(onClick = { confirmation = null }) { Text("Cancelar") } }
        )
    }
}
