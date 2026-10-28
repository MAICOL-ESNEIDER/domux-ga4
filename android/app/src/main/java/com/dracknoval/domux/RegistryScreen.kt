package com.dracknoval.domux

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.Image
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
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
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
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
import com.dracknoval.domux.data.UpdatePackageStatusRequest
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
import java.util.Date
import java.util.Locale

private fun isCancellation(e: Throwable): Boolean =
    e is CancellationException ||
        e.message?.contains("left the composition", ignoreCase = true) == true

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
fun RegistryScreen(navController: NavController) {
    val canRegister = Session.isGuard || Session.isAdmin
    val scope = rememberCoroutineScope()
    var packages by remember { mutableStateOf<List<PackageItem>>(emptyList()) }
    var visits by remember { mutableStateOf<List<Visit>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var message by remember { mutableStateOf("") }
    var search by remember { mutableStateOf("") }
    var statusFilter by remember { mutableStateOf<String?>(null) }
    var selectedTab by remember { mutableStateOf(0) }

    var selectedPackageResident by remember { mutableStateOf<ResidentSummary?>(null) }
    var packageDescription by remember { mutableStateOf("") }
    var packageStatus by remember { mutableStateOf("pendiente") }
    var packageDate by remember { mutableStateOf("") }
    var packageTime by remember { mutableStateOf("") }
    var mediaUrl by remember { mutableStateOf<String?>(null) }
    var mediaType by remember { mutableStateOf<String?>(null) }
    var mediaName by remember { mutableStateOf<String?>(null) }
    var attemptedPackage by remember { mutableStateOf(false) }

    var selectedVisitResident by remember { mutableStateOf<ResidentSummary?>(null) }
    var visitorName by remember { mutableStateOf("") }
    var visitorDocument by remember { mutableStateOf("") }
    var visitorType by remember { mutableStateOf("visitante") }
    var visitorConsent by remember { mutableStateOf(false) }
    var visitorPhotoUrl by remember { mutableStateOf<String?>(null) }
    var visitorPhotoType by remember { mutableStateOf<String?>(null) }
    var visitorPhotoName by remember { mutableStateOf<String?>(null) }
    var visitDescription by remember { mutableStateOf("") }
    var attemptedVisit by remember { mutableStateOf(false) }

    var deliveryPackage by remember { mutableStateOf<PackageItem?>(null) }
    var receiverName by remember { mutableStateOf("") }
    var pendingExit by remember { mutableStateOf<Visit?>(null) }
    var pendingQrExit by remember { mutableStateOf<Visit?>(null) }
    var confirmation by remember { mutableStateOf<Pair<String, () -> Unit>?>(null) }

    var qrPasses by remember { mutableStateOf<List<VisitQrPass>>(emptyList()) }
    var activeQrPass by remember { mutableStateOf<VisitQrPass?>(null) }
    var qrBitmap by remember { mutableStateOf<android.graphics.Bitmap?>(null) }
    var qrStartDate by remember {
        mutableStateOf(SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date()))
    }
    var qrEndDate by remember {
        mutableStateOf(SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date()))
    }
    var qrMaxPeople by remember { mutableStateOf("5") }
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

    val packageFilters = buildList {
        add("Todos" to null)
        add("En portería" to "pendiente")
        add("Por llegar" to "por_llegar")
        add("Entregados" to "entregado")
        if (canRegister) add("Papelera" to "papelera")
    }
    val tabs = if (Session.isResident) {
        listOf("Mis paquetes", "Mis visitas", "Código QR")
    } else {
        listOf("Paquetes", "Registrar paquete", "Visitas", "Registrar visita / QR")
    }
    val title = when {
        Session.isResident -> "Mis paquetes y visitas"
        Session.isGuard -> "Control de portería"
        else -> "Paquetería y visitas"
    }

    DomuxScreenScaffold(title = title, navController = navController) { scaffoldPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(scaffoldPadding)
                .padding(horizontal = 16.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            DomuxSectionTabs(tabs, selectedTab.coerceIn(tabs.indices)) { selectedTab = it }
            if (message.isNotBlank()) {
                DomuxFeedbackBanner(message) { message = "" }
            }
            if (loading) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())

            when {
                canRegister && selectedTab == 0 -> {
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
                        onStatusChange = { item, status ->
                            scope.launch {
                                runRegistryAction({ message = "No se pudo actualizar el estado: $it" }) {
                                    val response = RetrofitClient.api.updatePackageStatus(
                                        Session.bearer(), item.id, UpdatePackageStatusRequest(status)
                                    )
                                    if (response.isSuccessful) {
                                        message = "Estado del paquete actualizado."
                                        load()
                                    } else {
                                        message = mensajeDeError(response.code(), response.errorBody()?.string())
                                    }
                                }
                            }
                        },
                        onMoveToTrash = { item ->
                            confirmation = "¿Mover este paquete a la papelera?" to {
                                scope.launch {
                                    runRegistryAction({ message = "No se pudo mover el paquete: $it" }) {
                                        val response = RetrofitClient.api.deletePackage(
                                            Session.bearer(), item.id, force = false
                                        )
                                        message = if (response.isSuccessful) {
                                            response.body()?.message ?: "Paquete movido a la papelera."
                                        } else mensajeDeError(response.code(), response.errorBody()?.string())
                                        if (response.isSuccessful) load()
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
                        onDeletePermanently = { item ->
                            confirmation = "¿Eliminar permanentemente este paquete? Esta acción no se puede deshacer." to {
                                scope.launch {
                                    runRegistryAction({ message = "No se pudo eliminar el paquete: $it" }) {
                                        val response = RetrofitClient.api.deletePackage(
                                            Session.bearer(), item.id, force = true
                                        )
                                        message = if (response.isSuccessful) {
                                            response.body()?.message ?: "Paquete eliminado permanentemente."
                                        } else mensajeDeError(response.code(), response.errorBody()?.string())
                                        if (response.isSuccessful) load()
                                    }
                                }
                            }
                        }
                    )
                }

                canRegister && selectedTab == 1 -> {
                    PackageRegistrationSection(
                        modifier = Modifier.weight(1f),
                        resident = selectedPackageResident,
                        onResidentChange = { selectedPackageResident = it },
                        description = packageDescription,
                        onDescriptionChange = { packageDescription = it },
                        status = packageStatus,
                        onStatusChange = { packageStatus = it },
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
                                                    status = packageStatus
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

                canRegister && selectedTab == 2 -> {
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
                        onExit = { pendingExit = it }
                    )
                }

                canRegister && selectedTab == 3 -> {
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
                        visitorConsent = visitorConsent,
                        onVisitorConsentChange = { consent ->
                            visitorConsent = consent
                            if (!consent) {
                                visitorDocument = ""
                                visitorPhotoUrl = null
                                visitorPhotoType = null
                                visitorPhotoName = null
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
                                                mediaConsent = visitorConsent,
                                                mediaUrl = if (visitorConsent) visitorPhotoUrl else null,
                                                mediaType = if (visitorConsent) visitorPhotoType else null,
                                                description = visitDescription.trim().ifEmpty { null }
                                            )
                                        )
                                        if (response.isSuccessful) {
                                            message = "Registro enviado. El residente recibirá una solicitud para autorizar el ingreso."
                                            visitorName = ""
                                            visitorDocument = ""
                                            visitorConsent = false
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
                        scanner = { scanner.launch(
                            ScanOptions()
                                .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                                .setPrompt("Escanea el QR de visitas")
                        ) },
                        qrInspection = qrInspection,
                        qrVisitorName = qrVisitorName,
                        onQrVisitorNameChange = { qrVisitorName = it },
                        onEnterQr = { enterQrVisitor ->
                            val token = scannedQrToken
                            if (token != null) {
                                scope.launch {
                                    runRegistryAction({ message = "No se pudo registrar el ingreso QR: $it" }) {
                                        val response = RetrofitClient.api.enterVisitQr(
                                            Session.bearer(),
                                            token,
                                            QrVisitorEntryRequest(visitorName = enterQrVisitor.trim())
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
                        },
                        onLinkVisit = { visit ->
                            val token = scannedQrToken
                            if (token != null) {
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
                        },
                        onQrExit = { pendingQrExit = it },
                        onQrReentry = { visit ->
                            val token = scannedQrToken
                            if (token != null) {
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
                        }
                    )
                }

                Session.isResident && selectedTab == 0 -> {
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
                        onStatusChange = { _, _ -> },
                        onMoveToTrash = {},
                        onRestore = {},
                        onDeletePermanently = {}
                    )
                }

                Session.isResident && selectedTab == 1 -> {
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

                Session.isResident && selectedTab == 2 -> {
                    ResidentQrPassSection(
                        modifier = Modifier.weight(1f),
                        startDate = qrStartDate,
                        onStartDateChange = { qrStartDate = it },
                        endDate = qrEndDate,
                        onEndDateChange = { qrEndDate = it },
                        maxPeople = qrMaxPeople,
                        onMaxPeopleChange = { qrMaxPeople = it.filter(Char::isDigit) },
                        passes = qrPasses,
                        activePass = activeQrPass,
                        qrBitmap = qrBitmap,
                        onCreate = {
                            val limit = qrMaxPeople.toIntOrNull()
                            if (limit == null || limit < 1) {
                                message = "El límite de personas debe ser mayor que cero."
                            } else {
                                scope.launch {
                                    runRegistryAction({ message = "No se pudo crear el QR: $it" }) {
                                        val response = RetrofitClient.api.createVisitQrPass(
                                            Session.bearer(),
                                            CreateVisitQrPassRequest(qrStartDate, qrEndDate, limit)
                                        )
                                        if (response.isSuccessful) {
                                            activeQrPass = response.body()?.qrPass
                                            message = "Código QR creado."
                                            load()
                                        } else {
                                            message = mensajeDeError(response.code(), response.errorBody()?.string())
                                        }
                                    }
                                }
                            }
                        },
                        onSelectPass = { activeQrPass = it },
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
                        }
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
                Column {
                    Text("¿A quién se entregó ${item.description.orEmpty()}?")
                    OutlinedTextField(
                        value = receiverName,
                        onValueChange = { receiverName = it },
                        label = { Text("Nombre de quien recibe") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                }
            },
            confirmButton = {
                TextButton(
                    enabled = receiverName.isNotBlank(),
                    onClick = {
                        scope.launch {
                            runRegistryAction({ message = "No se pudo entregar el paquete: $it" }) {
                                val response = RetrofitClient.api.deliverPackage(
                                    Session.bearer(), item.id, DeliverPackageRequest(receiverName.trim())
                                )
                                message = if (response.isSuccessful) {
                                    "Paquete entregado a ${receiverName.trim()}."
                                } else mensajeDeError(response.code(), response.errorBody()?.string())
                                if (response.isSuccessful) {
                                    deliveryPackage = null
                                    receiverName = ""
                                    load()
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
    onStatusChange: (PackageItem, String) -> Unit,
    onMoveToTrash: (PackageItem) -> Unit,
    onRestore: (PackageItem) -> Unit,
    onDeletePermanently: (PackageItem) -> Unit
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
                                        "La papelera está vacía. Los paquetes entregados pasan aquí después de 7 días y se eliminan automáticamente a los 30 días."
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
                    onStatusChange = { onStatusChange(item, it) },
                    onMoveToTrash = { onMoveToTrash(item) },
                    onRestore = { onRestore(item) },
                    onDeletePermanently = { onDeletePermanently(item) }
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
    onStatusChange: (String) -> Unit,
    onMoveToTrash: () -> Unit,
    onRestore: () -> Unit,
    onDeletePermanently: () -> Unit
) {
    DomuxCard(Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
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
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(item.createdAt.orEmpty(), style = MaterialTheme.typography.bodySmall)
                if (item.isDeleted) {
                    DomuxStatusBadge("En papelera", DomuxBadgeTone.ALERT)
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
            MediaAttachmentChip(item.mediaUrl, item.mediaType)
            if (item.status == "entregado" && !item.deliveredTo.isNullOrBlank()) {
                Text("Recibido por: ${item.deliveredTo}")
            }
            if (canRegister) {
                if (item.isDeleted) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        TextButton(onClick = onRestore) { Text("Restaurar") }
                        TextButton(onClick = onDeletePermanently) { Text("Eliminar definitivo") }
                    }
                } else {
                    if (item.status == "por_llegar") {
                        TextButton(onClick = { onStatusChange("pendiente") }) {
                            Text("Recibir en portería")
                        }
                    }
                    if (item.status != "entregado") {
                        TextButton(onClick = onDeliver) { Text("Marcar entregado") }
                    }
                    TextButton(onClick = onMoveToTrash) { Text("Enviar a papelera") }
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
    onExit: (Visit) -> Unit
) {
    LazyColumn(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(6.dp)
    ) {
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
    onEntry: () -> Unit,
    onExit: () -> Unit
) {
    DomuxCard(Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(5.dp)
        ) {
            Text(visit.visitorName, style = MaterialTheme.typography.titleMedium)
            Text("${visit.type} · ${visit.createdAt.orEmpty()} · ${visit.approvalStatus}")
            Text("Para: ${visit.residentName.orEmpty()} · ${visit.apartment.orEmpty()}")
            if (visit.mediaConsent && !visit.visitorDocument.isNullOrBlank()) {
                Text("Documento: ${visit.visitorDocument}")
            }
            MediaAttachmentChip(visit.visitorPhotoUrl, visit.visitorPhotoType)
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
                    "${event.type} · ${event.createdAt.orEmpty()} · " +
                        "${event.method} · ${event.actorName.orEmpty()}",
                    style = MaterialTheme.typography.bodySmall
                )
            }
            if (isResident && visit.approvalStatus == "pendiente") {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextButton(onClick = { onDecision("aprobada") }) { Text("Autorizar") }
                    TextButton(onClick = { onDecision("rechazada") }) { Text("Rechazar") }
                }
            }
            if (isGuard && visit.approvalStatus == "pendiente") {
                TextButton(onClick = onAuthorizeByCall) { Text("Autorizar por llamada") }
            }
            if (isGuard && visit.approvalStatus == "aprobada") {
                if (visit.enteredAt == null || (visit.exitedAt != null && visit.exitReturning)) {
                    TextButton(onClick = onEntry) { Text("Registrar entrada") }
                } else if (visit.exitedAt != null && !visit.exitReturning) {
                    Text("Salida definitiva. Si vuelve, registra una nueva solicitud.")
                } else {
                    TextButton(onClick = onExit) { Text("Registrar salida") }
                }
            }
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
    status: String,
    onStatusChange: (String) -> Unit,
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
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(
                        selected = status == "pendiente",
                        onClick = { onStatusChange("pendiente") },
                        label = { Text("En portería") }
                    )
                    FilterChip(
                        selected = status == "por_llegar",
                        onClick = { onStatusChange("por_llegar") },
                        label = { Text("Por llegar") }
                    )
                }
                DatePickerField("Fecha del paquete", date, onDateChange)
                TimePickerField("Hora del paquete", time, onTimeChange)
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
    visitorConsent: Boolean,
    onVisitorConsentChange: (Boolean) -> Unit,
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
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    listOf("visitante", "domiciliario", "contratista").forEach { type ->
                        FilterChip(
                            selected = visitorType == type,
                            onClick = { onVisitorTypeChange(type) },
                            label = { Text(type.replaceFirstChar(Char::uppercase)) }
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
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = visitorConsent, onCheckedChange = onVisitorConsentChange)
                    Text("El visitante autoriza guardar su documento o foto (opcional)")
                }
                if (visitorConsent) {
                    OutlinedTextField(
                        value = visitorDocument,
                        onValueChange = onVisitorDocumentChange,
                        label = { Text("Documento (opcional)") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    MediaAttachmentPicker(
                        visitorPhotoName,
                        { url, type, name -> onVisitorPhoto(url, type, name) },
                        "image/*",
                        onMessage
                    )
                }
                Button(onClick = onRegisterVisit, modifier = Modifier.fillMaxWidth()) {
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
                    Button(onClick = scanner, modifier = Modifier.fillMaxWidth()) {
                        Text("Escanear QR")
                    }
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
                            modifier = Modifier.fillMaxWidth()
                        ) { Text("Registrar ingreso") }
                        if (inspection.linkableVisits.orEmpty().isNotEmpty()) {
                            Text("O vincular un visitante ya registrado:")
                            inspection.linkableVisits.orEmpty().forEach { visit ->
                                TextButton(
                                    enabled = inspection.canRegister,
                                    onClick = { onLinkVisit(visit) }
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
    startDate: String,
    onStartDateChange: (String) -> Unit,
    endDate: String,
    onEndDateChange: (String) -> Unit,
    maxPeople: String,
    onMaxPeopleChange: (String) -> Unit,
    passes: List<VisitQrPass>,
    activePass: VisitQrPass?,
    qrBitmap: android.graphics.Bitmap?,
    onCreate: () -> Unit,
    onSelectPass: (VisitQrPass) -> Unit,
    onRevokePass: (VisitQrPass) -> Unit
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
                Text("Duración máxima: 30 días. Cada persona distinta consume un cupo.")
                OutlinedTextField(
                    value = startDate,
                    onValueChange = onStartDateChange,
                    label = { Text("Válido desde (AAAA-MM-DD)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(
                    value = endDate,
                    onValueChange = onEndDateChange,
                    label = { Text("Válido hasta (AAAA-MM-DD)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(
                    value = maxPeople,
                    onValueChange = onMaxPeopleChange,
                    label = { Text("Límite de personas") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                Button(onClick = onCreate, modifier = Modifier.fillMaxWidth()) {
                    Text("Crear QR")
                }
                passes.forEach { pass ->
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        TextButton(onClick = { onSelectPass(pass) }) {
                            Text(
                                "${pass.validFrom} a ${pass.validUntil} · " +
                                    "${pass.registeredPeople}/${pass.maxPeople}"
                            )
                        }
                        if (!pass.revoked) {
                            TextButton(onClick = { onRevokePass(pass) }) { Text("Revocar") }
                        }
                    }
                }
                activePass?.let { pass ->
                    Text("Código activo · ${pass.remainingPeople} cupos disponibles")
                    qrBitmap?.let {
                        Image(
                            bitmap = it.asImageBitmap(),
                            contentDescription = "Código QR de visitas",
                            modifier = Modifier
                                .size(220.dp)
                                .align(Alignment.CenterHorizontally)
                        )
                    }
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
