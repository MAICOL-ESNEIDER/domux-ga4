package com.dracknoval.domux

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.dracknoval.domux.data.CreateVisitQrPassRequest
import com.dracknoval.domux.data.RegisterVisitRequest
import com.dracknoval.domux.data.ResidentSummary
import com.dracknoval.domux.data.Visit
import com.dracknoval.domux.data.VisitQrPass
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale

// Pantallas de visitas: historial con filtros, entrada y salida con estadía prevista, registro,
// ingreso por QR y los códigos QR del residente (HU-027 y HU-030 a HU-033). La lógica está en
// VisitsViewModel; aquí solo se dibuja y se avisa con lambdas.

/** El día de hace [daysAgo] días como AAAA-MM-DD (hora del teléfono, que es la de Colombia). */
private fun dayText(daysAgo: Int): String {
    val calendar = Calendar.getInstance()
    calendar.add(Calendar.DAY_OF_YEAR, -daysAgo)
    return SimpleDateFormat("yyyy-MM-dd", Locale.US).format(calendar.time)
}

private fun approvalLabel(status: String): String = when (status) {
    "aprobada" -> "Autorizada"
    "rechazada" -> "Rechazada"
    else -> "Pendiente"
}

/** La visita entró y todavía no registra salida. */
private fun Visit.isInside(): Boolean = enteredAt != null && exitedAt == null

// ---------------------------------------------------------------------------
// Historial (HU-030 y HU-032)
// ---------------------------------------------------------------------------

@Composable
fun VisitListSection(
    modifier: Modifier,
    state: VisitsUiState,
    isResident: Boolean,
    isGuard: Boolean,
    onStatusFilter: (String?) -> Unit,
    onInsideOnly: (Boolean) -> Unit,
    onSearch: (String) -> Unit,
    onDates: (from: String, to: String) -> Unit,
    onClearFilters: () -> Unit,
    onRefresh: () -> Unit,
    onLoadMore: () -> Unit,
    onDecision: (Visit, String) -> Unit,
    onAuthorizeByCall: (Visit) -> Unit,
    onEntry: (Visit) -> Unit,
    onExit: (Visit) -> Unit
) {
    // El texto del buscador vive aquí y el ViewModel recibe el valor ya aplicado, tras una pausa.
    var searchText by rememberSaveable { mutableStateOf("") }
    var showDates by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(searchText) {
        if (searchText.isNotBlank()) delay(300)
        onSearch(searchText)
    }
    val statusFilters = listOf<Pair<String, String?>>(
        "Todas" to null,
        "Pendientes" to "pendiente",
        "Autorizadas" to "aprobada",
        "Rechazadas" to "rechazada"
    )
    val dateRangeSet = state.dateFrom.isNotBlank() || state.dateTo.isNotBlank()
    val filtering = state.statusFilter != null || state.insideOnly || dateRangeSet || searchText.isNotBlank()

    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        OutlinedTextField(
            value = searchText,
            onValueChange = { searchText = it },
            label = { Text("Buscar visitante, residente o apartamento") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Row(
            modifier = Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            statusFilters.forEach { (label, value) ->
                FilterChip(
                    selected = state.statusFilter == value,
                    onClick = { onStatusFilter(value) },
                    label = { Text(label) }
                )
            }
            // Las que entraron y todavía no registran salida (HU-032).
            FilterChip(
                selected = state.insideOnly,
                onClick = { onInsideOnly(!state.insideOnly) },
                label = { Text("Sin salida") }
            )
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            TextButton(onClick = { showDates = !showDates }) {
                Text(
                    if (dateRangeSet) {
                        "Fechas: ${state.dateFrom.ifBlank { "…" }} a ${state.dateTo.ifBlank { "…" }}"
                    } else {
                        "Filtrar por fechas"
                    }
                )
            }
            TextButton(onClick = onRefresh) { Text("Actualizar") }
        }
        if (showDates) {
            Row(
                modifier = Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                FilterChip(
                    selected = state.dateFrom == dayText(0) && state.dateTo == dayText(0),
                    onClick = { onDates(dayText(0), dayText(0)) },
                    label = { Text("Hoy") }
                )
                FilterChip(
                    selected = state.dateFrom == dayText(6) && state.dateTo == dayText(0),
                    onClick = { onDates(dayText(6), dayText(0)) },
                    label = { Text("Últimos 7 días") }
                )
                FilterChip(
                    selected = state.dateFrom == dayText(29) && state.dateTo == dayText(0),
                    onClick = { onDates(dayText(29), dayText(0)) },
                    label = { Text("Últimos 30 días") }
                )
                FilterChip(
                    selected = !dateRangeSet,
                    onClick = { onDates("", "") },
                    label = { Text("Sin fechas") }
                )
            }
            DatePickerField("Desde", state.dateFrom, { onDates(it, state.dateTo) })
            DatePickerField("Hasta", state.dateTo, { onDates(state.dateFrom, it) })
        }
        if (state.page.total > 0) {
            Text(
                "Mostrando ${state.visits.size} de ${state.page.total} visitas",
                style = MaterialTheme.typography.bodySmall
            )
        }
        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            if (state.visits.isEmpty()) {
                item {
                    DomuxCard(Modifier.fillMaxWidth()) {
                        Column(
                            modifier = Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Text(
                                when {
                                    state.loading -> "Cargando visitas..."
                                    filtering -> "No hay visitas que coincidan con los filtros actuales."
                                    else -> "No hay visitas registradas."
                                }
                            )
                            if (filtering && !state.loading) {
                                TextButton(onClick = {
                                    searchText = ""
                                    onClearFilters()
                                }) { Text("Limpiar filtros y ver todas") }
                            }
                        }
                    }
                }
            }
            items(state.visits, key = { "visit-${it.id}" }) { visit ->
                VisitCard(
                    visit = visit,
                    isResident = isResident,
                    isGuard = isGuard,
                    busy = state.busy,
                    onDecision = { onDecision(visit, it) },
                    onAuthorizeByCall = { onAuthorizeByCall(visit) },
                    onEntry = { onEntry(visit) },
                    onExit = { onExit(visit) }
                )
            }
            if (state.page.page < state.page.totalPages) {
                item {
                    TextButton(
                        onClick = onLoadMore,
                        enabled = !state.loadingMore,
                        modifier = Modifier.fillMaxWidth()
                    ) { Text(if (state.loadingMore) "Cargando..." else "Ver más visitas") }
                }
            }
        }
    }
}

@Composable
private fun VisitCard(
    visit: Visit,
    isResident: Boolean,
    isGuard: Boolean,
    busy: Boolean,
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
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    visit.visitorName,
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.weight(1f)
                )
                DomuxStatusBadge(
                    approvalLabel(visit.approvalStatus),
                    when (visit.approvalStatus) {
                        "aprobada" -> DomuxBadgeTone.SUCCESS
                        "rechazada" -> DomuxBadgeTone.ALERT
                        else -> DomuxBadgeTone.PROGRESS
                    }
                )
            }
            Text("${visit.type.replaceFirstChar(Char::uppercase)} · ${visit.createdAt.orEmpty()}")
            Text("Para: ${visit.residentName.orEmpty()} · ${visit.apartment.orEmpty()}")
            if (visit.mediaConsent && !visit.visitorDocument.isNullOrBlank()) {
                Text("Documento: ${visit.visitorDocument}")
            }
            MediaAttachmentChip(visit.visitorPhotoUrl, visit.visitorPhotoType, "Foto del visitante")
            visit.description?.takeIf { it.isNotBlank() }?.let { Text("Pedido: $it") }
            visit.enteredAt?.let { Text("Última entrada: $it") }
            visit.exitedAt?.let { Text("Última salida: $it") }
            // Estadía prevista y cuánto lleva adentro (HU-031).
            visit.expectedStayMinutes?.let { Text("Estadía prevista: ${durationText(it)}") }
            if (visit.isInside()) {
                visit.insideMinutes?.let { Text("Lleva adentro: ${durationText(it)}") }
                if (visit.isOverstay) {
                    DomuxStatusBadge("Pasó la estadía prevista", DomuxBadgeTone.ALERT)
                } else {
                    DomuxStatusBadge("Dentro de la unidad", DomuxBadgeTone.PROGRESS)
                }
            }
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
                    TextButton(onClick = { onDecision("aprobada") }, enabled = !busy) { Text("Autorizar") }
                    TextButton(onClick = { onDecision("rechazada") }, enabled = !busy) { Text("Rechazar") }
                }
            }
            if (isGuard && visit.approvalStatus == "pendiente") {
                TextButton(onClick = onAuthorizeByCall, enabled = !busy) { Text("Autorizar por llamada") }
            }
            if (isGuard && visit.approvalStatus == "aprobada") {
                if (visit.enteredAt == null || (visit.exitedAt != null && visit.exitReturning)) {
                    TextButton(onClick = onEntry, enabled = !busy) { Text("Registrar entrada") }
                } else if (visit.exitedAt != null && !visit.exitReturning) {
                    Text("Salida definitiva. Si vuelve, registra una nueva solicitud.")
                } else {
                    TextButton(onClick = onExit, enabled = !busy) { Text("Registrar salida") }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Ventanas de entrada, salida y visitas sin salida
// ---------------------------------------------------------------------------

/** El guardia registra la entrada y, si quiere, anota cuánto se quedará la visita (HU-031). */
@Composable
fun VisitEntryDialog(
    visit: Visit,
    busy: Boolean,
    onConfirm: (stayMinutes: Int?) -> Unit,
    onDismiss: () -> Unit
) {
    var stay by remember { mutableStateOf(visit.expectedStayMinutes) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Registrar entrada") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Text("${visit.visitorName} · ${visit.apartment.orEmpty()}")
                StayChips(stay, { stay = it })
                Text(
                    "Si pasa ese tiempo y no ha salido, la portería recibe un aviso.",
                    style = MaterialTheme.typography.bodySmall
                )
            }
        },
        confirmButton = {
            TextButton(enabled = !busy, onClick = { onConfirm(stay) }) { Text("Registrar entrada") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancelar") } }
    )
}

/** La salida de una visita: si vuelve hoy puede entrar de nuevo, si no, la salida es definitiva. */
@Composable
fun VisitExitDialog(
    visit: Visit,
    busy: Boolean,
    onConfirm: (returningToday: Boolean) -> Unit,
    onDismiss: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Registrar salida") },
        text = { Text("¿${visit.visitorName} volverá a ingresar hoy?") },
        confirmButton = {
            TextButton(enabled = !busy, onClick = { onConfirm(true) }) { Text("Sí, regresa hoy") }
        },
        dismissButton = {
            TextButton(enabled = !busy, onClick = { onConfirm(false) }) { Text("No, salida definitiva") }
        }
    )
}

/** Las visitas que siguen adentro; el guardia que entra al turno las ve de una vez (HU-032). */
@Composable
fun VisitsInsideDialog(visits: List<Visit>, onSeeList: () -> Unit, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Visitas que siguen adentro (${visits.size})") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(
                    "Estas visitas entraron y todavía no tienen salida registrada. Revisa si ya se fueron.",
                    style = MaterialTheme.typography.bodySmall
                )
                visits.forEach { visit ->
                    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(visit.visitorName, style = MaterialTheme.typography.titleSmall)
                        Text(
                            "${visit.apartment.orEmpty()} · desde ${visit.enteredAt.orEmpty()}",
                            style = MaterialTheme.typography.bodySmall
                        )
                        visit.insideMinutes?.let {
                            Text("Lleva ${durationText(it)}", style = MaterialTheme.typography.bodySmall)
                        }
                        if (visit.isOverstay) {
                            DomuxStatusBadge("Pasó la estadía prevista", DomuxBadgeTone.ALERT)
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onSeeList) { Text("Ver en la lista") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cerrar") } }
    )
}

// ---------------------------------------------------------------------------
// Registro de una visita (guardia)
// ---------------------------------------------------------------------------

@Composable
fun VisitRegistrationSection(
    modifier: Modifier,
    busy: Boolean,
    onMessage: (String) -> Unit,
    onRegister: (request: RegisterVisitRequest, onSuccess: () -> Unit) -> Unit
) {
    var resident by remember { mutableStateOf<ResidentSummary?>(null) }
    var visitorName by rememberSaveable { mutableStateOf("") }
    var visitorDocument by rememberSaveable { mutableStateOf("") }
    var visitorType by rememberSaveable { mutableStateOf("visitante") }
    var consent by rememberSaveable { mutableStateOf(false) }
    var photoUrl by remember { mutableStateOf<String?>(null) }
    var photoType by remember { mutableStateOf<String?>(null) }
    var photoName by remember { mutableStateOf<String?>(null) }
    var description by rememberSaveable { mutableStateOf("") }
    var stay by remember { mutableStateOf<Int?>(null) }
    var attempted by rememberSaveable { mutableStateOf(false) }

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
                DomuxResidentSearchField(resident, { resident = it })
                OutlinedTextField(
                    value = visitorName,
                    onValueChange = { visitorName = it },
                    label = { Text("Nombre del visitante *") },
                    isError = attempted && visitorName.isBlank(),
                    supportingText = {
                        if (attempted && visitorName.isBlank()) Text("El nombre es obligatorio")
                    },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    listOf("visitante", "domiciliario", "contratista").forEach { type ->
                        FilterChip(
                            selected = visitorType == type,
                            onClick = { visitorType = type },
                            label = { Text(type.replaceFirstChar(Char::uppercase)) }
                        )
                    }
                }
                if (visitorType == "domiciliario") {
                    OutlinedTextField(
                        value = description,
                        onValueChange = { description = it },
                        label = { Text("Detalles del pedido (opcional)") },
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                StayChips(stay, { stay = it })
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(
                        checked = consent,
                        onCheckedChange = { checked ->
                            consent = checked
                            if (!checked) {
                                visitorDocument = ""
                                photoUrl = null
                                photoType = null
                                photoName = null
                            }
                        }
                    )
                    Text("El visitante autoriza guardar su documento o foto (opcional)")
                }
                if (consent) {
                    OutlinedTextField(
                        value = visitorDocument,
                        onValueChange = { visitorDocument = it },
                        label = { Text("Documento (opcional)") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    MediaAttachmentPicker(
                        photoName,
                        { url, type, name ->
                            photoUrl = url
                            photoType = type
                            photoName = name
                        },
                        onMessage,
                        kinds = AttachmentKinds.PHOTO,
                        onClear = { photoUrl = null; photoType = null; photoName = null }
                    )
                }
                Button(
                    onClick = {
                        attempted = true
                        val target = resident
                        if (target == null || visitorName.isBlank()) {
                            onMessage("Selecciona residente y escribe el nombre del visitante.")
                        } else {
                            val request = RegisterVisitRequest(
                                residentId = target.id,
                                visitorName = visitorName.trim(),
                                type = visitorType,
                                visitorDocument = visitorDocument.trim().ifEmpty { null },
                                mediaConsent = consent,
                                mediaUrl = if (consent) photoUrl else null,
                                mediaType = if (consent) photoType else null,
                                description = description.trim().ifEmpty { null },
                                expectedStayMinutes = stay
                            )
                            onRegister(request) {
                                resident = null
                                visitorName = ""
                                visitorDocument = ""
                                consent = false
                                photoUrl = null
                                photoType = null
                                photoName = null
                                description = ""
                                stay = null
                                attempted = false
                            }
                        }
                    },
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth()
                ) { Text("Registrar visita") }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Ingreso y salida por QR (guardia)
// ---------------------------------------------------------------------------

@Composable
fun QrEntrySection(
    modifier: Modifier,
    state: VisitsUiState,
    onScan: () -> Unit,
    onMessage: (String) -> Unit,
    onEnterNew: (name: String, stayMinutes: Int?, onSuccess: () -> Unit) -> Unit,
    onLinkVisit: (Visit) -> Unit,
    onReenter: (Visit) -> Unit,
    onExit: (Visit) -> Unit
) {
    var visitorName by rememberSaveable { mutableStateOf("") }
    var stay by remember { mutableStateOf<Int?>(null) }
    val inspection = state.qrInspection

    Column(
        modifier = modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        DomuxCard(Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text("Ingreso y salida por QR", style = MaterialTheme.typography.titleMedium)
                Button(onClick = onScan, modifier = Modifier.fillMaxWidth()) { Text("Escanear QR") }
                if (inspection == null) {
                    Text(
                        "Escanea el QR que le mostró el visitante para ver quién lo creó, los cupos " +
                            "disponibles y los nombres de los invitados.",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
                inspection?.let { scanned ->
                    Text("${scanned.residentName.orEmpty()} · ${scanned.apartment.orEmpty()}")
                    Text(
                        "Registrados: ${scanned.qrPass?.registeredPeople ?: 0}/" +
                            "${scanned.qrPass?.maxPeople ?: 0} · " +
                            "Disponibles: ${scanned.qrPass?.remainingPeople ?: 0}"
                    )
                    if (!scanned.canRegister) {
                        Text("Este QR está vencido o revocado: solo se permite registrar la salida.")
                    }
                    // Los nombres que el residente anotó al crear el QR, para tocarlos en vez de escribirlos (HU-033).
                    val pendingNames = scanned.pendingVisitorNames.orEmpty()
                    if (pendingNames.isNotEmpty()) {
                        Text("Invitados esperados (toca uno para llenar el nombre):")
                        Row(
                            modifier = Modifier.horizontalScroll(rememberScrollState()),
                            horizontalArrangement = Arrangement.spacedBy(6.dp)
                        ) {
                            pendingNames.forEach { name ->
                                FilterChip(
                                    selected = visitorName.trim().equals(name, ignoreCase = true),
                                    onClick = { visitorName = name },
                                    enabled = scanned.canRegister,
                                    label = { Text(name) }
                                )
                            }
                        }
                    }
                    OutlinedTextField(
                        value = visitorName,
                        onValueChange = { visitorName = it },
                        label = { Text("Nombre del visitante que ingresa") },
                        enabled = scanned.canRegister,
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    StayChips(stay, { stay = it })
                    Button(
                        onClick = {
                            if (visitorName.isBlank()) {
                                onMessage("Escribe el nombre del visitante.")
                            } else {
                                onEnterNew(visitorName, stay) {
                                    visitorName = ""
                                    stay = null
                                }
                            }
                        },
                        enabled = scanned.canRegister && !state.busy,
                        modifier = Modifier.fillMaxWidth()
                    ) { Text("Registrar ingreso") }
                    if (scanned.linkableVisits.orEmpty().isNotEmpty()) {
                        Text("O vincular un visitante ya registrado:")
                        scanned.linkableVisits.orEmpty().forEach { visit ->
                            TextButton(
                                enabled = scanned.canRegister && !state.busy,
                                onClick = { onLinkVisit(visit) }
                            ) { Text("${visit.visitorName} · vincular e ingresar") }
                        }
                    }
                    scanned.inside.orEmpty().forEach { visit ->
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text("${visit.visitorName} está dentro", modifier = Modifier.weight(1f))
                            TextButton(onClick = { onExit(visit) }, enabled = !state.busy) { Text("Salida") }
                        }
                    }
                    scanned.registeredVisits.orEmpty()
                        .filter { visit -> visit.exitedAt != null }
                        .forEach { visit ->
                            TextButton(
                                enabled = scanned.canRegister && !state.busy,
                                onClick = { onReenter(visit) }
                            ) { Text("Reingreso: ${visit.visitorName}") }
                        }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Códigos QR del residente (HU-027 y HU-033)
// ---------------------------------------------------------------------------

@Composable
fun ResidentQrSection(
    modifier: Modifier,
    state: VisitsUiState,
    onMessage: (String) -> Unit,
    onCreate: (request: CreateVisitQrPassRequest, onSuccess: () -> Unit) -> Unit,
    onSelect: (VisitQrPass?) -> Unit,
    onRevoke: (VisitQrPass) -> Unit
) {
    val context = LocalContext.current
    var startDate by rememberSaveable { mutableStateOf(dayText(0)) }
    var endDate by rememberSaveable { mutableStateOf(dayText(0)) }
    var maxPeople by rememberSaveable { mutableStateOf("5") }
    var namesText by rememberSaveable { mutableStateOf("") }
    var shareError by remember { mutableStateOf<String?>(null) }
    val active = state.activeQrPass
    val activeBitmap = rememberQrBitmap(active?.qrData)

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
                DatePickerField("Válido desde", startDate, { startDate = it }, allowPastDates = false)
                DatePickerField("Válido hasta", endDate, { endDate = it }, allowPastDates = false)
                OutlinedTextField(
                    value = maxPeople,
                    onValueChange = { maxPeople = it.filter(Char::isDigit) },
                    label = { Text("Límite de personas") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                // Los nombres ayudan a la portería a reconocer a los invitados (HU-033).
                OutlinedTextField(
                    value = namesText,
                    onValueChange = { namesText = it },
                    label = { Text("Nombres de los invitados (opcional)") },
                    supportingText = { Text("Uno por línea. Así la portería sabe a quién esperar.") },
                    minLines = 2,
                    modifier = Modifier.fillMaxWidth()
                )
                Button(
                    onClick = {
                        val limit = maxPeople.toIntOrNull()
                        val names = namesText.split('\n', ',').map { it.trim() }.filter { it.isNotEmpty() }
                        if (limit == null || limit < 1) {
                            onMessage("El límite de personas debe ser mayor que cero.")
                        } else if (names.size > limit) {
                            onMessage("Escribiste ${names.size} nombres pero el QR es para $limit personas.")
                        } else {
                            val request = CreateVisitQrPassRequest(
                                validFrom = startDate,
                                validUntil = endDate,
                                maxPeople = limit,
                                visitorNames = names.takeIf { it.isNotEmpty() }
                            )
                            onCreate(request) { namesText = "" }
                        }
                    },
                    enabled = !state.busy,
                    modifier = Modifier.fillMaxWidth()
                ) { Text("Crear QR") }
            }
        }

        if (state.qrPasses.isNotEmpty()) {
            DomuxCard(Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    Text("Mis códigos QR", style = MaterialTheme.typography.titleMedium)
                    state.qrPasses.forEach { pass ->
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            TextButton(
                                onClick = {
                                    shareError = null
                                    onSelect(pass)
                                },
                                modifier = Modifier.weight(1f)
                            ) {
                                Text(
                                    "${pass.validFrom} a ${pass.validUntil} · " +
                                        "${pass.registeredPeople}/${pass.maxPeople}" +
                                        if (pass.revoked) " · revocado" else ""
                                )
                            }
                            if (!pass.revoked) {
                                TextButton(onClick = { onRevoke(pass) }, enabled = !state.busy) {
                                    Text("Revocar")
                                }
                            }
                        }
                    }
                }
            }
        }

        if (active != null) {
            DomuxCard(Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        if (active.revoked) "Código revocado" else "Código activo · ${active.remainingPeople} cupos disponibles",
                        style = MaterialTheme.typography.titleSmall
                    )
                    Text("Válido del ${active.validFrom} al ${active.validUntil}")
                    active.visitorNames.orEmpty().takeIf { it.isNotEmpty() }?.let { names ->
                        Text("Invitados: ${names.joinToString(", ")}", style = MaterialTheme.typography.bodySmall)
                    }
                    QrImage(activeBitmap, "Código QR de visitas")
                    shareError?.let {
                        Text("⚠ $it", color = Color(0xFFF87171), style = MaterialTheme.typography.bodySmall)
                    }
                    if (!active.revoked) {
                        Button(
                            onClick = {
                                shareError = if (activeBitmap == null) {
                                    "No se pudo generar la imagen del QR."
                                } else {
                                    shareQrImage(
                                        context, activeBitmap, "Compartir QR de visitas",
                                        "Este es mi código QR para entrar a la unidad. Válido del " +
                                            "${active.validFrom} al ${active.validUntil}. Muéstralo al guardia en la portería."
                                    )
                                }
                            },
                            modifier = Modifier.fillMaxWidth()
                        ) { Text("Compartir QR") }
                    }
                }
            }
        }
    }
}
