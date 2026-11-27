package com.dracknoval.domux

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
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
import com.dracknoval.domux.data.PackageItem
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.Visit
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions

/**
 * Paquetería y visitas (portería, administración y residentes). Esta pantalla solo arma las
 * pestañas y las ventanas; lo que se carga y se guarda lo hacen [PackagesViewModel] y
 * [VisitsViewModel]. Paquetes: portería y administración los registran. Visitas y QR: solo
 * portería (ADR-015).
 */
@Composable
fun RegistryScreen(
    navController: NavController,
    initialTab: String = "",
    // Lo que deja el buscador general: el texto con el que abre la lista de paquetes o la de visitas.
    initialSearch: String = "",
    packagesVm: PackagesViewModel = viewModel(),
    visitsVm: VisitsViewModel = viewModel()
) {
    val canRegister = Session.isGuard || Session.isAdmin
    val packages by packagesVm.state.collectAsState()
    val visits by visitsVm.state.collectAsState()
    // El menú y los botones del inicio de portería abren directo una pestaña.
    var selectedTab by remember(initialTab) {
        mutableIntStateOf(
            when (initialTab) {
                "visitas" -> if (Session.isResident) 1 else 2
                "qr" -> when {
                    Session.isResident -> 2
                    Session.isGuard -> 4
                    else -> 0
                }
                "registrar-paquete" -> if (Session.isResident) 0 else 1
                "registrar-visita" -> if (Session.isGuard) 3 else 0
                "escanear" -> if (Session.isGuard) 4 else 0
                "esperados" -> if (Session.isResident) 0 else 5
                else -> 0
            }
        )
    }
    // El guardia ve Paquetes y Visitas como pantallas separadas: cada botón del menú abre solo
    // las pestañas de lo suyo. Al escanear un código se pasa sola a la que corresponde.
    var guardOnPackages by remember(initialTab) {
        mutableStateOf(initialTab == "paquetes" || initialTab == "registrar-paquete")
    }
    // El residente también ve «Mis paquetes» y «Mis visitas y mi QR» como pantallas separadas.
    val residentOnPackages = initialTab != "visitas" && initialTab != "qr"
    // Cambio de guardia con PIN (HU-010): guardName es quien tiene el turno ahora.
    var showGuardShift by remember { mutableStateOf(false) }
    var guardName by remember { mutableStateOf(Session.userName.orEmpty()) }
    // Ventanas que esta pantalla abre: entrada, salida y salida por QR de una visita.
    var pendingEntry by remember { mutableStateOf<Visit?>(null) }
    var pendingExit by remember { mutableStateOf<Visit?>(null) }
    var pendingQrExit by remember { mutableStateOf<Visit?>(null) }
    var confirmation by remember { mutableStateOf<Pair<String, () -> Unit>?>(null) }

    // Escáner del código de entrega de un paquete (HU-048) y del QR de visitas.
    val packageScanner = rememberLauncherForActivityResult(ScanContract()) { result ->
        result.contents?.let { packagesVm.lookupPickupCode(it) }
    }
    // Un solo escáner para la portería: el código dice si es de un paquete o de una visita.
    val anyScanner = rememberLauncherForActivityResult(ScanContract()) { result ->
        val raw = result.contents ?: return@rememberLauncherForActivityResult
        when (scannedCodeKind(raw)) {
            ScannedCode.PACKAGE -> {
                guardOnPackages = true
                selectedTab = 0
                packagesVm.lookupPickupCode(raw)
            }
            ScannedCode.VISIT -> {
                guardOnPackages = false
                selectedTab = 4
                visitsVm.onQrScanned(raw)
            }
            ScannedCode.UNKNOWN -> visitsVm.showNotice("El código leído no es de DOMUX: ni de una visita ni de un paquete.")
        }
    }
    val launchAnyScanner = {
        anyScanner.launch(
            ScanOptions()
                .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                .setPrompt("Escanea el QR de la visita o el código de entrega del paquete")
        )
    }
    // «Escanear código» del inicio abre la cámara de una vez.
    var autoScanDone by rememberSaveable(initialTab) { mutableStateOf(false) }
    LaunchedEffect(initialTab) {
        if (Session.isGuard && initialTab == "escanear" && !autoScanDone) {
            autoScanDone = true
            launchAnyScanner()
        }
    }

    val allTabs = when {
        Session.isResident -> listOf("Mis paquetes", "Mis visitas", "Código QR")
        Session.isGuard -> listOf(
            "Paquetes", "Registrar paquete", "Visitas", "Registrar visita", "Ingreso por QR", "Esperados"
        )
        // La administración consulta las visitas de los residentes, pero no las registra (ADR-015):
        // solo anuncia técnicos y contratistas para las zonas comunes y los paquetes de la unidad.
        else -> listOf("Paquetes", "Paquete para la unidad", "Visitas", "", "", "Técnicos esperados")
    }
    // Las pestañas que se ven (su número en allTabs): el guardia solo ve las de la sección abierta.
    val visibleTabs = when {
        Session.isGuard && guardOnPackages -> listOf(0, 1)
        Session.isGuard -> listOf(2, 3, 4, 5)
        Session.isAdmin -> listOf(0, 1, 2, 5)
        Session.isResident && residentOnPackages -> listOf(0)
        Session.isResident -> listOf(1, 2)
        else -> allTabs.indices.toList()
    }
    val title = when {
        Session.isResident && residentOnPackages -> "Mis paquetes"
        Session.isResident -> "Mis visitas y mi QR"
        Session.isGuard && guardOnPackages -> "Paquetes"
        Session.isGuard -> "Visitas"
        else -> "Paquetería y visitas"
    }
    val tab = if (selectedTab in visibleTabs) selectedTab else visibleTabs.first()
    // El texto buscado va a la lista que se abre: la de visitas si piden «visitas», si no la de paquetes.
    val packageSearch = if (initialTab == "visitas") "" else initialSearch
    val visitSearch = if (initialTab == "visitas") initialSearch else ""

    DomuxScreenScaffold(title = title, navController = navController) { scaffoldPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(scaffoldPadding)
                .padding(horizontal = 16.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            if (visibleTabs.size > 1) {
                DomuxSectionTabs(visibleTabs.map { allTabs[it] }, visibleTabs.indexOf(tab)) { selectedTab = visibleTabs[it] }
            }
            if (Session.isGuard) {
                OutlinedButton(
                    onClick = { launchAnyScanner() },
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                ) { Text("Escanear código (visita o paquete)") }
            }
            if (packages.message.isNotBlank()) {
                DomuxMessageBanner(packages.message, packages.messageIsError) { packagesVm.dismissMessage() }
            }
            if (visits.message.isNotBlank()) {
                DomuxMessageBanner(visits.message, visits.messageIsError) { visitsVm.dismissMessage() }
            }
            if (Session.isGuard) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        "Guardia en turno: $guardName",
                        modifier = Modifier.weight(1f),
                        style = MaterialTheme.typography.bodyMedium
                    )
                    TextButton(onClick = { showGuardShift = true }) { Text("Cambiar de guardia") }
                }
            }
            if (packages.loading || visits.loading) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())

            when {
                canRegister && tab == 0 -> PackageListSection(
                    modifier = Modifier.weight(1f),
                    state = packages,
                    canRegister = true,
                    onStatusFilter = { packagesVm.setStatusFilter(it) },
                    onSearch = { packagesVm.setSearch(it) },
                    onRefresh = { packagesVm.refresh() },
                    onScan = {
                        if (Session.isGuard) {
                            launchAnyScanner()
                        } else {
                            packageScanner.launch(
                                ScanOptions()
                                    .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                                    .setPrompt("Escanea el código de entrega del paquete")
                            )
                        }
                    },
                    onTypePin = { packagesVm.openPinEntry() },
                    onDeliver = { packagesVm.startDelivery(it) },
                    onStatusChange = { item, status -> packagesVm.changeStatus(item, status) },
                    onMoveToTrash = { item: PackageItem ->
                        confirmation = "¿Archivar este paquete? Sigue guardado y se puede sacar de «Archivados»." to { packagesVm.moveToTrash(item) }
                    },
                    onRestore = { packagesVm.restore(it) },
                    onCreatePickupCode = {},
                    initialSearch = packageSearch
                )

                canRegister && tab == 1 -> PackageRegistrationSection(
                    modifier = Modifier.weight(1f),
                    busy = packages.busy,
                    onMessage = { packagesVm.showNotice(it) },
                    onRegister = { request, onSuccess -> packagesVm.register(request, onSuccess) },
                    onRegistered = { selectedTab = 0 },
                    forUnit = Session.isAdmin
                )

                canRegister && tab == 5 -> ExpectedVisitsSection(
                    modifier = Modifier.weight(1f),
                    expected = visits.expected,
                    busy = visits.busy,
                    isAdmin = Session.isAdmin,
                    onMessage = { visitsVm.showNotice(it) },
                    onRegister = { request, onSuccess -> visitsVm.registerExpected(request, onSuccess) },
                    onCancel = { visit ->
                        confirmation = "¿Cancelar la visita de ${visit.visitorName}? La portería dejará de esperarla." to {
                            visitsVm.cancelExpected(visit)
                        }
                    },
                    onEntry = { pendingEntry = it }
                )

                canRegister && tab == 2 -> VisitListSection(
                    modifier = Modifier.weight(1f),
                    state = visits,
                    isResident = false,
                    isGuard = Session.isGuard,
                    onStatusFilter = { visitsVm.setStatusFilter(it) },
                    onInsideOnly = { visitsVm.setInsideOnly(it) },
                    onSearch = { visitsVm.setSearch(it) },
                    onDates = { from, to -> visitsVm.setDates(from, to) },
                    onClearFilters = { visitsVm.clearFilters() },
                    onRefresh = { visitsVm.refresh() },
                    onLoadMore = { visitsVm.loadMore() },
                    onDecision = { _, _ -> },
                    onAuthorizeByCall = { visitsVm.authorizeByCall(it) },
                    onRejectByCall = { visitsVm.rejectByCall(it) },
                    onEntry = { pendingEntry = it },
                    onExit = { pendingExit = it },
                    initialSearch = visitSearch
                )

                Session.isGuard && tab == 3 -> VisitRegistrationSection(
                    modifier = Modifier.weight(1f),
                    busy = visits.busy,
                    onMessage = { visitsVm.showNotice(it) },
                    onRegister = { request, onSuccess -> visitsVm.registerVisit(request, onSuccess) }
                )

                Session.isGuard && tab == 4 -> QrEntrySection(
                    modifier = Modifier.weight(1f),
                    state = visits,
                    onScan = launchAnyScanner,
                    onMessage = { visitsVm.showNotice(it) },
                    onEnterNew = { name, stay, onSuccess -> visitsVm.enterQrVisitor(name, stay, onSuccess) },
                    onLinkVisit = { visit ->
                        visitsVm.enterQrExistingVisit(visit, "${visit.visitorName} vinculado al QR.")
                    },
                    onReenter = { visit ->
                        visitsVm.enterQrExistingVisit(visit, "Reingreso de ${visit.visitorName} registrado.")
                    },
                    onExit = { pendingQrExit = it },
                    onEnterVehicle = { visitsVm.enterQrVehicle() },
                    onSkipVehicle = { visitsVm.skipQrVehicle() }
                )

                Session.isResident && tab == 0 -> PackageListSection(
                    modifier = Modifier.weight(1f),
                    state = packages,
                    canRegister = false,
                    onStatusFilter = { packagesVm.setStatusFilter(it) },
                    onSearch = { packagesVm.setSearch(it) },
                    onRefresh = { packagesVm.refresh() },
                    onScan = {},
                    onTypePin = {},
                    onDeliver = {},
                    onStatusChange = { _, _ -> },
                    onMoveToTrash = {},
                    onRestore = {},
                    onCreatePickupCode = { packagesVm.createPickupCode(it) },
                    initialSearch = packageSearch
                )

                Session.isResident && tab == 1 -> VisitListSection(
                    modifier = Modifier.weight(1f),
                    state = visits,
                    isResident = true,
                    isGuard = false,
                    onStatusFilter = { visitsVm.setStatusFilter(it) },
                    onInsideOnly = { visitsVm.setInsideOnly(it) },
                    onSearch = { visitsVm.setSearch(it) },
                    onDates = { from, to -> visitsVm.setDates(from, to) },
                    onClearFilters = { visitsVm.clearFilters() },
                    onRefresh = { visitsVm.refresh() },
                    onLoadMore = { visitsVm.loadMore() },
                    onDecision = { visit, decision -> visitsVm.decide(visit, decision) },
                    onAuthorizeByCall = {},
                    onEntry = {},
                    onExit = {},
                    initialSearch = visitSearch
                )

                Session.isResident && tab == 2 -> ResidentQrSection(
                    modifier = Modifier.weight(1f),
                    state = visits,
                    onMessage = { visitsVm.showNotice(it) },
                    onCreate = { request, onSuccess -> visitsVm.createQrPass(request, onSuccess) },
                    onSelect = { visitsVm.selectQrPass(it) },
                    onRevoke = { visitsVm.revokeQrPass(it) }
                )
            }
        }
    }

    confirmation?.let { (prompt, action) ->
        DomuxConfirmDialog(
            title = "¿Estás seguro de confirmar esta acción?",
            message = prompt,
            confirmLabel = "Confirmar",
            onConfirm = {
                confirmation = null
                action()
            },
            onDismiss = { confirmation = null }
        )
    }

    // Entrega de un paquete: a mano o con un código de entrega leído (HU-048).
    packages.delivery?.let { target ->
        DeliveryDialog(
            target = target,
            busy = packages.busy,
            error = packages.message.takeIf { packages.messageIsError && it.isNotBlank() },
            onConfirm = { receiver, pin -> packagesVm.deliver(target, receiver, pin) },
            onDismiss = { packagesVm.cancelDelivery() }
        )
    }

    // Entregar escribiendo el PIN, cuando el QR no se puede leer (HU-048).
    if (packages.typingPin) {
        PickupPinDialog(
            busy = packages.busy,
            error = packages.message.takeIf { packages.messageIsError && it.isNotBlank() },
            onSearch = { packagesVm.lookupPickupPin(it) },
            onDismiss = { packagesVm.closePinEntry() }
        )
    }

    // El código de entrega que el residente acaba de generar (se muestra una sola vez).
    val newCode = packages.pickupCode
    val newCodePackage = packages.pickupCodePackage
    if (newCode != null && newCodePackage != null) {
        PickupCodeDialog(item = newCodePackage, code = newCode, onDismiss = { packagesVm.closePickupCode() })
    }

    pendingEntry?.let { visit ->
        VisitEntryDialog(
            visit = visit,
            busy = visits.busy,
            onConfirm = { stay -> visitsVm.registerEntry(visit, stay) { pendingEntry = null } },
            onDismiss = { pendingEntry = null }
        )
    }

    pendingExit?.let { visit ->
        VisitExitDialog(
            visit = visit,
            busy = visits.busy,
            onConfirm = { returning -> visitsVm.registerExit(visit, returning) { pendingExit = null } },
            onDismiss = { pendingExit = null }
        )
    }

    pendingQrExit?.let { visit ->
        VisitExitDialog(
            visit = visit,
            busy = visits.busy,
            onConfirm = { returning -> visitsVm.exitQrVisit(visit, returning) { pendingQrExit = null } },
            onDismiss = { pendingQrExit = null }
        )
    }

    // Después de cambiar de guardia: las visitas que entraron y siguen adentro (HU-032).
    visits.insideAlert?.let { inside ->
        VisitsInsideDialog(
            visits = inside,
            onSeeList = {
                visitsVm.dismissInsideAlert()
                visitsVm.setInsideOnly(true)
                guardOnPackages = false
                selectedTab = 2
            },
            onDismiss = { visitsVm.dismissInsideAlert() }
        )
    }

    if (showGuardShift) {
        GuardShiftDialog(
            onDismiss = { showGuardShift = false },
            onShiftDone = { shiftMessage ->
                showGuardShift = false
                guardName = Session.userName.orEmpty()
                packagesVm.showNotice(shiftMessage, isError = false)
                // Lo que se vea desde ahora se pide con la sesión del guardia que entra.
                packagesVm.refresh()
                visitsVm.refresh()
                visitsVm.checkVisitsInside()
            }
        )
    }
}

/** Qué es un código escaneado en la portería: el de entrega de un paquete, el QR de una visita u otro. */
enum class ScannedCode { PACKAGE, VISIT, UNKNOWN }

fun scannedCodeKind(raw: String): ScannedCode = when {
    raw.startsWith(PackagesViewModel.PICKUP_QR_PREFIX) && raw.length > PackagesViewModel.PICKUP_QR_PREFIX.length -> ScannedCode.PACKAGE
    raw.startsWith(VisitsViewModel.QR_PREFIX) && raw.length > VisitsViewModel.QR_PREFIX.length -> ScannedCode.VISIT
    else -> ScannedCode.UNKNOWN
}
