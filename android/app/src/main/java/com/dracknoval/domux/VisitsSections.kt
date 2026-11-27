package com.dracknoval.domux

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
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
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.compose.runtime.mutableStateListOf
import com.dracknoval.domux.data.CreateVisitQrPassRequest
import com.dracknoval.domux.data.QrVehicle
import com.dracknoval.domux.data.QrVisitor
import com.dracknoval.domux.data.RegisterVisitRequest
import com.dracknoval.domux.data.ResidentSummary
import com.dracknoval.domux.data.Visit
import com.dracknoval.domux.data.VisitQrPass
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale
import com.dracknoval.domux.ui.theme.DomuxColor

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
    onRejectByCall: (Visit) -> Unit = {},
    onEntry: (Visit) -> Unit,
    onExit: (Visit) -> Unit,
    // El texto con el que abre la caja de búsqueda (lo deja puesto el buscador general).
    initialSearch: String = ""
) {
    // El texto del buscador vive aquí y el ViewModel recibe el valor ya aplicado, tras una pausa.
    var searchText by rememberSaveable { mutableStateOf(initialSearch) }
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
        // El buscador con el botón «Filtros»: estado, sin salida y fechas se eligen en la hoja.
        val activeFilters = buildList {
            state.statusFilter?.let { status ->
                val label = statusFilters.firstOrNull { it.second == status }?.first ?: status
                add(DomuxActiveFilter("Estado: $label") { onStatusFilter(null) })
            }
            if (state.insideOnly) add(DomuxActiveFilter("Sin salida") { onInsideOnly(false) })
            if (dateRangeSet) {
                add(
                    DomuxActiveFilter("Fechas: ${state.dateFrom.ifBlank { "…" }} a ${state.dateTo.ifBlank { "…" }}") {
                        onDates("", "")
                    }
                )
            }
        }
        DomuxSearchFilterBar(
            active = activeFilters,
            onClearFilters = {
                onStatusFilter(null)
                onInsideOnly(false)
                onDates("", "")
            },
            search = searchText,
            onSearch = { searchText = it },
            searchLabel = "Buscar visita",
            searchHint = "Visitante, residente o apartamento",
            sheetTitle = "Filtros de visitas"
        ) {
            DomuxFilterGroup("Estado") {
                statusFilters.forEach { (label, value) ->
                    DomuxFilterOption(label, state.statusFilter == value) { onStatusFilter(value) }
                }
            }
            // Las que entraron y todavía no registran salida (HU-032).
            DomuxFilterGroup("Salida") {
                DomuxFilterOption("Solo las que no han salido", state.insideOnly) { onInsideOnly(!state.insideOnly) }
            }
            DomuxFilterGroup("Fechas") {
                DomuxFilterOption("Hoy", state.dateFrom == dayText(0) && state.dateTo == dayText(0)) {
                    onDates(dayText(0), dayText(0))
                }
                DomuxFilterOption("Últimos 7 días", state.dateFrom == dayText(6) && state.dateTo == dayText(0)) {
                    onDates(dayText(6), dayText(0))
                }
                DomuxFilterOption("Últimos 30 días", state.dateFrom == dayText(29) && state.dateTo == dayText(0)) {
                    onDates(dayText(29), dayText(0))
                }
                DomuxFilterOption("Sin fechas", !dateRangeSet) { onDates("", "") }
            }
            DatePickerField("Desde", state.dateFrom, { onDates(it, state.dateTo) })
            DatePickerField("Hasta", state.dateTo, { onDates(state.dateFrom, it) })
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                if (state.page.total > 0) "Mostrando ${state.visits.size} de ${state.page.total} visitas" else "",
                style = MaterialTheme.typography.bodySmall
            )
            TextButton(onClick = onRefresh) { Text("Actualizar") }
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
                    onRejectByCall = { onRejectByCall(visit) },
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
    onRejectByCall: () -> Unit,
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
            Text("${visit.type.replaceFirstChar(Char::uppercase)} · ${whenText(visit.createdAt)}")
            Text("Para: ${visit.residentName.orEmpty()} · ${visit.apartment.orEmpty()}")
            if (visit.mediaConsent && !visit.visitorDocument.isNullOrBlank()) {
                Text("Documento: ${visit.visitorDocument}")
            } else if (visit.documentRefused) {
                Text("Documento: no quiso darlo")
            }
            MediaAttachmentChip(visit.visitorPhotoUrl, visit.visitorPhotoType, "Foto del visitante")
            visit.description?.takeIf { it.isNotBlank() }?.let { Text("Pedido: $it") }
            visit.enteredAt?.let { Text("Última entrada: ${whenText(it)}") }
            visit.exitedAt?.let { Text("Última salida: ${whenText(it)}") }
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
                    "${event.type} · ${whenText(event.createdAt)} · " +
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
                // Guía para autorizar por teléfono cuando el residente no responde en la app.
                CallGuide(visit, busy, onAuthorizeByCall, onRejectByCall)
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
                            "${visit.apartment.orEmpty()} · desde ${whenText(visit.enteredAt)}",
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
    // «dio» o «no»: el guardia siempre pide el documento y anota si la persona lo dio.
    var documentChoice by rememberSaveable { mutableStateOf("") }
    var photoUrl by remember { mutableStateOf<String?>(null) }
    var photoType by remember { mutableStateOf<String?>(null) }
    var photoName by remember { mutableStateOf<String?>(null) }
    var description by rememberSaveable { mutableStateOf("") }
    var stay by remember { mutableStateOf<Int?>(null) }
    var attempted by rememberSaveable { mutableStateOf(false) }
    // Registro simple: lo obligatorio a la vista; la estadía, los detalles y la foto en «Más datos».
    var showMore by rememberSaveable { mutableStateOf(false) }

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
                VisitorDocumentSection(
                    choice = documentChoice,
                    onChoice = { chosen ->
                        documentChoice = chosen
                        if (chosen != DOCUMENT_GIVEN) {
                            // Sin documento no se guarda nada de la persona: ni el número ni la foto.
                            visitorDocument = ""
                            photoUrl = null
                            photoType = null
                            photoName = null
                        }
                    },
                    document = visitorDocument,
                    onDocument = { visitorDocument = it },
                    attempted = attempted
                )
                TextButton(onClick = { showMore = !showMore }) {
                    Text(if (showMore) "Ocultar los datos opcionales" else "Más datos (opcional): estadía, detalles y foto")
                }
                if (showMore) {
                    StayChips(stay, { stay = it })
                    OutlinedTextField(
                        value = description,
                        onValueChange = { description = it },
                        label = { Text(if (visitorType == "domiciliario") "Detalles del pedido (opcional)" else "Detalles (opcional)") },
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                if (showMore && documentChoice == DOCUMENT_GIVEN) {
                    Text("Foto del visitante (opcional)", style = MaterialTheme.typography.titleSmall)
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
                        val given = documentChoice == DOCUMENT_GIVEN
                        val documentProblem = when {
                            documentChoice.isEmpty() -> DOCUMENT_MISSING_TEXT
                            given && visitorDocument.isBlank() ->
                                "Escribe el número del documento o marca «No quiso darlo»."
                            else -> null
                        }
                        if (target == null || visitorName.isBlank()) {
                            onMessage("Selecciona residente y escribe el nombre del visitante.")
                        } else if (documentProblem != null) {
                            onMessage(documentProblem)
                        } else {
                            val request = RegisterVisitRequest(
                                residentId = target.id,
                                visitorName = visitorName.trim(),
                                type = visitorType,
                                visitorDocument = if (given) visitorDocument.trim() else null,
                                documentRefused = documentChoice == DOCUMENT_REFUSED,
                                // Al dar el documento después del aviso, la persona acepta que se guarde.
                                mediaConsent = given,
                                mediaUrl = if (given) photoUrl else null,
                                mediaType = if (given) photoType else null,
                                description = description.trim().ifEmpty { null },
                                expectedStayMinutes = stay
                            )
                            onRegister(request) {
                                resident = null
                                visitorName = ""
                                visitorDocument = ""
                                documentChoice = ""
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

private const val DOCUMENT_GIVEN = "dio"
private const val DOCUMENT_REFUSED = "no"
private const val DOCUMENT_MISSING_TEXT =
    "Pide el documento a la persona. Si no lo quiere dar, marca «No quiso darlo»."

/**
 * El documento del visitante. El guardia siempre lo pide y antes le dice a la persona para qué es
 * (aviso de la Ley 1581 de 2012, de protección de datos). Si lo da, se anota con su número; si no
 * lo quiere dar, queda anotado así. Con las dos opciones la visita se registra.
 */
@Composable
private fun VisitorDocumentSection(
    choice: String,
    onChoice: (String) -> Unit,
    document: String,
    onDocument: (String) -> Unit,
    attempted: Boolean
) {
    Text("Documento del visitante *", style = MaterialTheme.typography.titleSmall)
    Text(
        "Antes de pedirlo, dile a la persona: «Le pedimos su documento solo para saber quién entra a la " +
            "unidad y por seguridad. Lo guarda la administración, no se usa para nada más y usted puede " +
            "pedirle verlo, corregirlo o borrarlo.»",
        style = MaterialTheme.typography.bodyMedium,
        color = DomuxColor.TextSoft
    )
    Column(Modifier.selectableGroup()) {
        DocumentChoiceRow("Dio su documento", choice == DOCUMENT_GIVEN) { onChoice(DOCUMENT_GIVEN) }
        DocumentChoiceRow("No quiso darlo", choice == DOCUMENT_REFUSED) { onChoice(DOCUMENT_REFUSED) }
    }
    when (choice) {
        DOCUMENT_GIVEN -> {
            val missing = attempted && document.isBlank()
            OutlinedTextField(
                value = document,
                onValueChange = { if (it.length <= 40) onDocument(it) },
                label = { Text("Número de documento *") },
                isError = missing,
                supportingText = {
                    Text(
                        if (missing) "Escribe el número del documento"
                        else "Queda anotado que la persona aceptó que se guarde su documento y, si la tomas, su foto."
                    )
                },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
        }
        DOCUMENT_REFUSED -> Text(
            "Queda anotado que no quiso darlo. La visita se registra igual y el residente decide si la deja entrar.",
            style = MaterialTheme.typography.bodyMedium
        )
        else -> if (attempted) {
            Text(DOCUMENT_MISSING_TEXT, color = DomuxColor.Bad, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

/** Una opción de la pregunta del documento; toda la fila se toca (mínimo 48 dp de alto). */
@Composable
private fun DocumentChoiceRow(text: String, selected: Boolean, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 48.dp)
            .selectable(selected = selected, onClick = onClick, role = Role.RadioButton),
        verticalAlignment = Alignment.CenterVertically
    ) {
        RadioButton(selected = selected, onClick = null)
        Text(text, modifier = Modifier.padding(start = 8.dp))
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
    onExit: (Visit) -> Unit,
    onEnterVehicle: () -> Unit = {},
    onSkipVehicle: () -> Unit = {}
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
                    scanned.qrPass?.vehicle?.let { vehicle ->
                        Text("Vienen en: ${vehicle.describe()}", style = MaterialTheme.typography.bodyMedium)
                        if (state.qrVehicleVisitId != null) {
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Button(onClick = onEnterVehicle, enabled = !state.busy) { Text(if (vehicle.type == "moto") "Registrar entrada de la moto" else "Registrar entrada del carro") }
                                TextButton(onClick = onSkipVehicle) { Text("No entra") }
                            }
                        }
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
                    // El documento que anotó el residente: el guardia lo compara con el que muestra la persona.
                    scanned.pendingVisitors.orEmpty()
                        .firstOrNull { it.name.equals(visitorName.trim(), ignoreCase = true) }
                        ?.document?.let { document ->
                            Text(
                                "Pide el documento y verifica que sea el $document.",
                                style = MaterialTheme.typography.bodyMedium,
                                color = DomuxColor.Primary
                            )
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
    // Una fila por persona: nombre y apellido, y su documento (los dos obligatorios). Máximo 5.
    val people = remember { mutableStateListOf(QrVisitorRow()) }
    // ¿Vienen en vehículo? Si sí: tipo, placa (obligatoria) y, si se quiere, marca y color.
    var withVehicle by rememberSaveable { mutableStateOf(false) }
    var vehicleType by rememberSaveable { mutableStateOf("carro") }
    var plate by rememberSaveable { mutableStateOf("") }
    var brand by rememberSaveable { mutableStateOf("") }
    var color by rememberSaveable { mutableStateOf("") }
    var attempted by rememberSaveable { mutableStateOf(false) }
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
                Text("Hasta $QR_MAX_PEOPLE personas por QR y 30 días de vigencia. La portería verifica el nombre y el documento de cada una.")
                DatePickerField("Válido desde", startDate, { startDate = it }, allowPastDates = false)
                DatePickerField("Válido hasta", endDate, { endDate = it }, allowPastDates = false)
                people.forEachIndexed { index, row ->
                    Text("Persona ${index + 1}", style = MaterialTheme.typography.labelLarge)
                    OutlinedTextField(
                        value = row.name,
                        onValueChange = { people[index] = row.copy(name = it.take(120)) },
                        label = { Text("Nombre y apellido *") },
                        isError = attempted && qrNameProblem(row.name) != null,
                        supportingText = { if (attempted) qrNameProblem(row.name)?.let { Text(it) } },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = row.document,
                        onValueChange = { people[index] = row.copy(document = it.take(15)) },
                        label = { Text("Documento *") },
                        isError = attempted && qrDocumentProblem(row.document) != null,
                        supportingText = {
                            Text(if (attempted) qrDocumentProblem(row.document) ?: "" else "Cédula, tarjeta de identidad o pasaporte")
                        },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    if (people.size > 1) {
                        TextButton(onClick = { people.removeAt(index) }) { Text("Quitar a la persona ${index + 1}") }
                    }
                }
                if (people.size < QR_MAX_PEOPLE) {
                    TextButton(onClick = { people.add(QrVisitorRow()) }) { Text("Agregar otra persona") }
                }
                FilterChip(
                    selected = withVehicle,
                    onClick = { withVehicle = !withVehicle },
                    label = { Text(if (withVehicle) "Vienen en vehículo: sí" else "¿Vienen en vehículo? Toca si es así") }
                )
                if (withVehicle) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        FilterChip(selected = vehicleType == "carro", onClick = { vehicleType = "carro" }, label = { Text("Carro") })
                        FilterChip(selected = vehicleType == "moto", onClick = { vehicleType = "moto" }, label = { Text("Moto") })
                    }
                    OutlinedTextField(
                        value = plate,
                        onValueChange = { plate = it.uppercase().filter { ch -> ch.isLetterOrDigit() }.take(7) },
                        label = { Text("Placa *") },
                        supportingText = { Text("Como ABC123 (carro) o ABC12D (moto)") },
                        isError = attempted && plate.length < 5,
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(brand, { brand = it.take(40) }, label = { Text("Marca (opcional)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(color, { color = it.take(30) }, label = { Text("Color (opcional)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                }
                Button(
                    onClick = {
                        attempted = true
                        val problem = people.firstNotNullOfOrNull { qrNameProblem(it.name) ?: qrDocumentProblem(it.document) }
                            ?: if (withVehicle && plate.length < 5) "escribe la placa del vehículo" else null
                        if (problem != null) {
                            onMessage("Revisa los datos de las personas: $problem")
                        } else {
                            val request = CreateVisitQrPassRequest(
                                validFrom = startDate,
                                validUntil = endDate,
                                maxPeople = people.size,
                                visitors = people.map { QrVisitor(it.name.trim(), cleanDocument(it.document)) },
                                vehicle = if (withVehicle) {
                                    QrVehicle(vehicleType, plate, brand.trim().ifBlank { null }, color.trim().ifBlank { null })
                                } else null
                            )
                            onCreate(request) {
                                people.clear()
                                people.add(QrVisitorRow())
                                withVehicle = false; plate = ""; brand = ""; color = ""
                                attempted = false
                            }
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
                    active.vehicle?.let { Text("Vehículo: ${it.describe()}") }
                    active.visitorNames.orEmpty().takeIf { it.isNotEmpty() }?.let { names ->
                        Text("Invitados: ${names.joinToString(", ")}", style = MaterialTheme.typography.bodySmall)
                    }
                    QrImage(activeBitmap, "Código QR de visitas")
                    shareError?.let {
                        Text("⚠ $it", color = DomuxColor.Bad, style = MaterialTheme.typography.bodySmall)
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


/** Una persona del QR mientras el residente la escribe. */
data class QrVisitorRow(val name: String = "", val document: String = "")

/** Máximo de personas por QR (la regla de la unidad; el servidor tiene la última palabra). */
const val QR_MAX_PEOPLE = 5

private val qrNameLetters = Regex("^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ' .-]+$")
private val qrDocument = Regex("^[A-Za-z0-9]{5,15}$")

fun cleanDocument(text: String): String = text.filterNot { it.isWhitespace() || it == '.' || it == '-' }.uppercase()

/** Qué le falta al nombre de una persona del QR, o null si está bien. */
fun qrNameProblem(name: String): String? {
    val clean = name.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }
    return when {
        clean.size < 2 -> "escribe nombre y apellido"
        !qrNameLetters.matches(name.trim()) -> "el nombre solo lleva letras"
        else -> null
    }
}

/** Qué le falta al documento, o null si está bien. */
fun qrDocumentProblem(document: String): String? =
    if (qrDocument.matches(cleanDocument(document))) null else "el documento debe tener de 5 a 15 letras o números"


/**
 * Registro guiado por llamada: cuando el residente no responde en la app, el guardia llama al
 * apartamento (citófono o teléfono de la portería), pregunta y marca lo que le dijeron.
 */
@Composable
private fun CallGuide(visit: Visit, busy: Boolean, onAuthorize: () -> Unit, onReject: () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("¿El residente no responde en la app?", style = MaterialTheme.typography.labelLarge)
        Text(
            "1. Llama a ${visit.apartment ?: "el apartamento"} por el citófono o el teléfono de la portería.\n" +
                "2. Pregunta si deja entrar a ${visit.visitorName}.\n" +
                "3. Marca lo que te respondió:",
            style = MaterialTheme.typography.bodySmall
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = onAuthorize, enabled = !busy) { Text("Sí autorizó") }
            TextButton(onClick = onReject, enabled = !busy) { Text("No autorizó") }
        }
    }
}
