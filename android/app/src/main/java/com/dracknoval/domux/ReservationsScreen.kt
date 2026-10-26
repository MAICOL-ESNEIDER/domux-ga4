package com.dracknoval.domux

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.SelectableDates
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.dracknoval.domux.data.CommonArea
import com.dracknoval.domux.data.AddReservationMessageRequest
import com.dracknoval.domux.data.CreateReservationRequest
import com.dracknoval.domux.data.Reservation
import com.dracknoval.domux.data.ReservationAvailabilityResponse
import com.dracknoval.domux.data.ResidentSummary
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.UpdateReservationStatusRequest
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.TimeZone

private val reservationSlots = listOf(
    "08:00-10:00", "10:00-12:00", "12:00-14:00", "14:00-16:00",
    "16:00-18:00", "18:00-20:00", "20:00-22:00"
)

private fun reservationDateString(date: Date): String =
    SimpleDateFormat("yyyy-MM-dd", Locale.US).apply {
        timeZone = TimeZone.getTimeZone("UTC")
    }.format(date)

private fun reservationTodayString(): String =
    SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Calendar.getInstance().time)

private fun reservationDateMillis(value: String): Long? = try {
    SimpleDateFormat("yyyy-MM-dd", Locale.US).apply {
        isLenient = false
        timeZone = TimeZone.getTimeZone("UTC")
    }.parse(value)?.time
} catch (_: Exception) {
    null
}

@Composable
@OptIn(ExperimentalMaterial3Api::class)
private fun ReservationCalendarPicker(
    value: String,
    blockedDates: Set<String>,
    onMonthChanged: (year: Int, month: Int) -> Unit,
    onValueChange: (String) -> Unit
) {
    var showPicker by remember { mutableStateOf(false) }
    val selectableDates = remember(blockedDates) {
        object : SelectableDates {
            override fun isSelectableDate(utcTimeMillis: Long): Boolean {
                val selectedDate = reservationDateString(Date(utcTimeMillis))
                return selectedDate >= reservationTodayString() && selectedDate !in blockedDates
            }

            override fun isSelectableYear(year: Int): Boolean =
                year >= Calendar.getInstance().get(Calendar.YEAR)
        }
    }
    val state = rememberDatePickerState(
        initialSelectedDateMillis = reservationDateMillis(value),
        selectableDates = selectableDates
    )
    LaunchedEffect(state.displayedMonthMillis) {
        val calendar = Calendar.getInstance(TimeZone.getTimeZone("UTC")).apply {
            timeInMillis = state.displayedMonthMillis
        }
        onMonthChanged(calendar.get(Calendar.YEAR), calendar.get(Calendar.MONTH) + 1)
    }
    OutlinedButton(onClick = { showPicker = true }, modifier = Modifier.fillMaxWidth()) {
        Text(if (value.isBlank()) "Seleccionar fecha" else "Fecha: $value")
    }
    if (blockedDates.isNotEmpty()) {
        Text("Los días totalmente ocupados aparecen bloqueados.", style = MaterialTheme.typography.bodySmall)
    }
    if (showPicker) {
        val selectedDate = state.selectedDateMillis?.let { reservationDateString(Date(it)) }
        val canConfirm = selectedDate != null &&
            selectedDate >= reservationTodayString() &&
            selectedDate !in blockedDates
        DatePickerDialog(
            onDismissRequest = { showPicker = false },
            confirmButton = {
                TextButton(
                    enabled = canConfirm,
                    onClick = {
                        state.selectedDateMillis?.let { onValueChange(reservationDateString(Date(it))) }
                        showPicker = false
                    }
                ) { Text("Aceptar") }
            },
            dismissButton = { TextButton(onClick = { showPicker = false }) { Text("Cancelar") } }
        ) {
            DatePicker(state = state)
        }
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class, ExperimentalMaterial3Api::class)
fun ReservationsScreen(navController: NavController, targetResidentId: Int? = null) {
    var reservations by remember { mutableStateOf<List<Reservation>>(emptyList()) }
    var areas by remember { mutableStateOf<List<CommonArea>>(emptyList()) }
    var residents by remember { mutableStateOf<List<ResidentSummary>>(emptyList()) }
    var availability by remember { mutableStateOf<ReservationAvailabilityResponse?>(null) }
    var blockedDates by remember { mutableStateOf<Set<String>>(emptySet()) }
    var calendarMonth by remember { mutableStateOf<Pair<Int, Int>?>(null) }
    var selectedArea by remember { mutableStateOf<CommonArea?>(null) }
    var selectedResident by remember { mutableStateOf<ResidentSummary?>(null) }
    var date by remember { mutableStateOf("") }
    var slot by remember { mutableStateOf("") }
    var requestMessage by remember { mutableStateOf("") }
    var requestMediaUrl by remember { mutableStateOf<String?>(null) }
    var requestMediaType by remember { mutableStateOf<String?>(null) }
    var requestMediaName by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(true) }
    var submitting by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var confirmation by remember { mutableStateOf<Pair<String, () -> Unit>?>(null) }
    var attemptedCreate by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    suspend fun load() {
        loading = true
        try {
            val response = RetrofitClient.api.getReservations(Session.bearer())
            if (response.isSuccessful) reservations = response.body()?.reservations.orEmpty()
            else message = mensajeDeError(response.code(), response.errorBody()?.string())
            val areaResponse = RetrofitClient.api.getCommonAreas(Session.bearer())
            if (areaResponse.isSuccessful) {
                areas = areaResponse.body()?.areas.orEmpty()
                if (selectedArea == null) selectedArea = areas.firstOrNull()
            }
            if (Session.isAdmin) {
                val residentResponse = RetrofitClient.api.getResidents(Session.bearer())
                if (residentResponse.isSuccessful) {
                    residents = residentResponse.body()?.residents.orEmpty()
                    selectedResident = residents.firstOrNull { it.id == targetResidentId }
                        ?: selectedResident?.takeIf { current ->
                            residents.any { it.id == current.id }
                        }
                        ?: residents.firstOrNull()
                }
            }
        } catch (exception: Exception) {
            message = "No se pudieron cargar las reservas: ${exception.message}"
        } finally {
            loading = false
        }
    }

    LaunchedEffect(Unit) { load() }
    LaunchedEffect(selectedArea?.id, date) {
        val area = selectedArea
        if (area != null && date.matches(Regex("\\d{4}-\\d{2}-\\d{2}"))) {
            availability = null
            try {
                val response = RetrofitClient.api.getReservationAvailability(
                    Session.bearer(), area.id, date
                )
                if (response.isSuccessful) availability = response.body()
                else message = mensajeDeError(response.code(), response.errorBody()?.string())
            } catch (exception: Exception) {
                message = "No se pudo consultar la disponibilidad: ${exception.message}"
            }
        } else availability = null
    }
    LaunchedEffect(selectedArea?.id, calendarMonth) {
        val area = selectedArea
        val month = calendarMonth
        if (area != null && month != null) {
            blockedDates = emptySet()
            try {
                val response = RetrofitClient.api.getReservationCalendar(
                    Session.bearer(), area.id, month.first, month.second
                )
                if (response.isSuccessful) blockedDates = response.body()?.blockedDates.orEmpty().toSet()
                else message = mensajeDeError(response.code(), response.errorBody()?.string())
            } catch (exception: Exception) {
                message = "No se pudo consultar el calendario: ${exception.message}"
            }
        } else blockedDates = emptySet()
    }

    Column(Modifier.fillMaxSize().padding(20.dp)) {
        Text("Reservas de zonas comunes", fontSize = 24.sp, color = MaterialTheme.colorScheme.primary)
        if (message.isNotBlank()) Text(message, color = MaterialTheme.colorScheme.error)
        if (Session.isAdmin || Session.isResident) {
            DomuxCard(Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
                Column(Modifier.padding(14.dp)) {
                    Text(if (Session.isAdmin) "Crear reserva para un residente" else "Nueva reserva", style = MaterialTheme.typography.titleMedium)
                    Text("Zona común")
                    Row {
                        areas.forEach { area ->
                            FilterChip(
                                selected = selectedArea?.id == area.id,
                                onClick = { selectedArea = area; slot = "" },
                                label = { Text(area.name) },
                                modifier = Modifier.padding(end = 5.dp)
                            )
                        }
                    }
                    if (Session.isAdmin) {
                        Text("Residente")
                        residents.forEach { resident ->
                            FilterChip(
                                selected = selectedResident?.id == resident.id,
                                onClick = { selectedResident = resident },
                                label = { Text("${resident.name} · ${resident.apartment.orEmpty()}") },
                                modifier = Modifier.padding(end = 5.dp)
                            )
                        }
                    }
                    ReservationCalendarPicker(
                        date,
                        blockedDates,
                        { year, month -> calendarMonth = year to month },
                        { date = it; slot = "" }
                    )
                    if (attemptedCreate && date.isBlank()) {
                        Text("La fecha es obligatoria.", color = MaterialTheme.colorScheme.error)
                    }
                    if (date.isNotBlank()) {
                        Text("Horarios disponibles", style = MaterialTheme.typography.titleSmall)
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            reservationSlots.forEach { time ->
                                val available = availability?.availableSlots?.contains(time) ?: false
                                FilterChip(
                                    selected = slot == time,
                                    enabled = available,
                                    onClick = { slot = time },
                                    label = { Text(if (available) time else "$time · Ocupado") }
                                )
                            }
                        }
                    }
                    if (attemptedCreate && slot.isBlank()) {
                        Text("Selecciona una franja horaria disponible.", color = MaterialTheme.colorScheme.error)
                    }
                    if (attemptedCreate && Session.isAdmin && selectedResident == null) {
                        Text("Selecciona el residente.", color = MaterialTheme.colorScheme.error)
                    }
                    OutlinedTextField(
                        value = requestMessage,
                        onValueChange = { requestMessage = it },
                        label = { Text("Mensaje opcional para administración") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    MediaAttachmentPicker(requestMediaName, { url, type, name ->
                        requestMediaUrl = url
                        requestMediaType = type
                        requestMediaName = name
                    }, { message = it })
                    Button(
                        enabled = !submitting,
                        onClick = {
                            attemptedCreate = true
                            val area = selectedArea
                            if (area == null || date.isBlank() || slot.isBlank() ||
                                (Session.isAdmin && selectedResident == null)
                            ) {
                                message = "Elige zona, fecha, horario y residente cuando corresponda."
                                return@Button
                            }
                            confirmation = "¿Estás seguro de crear esta reserva?" to {
                                scope.launch {
                                    submitting = true
                                    try {
                                        val response = RetrofitClient.api.createReservation(
                                            Session.bearer(),
                                            CreateReservationRequest(
                                                area.id, date, slot,
                                                if (Session.isAdmin) selectedResident?.id else null,
                                                requestMessage.trim().takeIf(String::isNotEmpty),
                                                requestMediaUrl,
                                                requestMediaType
                                            )
                                        )
                                        message = if (response.isSuccessful) {
                                            date = ""; slot = ""
                                            requestMessage = ""
                                            requestMediaUrl = null
                                            requestMediaType = null
                                            requestMediaName = null
                                            attemptedCreate = false
                                            load()
                                            "Reserva creada."
                                        } else mensajeDeError(response.code(), response.errorBody()?.string())
                                    } catch (exception: Exception) {
                                        message = "No se pudo crear la reserva: ${exception.message}"
                                    } finally {
                                        submitting = false
                                    }
                                }
                            }
                        },
                        modifier = Modifier.fillMaxWidth()
                    ) { Text(if (submitting) "Guardando..." else "Reservar") }
                }
            }
        }

        Text("Reservas registradas", style = MaterialTheme.typography.titleLarge)
        if (loading) CircularProgressIndicator()
        else LazyColumn(Modifier.weight(1f)) {
            items(reservations, key = { it.id }) { reservation ->
                DomuxCard(Modifier.fillMaxWidth().padding(vertical = 5.dp)) {
                    Column(Modifier.padding(14.dp)) {
                        Text(reservation.commonAreaName ?: "Zona común", style = MaterialTheme.typography.titleMedium)
                        Text("${reservation.date} · ${reservation.timeSlot}")
                        Text("Residente: ${reservation.residentName.orEmpty()} · ${reservation.apartment.orEmpty()}")
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
                        if (Session.isAdmin && reservation.status in listOf("pendiente", "activa")) {
                            Row {
                                TextButton(onClick = {
                                    confirmation = "¿Estás seguro de aprobar la reserva?" to {
                                        scope.launch {
                                            try {
                                                val response = RetrofitClient.api.updateReservationStatus(
                                                    Session.bearer(), reservation.id,
                                                    UpdateReservationStatusRequest("aprobada")
                                                )
                                                message = if (response.isSuccessful) "Reserva aprobada."
                                                else mensajeDeError(response.code(), response.errorBody()?.string())
                                                load()
                                            } catch (exception: Exception) {
                                                message = "No se pudo aprobar: ${exception.message}"
                                            }
                                        }
                                    }
                                }) { Text("Aprobar") }
                                TextButton(onClick = {
                                    confirmation = "¿Estás seguro de rechazar la reserva?" to {
                                        scope.launch {
                                            try {
                                                val response = RetrofitClient.api.updateReservationStatus(
                                                    Session.bearer(), reservation.id,
                                                    UpdateReservationStatusRequest("rechazada")
                                                )
                                                message = if (response.isSuccessful) "Reserva rechazada."
                                                else mensajeDeError(response.code(), response.errorBody()?.string())
                                                load()
                                            } catch (exception: Exception) {
                                                message = "No se pudo rechazar: ${exception.message}"
                                            }
                                        }
                                    }
                                }) { Text("Rechazar") }
                            }
                        }
                        if (
                            Session.isAdmin &&
                            reservation.status in listOf("pendiente", "activa", "aprobada")
                        ) {
                            TextButton(onClick = {
                                confirmation = "¿Estás seguro de cancelar esta reserva?" to {
                                    scope.launch {
                                        try {
                                            val response = RetrofitClient.api.cancelReservation(
                                                Session.bearer(), reservation.id
                                            )
                                            message = if (response.isSuccessful) "Reserva cancelada."
                                            else mensajeDeError(response.code(), response.errorBody()?.string())
                                            load()
                                        } catch (exception: Exception) {
                                            message = "No se pudo cancelar la reserva: ${exception.message}"
                                        }
                                    }
                                }
                            }) { Text("Cancelar reserva") }
                        }
                        if (
                            (Session.isResident || Session.isAdmin) &&
                            reservation.status in listOf("pendiente", "activa", "aprobada")
                        ) {
                            var reply by remember(reservation.id) { mutableStateOf("") }
                            var replyMediaUrl by remember(reservation.id) { mutableStateOf<String?>(null) }
                            var replyMediaType by remember(reservation.id) { mutableStateOf<String?>(null) }
                            var replyMediaName by remember(reservation.id) { mutableStateOf<String?>(null) }
                            OutlinedTextField(
                                value = reply,
                                onValueChange = { reply = it },
                                label = { Text("Mensaje para ${if (Session.isAdmin) "el residente" else "administración"}") },
                                modifier = Modifier.fillMaxWidth()
                            )
                            MediaAttachmentPicker(replyMediaName, { url, type, name ->
                                replyMediaUrl = url
                                replyMediaType = type
                                replyMediaName = name
                            }, { message = it })
                            TextButton(onClick = {
                                if (reply.isBlank() && replyMediaUrl == null) {
                                    message = "Escribe un mensaje o adjunta un archivo."
                                    return@TextButton
                                }
                                scope.launch {
                                    try {
                                        val response = RetrofitClient.api.addReservationMessage(
                                            Session.bearer(),
                                            reservation.id,
                                            AddReservationMessageRequest(
                                                reply.trim().takeIf(String::isNotEmpty),
                                                replyMediaUrl,
                                                replyMediaType
                                            )
                                        )
                                        message = if (response.isSuccessful) "Mensaje enviado."
                                        else mensajeDeError(response.code(), response.errorBody()?.string())
                                        if (response.isSuccessful) load()
                                    } catch (exception: Exception) {
                                        message = "No se pudo enviar el mensaje: ${exception.message}"
                                    }
                                }
                            }) { Text("Enviar mensaje") }
                        }
                        if (
                            Session.isResident &&
                            reservation.status in listOf("activa", "pendiente", "aprobada") &&
                            reservation.date > reservationTodayString()
                        ) {
                            TextButton(onClick = {
                                confirmation = "¿Estás seguro de cancelar esta reserva?" to {
                                    scope.launch {
                                        try {
                                            val response = RetrofitClient.api.cancelReservation(Session.bearer(), reservation.id)
                                            message = if (response.isSuccessful) "Reserva cancelada."
                                            else mensajeDeError(response.code(), response.errorBody()?.string())
                                            load()
                                        } catch (exception: Exception) {
                                            message = "No se pudo cancelar: ${exception.message}"
                                        }
                                    }
                                }
                            }) { Text("Cancelar") }
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
            danger = prompt.contains("rechazar", ignoreCase = true) ||
                prompt.contains("cancelar", ignoreCase = true),
            onConfirm = { confirmation = null; action() },
            onDismiss = { confirmation = null }
        )
    }
}
