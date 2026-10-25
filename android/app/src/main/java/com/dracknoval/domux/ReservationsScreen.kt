package com.dracknoval.domux

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.dracknoval.domux.data.CommonArea
import com.dracknoval.domux.data.CreateReservationRequest
import com.dracknoval.domux.data.Reservation
import com.dracknoval.domux.data.ReservationAvailabilityResponse
import com.dracknoval.domux.data.ResidentSummary
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.UpdateReservationStatusRequest
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.launch

private val reservationSlots = listOf(
    "08:00-10:00", "10:00-12:00", "12:00-14:00", "14:00-16:00",
    "16:00-18:00", "18:00-20:00", "20:00-22:00"
)

@Composable
@OptIn(ExperimentalLayoutApi::class)
fun ReservationsScreen(navController: NavController) {
    var reservations by remember { mutableStateOf<List<Reservation>>(emptyList()) }
    var areas by remember { mutableStateOf<List<CommonArea>>(emptyList()) }
    var residents by remember { mutableStateOf<List<ResidentSummary>>(emptyList()) }
    var availability by remember { mutableStateOf<ReservationAvailabilityResponse?>(null) }
    var selectedArea by remember { mutableStateOf<CommonArea?>(null) }
    var selectedResident by remember { mutableStateOf<ResidentSummary?>(null) }
    var date by remember { mutableStateOf("") }
    var slot by remember { mutableStateOf("") }
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
                    if (selectedResident == null) selectedResident = residents.firstOrNull()
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
                    DatePickerField(
                        "Seleccionar fecha",
                        date,
                        { date = it; slot = "" },
                        allowPastDates = false
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
                                                if (Session.isAdmin) selectedResident?.id else null
                                            )
                                        )
                                        message = if (response.isSuccessful) {
                                            date = ""; slot = ""
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
                        Text("Estado: ${reservation.status}")
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
                        if (Session.isResident && reservation.status in listOf("activa", "pendiente")) {
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
        AlertDialog(
            onDismissRequest = { confirmation = null },
            title = { Text("Confirmar acción") },
            text = { Text(prompt) },
            confirmButton = {
                TextButton(onClick = { confirmation = null; action() }) { Text("Confirmar") }
            },
            dismissButton = { TextButton(onClick = { confirmation = null }) { Text("Cancelar") } }
        )
    }
}
