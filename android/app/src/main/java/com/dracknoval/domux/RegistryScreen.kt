package com.dracknoval.domux

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.foundation.Image
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.animation.animateContentSize
import androidx.compose.ui.platform.LocalContext
import androidx.compose.foundation.clickable
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.dracknoval.domux.data.CreateVisitQrRequest
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
import com.google.zxing.BarcodeFormat
import com.journeyapps.barcodescanner.BarcodeEncoder
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

private fun isCancellation(e: Throwable): Boolean =
    e is CancellationException ||
        e.message?.contains("left the composition", ignoreCase = true) == true

private fun shiftQrDate(value: String, days: Int): String {
    val format = SimpleDateFormat("yyyy-MM-dd", Locale.US).apply { isLenient = false }
    val parsedDate = requireNotNull(format.parse(value)) { "La fecha del QR no es válida." }
    val calendar = Calendar.getInstance().apply {
        time = parsedDate
        add(Calendar.DAY_OF_MONTH, days)
    }
    return format.format(calendar.time)
}

private suspend fun runRegistryAction(
    onError: (String) -> Unit,
    action: suspend () -> Unit
) {
    try {
        action()
    } catch (exception: Exception) {
        if (isCancellation(exception)) {
            if (exception is CancellationException) throw exception else return
        }
        onError(exception.message.orEmpty())
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RegistryScreen(navController: NavController, initialTab: Int = 0) {
    val canRegister = Session.isGuard || Session.isAdmin
    val scope = rememberCoroutineScope()
    var packages by remember { mutableStateOf<List<PackageItem>>(emptyList()) }
    var visits by remember { mutableStateOf<List<Visit>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var message by remember { mutableStateOf("") }
    var messageIsError by remember { mutableStateOf(false) }
    var search by remember { mutableStateOf("") }
    var statusFilter by remember { mutableStateOf<String?>(null) }
    val isVisitsModule = if (Session.isResident) initialTab >= 1 else initialTab >= 2

    val tabs = if (isVisitsModule) {
        if (Session.isResident) {
            listOf("Mis visitas", "Crear QR")
        } else if (Session.isAdmin) {
            listOf("Visitas", "Crear QR", "Registrar visita")
        } else {
            listOf("Visitas activas", "Registrar visita")
        }
    } else {
        if (Session.isResident) {
            listOf("Mis paquetes")
        } else {
            listOf("Paquetes", "Registrar paquete")
        }
    }

    var selectedTab by remember(initialTab) {
        mutableStateOf(
            if (Session.isGuard) {
                if (isVisitsModule) (initialTab - 2).coerceAtLeast(0) else initialTab
            } else {
                0
            }
        )
    }

    val currentView = if (isVisitsModule) {
        if (Session.isResident) {
            selectedTab + 1
        } else if (Session.isAdmin) {
            if (selectedTab == 0) 2 else if (selectedTab == 1) 4 else 3
        } else {
            selectedTab + 2
        }
    } else {
        selectedTab
    }

    var selectedPackageResident by remember { mutableStateOf<ResidentSummary?>(null) }
    var packageDescription by remember { mutableStateOf("") }
    var packageDate by remember { mutableStateOf("") }
    var packageTime by remember { mutableStateOf("") }
    var mediaUrl by rememberSaveable { mutableStateOf<String?>(null) }
    var mediaType by rememberSaveable { mutableStateOf<String?>(null) }
    var mediaName by remember { mutableStateOf<String?>(null) }
    var attemptedPackage by remember { mutableStateOf(false) }

    var selectedVisitResident by remember { mutableStateOf<ResidentSummary?>(null) }
    var visitorName by remember { mutableStateOf("") }
    var visitorDocument by remember { mutableStateOf("") }
    var visitorType by remember { mutableStateOf("visitante") }
    var documentRefused by remember { mutableStateOf(false) }
    var visitorPhotoUrl by remember { mutableStateOf<String?>(null) }
    var visitorPhotoType by remember { mutableStateOf<String?>(null) }
    var visitorPhotoName by remember { mutableStateOf<String?>(null) }
    var visitDescription by remember { mutableStateOf("") }
    var attemptedVisit by remember { mutableStateOf(false) }

    var deliveryPackage by remember { mutableStateOf<PackageItem?>(null) }
    var receiverName by remember { mutableStateOf("") }
    var deliveryMediaUrl by rememberSaveable { mutableStateOf<String?>(null) }
    var deliveryMediaType by rememberSaveable { mutableStateOf<String?>(null) }
    var deliveryMediaName by remember { mutableStateOf<String?>(null) }
    var pendingExit by remember { mutableStateOf<Visit?>(null) }
    var pendingQrExit by remember { mutableStateOf<Visit?>(null) }
    var confirmation by remember { mutableStateOf<Pair<String, () -> Unit>?>(null) }

    var qrPasses by remember { mutableStateOf<List<VisitQrPass>>(emptyList()) }
    var activeQrPass by remember { mutableStateOf<VisitQrPass?>(null) }
    var qrBitmap by remember { mutableStateOf<android.graphics.Bitmap?>(null) }
    val initialQrStartDate = remember {
        SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())
    }
    var qrStartDate by remember { mutableStateOf(initialQrStartDate) }
    var qrEndDate by remember { mutableStateOf(shiftQrDate(initialQrStartDate, 1)) }
    var qrVisitorNames by remember { mutableStateOf(List(5) { "" }) }
    var qrVisitorDocuments by remember { mutableStateOf(List(5) { "" }) }
    var qrMaxGuests by remember { mutableStateOf(1) }
    var attemptedQrCreate by remember { mutableStateOf(false) }
    var scannedQrToken by remember { mutableStateOf<String?>(null) }
    var qrInspection by remember { mutableStateOf<VisitQrInspectionResponse?>(null) }
    var qrVisitorName by remember { mutableStateOf("") }

    val scanner = rememberLauncherForActivityResult(ScanContract()) { result ->
        val raw = result.contents.orEmpty()
        val token = raw.removePrefix("DOMUX:")
            .takeIf { raw.startsWith("DOMUX:") && it.isNotBlank() }
        if (token == null) {
            message = "El código leído no es un QR válido de DOMUX."
        } else {
            scannedQrToken = token
            scope.launch {
                runRegistryAction({ message = "No se pudo consultar el QR: $it" }) {
                    val response = RetrofitClient.api.inspectVisitQr(Session.bearer(), token)
                    if (response.isSuccessful) qrInspection = response.body()
                    else message = mensajeDeError(response.code(), response.errorBody()?.string())
                }
            }
        }
    }

    suspend fun load() {
        loading = true
        try {
            val packageResponse = RetrofitClient.api.getPackages(
                Session.bearer(),
                statusFilter,
                search.trim().ifEmpty { null }
            )
            if (packageResponse.isSuccessful) {
                packages = packageResponse.body()?.packages.orEmpty()
            } else {
                message = mensajeDeError(packageResponse.code(), packageResponse.errorBody()?.string())
            }

            val visitsResponse = RetrofitClient.api.getVisits(Session.bearer())
            if (visitsResponse.isSuccessful) {
                visits = visitsResponse.body()?.visits.orEmpty()
            } else {
                message = mensajeDeError(visitsResponse.code(), visitsResponse.errorBody()?.string())
            }

            if (Session.isResident) {
                val qrResponse = RetrofitClient.api.getVisitQrPasses(Session.bearer())
                if (qrResponse.isSuccessful) {
                    qrPasses = qrResponse.body()?.qrPasses.orEmpty()
                } else {
                    message = mensajeDeError(qrResponse.code(), qrResponse.errorBody()?.string())
                }
            }
        } catch (exception: Exception) {
            if (isCancellation(exception)) {
                if (exception is CancellationException) throw exception else return
            }
            message = "No se pudieron cargar los registros: ${exception.message}"
        } finally {
            loading = false
        }
    }

    LaunchedEffect(statusFilter, search) {
        if (search.isNotBlank()) delay(300)
        load()
    }

    LaunchedEffect(activeQrPass?.qrData) {
        qrBitmap = try {
            activeQrPass?.qrData?.let {
                BarcodeEncoder().encodeBitmap(it, BarcodeFormat.QR_CODE, 640, 640)
            }
        } catch (exception: Exception) {
            if (isCancellation(exception)) {
                if (exception is CancellationException) throw exception else return@LaunchedEffect
            }
            message = "No se pudo generar la imagen del QR: ${exception.message}"
            null
        }
    }

    fun exitQrVisit(returningToday: Boolean) {
        val visit = pendingQrExit ?: return
        val token = scannedQrToken ?: return
        scope.launch {
            runRegistryAction({ message = "No se pudo registrar la salida QR: $it" }) {
                val response = RetrofitClient.api.exitVisitQr(
                    Session.bearer(), token, QrVisitorExitRequest(visit.id, returningToday)
                )
                message = if (response.isSuccessful) {
                    if (returningToday) "Salida registrada; puede regresar hoy."
                    else "Salida definitiva registrada."
                } else mensajeDeError(response.code(), response.errorBody()?.string())
                if (response.isSuccessful) {
                    pendingQrExit = null
                    refreshQrInspection(token) { qrInspection = it }
                    load()
                }
            }
        }
    }

    val launchQrScanner = {
        scanner.launch(
            ScanOptions()
                .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                .setPrompt("Escanea el QR de visitas")
                .setOrientationLocked(true)
        )
    }

    fun enterQrVisitor(name: String) {
        val token = scannedQrToken ?: return
        scope.launch {
            runRegistryAction({ message = "No se pudo registrar el ingreso QR: $it" }) {
                val response = RetrofitClient.api.enterVisitQr(
                    Session.bearer(),
                    token,
                    QrVisitorEntryRequest(visitorName = name.trim())
                )
                message = if (response.isSuccessful) "Entrada por QR registrada."
                else mensajeDeError(response.code(), response.errorBody()?.string())
                if (response.isSuccessful) {
                    qrVisitorName = ""
                    refreshQrInspection(token) { qrInspection = it }
                    load()
                }
            }
        }
    }

    fun linkVisitToQr(visit: Visit) {
        val token = scannedQrToken ?: return
        scope.launch {
            runRegistryAction({ message = "No se pudo vincular al QR: $it" }) {
                val response = RetrofitClient.api.enterVisitQr(
                    Session.bearer(),
                    token,
                    QrVisitorEntryRequest(visitId = visit.id)
                )
                message = if (response.isSuccessful) {
                    "${visit.visitorName} vinculado al QR."
                } else mensajeDeError(response.code(), response.errorBody()?.string())
                if (response.isSuccessful) {
                    refreshQrInspection(token) { qrInspection = it }
                    load()
                }
            }
        }
    }

    fun reenterVisitByQr(visit: Visit) {
        val token = scannedQrToken ?: return
        scope.launch {
            runRegistryAction({ message = "No se pudo registrar el reingreso: $it" }) {
                val response = RetrofitClient.api.enterVisitQr(
                    Session.bearer(),
                    token,
                    QrVisitorEntryRequest(visitId = visit.id)
                )
                message = if (response.isSuccessful) {
                    "Reingreso de ${visit.visitorName} registrado."
                } else mensajeDeError(response.code(), response.errorBody()?.string())
                if (response.isSuccessful) {
                    refreshQrInspection(token) { qrInspection = it }
                    load()
                }
            }
        }
    }

    fun authorizeAndEnterByCall(visit: Visit) {
        scope.launch {
            runRegistryAction({ message = "No se pudo autorizar el ingreso: $it" }) {
                val authorization = RetrofitClient.api.authorizeVisitByCall(
                    Session.bearer(), visit.id
                )
                if (!authorization.isSuccessful) {
                    message = mensajeDeError(authorization.code(), authorization.errorBody()?.string())
                    return@runRegistryAction
                }
                val entry = RetrofitClient.api.registerVisitEntry(Session.bearer(), visit.id)
                message = if (entry.isSuccessful) "Visita autorizada e ingreso registrado."
                else mensajeDeError(entry.code(), entry.errorBody()?.string())
                load()
            }
        }
    }

    val packageFilters = buildList {
        add("Todos" to null)
        add("En portería" to "pendiente")
        add("Entregados" to "entregado")
        if (canRegister) add("Archivados" to "papelera")
    }
    val title = when {
        isVisitsModule -> "Visitas y QR"
        else -> "Paquetería"
    }

    DomuxScreenScaffold(title = title, navController = navController) { scaffoldPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(scaffoldPadding)
                .padding(horizontal = 16.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            if (tabs.isNotEmpty()) {
                DomuxSectionTabs(tabs, selectedTab.coerceIn(tabs.indices)) { selectedTab = it }
            }
            if (message.isNotBlank()) {
                DomuxFeedbackBanner(message, isError = messageIsError) { message = "" }
            }
            androidx.compose.foundation.layout.Box(modifier = Modifier.fillMaxWidth().height(4.dp)) {
                if (loading) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
            }

            when {
                canRegister && currentView == 0 -> {
                    PackageListSection(
                        modifier = Modifier.weight(1f),
                        packages = packages,
                        packageFilters = packageFilters,
                        statusFilter = statusFilter,
                        onStatusFilter = { statusFilter = it },
                        search = search,
                        onSearch = { search = it },
                        onRefresh = { scope.launch { load() } },
                        onClearFilters = {
                            statusFilter = null
                            search = ""
                        },
                        canRegister = canRegister,
                        onDeliver = {
                            deliveryPackage = it
                            receiverName = ""
                        },
                        onMoveToTrash = { item ->
                            confirmation = "¿Archivar este paquete?" to {
                                scope.launch {
                                    runRegistryAction({ message = "No se pudo mover el paquete: $it"; messageIsError = true }) {
                                        val response = RetrofitClient.api.deletePackage(
                                            Session.bearer(), item.id, force = false
                                        )
                                        if (response.isSuccessful) {
                                            message = "Paquete archivado."
                                            messageIsError = false
                                            load()
                                        } else {
                                            message = mensajeDeError(response.code(), response.errorBody()?.string())
                                            messageIsError = true
                                        }
                                    }
                                }
                            }
                        },
                        onRestore = { item ->
                            scope.launch {
                                runRegistryAction({ message = "No se pudo restaurar el paquete: $it" }) {
                                    val response = RetrofitClient.api.restorePackage(Session.bearer(), item.id)
                                    message = if (response.isSuccessful) {
                                        response.body()?.message ?: "Paquete restaurado."
                                    } else mensajeDeError(response.code(), response.errorBody()?.string())
                                    if (response.isSuccessful) load()
                                }
                            }
                        },
                        onArchiveAllDelivered = {
                            confirmation = "¿Archivar todos los paquetes entregados? Desaparecerán de la vista activa." to {
                                scope.launch {
                                    val delivered = packages.filter { it.status == "entregado" && !it.isDeleted }
                                    if (delivered.isEmpty()) return@launch
                                    var archivedCount = 0
                                    var failedCount = 0
                                    runRegistryAction({ message = "Error al archivar en bloque: $it"; messageIsError = true }) {
                                        for (pkg in delivered) {
                                            val response = RetrofitClient.api.deletePackage(Session.bearer(), pkg.id, force = false)
                                            if (response.isSuccessful) {
                                                archivedCount++
                                            } else {
                                                failedCount++
                                            }
                                        }
                                        if (failedCount == 0 && archivedCount > 0) {
                                            message = "Se archivaron $archivedCount paquetes entregados."
                                            messageIsError = false
                                        } else {
                                            message = "Se archivaron $archivedCount paquetes; $failedCount no pudieron archivarse."
                                            messageIsError = true
                                        }
                                        load()
                                    }
                                }
                            }
                        }
                    )
                }

                canRegister && currentView == 1 -> {
                    PackageRegistrationSection(
                        modifier = Modifier.weight(1f),
                        resident = selectedPackageResident,
                        onResidentChange = { selectedPackageResident = it },
                        description = packageDescription,
                        onDescriptionChange = { packageDescription = it },
                        date = packageDate,
                        onDateChange = { packageDate = it },
                        time = packageTime,
                        onTimeChange = { packageTime = it },
                        mediaName = mediaName,
                        onMedia = { url, type, name ->
                            mediaUrl = url
                            mediaType = type
                            mediaName = name
                        },
                        onMessage = { message = it },
                        attempted = attemptedPackage,
                        onRegister = {
                            attemptedPackage = true
                            if (selectedPackageResident == null || packageDescription.isBlank()) {
                                message = "Selecciona residente y escribe la descripción del paquete."
                            } else {
                                confirmation = "¿Estás seguro de guardar este paquete?" to {
                                    scope.launch {
                                        runRegistryAction({ message = "No se pudo registrar el paquete: $it" }) {
                                            val response = RetrofitClient.api.registerPackage(
                                                Session.bearer(),
                                                RegisterPackageRequest(
                                                    residentId = selectedPackageResident!!.id,
                                                    description = packageDescription.trim(),
                                                    mediaUrl = mediaUrl,
                                                    mediaType = mediaType,
                                                    eventDate = packageDate.ifBlank { null },
                                                    eventTime = packageTime.ifBlank { null },
                                                    status = "pendiente"
                                                )
                                            )
                                            if (response.isSuccessful) {
                                                message = "Paquete registrado."
                                                packageDescription = ""
                                                packageDate = ""
                                                packageTime = ""
                                                mediaUrl = null
                                                mediaType = null
                                                mediaName = null
                                                attemptedPackage = false
                                                selectedPackageResident = null
                                                selectedTab = 0
                                                load()
                                            } else {
                                                message = mensajeDeError(response.code(), response.errorBody()?.string())
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    )
                }

                canRegister && currentView == 2 -> {
                    VisitListSection(
                        modifier = Modifier.weight(1f),
                        visits = visits,
                        isResident = false,
                        isGuard = Session.isGuard,
                        onDecision = { visit, decision ->
                            scope.launch {
                                runRegistryAction({ message = "No se pudo responder la solicitud: $it" }) {
                                    val response = RetrofitClient.api.decideVisit(
                                        Session.bearer(), visit.id, VisitDecisionRequest(decision)
                                    )
                                    message = if (response.isSuccessful) {
                                        if (decision == "aprobada") "Acceso autorizado." else "Acceso rechazado."
                                    } else mensajeDeError(response.code(), response.errorBody()?.string())
                                    if (response.isSuccessful) load()
                                }
                            }
                        },
                        onAuthorizeByCall = { visit ->
                            scope.launch {
                                runRegistryAction({ message = "No se pudo registrar la autorización: $it" }) {
                                    val response = RetrofitClient.api.authorizeVisitByCall(
                                        Session.bearer(), visit.id
                                    )
                                    message = if (response.isSuccessful) {
                                        "Autorización por llamada registrada."
                                    } else mensajeDeError(response.code(), response.errorBody()?.string())
                                    if (response.isSuccessful) load()
                                }
                            }
                        },
                        onEntry = { visit ->
                            scope.launch {
                                runRegistryAction({ message = "No se pudo registrar la entrada: $it" }) {
                                    val response = RetrofitClient.api.registerVisitEntry(
                                        Session.bearer(), visit.id
                                    )
                                    message = if (response.isSuccessful) "Entrada registrada."
                                    else mensajeDeError(response.code(), response.errorBody()?.string())
                                    if (response.isSuccessful) load()
                                }
                            }
                        },
                        onExit = { pendingExit = it },
                        onAuthorizeAndEnter = { authorizeAndEnterByCall(it) },
                        onScanQr = launchQrScanner,
                        qrInspection = qrInspection,
                        qrVisitorName = qrVisitorName,
                        onQrVisitorNameChange = { qrVisitorName = it },
                        onQrMessage = { message = it },
                        onEnterQr = { enterQrVisitor(it) },
                        onLinkVisit = { linkVisitToQr(it) },
                        onQrExit = { pendingQrExit = it },
                        onQrReentry = { reenterVisitByQr(it) }
                    )
                }

                canRegister && currentView == 3 -> {
                    RegistrationAndQrSection(
                        modifier = Modifier.weight(1f),
                        resident = selectedVisitResident,
                        onResidentChange = { selectedVisitResident = it },
                        visitorName = visitorName,
                        onVisitorNameChange = { visitorName = it },
                        visitorDocument = visitorDocument,
                        onVisitorDocumentChange = { visitorDocument = it },
                        visitorType = visitorType,
                        onVisitorTypeChange = { visitorType = it },
                        documentRefused = documentRefused,
                        onDocumentRefusedChange = { refused ->
                            documentRefused = refused
                            if (refused) {
                                visitorDocument = ""
                            }
                        },
                        visitorPhotoName = visitorPhotoName,
                        onVisitorPhoto = { url, type, name ->
                            visitorPhotoUrl = url
                            visitorPhotoType = type
                            visitorPhotoName = name
                        },
                        visitDescription = visitDescription,
                        onVisitDescriptionChange = { visitDescription = it },
                        attemptedVisit = attemptedVisit,
                        onMessage = { message = it },
                        onRegisterVisit = {
                            attemptedVisit = true
                            if (selectedVisitResident == null || visitorName.isBlank()) {
                                message = "Selecciona residente y escribe el nombre del visitante."
                            } else if (!documentRefused && visitorDocument.isBlank()) {
                                message = "El documento de identidad del visitante es obligatorio, o debes marcar que se negó a suministrarlo."
                            } else {
                                scope.launch {
                                    runRegistryAction({ message = "No se pudo registrar la visita: $it" }) {
                                        val response = RetrofitClient.api.registerVisit(
                                            Session.bearer(),
                                            RegisterVisitRequest(
                                                residentId = selectedVisitResident!!.id,
                                                visitorName = visitorName.trim(),
                                                type = visitorType,
                                                visitorDocument = visitorDocument.trim().ifEmpty { null },
                                                documentRefused = documentRefused,
                                                mediaConsent = visitorDocument.isNotBlank() ||
                                                    !visitorPhotoUrl.isNullOrBlank(),
                                                mediaUrl = visitorPhotoUrl,
                                                mediaType = visitorPhotoType,
                                                description = visitDescription.trim().ifEmpty { null }
                                            )
                                        )
                                        if (response.isSuccessful) {
                                            message = "Registro enviado. El residente recibirá una solicitud para autorizar el ingreso."
                                            visitorName = ""
                                            visitorDocument = ""
                                            documentRefused = false
                                            visitorPhotoUrl = null
                                            visitorPhotoType = null
                                            visitorPhotoName = null
                                            visitDescription = ""
                                            selectedVisitResident = null
                                            attemptedVisit = false
                                            load()
                                        } else {
                                            message = mensajeDeError(response.code(), response.errorBody()?.string())
                                        }
                                    }
                                }
                            }
                        },
                        isGuard = Session.isGuard,
                        scanner = launchQrScanner,
                        qrInspection = qrInspection,
                        qrVisitorName = qrVisitorName,
                        onQrVisitorNameChange = { qrVisitorName = it },
                        onEnterQr = { enterQrVisitor(it) },
                        onLinkVisit = { linkVisitToQr(it) },
                        onQrExit = { pendingQrExit = it },
                        onQrReentry = { reenterVisitByQr(it) }
                    )
                }

                Session.isResident && currentView == 0 -> {
                    PackageListSection(
                        modifier = Modifier.weight(1f),
                        packages = packages,
                        packageFilters = packageFilters,
                        statusFilter = statusFilter,
                        onStatusFilter = { statusFilter = it },
                        search = search,
                        onSearch = { search = it },
                        onRefresh = { scope.launch { load() } },
                        onClearFilters = {
                            statusFilter = null
                            search = ""
                        },
                        canRegister = false,
                        onDeliver = {},
                        onMoveToTrash = {},
                        onRestore = {},
                        onArchiveAllDelivered = {}
                    )
                }

                Session.isResident && currentView == 1 -> {
                    VisitListSection(
                        modifier = Modifier.weight(1f),
                        visits = visits,
                        isResident = true,
                        isGuard = false,
                        onDecision = { visit, decision ->
                            scope.launch {
                                runRegistryAction({ message = "No se pudo responder la solicitud: $it" }) {
                                    val response = RetrofitClient.api.decideVisit(
                                        Session.bearer(), visit.id, VisitDecisionRequest(decision)
                                    )
                                    message = if (response.isSuccessful) {
                                        if (decision == "aprobada") "Acceso autorizado." else "Acceso rechazado."
                                    } else mensajeDeError(response.code(), response.errorBody()?.string())
                                    if (response.isSuccessful) load()
                                }
                            }
                        },
                        onAuthorizeByCall = {},
                        onEntry = {},
                        onExit = {}
                    )
                }

                Session.isAdmin && currentView == 4 -> {
        ResidentQrPassSection(
            modifier = Modifier.weight(1f),
            resident = selectedVisitResident,
            onResidentChange = { selectedVisitResident = it },
            startDate = qrStartDate,
            onStartDateChange = { newStartDate ->
                qrStartDate = newStartDate
                val latestEndDate = shiftQrDate(newStartDate, 3)
                if (qrEndDate < newStartDate || qrEndDate > latestEndDate) {
                    qrEndDate = shiftQrDate(newStartDate, 1)
                }
            },
            endDate = qrEndDate,
            onEndDateChange = { qrEndDate = it },
            visitorNames = qrVisitorNames,
            onVisitorNameChange = { index, name ->
                qrVisitorNames = qrVisitorNames.toMutableList().apply { set(index, name) }
            },
            visitorDocuments = qrVisitorDocuments,
            onVisitorDocumentChange = { index, doc ->
                qrVisitorDocuments = qrVisitorDocuments.toMutableList().apply { set(index, doc) }
            },
            maxGuests = qrMaxGuests,
            onMaxGuestsChange = { qrMaxGuests = it },
            attemptedCreate = attemptedQrCreate,
            passes = qrPasses,
            activePass = activeQrPass,
            qrBitmap = qrBitmap,
            onCreate = {
                attemptedQrCreate = true
                if (qrVisitorNames.take(qrMaxGuests).any { it.isBlank() } ||
                    qrVisitorDocuments.take(qrMaxGuests).any { it.isBlank() } ||
                    selectedVisitResident == null
                ) {
                    message = "Selecciona residente y escribe datos de los visitantes."
                    messageIsError = true
                } else if (qrEndDate < qrStartDate || qrEndDate > shiftQrDate(qrStartDate, 3)) {
                    message = "La vigencia del QR no puede superar 72 horas desde el inicio."
                    messageIsError = true
                } else if (qrMaxGuests !in 1..5) {
                    message = "La cantidad de personas debe estar entre 1 y 5."
                    messageIsError = true
                } else {
                    scope.launch {
                        runRegistryAction({ message = "No se pudo crear el QR: $it"; messageIsError = true }) {
                            val response = RetrofitClient.api.createVisitQrPass(
                                Session.bearer(),
                                CreateVisitQrRequest(
                                    residentId = selectedVisitResident?.id,
                                    validFrom = qrStartDate,
                                    validUntil = qrEndDate,
                                    visitorName = qrVisitorNames.take(qrMaxGuests).joinToString(" / "),
                                    visitorDocument = qrVisitorDocuments.take(qrMaxGuests).joinToString(" / "),
                                    maxGuests = qrMaxGuests
                                )
                            )
                            if (response.isSuccessful) {
                                activeQrPass = response.body()?.qrPass
                                qrVisitorNames = List(5) { "" }
                                qrVisitorDocuments = List(5) { "" }
                                attemptedQrCreate = false
                                message = "Código QR creado."
                                messageIsError = false
                                load()
                            } else {
                                message = mensajeDeError(response.code(), response.errorBody()?.string())
                                messageIsError = true
                            }
                        }
                    }
                }
            },
            onSelectPass = {
                scope.launch {
                    try {
                        qrBitmap = it.qrData?.let { data -> 
                            com.journeyapps.barcodescanner.BarcodeEncoder().encodeBitmap(data, com.google.zxing.BarcodeFormat.QR_CODE, 640, 640)
                        }
                        activeQrPass = it
                    } catch (e: Exception) {
                        message = "Error generando QR: ${e.message}"
                        messageIsError = true
                    }
                }
            },
            onRevokePass = { pass ->
                scope.launch {
                    runRegistryAction({ message = "Error revocando QR: $it"; messageIsError = true }) {
                        val response = RetrofitClient.api.revokeVisitQrPass(Session.bearer(), pass.id)
                        if (response.isSuccessful) {
                            message = "Pase QR revocado."
                            messageIsError = false
                            activeQrPass = null
                            qrBitmap = null
                            load()
                        } else {
                            message = mensajeDeError(response.code(), response.errorBody()?.string())
                            messageIsError = true
                        }
                    }
                }
            },
            onClosePass = { activeQrPass = null; qrBitmap = null }
        )
    }

    Session.isResident && currentView == 2 -> {
                    ResidentQrPassSection(
                        modifier = Modifier.weight(1f),
                        startDate = qrStartDate,
                        onStartDateChange = { newStartDate ->
                            qrStartDate = newStartDate
                            val latestEndDate = shiftQrDate(newStartDate, 3)
                            if (qrEndDate < newStartDate || qrEndDate > latestEndDate) {
                                qrEndDate = shiftQrDate(newStartDate, 1)
                            }
                        },
                        endDate = qrEndDate,
                        onEndDateChange = { qrEndDate = it },
                        visitorNames = qrVisitorNames,
                        onVisitorNameChange = { index, name ->
                            qrVisitorNames = qrVisitorNames.toMutableList().apply { set(index, name) }
                        },
                        visitorDocuments = qrVisitorDocuments,
                        onVisitorDocumentChange = { index, doc ->
                            qrVisitorDocuments = qrVisitorDocuments.toMutableList().apply { set(index, doc) }
                        },
                        maxGuests = qrMaxGuests,
                        onMaxGuestsChange = { qrMaxGuests = it },
                        attemptedCreate = attemptedQrCreate,
                        passes = qrPasses,
                        activePass = activeQrPass,
                        qrBitmap = qrBitmap,
                        onCreate = {
                            attemptedQrCreate = true
                            if (qrVisitorNames.take(qrMaxGuests).any { it.isBlank() } ||
                                qrVisitorDocuments.take(qrMaxGuests).any { it.isBlank() }
                            ) {
                                message = "Escribe el nombre y documento de todos los visitantes."
                                messageIsError = true
                            } else if (
                                qrEndDate < qrStartDate ||
                                qrEndDate > shiftQrDate(qrStartDate, 3)
                            ) {
                                message = "La vigencia del QR no puede superar 72 horas desde el inicio."
                                messageIsError = true
                            } else if (qrMaxGuests !in 1..5) {
                                message = "La cantidad de personas debe estar entre 1 y 5."
                                messageIsError = true
                            } else {
                                scope.launch {
                                    runRegistryAction({ message = "No se pudo crear el QR: $it"; messageIsError = true }) {
                                        val response = RetrofitClient.api.createVisitQrPass(
                                            Session.bearer(),
                                            CreateVisitQrRequest(
                                                validFrom = qrStartDate,
                                                validUntil = qrEndDate,
                                                visitorName = qrVisitorNames.take(qrMaxGuests).joinToString(" / "),
                                                visitorDocument = qrVisitorDocuments.take(qrMaxGuests).joinToString(" / "),
                                                maxGuests = qrMaxGuests
                                            )
                                        )
                                        if (response.isSuccessful) {
                                            activeQrPass = response.body()?.qrPass
                                            qrVisitorNames = List(5) { "" }
                                            qrVisitorDocuments = List(5) { "" }
                                            attemptedQrCreate = false
                                            message = "Código QR creado."
                                            messageIsError = false
                                            load()
                                        } else {
                                            message = mensajeDeError(response.code(), response.errorBody()?.string())
                                            messageIsError = true
                                        }
                                    }
                                }
                            }
                        },
                        onSelectPass = { if (it.id == -1) activeQrPass = null else activeQrPass = it },
                        onRevokePass = { pass ->
                            scope.launch {
                                runRegistryAction({ message = "No se pudo revocar el QR: $it" }) {
                                    val response = RetrofitClient.api.revokeVisitQrPass(
                                        Session.bearer(), pass.id
                                    )
                                    message = if (response.isSuccessful) "QR revocado."
                                    else mensajeDeError(response.code(), response.errorBody()?.string())
                                    if (response.isSuccessful) {
                                        if (activeQrPass?.id == pass.id) activeQrPass = null
                                        load()
                                    }
                                }
                            }
                        },
                        onClosePass = { activeQrPass = null; qrBitmap = null }
                    )
                }
            }
        }
    }

    confirmation?.let { (prompt, action) ->
        DomuxConfirmDialog(
            title = "¿Estás seguro de confirmar esta acción?",
            message = prompt,
            confirmLabel = "Confirmar",
            danger = prompt.contains("eliminar", ignoreCase = true) ||
                prompt.contains("entregado", ignoreCase = true),
            onConfirm = { confirmation = null; action() },
            onDismiss = { confirmation = null }
        )
    }

    deliveryPackage?.let { item ->
        AlertDialog(
            onDismissRequest = { deliveryPackage = null },
            title = { Text("Confirmar entrega") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("¿A quién se entregó ${item.description.orEmpty()}?")
                    OutlinedTextField(
                        value = receiverName,
                        onValueChange = { receiverName = it },
                        label = { Text("Nombre de quien recibe *") },
                        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words),
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    MediaAttachmentPicker(
                        attachmentName = deliveryMediaName,
                        onAttachment = { url, type, name ->
                            deliveryMediaUrl = url
                            deliveryMediaType = type
                            deliveryMediaName = name
                        },
                        mimeTypeFilter = "image/*",
                        onError = { message = it; messageIsError = true }
                    )
                }
            },
            confirmButton = {
                TextButton(
                    enabled = receiverName.isNotBlank(),
                    onClick = {
                        scope.launch {
                            runRegistryAction({ message = "No se pudo entregar el paquete: $it"; messageIsError = true }) {
                                val response = RetrofitClient.api.deliverPackage(
                                    Session.bearer(),
                                    item.id,
                                    DeliverPackageRequest(
                                        receivedBy = receiverName.trim(),
                                        mediaUrl = deliveryMediaUrl,
                                        mediaType = deliveryMediaType
                                    )
                                )
                                if (response.isSuccessful) {
                                    message = "Paquete entregado a ${receiverName.trim()}."
                                    messageIsError = false
                                    deliveryPackage = null
                                    receiverName = ""
                                    deliveryMediaUrl = null
                                    deliveryMediaType = null
                                    deliveryMediaName = null
                                    load()
                                } else {
                                    message = mensajeDeError(response.code(), response.errorBody()?.string())
                                    messageIsError = true
                                }
                            }
                        }
                    }
                ) { Text("Registrar entrega") }
            },
            dismissButton = {
                TextButton(onClick = { deliveryPackage = null }) { Text("Cancelar") }
            }
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
                        runRegistryAction({ message = "No se pudo registrar la salida: $it" }) {
                            val response = RetrofitClient.api.registerVisitExit(
                                Session.bearer(), visit.id, VisitExitRequest(true)
                            )
                            message = if (response.isSuccessful) {
                                "Salida registrada; puede regresar hoy."
                            } else mensajeDeError(response.code(), response.errorBody()?.string())
                            if (response.isSuccessful) {
                                pendingExit = null
                                load()
                            }
                        }
                    }
                }) { Text("Sí, regresa hoy") }
            },
            dismissButton = {
                TextButton(onClick = {
                    scope.launch {
                        runRegistryAction({ message = "No se pudo registrar la salida: $it" }) {
                            val response = RetrofitClient.api.registerVisitExit(
                                Session.bearer(), visit.id, VisitExitRequest(false)
                            )
                            message = if (response.isSuccessful) "Salida definitiva registrada."
                            else mensajeDeError(response.code(), response.errorBody()?.string())
                            if (response.isSuccessful) {
                                pendingExit = null
                                load()
                            }
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
                TextButton(onClick = { exitQrVisit(true) }) { Text("Sí, regresa hoy") }
            },
            dismissButton = {
                TextButton(onClick = { exitQrVisit(false) }) { Text("No, salida definitiva") }
            }
        )
    }
}

@Composable
private fun PackageListSection(
    packages: List<PackageItem>,
    modifier: Modifier,
    packageFilters: List<Pair<String, String?>>,
    statusFilter: String?,
    onStatusFilter: (String?) -> Unit,
    search: String,
    onSearch: (String) -> Unit,
    onRefresh: () -> Unit,
    onClearFilters: () -> Unit,
    canRegister: Boolean,
    onDeliver: (PackageItem) -> Unit,
    onMoveToTrash: (PackageItem) -> Unit,
    onRestore: (PackageItem) -> Unit,
    onArchiveAllDelivered: () -> Unit
) {
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        OutlinedTextField(
            value = search,
            onValueChange = onSearch,
            label = { Text("Buscar residente, apartamento o paquete") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Row(
            modifier = Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            packageFilters.forEach { (label, value) ->
                FilterChip(
                    selected = statusFilter == value,
                    onClick = { onStatusFilter(value) },
                    label = { Text(label) }
                )
            }
        }
        TextButton(onClick = onRefresh) { Text("Actualizar registros") }
        val isTrash = statusFilter == "papelera"
        val countDelivered = packages.count { it.status == "entregado" && !it.isDeleted }
        if (canRegister && countDelivered > 0 && !isTrash) {
            Button(
                onClick = onArchiveAllDelivered,
                modifier = Modifier.fillMaxWidth().heightIn(min = 40.dp)
            ) {
                Text("Archivar entregados ($countDelivered)")
            }
        }
        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            if (packages.isEmpty()) {
                item {
                    DomuxCard(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                        Column(
                            modifier = Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Text(
                                when {
                                    statusFilter == "papelera" ->
                                        "No hay paquetes archivados. Los paquetes entregados pasan aquí después de 7 días y se eliminan automáticamente a los 30 días."
                                    statusFilter != null || search.isNotBlank() ->
                                        "No hay paquetes que coincidan con el filtro o búsqueda actual."
                                    else -> "Aún no hay paquetes registrados en el sistema."
                                },
                                color = MaterialTheme.colorScheme.onSurface
                            )
                            if (statusFilter != null || search.isNotBlank()) {
                                TextButton(onClick = onClearFilters) {
                                    Text("Limpiar filtros y ver todos")
                                }
                            }
                        }
                    }
                }
            }
            items(packages, key = { "package-${it.id}" }) { item ->
                PackageRegistryCard(
                    item = item,
                    canRegister = canRegister,
                    onDeliver = { onDeliver(item) },
                    onMoveToTrash = { onMoveToTrash(item) },
                    onRestore = { onRestore(item) }
                )
            }
        }
    }
}

@Composable
private fun PackageRegistryCard(
    item: PackageItem,
    canRegister: Boolean,
    onDeliver: () -> Unit,
    onMoveToTrash: () -> Unit,
    onRestore: () -> Unit
) {
    DomuxCard(Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Text(item.description.orEmpty(), style = MaterialTheme.typography.titleMedium)
            Text("Para: ${item.residentName.orEmpty()} · ${item.apartment.orEmpty()}")
            val statusLabel = when (item.status) {
                "pendiente", "por_llegar" -> "En portería"
                else -> "Entregado"
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(item.createdAt.orEmpty(), style = MaterialTheme.typography.bodySmall)
                if (item.isDeleted) {
                    DomuxStatusBadge("Archivado", DomuxBadgeTone.ALERT)
                } else {
                    DomuxStatusBadge(
                        statusLabel,
                        if (item.status == "entregado") DomuxBadgeTone.SUCCESS
                        else DomuxBadgeTone.PROGRESS
                    )
                }
            }
            if (item.eventDate != null || item.eventTime != null) {
                Text("Registro: ${item.eventDate.orEmpty()} ${item.eventTime.orEmpty()}")
            }
            DomuxAttachmentPreview(item.mediaUrl, item.mediaType)
            if (item.status == "entregado" && !item.deliveredTo.isNullOrBlank()) {
                Text("Recibido por: ${item.deliveredTo}")
            }
            if (canRegister) {
                if (item.isDeleted) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        TextButton(onClick = onRestore) { Text("Restaurar") }
                    }
                } else {
                    if (Session.isGuard && item.status != "entregado") {
                        TextButton(onClick = onDeliver) { Text("Marcar entregado") }
                    }
                    TextButton(onClick = onMoveToTrash) { Text("Archivar") }
                }
            }
        }
    }
}

@Composable
private fun VisitListSection(
    modifier: Modifier,
    visits: List<Visit>,
    isResident: Boolean,
    isGuard: Boolean,
    onDecision: (Visit, String) -> Unit,
    onAuthorizeByCall: (Visit) -> Unit,
    onEntry: (Visit) -> Unit,
    onExit: (Visit) -> Unit,
    onAuthorizeAndEnter: (Visit) -> Unit = {},
    onScanQr: (() -> Unit)? = null,
    qrInspection: VisitQrInspectionResponse? = null,
    qrVisitorName: String = "",
    onQrVisitorNameChange: (String) -> Unit = {},
    onQrMessage: (String) -> Unit = {},
    onEnterQr: (String) -> Unit = {},
    onLinkVisit: (Visit) -> Unit = {},
    onQrExit: (Visit) -> Unit = {},
    onQrReentry: (Visit) -> Unit = {}
) {
    LazyColumn(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        if (isGuard) {
            item(key = "visit-qr-scan") {
                Button(
                    onClick = { onScanQr?.invoke() },
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                ) { Text("Escanear / Validar Código QR") }
            }
            qrInspection?.let { inspection ->
                item(key = "visit-qr-inspection") {
                    DomuxCard(Modifier.fillMaxWidth()) {
                        VisitQrInspectionContent(
                            inspection = inspection,
                            qrVisitorName = qrVisitorName,
                            onQrVisitorNameChange = onQrVisitorNameChange,
                            onMessage = onQrMessage,
                            onEnterQr = onEnterQr,
                            onLinkVisit = onLinkVisit,
                            onQrExit = onQrExit,
                            onQrReentry = onQrReentry
                        )
                    }
                }
            }
        }
        if (visits.isEmpty()) {
            item {
                DomuxCard(Modifier.fillMaxWidth()) {
                    Text(
                        "No hay visitas registradas.",
                        modifier = Modifier.padding(16.dp)
                    )
                }
            }
        }
        items(visits, key = { "visit-${it.id}" }) { visit ->
            VisitRegistryCard(
                visit = visit,
                isResident = isResident,
                isGuard = isGuard,
                onDecision = { onDecision(visit, it) },
                onAuthorizeByCall = { onAuthorizeByCall(visit) },
                onAuthorizeAndEnter = { onAuthorizeAndEnter(visit) },
                onEntry = { onEntry(visit) },
                onExit = { onExit(visit) }
            )
        }
    }
}

@Composable
private fun VisitRegistryCard(
    visit: Visit,
    isResident: Boolean,
    isGuard: Boolean,
    onDecision: (String) -> Unit,
    onAuthorizeByCall: () -> Unit,
    onAuthorizeAndEnter: () -> Unit,
    onEntry: () -> Unit,
    onExit: () -> Unit
) {
    var expanded by remember { mutableStateOf(false) }
    val context = LocalContext.current
    
    DomuxCard(Modifier.fillMaxWidth().padding(vertical = 5.dp)) {
        Column(
            modifier = Modifier.fillMaxWidth().animateContentSize()
        ) {
            Column(
                modifier = Modifier.fillMaxWidth().clickable { expanded = !expanded }.padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(5.dp)
            ) {
                val radicado = "VIS-${visit.createdAt?.take(4) ?: "2026"}-${visit.id.toString().padStart(4, '0')}"
                Text(radicado, style = MaterialTheme.typography.labelSmall, color = androidx.compose.ui.graphics.Color.Gray)
                Text(visit.visitorName, style = MaterialTheme.typography.titleMedium)
                Text("${visit.type.toDomuxDisplayLabel()} · ${visit.residentName.orEmpty()} · ${visit.apartment.orEmpty()}")
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(visit.approvalStatus.toDomuxDisplayLabel())
                    if (visit.enteredAt != null && (visit.exitedAt == null || visit.exitReturning)) {
                        if (visit.overstayWarning) {
                            DomuxStatusBadge("Plazo vencido (>${visit.maxStayHours}h)", DomuxBadgeTone.ALERT)
                        } else {
                            DomuxStatusBadge("En tiempo", DomuxBadgeTone.SUCCESS)
                        }
                    }
                }
            }
            if (expanded) {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(start = 14.dp, end = 14.dp, bottom = 14.dp),
                    verticalArrangement = Arrangement.spacedBy(5.dp)
                ) {
                    androidx.compose.material3.HorizontalDivider(Modifier.padding(vertical = 8.dp))
                    if (visit.documentRefused || visit.visitorDocument == "NO SUMINISTRADO") {
                        DomuxStatusBadge("Sin documento (Se negó)", DomuxBadgeTone.ALERT)
                    } else if (visit.mediaConsent && !visit.visitorDocument.isNullOrBlank()) {
                        Text("Documento: ${visit.visitorDocument}")
                    }
                    DomuxAttachmentPreview(visit.visitorPhotoUrl, visit.visitorPhotoType)
                    visit.description?.takeIf { it.isNotBlank() }?.let { Text("Pedido: $it") }
                    visit.enteredAt?.let { Text("Última entrada: $it") }
                    visit.exitedAt?.let { Text("Última salida: $it") }
                    Text(
                        "Autorización: " + when (visit.authorizationMethod) {
                            "llamada" -> "por llamada"
                            "qr" -> "por QR"
                            "app" -> "desde la app"
                            else -> "pendiente"
                        }
                    )
                    visit.events.orEmpty().forEach { event ->
                        Text(
                            "${event.type.toDomuxDisplayLabel()} · ${event.createdAt.orEmpty()} · " +
                                "${event.method.toDomuxDisplayLabel()} · ${event.actorName.orEmpty()}",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    if (isResident && visit.approvalStatus == "pendiente") {
                        Row(
                            modifier = Modifier.horizontalScroll(rememberScrollState()),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            TextButton(onClick = { onDecision("aprobada") }) { Text("Autorizar") }
                            TextButton(onClick = { onDecision("rechazada") }) { Text("Rechazar") }
                        }
                    }
                    if (isGuard && visit.approvalStatus == "pendiente") {
                        Column(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.padding(top = 8.dp)) {
                            Button(
                                onClick = onAuthorizeAndEnter,
                                modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                            ) { Text("Autorizar e ingresar") }
                            OutlinedButton(
                                onClick = {
                                    val phone = visit.residentPhone?.filter { it.isDigit() }
                                    if (phone.isNullOrEmpty()) {
                                        android.widget.Toast.makeText(context, "Este residente no tiene teléfono registrado", android.widget.Toast.LENGTH_SHORT).show()
                                    } else {
                                        try {
                                            val intent = android.content.Intent(android.content.Intent.ACTION_DIAL, android.net.Uri.parse("tel:$phone"))
                                            context.startActivity(intent)
                                        } catch (e: Exception) {
                                            android.widget.Toast.makeText(context, "No se pudo iniciar la llamada: ${e.message}", android.widget.Toast.LENGTH_SHORT).show()
                                        }
                                    }
                                },
                                modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                            ) { Text("Llamar al residente") }
                            TextButton(
                                onClick = onAuthorizeByCall,
                                modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                            ) { Text("Confirmar autorización por llamada") }
                        }
                    }
                    if (isGuard && visit.approvalStatus == "aprobada") {
                        Column(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.padding(top = 8.dp)) {
                            if (visit.overstayWarning) {
                                OutlinedButton(
                                    onClick = {
                                        val phone = visit.residentPhone?.filter { it.isDigit() }
                                        if (phone.isNullOrEmpty()) {
                                            android.widget.Toast.makeText(context, "Este residente no tiene teléfono registrado", android.widget.Toast.LENGTH_SHORT).show()
                                        } else {
                                            try {
                                                val intent = android.content.Intent(android.content.Intent.ACTION_DIAL, android.net.Uri.parse("tel:$phone"))
                                                context.startActivity(intent)
                                            } catch (e: Exception) {
                                                android.widget.Toast.makeText(context, "No se pudo iniciar la llamada: ${e.message}", android.widget.Toast.LENGTH_SHORT).show()
                                            }
                                        }
                                    },
                                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                                ) { Text("Llamar al residente (vencido)") }
                            }
                            if (visit.enteredAt == null || (visit.exitedAt != null && visit.exitReturning)) {
                                Button(onClick = onEntry, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                                    Text("Registrar entrada")
                                }
                            } else if (visit.exitedAt != null && !visit.exitReturning) {
                                Text("Salida definitiva. Si vuelve, registra una nueva solicitud.")
                            } else {
                                OutlinedButton(onClick = onExit, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                                    Text("Registrar salida")
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun VisitQrInspectionContent(
    inspection: VisitQrInspectionResponse,
    qrVisitorName: String,
    onQrVisitorNameChange: (String) -> Unit,
    onMessage: (String) -> Unit,
    onEnterQr: (String) -> Unit,
    onLinkVisit: (Visit) -> Unit,
    onQrExit: (Visit) -> Unit,
    onQrReentry: (Visit) -> Unit
) {
    Column(
        modifier = Modifier.fillMaxWidth().padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Text("${inspection.residentName.orEmpty()} · ${inspection.apartment.orEmpty()}")
        Text("Nombre pre-registrado: ${inspection.qrPass?.visitorName.orEmpty().ifBlank { "—" }}")
        Text("Documento pre-registrado: ${inspection.qrPass?.visitorDocument.orEmpty().ifBlank { "—" }}")
        Text(
            "Cupos usados: ${inspection.qrPass?.usedEntries ?: 0} / " +
                "${inspection.qrPass?.maxGuests ?: 0}"
        )
        if (!inspection.canRegister) {
            Text("Este QR está vencido o revocado: solo se permite registrar la salida.")
        }
        OutlinedTextField(
            value = qrVisitorName,
            onValueChange = onQrVisitorNameChange,
            label = { Text("Nombre del visitante que ingresa") },
            enabled = inspection.canRegister,
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Button(
            onClick = {
                if (qrVisitorName.isBlank()) onMessage("Escribe el nombre del visitante.")
                else onEnterQr(qrVisitorName)
            },
            enabled = inspection.canRegister,
            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
        ) { Text("Registrar ingreso") }
        if (inspection.linkableVisits.orEmpty().isNotEmpty()) {
            Text("O vincular un visitante ya registrado:")
            inspection.linkableVisits.orEmpty().forEach { visit ->
                OutlinedButton(
                    enabled = inspection.canRegister,
                    onClick = { onLinkVisit(visit) },
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                ) { Text("${visit.visitorName} · vincular e ingresar") }
            }
        }
        inspection.inside.orEmpty().forEach { visit ->
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("${visit.visitorName} está dentro")
                TextButton(onClick = { onQrExit(visit) }) { Text("Salida") }
            }
        }
        inspection.registeredVisits.orEmpty()
            .filter { it.exitedAt != null }
            .forEach { visit ->
                TextButton(
                    enabled = inspection.canRegister,
                    onClick = { onQrReentry(visit) }
                ) { Text("Reingreso: ${visit.visitorName}") }
            }
    }
}

@Composable
private fun PackageRegistrationSection(
    modifier: Modifier,
    resident: ResidentSummary?,
    onResidentChange: (ResidentSummary?) -> Unit,
    description: String,
    onDescriptionChange: (String) -> Unit,
    date: String,
    onDateChange: (String) -> Unit,
    time: String,
    onTimeChange: (String) -> Unit,
    mediaName: String?,
    onMedia: (String, String, String) -> Unit,
    onMessage: (String) -> Unit,
    attempted: Boolean,
    onRegister: () -> Unit
) {
    Column(
        modifier = modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        DomuxCard(Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Text("Registrar paquete", style = MaterialTheme.typography.titleMedium)
                DomuxResidentSearchField(resident, onResidentChange)
                OutlinedTextField(
                    value = description,
                    onValueChange = onDescriptionChange,
                    label = { Text("Descripción *") },
                    isError = attempted && description.isBlank(),
                    supportingText = {
                        if (attempted && description.isBlank()) Text("La descripción es obligatoria")
                    },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                Text(
                    "Fecha y hora de llegada: Hoy · ${java.text.SimpleDateFormat("HH:mm", java.util.Locale.US).format(java.util.Date())} (registro automático)",
                    style = MaterialTheme.typography.bodySmall,
                    color = androidx.compose.ui.graphics.Color.Gray
                )
                MediaAttachmentPicker(
                    mediaName,
                    { url, type, name -> onMedia(url, type, name) },
                    onMessage
                )
                Button(
                    onClick = onRegister,
                    modifier = Modifier.fillMaxWidth()
                ) { Text("Registrar paquete") }
            }
        }
    }
}

@Composable
private fun RegistrationAndQrSection(
    modifier: Modifier,
    resident: ResidentSummary?,
    onResidentChange: (ResidentSummary?) -> Unit,
    visitorName: String,
    onVisitorNameChange: (String) -> Unit,
    visitorDocument: String,
    onVisitorDocumentChange: (String) -> Unit,
    visitorType: String,
    onVisitorTypeChange: (String) -> Unit,
    documentRefused: Boolean,
    onDocumentRefusedChange: (Boolean) -> Unit,
    visitorPhotoName: String?,
    onVisitorPhoto: (String, String, String) -> Unit,
    visitDescription: String,
    onVisitDescriptionChange: (String) -> Unit,
    attemptedVisit: Boolean,
    onMessage: (String) -> Unit,
    onRegisterVisit: () -> Unit,
    isGuard: Boolean,
    scanner: () -> Unit,
    qrInspection: VisitQrInspectionResponse?,
    qrVisitorName: String,
    onQrVisitorNameChange: (String) -> Unit,
    onEnterQr: (String) -> Unit,
    onLinkVisit: (Visit) -> Unit,
    onQrExit: (Visit) -> Unit,
    onQrReentry: (Visit) -> Unit
) {
    Column(
        modifier = modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        DomuxCard(Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Text("Registrar visita", style = MaterialTheme.typography.titleMedium)
                DomuxResidentSearchField(resident, onResidentChange)
                OutlinedTextField(
                    value = visitorName,
                    onValueChange = onVisitorNameChange,
                    label = { Text("Nombre del visitante *") },
                    isError = attemptedVisit && visitorName.isBlank(),
                    supportingText = {
                        if (attemptedVisit && visitorName.isBlank()) Text("El nombre es obligatorio")
                    },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    listOf("visitante", "domiciliario", "contratista").forEach { type ->
                        FilterChip(
                            selected = visitorType == type,
                            onClick = { onVisitorTypeChange(type) },
                            label = { Text(type.toDomuxDisplayLabel()) }
                        )
                    }
                }
                if (visitorType == "domiciliario") {
                    OutlinedTextField(
                        value = visitDescription,
                        onValueChange = onVisitDescriptionChange,
                        label = { Text("Detalles del pedido (opcional)") },
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                OutlinedTextField(
                    value = visitorDocument,
                    onValueChange = onVisitorDocumentChange,
                    label = { Text("Documento de identidad del visitante *") },
                    enabled = !documentRefused,
                    isError = attemptedVisit && !documentRefused && visitorDocument.isBlank(),
                    supportingText = {
                        if (attemptedVisit && !documentRefused && visitorDocument.isBlank()) {
                            Text("El documento es obligatorio, salvo que se marque la excepción.")
                        }
                    },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(
                        checked = documentRefused,
                        onCheckedChange = onDocumentRefusedChange
                    )
                    Text("El visitante se negó a entregar documento de identidad (Excepción)")
                }
                MediaAttachmentPicker(
                    visitorPhotoName,
                    { url, type, name -> onVisitorPhoto(url, type, name) },
                    "image/*",
                    onMessage
                )
                Button(
                    onClick = onRegisterVisit,
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                ) {
                    Text("Registrar visita")
                }
            }
        }

        if (isGuard) {
            DomuxCard(Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Text("Ingreso y salida por QR", style = MaterialTheme.typography.titleMedium)
                    Button(
                        onClick = scanner,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                    ) {
                        Text("Escanear QR")
                    }
                    qrInspection?.let { inspection ->
                        Text("${inspection.residentName.orEmpty()} · ${inspection.apartment.orEmpty()}")
                        Text("Nombre pre-registrado: ${inspection.qrPass?.visitorName.orEmpty().ifBlank { "—" }}")
                        Text("Documento pre-registrado: ${inspection.qrPass?.visitorDocument.orEmpty().ifBlank { "—" }}")
                        Text(
                            "Cupos usados: ${inspection.qrPass?.usedEntries ?: 0} / " +
                                "${inspection.qrPass?.maxGuests ?: 0}"
                        )
                        if (!inspection.canRegister) {
                            Text("Este QR está vencido o revocado: solo se permite registrar la salida.")
                        }
                        OutlinedTextField(
                            value = qrVisitorName,
                            onValueChange = onQrVisitorNameChange,
                            label = { Text("Nombre del visitante que ingresa") },
                            enabled = inspection.canRegister,
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth()
                        )
                        Button(
                            onClick = {
                                if (qrVisitorName.isBlank()) onMessage("Escribe el nombre del visitante.")
                                else onEnterQr(qrVisitorName)
                            },
                            enabled = inspection.canRegister,
                            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                        ) { Text("Registrar ingreso") }
                        if (inspection.linkableVisits.orEmpty().isNotEmpty()) {
                            Text("O vincular un visitante ya registrado:")
                            inspection.linkableVisits.orEmpty().forEach { visit ->
                                OutlinedButton(
                                    enabled = inspection.canRegister,
                                    onClick = { onLinkVisit(visit) },
                                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                                ) { Text("${visit.visitorName} · vincular e ingresar") }
                            }
                        }
                        inspection.inside.orEmpty().forEach { visit ->
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text("${visit.visitorName} está dentro")
                                TextButton(onClick = { onQrExit(visit) }) { Text("Salida") }
                            }
                        }
                        inspection.registeredVisits.orEmpty()
                            .filter { it.exitedAt != null }
                            .forEach { visit ->
                                TextButton(
                                    enabled = inspection.canRegister,
                                    onClick = { onQrReentry(visit) }
                                ) { Text("Reingreso: ${visit.visitorName}") }
                            }
                    }
                }
            }
        }
    }
}

@Composable
private fun ResidentQrPassSection(
    modifier: Modifier,
    resident: ResidentSummary? = null,
    onResidentChange: (ResidentSummary?) -> Unit = {},
    startDate: String,
    onStartDateChange: (String) -> Unit,
    endDate: String,
    onEndDateChange: (String) -> Unit,
    visitorNames: List<String>,
    onVisitorNameChange: (Int, String) -> Unit,
    visitorDocuments: List<String>,
    onVisitorDocumentChange: (Int, String) -> Unit,
    maxGuests: Int,
    onMaxGuestsChange: (Int) -> Unit,
    attemptedCreate: Boolean,
    passes: List<VisitQrPass>,
    activePass: VisitQrPass?,
    qrBitmap: android.graphics.Bitmap?,
    onCreate: () -> Unit,
    onSelectPass: (VisitQrPass) -> Unit,
    onRevokePass: (VisitQrPass) -> Unit,
    onClosePass: () -> Unit
) {
    Column(
        modifier = modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        DomuxCard(Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text("Código QR para visitas", style = MaterialTheme.typography.titleMedium)
            
            if (Session.isAdmin) {
                DomuxResidentSearchField(
                    selectedResident = resident,
                    onSelectResident = onResidentChange
                )
            }
            
            Text("Vigencia máxima: 72 horas (por defecto 24 h).")
                Text("Cantidad de personas")
                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    (1..5).forEach { count ->
                        FilterChip(
                            selected = maxGuests == count,
                            onClick = { onMaxGuestsChange(count) },
                            label = { Text(count.toString()) }
                        )
                    }
                }
                (0 until maxGuests).forEach { index ->
                    Text("Visitante ${index + 1}", style = MaterialTheme.typography.labelLarge)
                    OutlinedTextField(
                        value = visitorNames[index],
                        onValueChange = { onVisitorNameChange(index, it) },
                        label = { Text("Nombre completo *") },
                        isError = attemptedCreate && visitorNames[index].isBlank(),
                        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words),
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = visitorDocuments[index],
                        onValueChange = { onVisitorDocumentChange(index, it) },
                        label = { Text("Documento de identidad *") },
                        isError = attemptedCreate && visitorDocuments[index].isBlank(),
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                Button(
                    onClick = onCreate,
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                ) {
                    Text("Crear QR")
                }
                passes.forEach { pass ->
                    DomuxCard(
                        modifier = Modifier.fillMaxWidth().clickable { onSelectPass(pass) }
                    ) {
                        Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                            Text(pass.visitorName ?: "Visitantes", fontWeight = FontWeight.Bold)
                            Text("Vigencia: ${pass.validFrom} al ${pass.validUntil}", style = MaterialTheme.typography.bodySmall)
                            val remaining = pass.remainingEntries
                            Text(if (remaining == 1) "1 cupo disponible" else "$remaining cupos disponibles", color = androidx.compose.ui.graphics.Color(0xFF38BDF8))
                            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                                TextButton(onClick = { onSelectPass(pass) }) { Text("Ver QR") }
                                if (!pass.revoked) {
                                    TextButton(onClick = { onRevokePass(pass) }) { Text("Revocar", color = MaterialTheme.colorScheme.error) }
                                }
                            }
                        }
                    }
                }
                val context = LocalContext.current
                activePass?.let { pass ->
                    androidx.compose.material3.AlertDialog(
                        onDismissRequest = onClosePass,
                        confirmButton = {
                            TextButton(onClick = { 
                                qrBitmap?.let { bmp ->
                                    try {
                                        val finalBitmap = android.graphics.Bitmap.createBitmap(bmp.width, bmp.height + 180, android.graphics.Bitmap.Config.ARGB_8888)
                                        val canvas = android.graphics.Canvas(finalBitmap)
                                        canvas.drawColor(android.graphics.Color.WHITE)
                                        val paint = android.graphics.Paint().apply {
                                            color = android.graphics.Color.BLACK
                                            textSize = 40f
                                            textAlign = android.graphics.Paint.Align.CENTER
                                            isAntiAlias = true
                                            isFakeBoldText = true
                                        }
                                        canvas.drawText("Pase de acceso DOMUX", bmp.width / 2f, 60f, paint)
                                        paint.textSize = 30f
                                        paint.isFakeBoldText = false
                                        canvas.drawText(pass.visitorName ?: "Visitante", bmp.width / 2f, 110f, paint)
                                        paint.textSize = 24f
                                        canvas.drawText("Válido: ${pass.validFrom} al ${pass.validUntil}", bmp.width / 2f, 150f, paint)
                                        canvas.drawBitmap(bmp, 0f, 180f, null)

                                        val newFile = java.io.File(context.cacheDir, "qr_pass.png")
                                        val stream = java.io.FileOutputStream(newFile)
                                        finalBitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, stream)
                                        stream.close()

                                        val contentUri = androidx.core.content.FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", newFile)
                                        val shareIntent = android.content.Intent().apply {
                                            action = android.content.Intent.ACTION_SEND
                                            addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION)
                                            setDataAndType(contentUri, "image/png")
                                            putExtra(android.content.Intent.EXTRA_STREAM, contentUri)
                                        }
                                        context.startActivity(android.content.Intent.createChooser(shareIntent, "Compartir QR"))
                                    } catch (e: Exception) {
                                        e.printStackTrace()
                                    }
                                }
                            }) { Text("Compartir QR") }
                        },
                        dismissButton = { TextButton(onClick = onClosePass) { Text("Cerrar") } },
                        title = { Text("Pase de acceso") },
                        text = {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Text("Código activo · ${pass.remainingEntries} cupos disponibles")
                                qrBitmap?.let {
                                    Image(
                                        bitmap = it.asImageBitmap(),
                                        contentDescription = "Código QR de visitas",
                                        modifier = Modifier.size(240.dp)
                                    )
                                }
                            }
                        }
                    )
                }
            }
        }
    }
}

private suspend fun refreshQrInspection(
    token: String,
    onUpdate: (VisitQrInspectionResponse?) -> Unit
) {
    val response = RetrofitClient.api.inspectVisitQr(Session.bearer(), token)
    if (response.isSuccessful) onUpdate(response.body())
}
