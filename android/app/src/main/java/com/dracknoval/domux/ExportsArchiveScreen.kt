package com.dracknoval.domux

import android.content.Intent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.dracknoval.domux.data.PackageItem
import com.dracknoval.domux.data.Pqrs
import com.dracknoval.domux.data.Reservation
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

@Composable
fun ExportsArchiveScreen(navController: NavController) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var selectedTab by remember { mutableStateOf(0) }
    var archiveCategory by remember { mutableStateOf("pqrs") } // pqrs, reservas, paquetes
    
    var message by remember { mutableStateOf("") }
    var isError by remember { mutableStateOf<Boolean?>(null) }
    var loading by remember { mutableStateOf(false) }
    
    var legalPqrsBusy by remember { mutableStateOf(false) }
    var legalReservationsBusy by remember { mutableStateOf(false) }
    var lastSavedUri by remember { mutableStateOf<android.net.Uri?>(null) }
    var lastSavedMime by remember { mutableStateOf<String?>(null) }

    var archivedPqrs by remember { mutableStateOf<List<Pqrs>>(emptyList()) }
    var archivedReservations by remember { mutableStateOf<List<Reservation>>(emptyList()) }
    var archivedPackages by remember { mutableStateOf<List<PackageItem>>(emptyList()) }

    var confirmationDialog by remember { mutableStateOf<Pair<String, () -> Unit>?>(null) }

    suspend fun loadArchived() {
        if (!Session.isAdmin) return
        loading = true
        try {
            when (archiveCategory) {
                "pqrs" -> {
                    val response = RetrofitClient.api.getPqrs(
                        auth = Session.bearer(),
                        includeArchived = "true"
                    )
                    if (response.isSuccessful) {
                        archivedPqrs = response.body()?.pqrs?.filter { it.isArchived || !it.archivedAt.isNullOrBlank() } ?: emptyList()
                    } else {
                        message = mensajeDeError(response.code(), response.errorBody()?.string())
                        isError = true
                    }
                }
                "reservas" -> {
                    val response = RetrofitClient.api.getReservations(
                        auth = Session.bearer(),
                        includeArchived = "true"
                    )
                    if (response.isSuccessful) {
                        archivedReservations = response.body()?.reservations?.filter { it.isArchived || !it.archivedAt.isNullOrBlank() } ?: emptyList()
                    } else {
                        message = mensajeDeError(response.code(), response.errorBody()?.string())
                        isError = true
                    }
                }
                "paquetes" -> {
                    val response = RetrofitClient.api.getPackages(
                        auth = Session.bearer(),
                        status = "papelera"
                    )
                    if (response.isSuccessful) {
                        archivedPackages = response.body()?.packages ?: emptyList()
                    } else {
                        message = mensajeDeError(response.code(), response.errorBody()?.string())
                        isError = true
                    }
                }
            }
        } catch (e: Exception) {
            if (e !is CancellationException) {
                message = "Error de conexión: ${e.message}"
                isError = true
            }
        } finally {
            loading = false
        }
    }

    LaunchedEffect(selectedTab, archiveCategory) {
        if (selectedTab == 1) {
            loadArchived()
        }
    }

    DomuxScreenScaffold(title = "Respaldo y Archivo", navController = navController) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            DomuxSectionTabs(
                tabs = listOf("Exportación Excel", "Archivo histórico"),
                selectedIndex = selectedTab,
                onSelect = { selectedTab = it; message = ""; isError = null; lastSavedUri = null }
            )
            
            if (message.isNotBlank()) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    DomuxFeedbackBanner(message, isError) { message = ""; isError = null; lastSavedUri = null }
                    if (lastSavedUri != null && isError == false) {
                        Button(
                            onClick = {
                                val intent = Intent(Intent.ACTION_VIEW).apply {
                                    setDataAndType(lastSavedUri, lastSavedMime ?: "*/*")
                                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                                }
                                try {
                                    context.startActivity(Intent.createChooser(intent, "Abrir archivo Excel"))
                                } catch (e: Exception) {
                                    message = "No hay aplicación disponible para abrir archivos Excel."
                                    isError = true
                                }
                            }
                        ) {
                            Text("Abrir archivo Excel")
                        }
                    }
                }
            }

            if (selectedTab == 0) {
                // Pestaña 1: Exportación Excel
                LazyColumn(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    item {
                        DomuxCard(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                Text("Respaldo consolidado (Excel)", style = MaterialTheme.typography.titleMedium)
                                Text("Descarga el libro completo con 4 hojas (PQRS, Historial de chats, Reservas y Logs de auditoría) sin modificar ningún registro activo.")
                                
                                Button(
                                    enabled = !legalPqrsBusy,
                                    onClick = {
                                        legalPqrsBusy = true
                                        message = ""
                                        isError = null
                                        lastSavedUri = null
                                        scope.launch {
                                            try {
                                                val response = RetrofitClient.api.exportLegalReport(Session.bearer())
                                                if (response.isSuccessful) {
                                                    val file = response.body() ?: error("Reporte vacío.")
                                                    val cleanFileName = file.fileName.replace("Reporte_Legal", "Respaldo_Historico", ignoreCase = true)
                                                    val mime = file.mimeType ?: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                                    val base64Bytes = android.util.Base64.decode(file.base64, android.util.Base64.DEFAULT)
                                                    val uri = saveBytesToDownloads(context, cleanFileName, mime, base64Bytes)
                                                    if (uri != null) {
                                                        message = "Reporte guardado exitosamente en Descargas/$cleanFileName."
                                                        isError = false
                                                        lastSavedUri = uri
                                                        lastSavedMime = mime
                                                    } else {
                                                        message = "No se pudo guardar el archivo en Descargas."
                                                        isError = true
                                                    }
                                                } else {
                                                    message = mensajeDeError(response.code(), response.errorBody()?.string())
                                                    isError = true
                                                }
                                            } catch (e: Exception) {
                                                if (e !is CancellationException) {
                                                    message = "Error de descarga: ${e.message}"
                                                    isError = true
                                                }
                                            } finally {
                                                legalPqrsBusy = false
                                            }
                                        }
                                    },
                                    modifier = Modifier.fillMaxWidth()
                                ) { Text(if (legalPqrsBusy) "Descargando..." else "Descargar respaldo completo (Excel)") }
                            }
                        }
                    }

                    item {
                        DomuxCard(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                Text("Limpiar bandeja de PQRS resueltas", style = MaterialTheme.typography.titleMedium)
                                Text("Mueve las PQRS en estado Resuelta al Archivo histórico (no se eliminan por reglas operativas e integridad de la información) y descarga copia Excel.")
                                
                                OutlinedButton(
                                    enabled = !legalPqrsBusy,
                                    onClick = {
                                        confirmationDialog = "¿Deseas archivar todas las PQRS resueltas? Se moverán al archivo histórico." to {
                                            legalPqrsBusy = true
                                            scope.launch {
                                                try {
                                                    val response = RetrofitClient.api.archiveHistory(Session.bearer())
                                                    if (response.isSuccessful) {
                                                        val file = response.body() ?: error("Archivo vacío.")
                                                        val cleanFileName = file.fileName.replace("Reporte_Legal", "Respaldo_Historico", ignoreCase = true)
                                                        val mime = file.mimeType ?: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                                        val base64Bytes = android.util.Base64.decode(file.base64, android.util.Base64.DEFAULT)
                                                        val uri = saveBytesToDownloads(context, cleanFileName, mime, base64Bytes)
                                                        if (uri != null) {
                                                            message = "PQRS resueltas archivadas. Respaldo guardado en Descargas/$cleanFileName."
                                                            isError = false
                                                            lastSavedUri = uri
                                                            lastSavedMime = mime
                                                        } else {
                                                            message = "PQRS archivadas, pero no se pudo guardar el archivo local."
                                                            isError = false
                                                        }
                                                    } else {
                                                        message = mensajeDeError(response.code(), response.errorBody()?.string())
                                                        isError = true
                                                    }
                                                } catch (e: Exception) {
                                                    if (e !is CancellationException) {
                                                        message = "Error al archivar: ${e.message}"
                                                        isError = true
                                                    }
                                                } finally {
                                                    legalPqrsBusy = false
                                                }
                                            }
                                        }
                                    },
                                    modifier = Modifier.fillMaxWidth()
                                ) { Text("Archivar PQRS resueltas") }
                            }
                        }
                    }

                    item {
                        DomuxCard(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                Text("Limpiar calendario de Reservas finalizadas", style = MaterialTheme.typography.titleMedium)
                                Text("Mueve las reservas finalizadas, canceladas o rechazadas al Archivo histórico (sin borrar datos) y descarga copia Excel.")
                                
                                OutlinedButton(
                                    enabled = !legalReservationsBusy,
                                    onClick = {
                                        confirmationDialog = "¿Deseas archivar las reservas finalizadas? Se moverán al archivo histórico." to {
                                            legalReservationsBusy = true
                                            scope.launch {
                                                try {
                                                    val response = RetrofitClient.api.archiveHistory(Session.bearer())
                                                    if (response.isSuccessful) {
                                                        val file = response.body() ?: error("Archivo vacío.")
                                                        val cleanFileName = file.fileName.replace("Reporte_Legal", "Respaldo_Historico", ignoreCase = true)
                                                        val mime = file.mimeType ?: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                                        val base64Bytes = android.util.Base64.decode(file.base64, android.util.Base64.DEFAULT)
                                                        val uri = saveBytesToDownloads(context, cleanFileName, mime, base64Bytes)
                                                        if (uri != null) {
                                                            message = "Reservas archivadas. Respaldo guardado en Descargas/$cleanFileName."
                                                            isError = false
                                                            lastSavedUri = uri
                                                            lastSavedMime = mime
                                                        } else {
                                                            message = "Reservas archivadas, pero no se pudo guardar el archivo local."
                                                            isError = false
                                                        }
                                                    } else {
                                                        message = mensajeDeError(response.code(), response.errorBody()?.string())
                                                        isError = true
                                                    }
                                                } catch (e: Exception) {
                                                    if (e !is CancellationException) {
                                                        message = "Error al archivar: ${e.message}"
                                                        isError = true
                                                    }
                                                } finally {
                                                    legalReservationsBusy = false
                                                }
                                            }
                                        }
                                    },
                                    modifier = Modifier.fillMaxWidth()
                                ) { Text("Archivar reservas finalizadas") }
                            }
                        }
                    }
                }
            } else {
                // Pestaña 2: Archivo histórico
                Row(
                    modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    val pqrsCount = if (archiveCategory == "pqrs" && !loading) " (${archivedPqrs.size})" else ""
                    val resCount = if (archiveCategory == "reservas" && !loading) " (${archivedReservations.size})" else ""
                    val pkgCount = if (archiveCategory == "paquetes" && !loading) " (${archivedPackages.size})" else ""
                    
                    FilterChip(
                        selected = archiveCategory == "pqrs",
                        onClick = { archiveCategory = "pqrs" },
                        label = { Text("PQRS$pqrsCount", maxLines = 1, softWrap = false) }
                    )
                    FilterChip(
                        selected = archiveCategory == "reservas",
                        onClick = { archiveCategory = "reservas" },
                        label = { Text("Reservas$resCount", maxLines = 1, softWrap = false) }
                    )
                    FilterChip(
                        selected = archiveCategory == "paquetes",
                        onClick = { archiveCategory = "paquetes" },
                        label = { Text("Paquetes$pkgCount", maxLines = 1, softWrap = false) }
                    )
                }

                if (loading) {
                    LinearProgressIndicator(Modifier.fillMaxWidth())
                } else {
                    LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.weight(1f)) {
                        when (archiveCategory) {
                            "pqrs" -> {
                                if (archivedPqrs.isEmpty()) {
                                    item {
                                        Box(modifier = Modifier.fillMaxWidth().padding(32.dp), contentAlignment = androidx.compose.ui.Alignment.Center) {
                                            Text("No hay PQRS archivadas", color = androidx.compose.ui.graphics.Color(0xFF94A3B8))
                                        }
                                    }
                                } else {
                                    items(archivedPqrs, key = { it.id }) { pqrs ->
                                        DomuxCard(Modifier.fillMaxWidth()) {
                                            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                                Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                                                    Text(pqrs.subject, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                                                    Surface(color = androidx.compose.ui.graphics.Color(0xFF1E3A8A), shape = androidx.compose.foundation.shape.RoundedCornerShape(8.dp)) {
                                                        Text("Archivada", modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp), style = MaterialTheme.typography.labelSmall, color = androidx.compose.ui.graphics.Color(0xFF93C5FD))
                                                    }
                                                }
                                                Text("Estado real: ${pqrs.status.toDomuxDisplayLabel()}", fontWeight = androidx.compose.ui.text.font.FontWeight.Medium)
                                                Text("Radicado: ${pqrs.id}")
                                                Text("Residente: ${pqrs.residentName ?: "—"}")
                                                Text("Fecha: ${pqrs.createdAt}")
                                                pqrs.archivedAt?.let { Text("Archivada el: $it", style = MaterialTheme.typography.bodySmall, color = androidx.compose.ui.graphics.Color(0xFF94A3B8)) }
                                            }
                                        }
                                    }
                                }
                            }
                            "reservas" -> {
                                if (archivedReservations.isEmpty()) {
                                    item {
                                        Box(modifier = Modifier.fillMaxWidth().padding(32.dp), contentAlignment = androidx.compose.ui.Alignment.Center) {
                                            Text("No hay reservas archivadas", color = androidx.compose.ui.graphics.Color(0xFF94A3B8))
                                        }
                                    }
                                } else {
                                    items(archivedReservations, key = { it.id }) { res ->
                                        DomuxCard(Modifier.fillMaxWidth()) {
                                            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                                Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                                                    Text("Zona: ${res.commonAreaName}", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                                                    Surface(color = androidx.compose.ui.graphics.Color(0xFF1E3A8A), shape = androidx.compose.foundation.shape.RoundedCornerShape(8.dp)) {
                                                        Text("Archivada", modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp), style = MaterialTheme.typography.labelSmall, color = androidx.compose.ui.graphics.Color(0xFF93C5FD))
                                                    }
                                                }
                                                Text("Estado real: ${res.status.toDomuxDisplayLabel()}", fontWeight = androidx.compose.ui.text.font.FontWeight.Medium)
                                                Text("Residente: ${res.residentName ?: "—"}")
                                                Text("Fecha del evento: ${res.date}")
                                                res.archivedAt?.let { Text("Archivada el: $it", style = MaterialTheme.typography.bodySmall, color = androidx.compose.ui.graphics.Color(0xFF94A3B8)) }
                                            }
                                        }
                                    }
                                }
                            }
                            "paquetes" -> {
                                if (archivedPackages.isEmpty()) {
                                    item {
                                        Box(modifier = Modifier.fillMaxWidth().padding(32.dp), contentAlignment = androidx.compose.ui.Alignment.Center) {
                                            Text("No hay paquetes archivados", color = androidx.compose.ui.graphics.Color(0xFF94A3B8))
                                        }
                                    }
                                } else {
                                    items(archivedPackages, key = { it.id }) { pkg ->
                                        DomuxCard(Modifier.fillMaxWidth()) {
                                            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                                Text(pkg.description ?: "Paquete", style = MaterialTheme.typography.titleMedium)
                                                Text("Residente: ${pkg.residentName ?: "—"}")
                                                Text("Entregado a: ${pkg.deliveredTo ?: "—"}")
                                                Text("Fecha registro: ${pkg.createdAt}")
                                                Spacer(Modifier.height(8.dp))
                                                OutlinedButton(onClick = {
                                                    confirmationDialog = "¿Restaurar el paquete a la bandeja activa?" to {
                                                        scope.launch {
                                                            try {
                                                                val response = RetrofitClient.api.restorePackage(Session.bearer(), pkg.id)
                                                                if (response.isSuccessful) {
                                                                    message = "Paquete restaurado exitosamente."
                                                                    isError = false
                                                                    loadArchived()
                                                                } else {
                                                                    message = mensajeDeError(response.code(), response.errorBody()?.string())
                                                                    isError = true
                                                                }
                                                            } catch (e: Exception) {
                                                                if (e !is CancellationException) {
                                                                    message = "Error al restaurar: ${e.message}"
                                                                    isError = true
                                                                }
                                                            }
                                                        }
                                                    }
                                                }) {
                                                    Text("Restaurar")
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    confirmationDialog?.let { (prompt, action) ->
        DomuxConfirmDialog(
            title = "Confirmar acción",
            message = prompt,
            confirmLabel = "Confirmar",
            onConfirm = {
                confirmationDialog = null
                action()
            },
            onDismiss = { confirmationDialog = null }
        )
    }
}
