package com.dracknoval.domux

import android.content.Intent
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.google.zxing.BarcodeFormat
import com.journeyapps.barcodescanner.BarcodeEncoder
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import com.dracknoval.domux.data.CreateVisitQrPassRequest
import com.dracknoval.domux.data.DeliverPackageRequest
import com.dracknoval.domux.data.PackageItem
import com.dracknoval.domux.data.QrVisitorEntryRequest
import com.dracknoval.domux.data.QrVisitorExitRequest
import com.dracknoval.domux.data.RegisterPackageRequest
import com.dracknoval.domux.data.RegisterVisitRequest
import com.dracknoval.domux.data.ResidentSummary
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.Visit
import com.dracknoval.domux.data.VisitDecisionRequest
import com.dracknoval.domux.data.VisitExitRequest
import com.dracknoval.domux.data.VisitQrInspectionResponse
import com.dracknoval.domux.data.VisitQrPass
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

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
    var residentSearch by remember { mutableStateOf("") }
    var residentsExpanded by remember { mutableStateOf(false) }
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
    var visitorConsent by remember { mutableStateOf(false) }
    var visitorPhotoUrl by remember { mutableStateOf<String?>(null) }
    var visitorPhotoType by remember { mutableStateOf<String?>(null) }
    var visitorPhotoName by remember { mutableStateOf<String?>(null) }
    var deliveryPackage by remember { mutableStateOf<PackageItem?>(null) }
    var receiverName by remember { mutableStateOf("") }
    var pendingExit by remember { mutableStateOf<Visit?>(null) }
    var qrPasses by remember { mutableStateOf<List<VisitQrPass>>(emptyList()) }
    var activeQrPass by remember { mutableStateOf<VisitQrPass?>(null) }
    var qrBitmap by remember { mutableStateOf<android.graphics.Bitmap?>(null) }
    var qrStartDate by remember { mutableStateOf(SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())) }
    var qrEndDate by remember { mutableStateOf(SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())) }
    var qrMaxPeople by remember { mutableStateOf("5") }
    var scannedQrToken by remember { mutableStateOf<String?>(null) }
    var qrInspection by remember { mutableStateOf<VisitQrInspectionResponse?>(null) }
    var qrVisitorName by remember { mutableStateOf("") }
    var pendingQrExit by remember { mutableStateOf<Visit?>(null) }
    var confirmation by remember { mutableStateOf<Pair<String, () -> Unit>?>(null) }
    var attemptedPackage by remember { mutableStateOf(false) }
    var attemptedVisit by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val canRegister = Session.isGuard || Session.isAdmin
    val context = LocalContext.current
    val scanner = rememberLauncherForActivityResult(ScanContract()) { result ->
        val raw = result.contents.orEmpty()
        val token = raw.removePrefix("DOMUX:").takeIf { raw.startsWith("DOMUX:") && it.isNotBlank() }
        if (token == null) {
            message = "El código leído no es un QR válido de DOMUX."
        } else {
            scannedQrToken = token
            scope.launch {
                try {
                    val response = RetrofitClient.api.inspectVisitQr(Session.bearer(), token)
                    if (response.isSuccessful) qrInspection = response.body()
                    else message = mensajeDeError(response.code(), response.errorBody()?.string())
                } catch (exception: Exception) {
                    message = "No se pudo consultar el QR: ${exception.message}"
                }
            }
        }
    }

    suspend fun loadResidents() {
        if (!canRegister) return
        if (residentSearch.isBlank()) {
            residents = emptyList()
            return
        }
        try {
            val residentResponse = RetrofitClient.api.getResidents(
                Session.bearer(), residentSearch.trim().ifEmpty { null }
            )
            if (residentResponse.isSuccessful) {
                residents = residentResponse.body()?.residents.orEmpty()
                if (selectedResident == null && residents.size == 1) selectedResident = residents.first()
            } else message = mensajeDeError(residentResponse.code(), residentResponse.errorBody()?.string())
        } catch (exception: Exception) {
            message = "No se pudieron buscar residentes: ${exception.message}"
        }
    }

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

            loadResidents()
            if (Session.isResident) {
                val qrResponse = RetrofitClient.api.getVisitQrPasses(Session.bearer())
                if (qrResponse.isSuccessful) qrPasses = qrResponse.body()?.qrPasses.orEmpty()
                else message = mensajeDeError(qrResponse.code(), qrResponse.errorBody()?.string())
            }
        } catch (exception: Exception) {
            message = "No se pudieron cargar los registros: ${exception.message}"
        } finally {
            loading = false
        }
    }

    LaunchedEffect(statusFilter, search) { load() }
    LaunchedEffect(residentSearch) {
        if (canRegister) {
            delay(300)
            loadResidents()
        }
    }

    LaunchedEffect(activeQrPass?.qrData) {
        qrBitmap = try {
            activeQrPass?.qrData?.let { BarcodeEncoder().encodeBitmap(it, BarcodeFormat.QR_CODE, 640, 640) }
        } catch (exception: Exception) {
            message = "No se pudo generar la imagen del QR: ${exception.message}"
            null
        }
    }

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
        TextButton(onClick = { scope.launch { load() } }) { Text("Actualizar registros") }
        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            packageFilters.forEach { (label, value) ->
                FilterChip(selected = statusFilter == value, onClick = { statusFilter = value }, label = { Text(label) })
            }
        }

        Column(
            Modifier.weight(0.48f).verticalScroll(rememberScrollState())
        ) {
        if (canRegister) {
            DomuxCard(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                Column(Modifier.padding(12.dp)) {
                    Text("Registrar paquete", style = MaterialTheme.typography.titleMedium)
                    ResidentPicker(
                        search = residentSearch,
                        residents = residents,
                        selected = selectedResident,
                        expanded = residentsExpanded,
                        onSearch = { residentSearch = it; selectedResident = null; residentsExpanded = true },
                        onExpanded = { residentsExpanded = it },
                        onSelect = { selectedResident = it; residentsExpanded = false }
                    )
                    selectedResident?.phone?.takeIf { it.isNotBlank() }?.let { phone ->
                        TextButton(onClick = {
                            context.startActivity(
                                Intent(Intent.ACTION_DIAL, Uri.parse("tel:${Uri.encode(phone)}"))
                            )
                        }) { Text("Llamar al residente · $phone") }
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
                    ResidentPicker(
                        search = residentSearch,
                        residents = residents,
                        selected = selectedResident,
                        expanded = residentsExpanded,
                        onSearch = { residentSearch = it; selectedResident = null; residentsExpanded = true },
                        onExpanded = { residentsExpanded = it },
                        onSelect = { selectedResident = it; residentsExpanded = false }
                    )
                    OutlinedTextField(
                        visitorName, { visitorName = it }, label = { Text("Nombre del visitante *") },
                        isError = attemptedVisit && visitorName.trim().isEmpty(),
                        supportingText = { if (attemptedVisit && visitorName.trim().isEmpty()) Text("El nombre es obligatorio") },
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
                    if (visitorType == "domiciliario") {
                        OutlinedTextField(
                            description, { description = it },
                            label = { Text("Detalles del pedido (opcional)") },
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                    Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                        Checkbox(checked = visitorConsent, onCheckedChange = {
                            visitorConsent = it
                            if (!it) {
                                visitorDocument = ""
                                visitorPhotoUrl = null
                                visitorPhotoType = null
                                visitorPhotoName = null
                            }
                        })
                        Text("El visitante autoriza guardar su documento o foto (opcional)")
                    }
                    if (visitorConsent) {
                        OutlinedTextField(
                            visitorDocument, { visitorDocument = it },
                            label = { Text("Documento (opcional)") },
                            singleLine = true, modifier = Modifier.fillMaxWidth()
                        )
                        MediaAttachmentPicker(visitorPhotoName, { url, type, name ->
                            visitorPhotoUrl = url
                            visitorPhotoType = type
                            visitorPhotoName = name
                        }, "image/*") { message = it }
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
                                        visitorDocument.trim().ifEmpty { null },
                                        visitorConsent,
                                        if (visitorConsent) visitorPhotoUrl else null,
                                        if (visitorConsent) visitorPhotoType else null,
                                        description.trim().ifEmpty { null }
                                    )
                                )
                                message = if (response.isSuccessful) {
                                    visitorName = ""; visitorDocument = ""
                                    visitorConsent = false
                                    visitorPhotoUrl = null; visitorPhotoType = null; visitorPhotoName = null
                                    description = ""
                                    attemptedVisit = false
                                    "Registro enviado. El residente recibirá una solicitud para autorizar el ingreso."
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

        if (Session.isResident) {
            DomuxCard(Modifier.fillMaxWidth().padding(vertical = 5.dp)) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Código QR para visitas", style = MaterialTheme.typography.titleMedium)
                    Text("Duración máxima: 30 días. Cada persona distinta consume un cupo.")
                    OutlinedTextField(
                        qrStartDate, { qrStartDate = it }, label = { Text("Válido desde (AAAA-MM-DD)") },
                        singleLine = true, modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        qrEndDate, { qrEndDate = it }, label = { Text("Válido hasta (AAAA-MM-DD)") },
                        singleLine = true, modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        qrMaxPeople, { qrMaxPeople = it.filter(Char::isDigit) },
                        label = { Text("Límite de personas") }, singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    Button(onClick = {
                        val limit = qrMaxPeople.toIntOrNull()
                        if (limit == null || limit < 1) {
                            message = "El límite de personas debe ser mayor que cero."
                        } else {
                            scope.launch {
                                try {
                                    val response = RetrofitClient.api.createVisitQrPass(
                                        Session.bearer(),
                                        CreateVisitQrPassRequest(qrStartDate, qrEndDate, limit)
                                    )
                                    if (response.isSuccessful) {
                                        activeQrPass = response.body()?.qrPass
                                        message = "Código QR creado."
                                        load()
                                    } else message = mensajeDeError(response.code(), response.errorBody()?.string())
                                } catch (exception: Exception) {
                                    message = "No se pudo crear el QR: ${exception.message}"
                                }
                            }
                        }
                    }, modifier = Modifier.fillMaxWidth()) { Text("Crear QR") }
                    qrPasses.forEach { pass ->
                        Row(
                            Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
                        ) {
                            TextButton(onClick = { activeQrPass = pass }) {
                                Text("${pass.validFrom} a ${pass.validUntil} · ${pass.registeredPeople}/${pass.maxPeople}")
                            }
                            if (!pass.revoked) TextButton(onClick = {
                                scope.launch {
                                    try {
                                        val response = RetrofitClient.api.revokeVisitQrPass(Session.bearer(), pass.id)
                                        message = if (response.isSuccessful) "QR revocado."
                                        else mensajeDeError(response.code(), response.errorBody()?.string())
                                        if (response.isSuccessful) {
                                            if (activeQrPass?.id == pass.id) activeQrPass = null
                                            load()
                                        }
                                    } catch (exception: Exception) {
                                        message = "No se pudo revocar el QR: ${exception.message}"
                                    }
                                }
                            }) { Text("Revocar") }
                        }
                    }
                    activeQrPass?.let { pass ->
                        Text("Código activo · ${pass.remainingPeople} cupos disponibles")
                        qrBitmap?.let { Image(
                            bitmap = it.asImageBitmap(),
                            contentDescription = "Código QR de visitas",
                            modifier = Modifier.size(220.dp).align(androidx.compose.ui.Alignment.CenterHorizontally)
                        ) }
                    }
                }
            }
        }

        if (Session.isGuard) {
            DomuxCard(Modifier.fillMaxWidth().padding(vertical = 5.dp)) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Ingreso y salida por QR", style = MaterialTheme.typography.titleMedium)
                    Button(onClick = {
                        scanner.launch(ScanOptions().setDesiredBarcodeFormats(ScanOptions.QR_CODE).setPrompt("Escanea el QR de visitas"))
                    }, modifier = Modifier.fillMaxWidth()) { Text("Escanear QR") }
                    qrInspection?.let { inspection ->
                        Text("${inspection.residentName.orEmpty()} · ${inspection.apartment.orEmpty()}")
                        Text(
                            "Registrados: ${inspection.qrPass?.registeredPeople ?: 0}/" +
                                "${inspection.qrPass?.maxPeople ?: 0} · " +
                                "Disponibles: ${inspection.qrPass?.remainingPeople ?: 0}"
                        )
                        if (!inspection.canRegister) {
                            Text("Este QR está vencido o revocado: solo se permite registrar la salida.")
                        }
                        OutlinedTextField(
                            qrVisitorName, { qrVisitorName = it },
                            label = { Text("Nombre del visitante que ingresa") },
                            enabled = inspection.canRegister,
                            singleLine = true, modifier = Modifier.fillMaxWidth()
                        )
                        Button(onClick = {
                            val token = scannedQrToken ?: return@Button
                            if (qrVisitorName.trim().isEmpty()) {
                                message = "Escribe el nombre del visitante."
                            } else scope.launch {
                                try {
                                    val response = RetrofitClient.api.enterVisitQr(
                                        Session.bearer(), token,
                                        QrVisitorEntryRequest(visitorName = qrVisitorName.trim())
                                    )
                                    message = if (response.isSuccessful) "Entrada por QR registrada."
                                    else mensajeDeError(response.code(), response.errorBody()?.string())
                                    if (response.isSuccessful) {
                                        qrVisitorName = ""
                                        val refreshed = RetrofitClient.api.inspectVisitQr(Session.bearer(), token)
                                        if (refreshed.isSuccessful) qrInspection = refreshed.body()
                                        load()
                                    }
                                } catch (exception: Exception) {
                                    message = "No se pudo registrar el ingreso QR: ${exception.message}"
                                }
                            }
                        }, enabled = inspection.canRegister, modifier = Modifier.fillMaxWidth()) {
                            Text("Registrar ingreso")
                        }
                        if (inspection.linkableVisits.orEmpty().isNotEmpty()) {
                            Text("O vincular un visitante ya registrado:")
                            inspection.linkableVisits.orEmpty().forEach { visit ->
                                TextButton(
                                    enabled = inspection.canRegister,
                                    onClick = {
                                        val token = scannedQrToken ?: return@TextButton
                                        scope.launch {
                                            try {
                                                val response = RetrofitClient.api.enterVisitQr(
                                                    Session.bearer(), token,
                                                    QrVisitorEntryRequest(visitId = visit.id)
                                                )
                                                message = if (response.isSuccessful) {
                                                    "${visit.visitorName} vinculado al QR."
                                                } else mensajeDeError(response.code(), response.errorBody()?.string())
                                                if (response.isSuccessful) {
                                                    val refreshed = RetrofitClient.api.inspectVisitQr(Session.bearer(), token)
                                                    if (refreshed.isSuccessful) qrInspection = refreshed.body()
                                                    load()
                                                }
                                            } catch (exception: Exception) {
                                                message = "No se pudo vincular al QR: ${exception.message}"
                                            }
                                        }
                                    }
                                ) { Text("${visit.visitorName} · vincular e ingresar") }
                            }
                        }
                        inspection.inside.orEmpty().forEach { visit ->
                            Row(
                                Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
                            ) {
                                Text("${visit.visitorName} está dentro")
                                TextButton(onClick = { pendingQrExit = visit }) { Text("Salida") }
                            }
                        }
                        inspection.registeredVisits.orEmpty()
                            .filter { it.exitedAt != null }
                            .forEach { visit ->
                                TextButton(
                                    enabled = inspection.canRegister,
                                    onClick = {
                                        val token = scannedQrToken ?: return@TextButton
                                        scope.launch {
                                            try {
                                                val response = RetrofitClient.api.enterVisitQr(
                                                    Session.bearer(), token,
                                                    QrVisitorEntryRequest(visitId = visit.id)
                                                )
                                                message = if (response.isSuccessful) {
                                                    "Reingreso de ${visit.visitorName} registrado."
                                                } else mensajeDeError(response.code(), response.errorBody()?.string())
                                                if (response.isSuccessful) {
                                                    val refreshed = RetrofitClient.api.inspectVisitQr(Session.bearer(), token)
                                                    if (refreshed.isSuccessful) qrInspection = refreshed.body()
                                                    load()
                                                }
                                            } catch (exception: Exception) {
                                                message = "No se pudo registrar el reingreso: ${exception.message}"
                                            }
                                        }
                                    }
                                ) { Text("Reingreso: ${visit.visitorName}") }
                            }
                    }
                }
            }
        }
        }

        if (loading) CircularProgressIndicator()
        else LazyColumn(Modifier.weight(0.52f)) {
            item { Text("Paquetes", style = MaterialTheme.typography.titleLarge) }
            if (packages.isEmpty()) item { Text("No hay paquetes para estos filtros.") }
            items(packages, key = { "package-${it.id}" }) { item ->
                DomuxCard(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                    Column(Modifier.padding(12.dp)) {
                        Text(item.description.orEmpty(), style = MaterialTheme.typography.titleMedium)
                        Text("Para: ${item.residentName.orEmpty()} · ${item.apartment.orEmpty()}")
                        val statusLabel = when (item.status) {
                            "por_llegar" -> "Por llegar"
                            "pendiente" -> "En portería"
                            else -> "Entregado"
                        }
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
                        ) {
                            Text(item.createdAt.orEmpty(), style = MaterialTheme.typography.bodySmall)
                            DomuxStatusBadge(
                                statusLabel,
                                if (item.status == "entregado") DomuxBadgeTone.SUCCESS
                                else DomuxBadgeTone.PROGRESS
                            )
                        }
                        if (item.eventDate != null || item.eventTime != null) {
                            Text("Registro: ${item.eventDate.orEmpty()} ${item.eventTime.orEmpty()}")
                        }
                        MediaAttachmentChip(item.mediaUrl, item.mediaType)
                        if (item.status == "entregado" && !item.deliveredTo.isNullOrBlank()) {
                            Text("Recibido por: ${item.deliveredTo}")
                        }
                        if (canRegister && item.status != "entregado") {
                            TextButton(onClick = {
                                deliveryPackage = item
                                receiverName = ""
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
                        Text("${item.type} · ${item.createdAt.orEmpty()} · ${item.approvalStatus}")
                        Text("Para: ${item.residentName.orEmpty()} · ${item.apartment.orEmpty()}")
                        if (item.mediaConsent && !item.visitorDocument.isNullOrBlank()) {
                            Text("Documento: ${item.visitorDocument}")
                        }
                        MediaAttachmentChip(item.visitorPhotoUrl, item.visitorPhotoType)
                        item.description?.takeIf { it.isNotBlank() }?.let { Text("Pedido: $it") }
                        item.enteredAt?.let { Text("Última entrada: $it") }
                        item.exitedAt?.let { Text("Última salida: $it") }
                        Text(
                            "Autorización: " + when (item.authorizationMethod) {
                                "llamada" -> "por llamada"
                                "qr" -> "por QR"
                                "app" -> "desde la app"
                                else -> "pendiente"
                            }
                        )
                        item.events.orEmpty().forEach { event ->
                            Text(
                                "${event.type} · ${event.createdAt.orEmpty()} · " +
                                    "${event.method} · ${event.actorName.orEmpty()}",
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                        if (Session.isResident && item.approvalStatus == "pendiente") {
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                TextButton(onClick = {
                                    scope.launch {
                                        try {
                                            val response = RetrofitClient.api.decideVisit(
                                                Session.bearer(), item.id, VisitDecisionRequest("aprobada")
                                            )
                                            message = if (response.isSuccessful) "Acceso autorizado."
                                            else mensajeDeError(response.code(), response.errorBody()?.string())
                                            if (response.isSuccessful) load()
                                        } catch (exception: Exception) {
                                            message = "No se pudo autorizar la visita: ${exception.message}"
                                        }
                                    }
                                }) { Text("Autorizar") }
                                TextButton(onClick = {
                                    scope.launch {
                                        try {
                                            val response = RetrofitClient.api.decideVisit(
                                                Session.bearer(), item.id, VisitDecisionRequest("rechazada")
                                            )
                                            message = if (response.isSuccessful) "Acceso rechazado."
                                            else mensajeDeError(response.code(), response.errorBody()?.string())
                                            if (response.isSuccessful) load()
                                        } catch (exception: Exception) {
                                            message = "No se pudo rechazar la visita: ${exception.message}"
                                        }
                                    }
                                }) { Text("Rechazar") }
                            }
                        }
                        if (Session.isGuard && item.approvalStatus == "pendiente") {
                            TextButton(onClick = {
                                scope.launch {
                                    try {
                                        val response = RetrofitClient.api.authorizeVisitByCall(Session.bearer(), item.id)
                                        message = if (response.isSuccessful) "Autorización por llamada registrada."
                                        else mensajeDeError(response.code(), response.errorBody()?.string())
                                        if (response.isSuccessful) load()
                                    } catch (exception: Exception) {
                                        message = "No se pudo registrar la autorización: ${exception.message}"
                                    }
                                }
                            }) { Text("Autorizar por llamada") }
                        }
                        if (Session.isGuard && item.approvalStatus == "aprobada") {
                            if (item.enteredAt == null || (item.exitedAt != null && item.exitReturning)) {
                                TextButton(onClick = {
                                    scope.launch {
                                        try {
                                            val response = RetrofitClient.api.registerVisitEntry(Session.bearer(), item.id)
                                            message = if (response.isSuccessful) "Entrada registrada."
                                            else mensajeDeError(response.code(), response.errorBody()?.string())
                                            if (response.isSuccessful) load()
                                        } catch (exception: Exception) {
                                            message = "No se pudo registrar la entrada: ${exception.message}"
                                        }
                                    }
                                }) { Text("Registrar entrada") }
                            } else if (item.exitedAt != null && !item.exitReturning) {
                                Text("Salida definitiva. Si vuelve, registra una nueva solicitud.")
                            } else {
                                TextButton(onClick = { pendingExit = item }) { Text("Registrar salida") }
                            }
                        }
                    }
                }
            }
        }
        TextButton(onClick = { navController.popBackStack() }) { Text("Volver") }
    }

    confirmation?.let { (prompt, action) ->
        DomuxConfirmDialog(
            title = "¿Estás seguro de confirmar esta acción?",
            message = prompt,
            confirmLabel = "Confirmar",
            danger = prompt.contains("entregado", ignoreCase = true),
            onConfirm = { confirmation = null; action() },
            onDismiss = { confirmation = null }
        )
    }

    deliveryPackage?.let { item ->
        AlertDialog(
            onDismissRequest = { deliveryPackage = null },
            title = { Text("Confirmar entrega") },
            text = {
                Column {
                    Text("¿A quién se entregó ${item.description.orEmpty()}?")
                    OutlinedTextField(
                        receiverName, { receiverName = it },
                        label = { Text("Nombre de quien recibe") },
                        singleLine = true, modifier = Modifier.fillMaxWidth()
                    )
                }
            },
            confirmButton = {
                TextButton(
                    enabled = receiverName.isNotBlank(),
                    onClick = {
                        scope.launch {
                            try {
                                val response = RetrofitClient.api.deliverPackage(
                                    Session.bearer(), item.id, DeliverPackageRequest(receiverName.trim())
                                )
                                message = if (response.isSuccessful) "Paquete entregado a ${receiverName.trim()}."
                                else mensajeDeError(response.code(), response.errorBody()?.string())
                                if (response.isSuccessful) {
                                    deliveryPackage = null
                                    receiverName = ""
                                    load()
                                }
                            } catch (exception: Exception) {
                                message = "No se pudo entregar el paquete: ${exception.message}"
                            }
                        }
                    }
                ) { Text("Registrar entrega") }
            },
            dismissButton = { TextButton(onClick = { deliveryPackage = null }) { Text("Cancelar") } }
        )
    }

    pendingExit?.let { visit ->
        AlertDialog(
            onDismissRequest = { pendingExit = null },
            title = { Text("Registrar salida") },
            text = { Text("¿${visit.visitorName} volverá a ingresar hoy?") },
            confirmButton = {
                TextButton(onClick = {
                    scope.launch {
                        try {
                            val response = RetrofitClient.api.registerVisitExit(
                                Session.bearer(), visit.id, VisitExitRequest(true)
                            )
                            message = if (response.isSuccessful) "Salida registrada; puede regresar hoy."
                            else mensajeDeError(response.code(), response.errorBody()?.string())
                            if (response.isSuccessful) { pendingExit = null; load() }
                        } catch (exception: Exception) {
                            message = "No se pudo registrar la salida: ${exception.message}"
                        }
                    }
                }) { Text("Sí, regresa hoy") }
            },
            dismissButton = {
                TextButton(onClick = {
                    scope.launch {
                        try {
                            val response = RetrofitClient.api.registerVisitExit(
                                Session.bearer(), visit.id, VisitExitRequest(false)
                            )
                            message = if (response.isSuccessful) "Salida definitiva registrada."
                            else mensajeDeError(response.code(), response.errorBody()?.string())
                            if (response.isSuccessful) { pendingExit = null; load() }
                        } catch (exception: Exception) {
                            message = "No se pudo registrar la salida: ${exception.message}"
                        }
                    }
                }) { Text("No, salida definitiva") }
            }
        )
    }

    pendingQrExit?.let { visit ->
        AlertDialog(
            onDismissRequest = { pendingQrExit = null },
            title = { Text("Salida por QR") },
            text = { Text("¿${visit.visitorName} volverá a ingresar hoy?") },
            confirmButton = {
                TextButton(onClick = {
                    val token = scannedQrToken
                    if (token != null) scope.launch {
                        try {
                            val response = RetrofitClient.api.exitVisitQr(
                                Session.bearer(), token, QrVisitorExitRequest(visit.id, true)
                            )
                            message = if (response.isSuccessful) "Salida registrada; puede regresar hoy."
                            else mensajeDeError(response.code(), response.errorBody()?.string())
                            if (response.isSuccessful) {
                                pendingQrExit = null
                                val refreshed = RetrofitClient.api.inspectVisitQr(Session.bearer(), token)
                                if (refreshed.isSuccessful) qrInspection = refreshed.body()
                                load()
                            }
                        } catch (exception: Exception) {
                            message = "No se pudo registrar la salida QR: ${exception.message}"
                        }
                    }
                }) { Text("Sí, regresa hoy") }
            },
            dismissButton = {
                TextButton(onClick = {
                    val token = scannedQrToken
                    if (token != null) scope.launch {
                        try {
                            val response = RetrofitClient.api.exitVisitQr(
                                Session.bearer(), token, QrVisitorExitRequest(visit.id, false)
                            )
                            message = if (response.isSuccessful) "Salida definitiva registrada."
                            else mensajeDeError(response.code(), response.errorBody()?.string())
                            if (response.isSuccessful) {
                                pendingQrExit = null
                                val refreshed = RetrofitClient.api.inspectVisitQr(Session.bearer(), token)
                                if (refreshed.isSuccessful) qrInspection = refreshed.body()
                                load()
                            }
                        } catch (exception: Exception) {
                            message = "No se pudo registrar la salida QR: ${exception.message}"
                        }
                    }
                }) { Text("No, salida definitiva") }
            }
        )
    }
}

@Composable
private fun ResidentPicker(
    search: String,
    residents: List<ResidentSummary>,
    selected: ResidentSummary?,
    expanded: Boolean,
    onSearch: (String) -> Unit,
    onExpanded: (Boolean) -> Unit,
    onSelect: (ResidentSummary) -> Unit
) {
    Column {
        OutlinedTextField(
            value = selected?.let {
                "${it.name} · ${it.apartment.orEmpty()}" +
                    if (it.phone.isNullOrBlank()) "" else " · ${it.phone}"
            } ?: search,
            onValueChange = onSearch,
            label = { Text("Buscar por nombre, documento o apartamento") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        DropdownMenu(expanded = expanded && residents.isNotEmpty(), onDismissRequest = { onExpanded(false) }) {
            residents.forEach { resident ->
                DropdownMenuItem(
                    text = {
                        Text("${resident.name} · ${resident.apartment.orEmpty()}" +
                            if (resident.phone.isNullOrBlank()) "" else " · ${resident.phone}")
                    },
                    onClick = { onSelect(resident) }
                )
            }
        }
        if (residents.isEmpty() && search.isNotBlank()) {
            Text("No se encontraron residentes con esa búsqueda.", style = MaterialTheme.typography.bodySmall)
        }
    }
}
