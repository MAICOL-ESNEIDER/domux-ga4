// ReservationsScreen.kt — reserva de zonas comunes (ej. salón social).
// Residente: elige zona común, fecha y horario, reserva y puede cancelar las suyas.
// Administrador: ve todas las reservas de la unidad (solo lectura).

package com.dracknoval.domux

import androidx.compose.foundation.layout.*
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
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.launch

@Composable
fun ReservationsScreen(navController: NavController) {
    var cargando by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var reservas by remember { mutableStateOf<List<Reservation>>(emptyList()) }
    var zonas by remember { mutableStateOf<List<CommonArea>>(emptyList()) }
    val scope = rememberCoroutineScope()

    var zonaSeleccionada by remember { mutableStateOf<CommonArea?>(null) }
    var fecha by remember { mutableStateOf("") }     // formato libre, ej. 2026-09-20
    var horario by remember { mutableStateOf("") }   // ej. 18:00-20:00
    var enviando by remember { mutableStateOf(false) }
    var resultForm by remember { mutableStateOf("") }

    suspend fun cargar() {
        cargando = true
        error = null
        try {
            val respReservas = RetrofitClient.api.getReservations(Session.bearer())
            if (respReservas.isSuccessful) {
                reservas = respReservas.body()?.reservations ?: emptyList()
            } else {
                error = mensajeDeError(respReservas.code(), respReservas.errorBody()?.string())
            }
            if (Session.isResident) {
                val respZonas = RetrofitClient.api.getCommonAreas(Session.bearer())
                if (respZonas.isSuccessful) {
                    zonas = respZonas.body()?.areas ?: emptyList()
                    if (zonaSeleccionada == null) zonaSeleccionada = zonas.firstOrNull()
                }
            }
        } catch (e: Exception) {
            error = "⚠️ Sin conexión con el servidor: ${e.message}"
        } finally {
            cargando = false
        }
    }

    LaunchedEffect(Unit) { cargar() }

    Column(modifier = Modifier.fillMaxSize().padding(24.dp)) {
        Text(if (Session.isAdmin) "Reservas de la unidad" else "Reservar zona común", fontSize = 22.sp)
        Spacer(Modifier.height(12.dp))

        when {
            cargando -> Box(Modifier.fillMaxWidth().padding(24.dp)) { CircularProgressIndicator() }
            error != null -> Text("❌ $error")
            reservas.isEmpty() -> Text("No hay reservas registradas todavía.")
            else -> {
                LazyColumn(modifier = Modifier.weight(1f)) {
                    items(reservas) { r ->
                        Card(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                if (Session.isAdmin) {
                                    Text("Residente: ${r.residentName ?: ""}", fontSize = 12.sp)
                                }
                                Text("${r.commonAreaName ?: "Zona común"} — ${r.date} · ${r.timeSlot}")
                                Text("Estado: ${r.status}", fontSize = 12.sp)
                                // El residente puede cancelar sus propias reservas activas.
                                if (Session.isResident && r.status == "activa") {
                                    Spacer(Modifier.height(6.dp))
                                    TextButton(onClick = {
                                        scope.launch {
                                            try {
                                                RetrofitClient.api.cancelReservation(Session.bearer(), r.id)
                                                cargar()
                                            } catch (_: Exception) { }
                                        }
                                    }) { Text("Cancelar") }
                                }
                            }
                        }
                    }
                }
            }
        }

        // Solo el Residente puede crear reservas nuevas.
        if (Session.isResident) {
            HorizontalDivider(Modifier.padding(vertical = 12.dp))
            Text("Nueva reserva", fontSize = 16.sp)
            Spacer(Modifier.height(8.dp))
            Row {
                zonas.forEach { z ->
                    FilterChip(
                        selected = zonaSeleccionada?.id == z.id,
                        onClick = { zonaSeleccionada = z },
                        label = { Text(z.name) },
                        modifier = Modifier.padding(end = 6.dp)
                    )
                }
            }
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = fecha, onValueChange = { fecha = it },
                label = { Text("Fecha (AAAA-MM-DD)") }, singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = horario, onValueChange = { horario = it },
                label = { Text("Horario (ej. 18:00-20:00)") }, singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(8.dp))
            Button(
                onClick = {
                    val zona = zonaSeleccionada
                    if (zona == null || fecha.isBlank() || horario.isBlank()) {
                        resultForm = "Elige zona, fecha y horario"
                        return@Button
                    }
                    enviando = true
                    resultForm = ""
                    scope.launch {
                        try {
                            val resp = RetrofitClient.api.createReservation(
                                Session.bearer(),
                                CreateReservationRequest(zona.id, fecha, horario)
                            )
                            if (resp.isSuccessful) {
                                fecha = ""; horario = ""
                                resultForm = "✅ Reserva creada"
                                cargar()
                            } else {
                                resultForm = "❌ ${mensajeDeError(resp.code(), resp.errorBody()?.string())}"
                            }
                        } catch (e: Exception) {
                            resultForm = "⚠️ ${e.message}"
                        } finally {
                            enviando = false
                        }
                    }
                },
                enabled = !enviando,
                modifier = Modifier.fillMaxWidth()
            ) { Text(if (enviando) "Reservando..." else "Reservar") }
            if (resultForm.isNotEmpty()) { Spacer(Modifier.height(8.dp)); Text(resultForm) }
        }

        Spacer(Modifier.height(12.dp))
        TextButton(onClick = { navController.popBackStack() }) { Text("Volver") }
    }
}
