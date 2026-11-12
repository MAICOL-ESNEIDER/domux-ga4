package com.dracknoval.domux

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
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
    packagesVm: PackagesViewModel = viewModel(),
    visitsVm: VisitsViewModel = viewModel()
) {
    val canRegister = Session.isGuard || Session.isAdmin
    val packages by packagesVm.state.collectAsState()
    val visits by visitsVm.state.collectAsState()
    var selectedTab by remember { mutableIntStateOf(0) }
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
    val visitScanner = rememberLauncherForActivityResult(ScanContract()) { result ->
        result.contents?.let { visitsVm.onQrScanned(it) }
    }

    val tabs = when {
        Session.isResident -> listOf("Mis paquetes", "Mis visitas", "Código QR")
        Session.isGuard -> listOf(
            "Paquetes", "Registrar paquete", "Visitas", "Registrar visita", "Ingreso por QR"
        )
        // La administración consulta las visitas, pero no las registra (ADR-015).
        else -> listOf("Paquetes", "Registrar paquete", "Visitas")
    }
    val title = when {
        Session.isResident -> "Mis paquetes y visitas"
        Session.isGuard -> "Control de portería"
        else -> "Paquetería y visitas"
    }
    val tab = selectedTab.coerceIn(tabs.indices)

    DomuxScreenScaffold(title = title, navController = navController) { scaffoldPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(scaffoldPadding)
                .padding(horizontal = 16.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            DomuxSectionTabs(tabs, tab) { selectedTab = it }
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
                        packageScanner.launch(
                            ScanOptions()
                                .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                                .setPrompt("Escanea el código de entrega del paquete")
                        )
                    },
                    onDeliver = { packagesVm.startDelivery(it) },
                    onStatusChange = { item, status -> packagesVm.changeStatus(item, status) },
                    onMoveToTrash = { item: PackageItem ->
                        confirmation = "¿Mover este paquete a la papelera?" to { packagesVm.moveToTrash(item) }
                    },
                    onRestore = { packagesVm.restore(it) },
                    onCreatePickupCode = {}
                )

                canRegister && tab == 1 -> PackageRegistrationSection(
                    modifier = Modifier.weight(1f),
                    busy = packages.busy,
                    onMessage = { packagesVm.showNotice(it) },
                    onRegister = { request, onSuccess -> packagesVm.register(request, onSuccess) },
                    onRegistered = { selectedTab = 0 }
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
                    onEntry = { pendingEntry = it },
                    onExit = { pendingExit = it }
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
                    onScan = {
                        visitScanner.launch(
                            ScanOptions()
                                .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                                .setPrompt("Escanea el QR de visitas")
                        )
                    },
                    onMessage = { visitsVm.showNotice(it) },
                    onEnterNew = { name, stay, onSuccess -> visitsVm.enterQrVisitor(name, stay, onSuccess) },
                    onLinkVisit = { visit ->
                        visitsVm.enterQrExistingVisit(visit, "${visit.visitorName} vinculado al QR.")
                    },
                    onReenter = { visit ->
                        visitsVm.enterQrExistingVisit(visit, "Reingreso de ${visit.visitorName} registrado.")
                    },
                    onExit = { pendingQrExit = it }
                )

                Session.isResident && tab == 0 -> PackageListSection(
                    modifier = Modifier.weight(1f),
                    state = packages,
                    canRegister = false,
                    onStatusFilter = { packagesVm.setStatusFilter(it) },
                    onSearch = { packagesVm.setSearch(it) },
                    onRefresh = { packagesVm.refresh() },
                    onScan = {},
                    onDeliver = {},
                    onStatusChange = { _, _ -> },
                    onMoveToTrash = {},
                    onRestore = {},
                    onCreatePickupCode = { packagesVm.createPickupCode(it) }
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
                    onExit = {}
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
