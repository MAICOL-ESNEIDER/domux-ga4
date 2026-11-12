package com.dracknoval.domux

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SelectableDates
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.dracknoval.domux.data.CommonArea
import com.dracknoval.domux.data.Reservation
import com.dracknoval.domux.data.ResidentSummary
import com.dracknoval.domux.data.Session
import java.util.Calendar
import java.util.TimeZone

private const val TAB_LIST = "Reservas registradas"
private const val TAB_NEW = "Nueva reserva"

// Estados en los que una reserva todavía se puede aprobar, rechazar o cancelar.
private val OPEN_STATUSES = listOf("pendiente", "activa", "aprobada")

/** Lo que se le pregunta a la persona antes de ejecutar una acción. */
private class ReservationConfirmation(
    val message: String,
    val confirmLabel: String,
    val danger: Boolean,
    val action: () -> Unit
)

/**
 * Reservas de zonas comunes (HU-050 a HU-055). El residente reserva y cancela dentro del plazo de
 * cada zona; la administración reserva por un residente, aprueba, rechaza y cancela. La pantalla
 * solo dibuja lo que le da [ReservationsViewModel].
 */
@Composable
fun ReservationsScreen(
    navController: NavController,
    targetResidentId: Int? = null,
    viewModel: ReservationsViewModel = viewModel()
) {
    val state by viewModel.state.collectAsState()
    val canBook = Session.isAdmin || Session.isResident
    val tabs = if (canBook) listOf(TAB_LIST, TAB_NEW) else listOf(TAB_LIST)
    // Si la administración llega desde el perfil de un residente, abre directo la reserva nueva.
    var selectedTab by rememberSaveable { mutableStateOf(if (targetResidentId != null && canBook) 1 else 0) }
    val tab = selectedTab.coerceIn(tabs.indices)
    var confirmation by remember { mutableStateOf<ReservationConfirmation?>(null) }

    LaunchedEffect(Unit) { viewModel.start() }
    LaunchedEffect(targetResidentId) {
        if (targetResidentId != null) viewModel.useResident(targetResidentId)
    }

    DomuxScreenScaffold(title = "Reservas de zonas comunes", navController = navController) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            DomuxSectionTabs(tabs, tab) { selectedTab = it }
            if (state.message.isNotBlank()) {
                DomuxMessageBanner(state.message, state.messageIsError) { viewModel.dismissMessage() }
            }
            if (tabs[tab] == TAB_NEW) {
                ReservationForm(
                    modifier = Modifier.weight(1f),
                    state = state,
                    onArea = { viewModel.selectArea(it) },
                    onDate = { viewModel.selectDate(it) },
                    onSlot = { viewModel.selectSlot(it) },
                    onMonth = { year, month -> viewModel.showMonth(year, month) },
                    onResident = { viewModel.selectResident(it) },
                    onNotice = { viewModel.showNotice(it) },
                    onSubmit = { summary, attendees, note, mediaUrl, mediaType ->
                        confirmation = ReservationConfirmation(
                            message = summary,
                            confirmLabel = "Reservar",
                            danger = false,
                            action = { viewModel.create(attendees, note, mediaUrl, mediaType) }
                        )
                    },
                    onCreated = { selectedTab = 0 }
                )
            } else {
                ReservationList(
                    modifier = Modifier.weight(1f),
                    state = state,
                    onIncludeArchived = { viewModel.setIncludeArchived(it) },
                    onRefresh = { viewModel.refresh() },
                    onDecide = { reservation, status ->
                        val approving = status == "aprobada"
                        confirmation = ReservationConfirmation(
                            message = if (approving) {
                                "¿Estás seguro de aprobar la reserva de ${reservation.commonAreaName.orEmpty()} del ${humanDate(reservation.date)}?"
                            } else {
                                "¿Estás seguro de rechazar la reserva de ${reservation.commonAreaName.orEmpty()} del ${humanDate(reservation.date)}?"
                            },
                            confirmLabel = if (approving) "Aprobar" else "Rechazar",
                            danger = !approving,
                            action = { viewModel.decide(reservation, status) }
                        )
                    },
                    onCancel = { reservation ->
                        confirmation = ReservationConfirmation(
                            message = "¿Estás seguro de cancelar la reserva de ${reservation.commonAreaName.orEmpty()} del ${humanDate(reservation.date)}?",
                            confirmLabel = "Cancelar reserva",
                            danger = true,
                            action = { viewModel.cancel(reservation) }
                        )
                    },
                    onSend = { reservation, text, mediaUrl, mediaType ->
                        viewModel.sendMessage(reservation, text, mediaUrl, mediaType)
                    },
                    onNotice = { viewModel.showNotice(it) }
                )
            }
        }
    }

    confirmation?.let { pending ->
        DomuxConfirmDialog(
            title = "¿Estás seguro de confirmar esta acción?",
            message = pending.message,
            confirmLabel = pending.confirmLabel,
            danger = pending.danger,
            onConfirm = {
                confirmation = null
                pending.action()
            },
            onDismiss = { confirmation = null }
        )
    }
}

// ---------------------------------------------------------------------------
// Lista de reservas
// ---------------------------------------------------------------------------

@Composable
private fun ReservationList(
    modifier: Modifier,
    state: ReservationsUiState,
    onIncludeArchived: (Boolean) -> Unit,
    onRefresh: () -> Unit,
    onDecide: (Reservation, String) -> Unit,
    onCancel: (Reservation) -> Unit,
    onSend: (Reservation, String?, String?, String?) -> Unit,
    onNotice: (String) -> Unit
) {
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        if (state.loading) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            // El respaldo va dentro de la lista para que se desplace con ella y deje ver las reservas.
            if (Session.isAdmin) {
                item {
                    LegalBackupCard(
                        archiveLabel = "Archivar finalizadas y limpiar",
                        archiveMessage = "Las reservas finalizadas y las PQRS resueltas se respaldarán en un archivo Excel en este dispositivo y se ocultarán de la bandeja activa.",
                        includeArchived = state.includeArchived,
                        onToggleArchived = { onIncludeArchived(!state.includeArchived) },
                        onArchived = onRefresh
                    )
                }
            }
            if (state.reservations.isEmpty() && !state.loading) {
                item { Text("No hay reservas registradas.") }
            }
            items(state.reservations, key = { it.id }) { reservation ->
                ReservationCard(
                    reservation = reservation,
                    busy = state.busy,
                    onDecide = { status -> onDecide(reservation, status) },
                    onCancel = { onCancel(reservation) },
                    onSend = { text, mediaUrl, mediaType -> onSend(reservation, text, mediaUrl, mediaType) },
                    onNotice = onNotice
                )
            }
        }
    }
}

@Composable
private fun ReservationCard(
    reservation: Reservation,
    busy: Boolean,
    onDecide: (String) -> Unit,
    onCancel: () -> Unit,
    onSend: (String?, String?, String?) -> Unit,
    onNotice: (String) -> Unit
) {
    val actionable = reservation.status in OPEN_STATUSES && !reservation.isArchived
    DomuxCard(Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Text(reservation.commonAreaName ?: "Zona común", style = MaterialTheme.typography.titleMedium)
            Text("${humanDate(reservation.date)} · ${reservation.timeSlot}")
            Text("Residente: ${reservation.residentName.orEmpty()} · ${reservation.apartment.orEmpty()}")
            reservation.attendees?.let { people ->
                Text("Personas: $people")
            }
            if (reservation.createdByAdministration) {
                Text("Creada por administración", style = MaterialTheme.typography.labelSmall)
            }
            reservation.messages.orEmpty().forEach { item ->
                Text(
                    "${item.authorName ?: item.authorRole} · ${item.createdAt.orEmpty()}",
                    style = MaterialTheme.typography.labelSmall
                )
                if (!item.message.isNullOrBlank()) Text(item.message)
                MediaAttachmentChip(item.mediaUrl, item.mediaType)
            }
            DomuxStatusBadge(
                reservation.status.replaceFirstChar(Char::uppercase).replace('_', ' '),
                when (reservation.status) {
                    "aprobada", "activa" -> DomuxBadgeTone.SUCCESS
                    "rechazada", "cancelada" -> DomuxBadgeTone.ALERT
                    else -> DomuxBadgeTone.PROGRESS
                }
            )
            if (reservation.requestedByMinor) {
                DomuxStatusBadge("Menor con autorización parental", DomuxBadgeTone.PROGRESS)
            }
            if (reservation.isArchived) {
                DomuxStatusBadge("Archivada en Excel", DomuxBadgeTone.ALERT)
            }
            // El residente cancela hasta el plazo de la zona (HU-053); después, debe escribirle a la administración.
            if (Session.isResident && actionable) {
                val until = humanDate(reservation.cancelUntil)
                if (reservation.canCancel) {
                    if (until.isNotEmpty()) {
                        Text(
                            "Puedes cancelarla hasta el $until.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.secondary
                        )
                    }
                    TextButton(enabled = !busy, onClick = onCancel) { Text("Cancelar reserva") }
                } else if (until.isNotEmpty()) {
                    Text(
                        "Ya no se puede cancelar: el plazo terminó el $until. Si necesitas cambiarla, escríbele a la administración.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.secondary
                    )
                }
            }
            if (Session.isAdmin && actionable) {
                Row(modifier = Modifier.horizontalScroll(rememberScrollState())) {
                    if (reservation.status == "pendiente" || reservation.status == "activa") {
                        TextButton(enabled = !busy, onClick = { onDecide("aprobada") }) { Text("Aprobar") }
                        TextButton(enabled = !busy, onClick = { onDecide("rechazada") }) { Text("Rechazar") }
                    }
                    TextButton(enabled = !busy, onClick = onCancel) { Text("Cancelar reserva") }
                }
            }
            if ((Session.isResident || Session.isAdmin) && actionable) {
                ReservationReplyBox(reservation, busy, onSend, onNotice)
            }
        }
    }
}

@Composable
private fun ReservationReplyBox(
    reservation: Reservation,
    busy: Boolean,
    onSend: (String?, String?, String?) -> Unit,
    onNotice: (String) -> Unit
) {
    // Cuando el servidor acepta el mensaje la lista trae uno más y el cuadro queda limpio.
    val count = reservation.messages?.size
    var reply by remember(reservation.id, count) { mutableStateOf("") }
    var mediaUrl by remember(reservation.id, count) { mutableStateOf<String?>(null) }
    var mediaType by remember(reservation.id, count) { mutableStateOf<String?>(null) }
    var mediaName by remember(reservation.id, count) { mutableStateOf<String?>(null) }
    OutlinedTextField(
        value = reply,
        onValueChange = { reply = it },
        label = { Text("Mensaje para ${if (Session.isAdmin) "el residente" else "administración"}") },
        modifier = Modifier.fillMaxWidth()
    )
    MediaAttachmentPicker(
        mediaName,
        { url, type, name ->
            mediaUrl = url
            mediaType = type
            mediaName = name
        },
        { onNotice(it) },
        kinds = AttachmentKinds.MEDIA_AND_PDF,
        onClear = { mediaUrl = null; mediaType = null; mediaName = null }
    )
    TextButton(
        enabled = !busy,
        onClick = {
            if (reply.isBlank() && mediaUrl == null) {
                onNotice("Escribe un mensaje o adjunta un archivo.")
            } else {
                onSend(reply.trim().ifEmpty { null }, mediaUrl, mediaType)
            }
        }
    ) { Text("Enviar mensaje") }
}

// ---------------------------------------------------------------------------
// Reserva nueva
// ---------------------------------------------------------------------------

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun ReservationForm(
    modifier: Modifier,
    state: ReservationsUiState,
    onArea: (Int) -> Unit,
    onDate: (String) -> Unit,
    onSlot: (String) -> Unit,
    onMonth: (Int, Int) -> Unit,
    onResident: (ResidentSummary?) -> Unit,
    onNotice: (String) -> Unit,
    onSubmit: (String, Int?, String?, String?, String?) -> Unit,
    onCreated: () -> Unit
) {
    var attendeesText by rememberSaveable { mutableStateOf("") }
    var note by rememberSaveable { mutableStateOf("") }
    var attempted by rememberSaveable { mutableStateOf(false) }
    // El adjunto va en base64 y puede pesar varios MB: no se guarda con el estado de la pantalla.
    var mediaUrl by remember { mutableStateOf<String?>(null) }
    var mediaType by remember { mutableStateOf<String?>(null) }
    var mediaName by remember { mutableStateOf<String?>(null) }
    var handled by rememberSaveable { mutableStateOf(state.created) }

    // Cuando el servidor acepta la reserva, el formulario queda limpio y se vuelve a la lista.
    LaunchedEffect(state.created) {
        if (state.created != handled) {
            handled = state.created
            attendeesText = ""
            note = ""
            attempted = false
            mediaUrl = null
            mediaType = null
            mediaName = null
            onCreated()
        }
    }

    val admin = Session.isAdmin
    val minorBlocked = Session.isResident && Session.isMinor && !Session.parentalConsent
    val area = state.area
    val today = colombiaToday()
    // El residente reserva dentro de la anticipación de la zona; la administración, desde hoy (HU-055).
    val firstDate = addDaysIso(today, if (admin) 0 else (area?.minAdvanceDays ?: 0))
    val lastDate = if (admin || area == null || area.maxAdvanceDays <= 0) null else addDaysIso(today, area.maxAdvanceDays)
    val capacity = area?.capacity
    val people = attendeesText.toIntOrNull()
    val peopleError = capacity != null && (people == null || people < 1 || people > capacity)

    Column(
        modifier = modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        DomuxCard(Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                if (minorBlocked) {
                    Text(
                        "Los menores de edad no pueden reservar zonas comunes salvo que cuenten con autorización parental activa registrada en administración.",
                        color = MaterialTheme.colorScheme.error
                    )
                }
                Text(
                    if (admin) "Crear reserva para un residente" else "Nueva reserva",
                    style = MaterialTheme.typography.titleMedium
                )
                Text("Zona común", style = MaterialTheme.typography.labelLarge)
                if (state.areas.isEmpty()) {
                    Text("Todavía no hay zonas comunes configuradas.")
                } else {
                    Row(
                        modifier = Modifier.horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        state.areas.forEach { option ->
                            FilterChip(
                                selected = state.areaId == option.id,
                                onClick = { onArea(option.id) },
                                label = { Text(option.name) }
                            )
                        }
                    }
                }
                if (area != null) ZoneRules(area, admin)
                if (admin) {
                    DomuxResidentSearchField(
                        selectedResident = state.resident,
                        onSelectResident = onResident
                    )
                    if (attempted && state.resident == null) {
                        Text("Selecciona el residente.", color = MaterialTheme.colorScheme.error)
                    }
                }
                ReservationDatePicker(
                    value = state.date,
                    firstDate = firstDate,
                    lastDate = lastDate,
                    unavailable = state.fullDates + state.closedDates,
                    onMonthChanged = onMonth,
                    onValueChange = onDate
                )
                Text(
                    if (lastDate != null) {
                        "Puedes reservar del ${humanDate(firstDate)} al ${humanDate(lastDate)}. Los días sin horarios libres o cerrados por mantenimiento aparecen bloqueados."
                    } else {
                        "Los días sin horarios libres o cerrados por mantenimiento aparecen bloqueados."
                    },
                    style = MaterialTheme.typography.bodySmall
                )
                if (attempted && state.date.isBlank()) {
                    Text("La fecha es obligatoria.", color = MaterialTheme.colorScheme.error)
                }
                if (state.date.isNotBlank()) {
                    Text("Horarios", style = MaterialTheme.typography.titleSmall)
                    when {
                        state.availabilityLoading -> LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                        state.availability?.closed == true -> Text(
                            "${area?.name ?: "La zona"} está cerrada ese día por mantenimiento. Elige otra fecha.",
                            color = MaterialTheme.colorScheme.error
                        )
                        else -> FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(4.dp),
                            verticalArrangement = Arrangement.spacedBy(4.dp)
                        ) {
                            state.slots.forEach { time ->
                                val available = state.availability?.availableSlots?.contains(time) ?: false
                                FilterChip(
                                    selected = state.slot == time,
                                    enabled = available,
                                    onClick = { onSlot(time) },
                                    label = { Text(if (available) time else "$time · Ocupado") }
                                )
                            }
                        }
                    }
                }
                if (attempted && state.slot.isBlank()) {
                    Text("Selecciona una franja horaria disponible.", color = MaterialTheme.colorScheme.error)
                }
                if (capacity != null) {
                    OutlinedTextField(
                        value = attendeesText,
                        onValueChange = { attendeesText = it.filter(Char::isDigit).take(4) },
                        label = { Text("¿Cuántas personas asistirán? * (máximo $capacity)") },
                        isError = attempted && peopleError,
                        supportingText = {
                            if (attempted && peopleError) Text("Escribe un número entre 1 y $capacity")
                        },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                OutlinedTextField(
                    value = note,
                    onValueChange = { note = it },
                    label = { Text("Mensaje opcional para administración") },
                    modifier = Modifier.fillMaxWidth()
                )
                MediaAttachmentPicker(
                    mediaName,
                    { url, type, name ->
                        mediaUrl = url
                        mediaType = type
                        mediaName = name
                    },
                    { onNotice(it) },
                    kinds = AttachmentKinds.MEDIA_AND_PDF,
                    onClear = { mediaUrl = null; mediaType = null; mediaName = null }
                )
                Button(
                    enabled = !state.busy && !minorBlocked && area != null,
                    onClick = {
                        attempted = true
                        val chosen = area
                        val incomplete = state.date.isBlank() || state.slot.isBlank() ||
                            (admin && state.resident == null) || peopleError
                        if (chosen == null || incomplete) {
                            onNotice("Revisa los datos marcados en rojo.")
                        } else {
                            val resident = state.resident
                            val onBehalf = if (admin && resident != null) " a nombre de ${resident.name}" else ""
                            onSubmit(
                                "¿Crear la reserva de ${chosen.name} para el ${humanDate(state.date)}, en la franja ${state.slot}$onBehalf?",
                                if (capacity != null) people else null,
                                note.trim().ifEmpty { null },
                                mediaUrl,
                                mediaType
                            )
                        }
                    },
                    modifier = Modifier.fillMaxWidth()
                ) { Text(if (state.busy) "Guardando..." else "Reservar") }
            }
        }
    }
}

/** Las reglas de la zona elegida (HU-055), para que quien reserva sepa de antemano qué se le va a pedir. */
@Composable
private fun ZoneRules(area: CommonArea, admin: Boolean) {
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        zoneRuleLines(area, admin).forEach { line ->
            Text(
                "• $line",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

private fun zoneRuleLines(area: CommonArea, admin: Boolean): List<String> {
    val lines = mutableListOf<String>()
    val opensAt = area.openTime
    val closesAt = area.closeTime
    if (opensAt != null && closesAt != null) {
        val slotText = if (area.slotMinutes > 0) ", en franjas de ${slotLengthText(area.slotMinutes)}" else ""
        lines.add("Horario: de $opensAt a $closesAt$slotText.")
    }
    area.capacity?.let { lines.add("Aforo máximo: $it personas.") }
    if (admin) {
        lines.add("Como administración puedes reservar sin el límite diario ni semanal del residente.")
    } else {
        if (area.minAdvanceDays > 0) {
            lines.add("Se reserva con al menos ${daysText(area.minAdvanceDays)} de anticipación.")
        }
        if (area.maxAdvanceDays > 0) {
            lines.add("Se puede reservar hasta con ${daysText(area.maxAdvanceDays)} de anticipación.")
        }
        if (area.weeklyLimit > 0) {
            val noun = if (area.weeklyLimit == 1) "reserva" else "reservas"
            lines.add("Máximo ${area.weeklyLimit} $noun por semana (de lunes a domingo) en esta zona, y 1 por día.")
        }
    }
    if (area.cancelDeadlineDays > 0) {
        lines.add("El residente puede cancelar hasta ${daysText(area.cancelDeadlineDays)} antes de la fecha reservada.")
    }
    area.maintenanceWeekday?.let { weekday ->
        lines.add("Cierra por mantenimiento los ${weekdayPlural(weekday)} (si ese día es festivo, pasa al día siguiente).")
    }
    return lines
}

// ---------------------------------------------------------------------------
// Calendario de la reserva
// ---------------------------------------------------------------------------

@Composable
private fun ReservationDatePicker(
    value: String,
    firstDate: String,
    lastDate: String?,
    unavailable: Set<String>,
    onMonthChanged: (year: Int, month: Int) -> Unit,
    onValueChange: (String) -> Unit
) {
    var showPicker by remember { mutableStateOf(false) }
    OutlinedButton(onClick = { showPicker = true }, modifier = Modifier.fillMaxWidth()) {
        Text(if (value.isBlank()) "Seleccionar fecha" else "Fecha: ${humanDate(value)}")
    }
    if (showPicker) {
        ReservationDateDialog(
            value = value,
            firstDate = firstDate,
            lastDate = lastDate,
            unavailable = unavailable,
            onMonthChanged = onMonthChanged,
            onPicked = { picked ->
                onValueChange(picked)
                showPicker = false
            },
            onDismiss = { showPicker = false }
        )
    }
}

/**
 * Calendario de Material con los días que no se pueden elegir apagados: los anteriores a
 * [firstDate], los posteriores a [lastDate], los sin franjas libres y los de mantenimiento.
 * Los días sin franjas llegan del servidor después de abrirlo; por eso se leen al momento de
 * dibujar cada día y no al crearlo.
 */
@Composable
@OptIn(ExperimentalMaterial3Api::class)
private fun ReservationDateDialog(
    value: String,
    firstDate: String,
    lastDate: String?,
    unavailable: Set<String>,
    onMonthChanged: (year: Int, month: Int) -> Unit,
    onPicked: (String) -> Unit,
    onDismiss: () -> Unit
) {
    val unavailableNow by rememberUpdatedState(unavailable)
    val selectableDates = remember(firstDate, lastDate) {
        object : SelectableDates {
            override fun isSelectableDate(utcTimeMillis: Long): Boolean {
                val day = isoFromUtcMillis(utcTimeMillis)
                return day >= firstDate && (lastDate == null || day <= lastDate) && day !in unavailableNow
            }

            override fun isSelectableYear(year: Int): Boolean {
                val firstYear = firstDate.take(4).toIntOrNull() ?: 0
                val lastYear = lastDate?.take(4)?.toIntOrNull() ?: Int.MAX_VALUE
                return year in firstYear..lastYear
            }
        }
    }
    val pickerState = rememberDatePickerState(
        initialSelectedDateMillis = utcMillisFromIso(value),
        initialDisplayedMonthMillis = utcMillisFromIso(value) ?: utcMillisFromIso(firstDate),
        selectableDates = selectableDates
    )
    LaunchedEffect(pickerState.displayedMonthMillis) {
        val calendar = Calendar.getInstance(TimeZone.getTimeZone("UTC"))
        calendar.timeInMillis = pickerState.displayedMonthMillis
        onMonthChanged(calendar.get(Calendar.YEAR), calendar.get(Calendar.MONTH) + 1)
    }
    val picked = pickerState.selectedDateMillis?.let { isoFromUtcMillis(it) }
    val canConfirm = picked != null &&
        picked >= firstDate &&
        (lastDate == null || picked <= lastDate) &&
        picked !in unavailable
    DatePickerDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(
                enabled = canConfirm,
                onClick = { if (picked != null) onPicked(picked) }
            ) { Text("Aceptar") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancelar") } }
    ) {
        DatePicker(state = pickerState)
    }
}
