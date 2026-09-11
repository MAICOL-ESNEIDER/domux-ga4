// RegistryScreen.kt — "Portería": paquetes y visitantes/domiciliarios, todo en una
// sola pantalla para no duplicar código entre los 3 roles.
// Guardia: registra paquetes y visitas, y marca paquetes como entregados.
// Residente: ve el historial de sus propios paquetes y visitas (sus "notificaciones").
// Administrador: ve todo lo que los guardias han registrado (solo lectura).

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
import com.dracknoval.domux.data.PackageItem
import com.dracknoval.domux.data.RegisterPackageRequest
import com.dracknoval.domux.data.RegisterVisitRequest
import com.dracknoval.domux.data.ResidentSummary
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.Visit
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.launch

@Composable
fun RegistryScreen(navController: NavController) {
    var cargando by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var paquetes by remember { mutableStateOf<List<PackageItem>>(emptyList()) }
    var visitas by remember { mutableStateOf<List<Visit>>(emptyList()) }
    var residentes by remember { mutableStateOf<List<ResidentSummary>>(emptyList()) }
    val scope = rememberCoroutineScope()

    // Formulario de paquete (solo Guardia).
    var residenteParaPaquete by remember { mutableStateOf<ResidentSummary?>(null) }
    var descripcionPaquete by remember { mutableStateOf("") }
    var enviandoPaquete by remember { mutableStateOf(false) }
    var resultPaquete by remember { mutableStateOf("") }

    // Formulario de visita (solo Guardia).
    var residenteParaVisita by remember { mutableStateOf<ResidentSummary?>(null) }
    var nombreVisitante by remember { mutableStateOf("") }
    var tipoVisita by remember { mutableStateOf("visitante") }
    var enviandoVisita by remember { mutableStateOf(false) }
    var resultVisita by remember { mutableStateOf("") }

    suspend fun cargar() {
        cargando = true
        error = null
        try {
            val respPaquetes = RetrofitClient.api.getPackages(Session.bearer())
            if (respPaquetes.isSuccessful) paquetes = respPaquetes.body()?.packages ?: emptyList()
            else error = mensajeDeError(respPaquetes.code(), respPaquetes.errorBody()?.string())

            val respVisitas = RetrofitClient.api.getVisits(Session.bearer())
            if (respVisitas.isSuccessful) visitas = respVisitas.body()?.visits ?: emptyList()

            if (Session.isGuard) {
                val respResidentes = RetrofitClient.api.getResidents(Session.bearer())
                if (respResidentes.isSuccessful) {
                    residentes = respResidentes.body()?.residents ?: emptyList()
                    if (residenteParaPaquete == null) residenteParaPaquete = residentes.firstOrNull()
                    if (residenteParaVisita == null) residenteParaVisita = residentes.firstOrNull()
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
        Text(
            when {
                Session.isGuard -> "Registrar paquete / visitante"
                Session.isResident -> "Mis notificaciones"
                else -> "Registros de portería"
            },
            fontSize = 22.sp
        )
        Spacer(Modifier.height(12.dp))

        if (cargando) {
            Box(Modifier.fillMaxWidth().padding(24.dp)) { CircularProgressIndicator() }
        } else if (error != null) {
            Text("❌ $error")
        } else {
            LazyColumn(modifier = Modifier.weight(1f)) {
                item {
                    Text("Paquetes", fontSize = 16.sp)
                    Spacer(Modifier.height(6.dp))
                }
                if (paquetes.isEmpty()) {
                    item { Text("Sin paquetes registrados.") }
                }
                items(paquetes) { p ->
                    Card(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                        Column(modifier = Modifier.padding(10.dp)) {
                            if (!Session.isResident) {
                                Text("Para: ${p.residentName ?: ""}", fontSize = 12.sp)
                            }
                            Text(p.description?.ifBlank { "Paquete sin descripción" } ?: "Paquete")
                            Text("Estado: ${p.status}", fontSize = 12.sp)
                            if (Session.isGuard && p.status == "pendiente") {
                                TextButton(onClick = {
                                    scope.launch {
                                        try {
                                            RetrofitClient.api.deliverPackage(Session.bearer(), p.id)
                                            cargar()
                                        } catch (_: Exception) { }
                                    }
                                }) { Text("Marcar entregado") }
                            }
                        }
                    }
                }

                item {
                    Spacer(Modifier.height(12.dp))
                    Text("Visitantes / domiciliarios", fontSize = 16.sp)
                    Spacer(Modifier.height(6.dp))
                }
                if (visitas.isEmpty()) {
                    item { Text("Sin visitas registradas.") }
                }
                items(visitas) { v ->
                    Card(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                        Column(modifier = Modifier.padding(10.dp)) {
                            if (!Session.isResident) {
                                Text("Para: ${v.residentName ?: ""}", fontSize = 12.sp)
                            }
                            Text("${v.visitorName} (${v.type})")
                            Text(v.createdAt ?: "", fontSize = 12.sp)
                        }
                    }
                }
            }
        }

        // Solo el Guardia registra paquetes y visitas.
        if (Session.isGuard) {
            HorizontalDivider(Modifier.padding(vertical = 12.dp))
            Text("Registrar paquete", fontSize = 16.sp)
            Spacer(Modifier.height(6.dp))
            Row {
                residentes.take(4).forEach { r ->
                    FilterChip(
                        selected = residenteParaPaquete?.id == r.id,
                        onClick = { residenteParaPaquete = r },
                        label = { Text(r.name) },
                        modifier = Modifier.padding(end = 6.dp)
                    )
                }
            }
            Spacer(Modifier.height(6.dp))
            OutlinedTextField(
                value = descripcionPaquete, onValueChange = { descripcionPaquete = it },
                label = { Text("Descripción (opcional)") }, singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(6.dp))
            Button(
                onClick = {
                    val r = residenteParaPaquete
                    if (r == null) { resultPaquete = "Elige un residente"; return@Button }
                    enviandoPaquete = true
                    resultPaquete = ""
                    scope.launch {
                        try {
                            val resp = RetrofitClient.api.registerPackage(
                                Session.bearer(),
                                RegisterPackageRequest(r.id, descripcionPaquete.ifBlank { null })
                            )
                            resultPaquete = if (resp.isSuccessful) {
                                descripcionPaquete = ""
                                cargar()
                                "✅ Paquete registrado, se notificó a ${r.name}"
                            } else {
                                "❌ ${mensajeDeError(resp.code(), resp.errorBody()?.string())}"
                            }
                        } catch (e: Exception) {
                            resultPaquete = "⚠️ ${e.message}"
                        } finally {
                            enviandoPaquete = false
                        }
                    }
                },
                enabled = !enviandoPaquete,
                modifier = Modifier.fillMaxWidth()
            ) { Text(if (enviandoPaquete) "Registrando..." else "Registrar paquete") }
            if (resultPaquete.isNotEmpty()) { Spacer(Modifier.height(6.dp)); Text(resultPaquete) }

            Spacer(Modifier.height(16.dp))
            Text("Registrar visitante / domiciliario", fontSize = 16.sp)
            Spacer(Modifier.height(6.dp))
            Row {
                residentes.take(4).forEach { r ->
                    FilterChip(
                        selected = residenteParaVisita?.id == r.id,
                        onClick = { residenteParaVisita = r },
                        label = { Text(r.name) },
                        modifier = Modifier.padding(end = 6.dp)
                    )
                }
            }
            Spacer(Modifier.height(6.dp))
            OutlinedTextField(
                value = nombreVisitante, onValueChange = { nombreVisitante = it },
                label = { Text("Nombre del visitante") }, singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(6.dp))
            Row {
                listOf("visitante", "domiciliario").forEach { opcion ->
                    FilterChip(
                        selected = tipoVisita == opcion,
                        onClick = { tipoVisita = opcion },
                        label = { Text(opcion) },
                        modifier = Modifier.padding(end = 6.dp)
                    )
                }
            }
            Spacer(Modifier.height(6.dp))
            Button(
                onClick = {
                    val r = residenteParaVisita
                    if (r == null || nombreVisitante.isBlank()) {
                        resultVisita = "Elige un residente y escribe el nombre del visitante"
                        return@Button
                    }
                    enviandoVisita = true
                    resultVisita = ""
                    scope.launch {
                        try {
                            val resp = RetrofitClient.api.registerVisit(
                                Session.bearer(),
                                RegisterVisitRequest(r.id, nombreVisitante, tipoVisita)
                            )
                            resultVisita = if (resp.isSuccessful) {
                                nombreVisitante = ""
                                cargar()
                                "✅ Ingreso registrado, se notificó a ${r.name}"
                            } else {
                                "❌ ${mensajeDeError(resp.code(), resp.errorBody()?.string())}"
                            }
                        } catch (e: Exception) {
                            resultVisita = "⚠️ ${e.message}"
                        } finally {
                            enviandoVisita = false
                        }
                    }
                },
                enabled = !enviandoVisita,
                modifier = Modifier.fillMaxWidth()
            ) { Text(if (enviandoVisita) "Registrando..." else "Registrar ingreso") }
            if (resultVisita.isNotEmpty()) { Spacer(Modifier.height(6.dp)); Text(resultVisita) }
        }

        Spacer(Modifier.height(12.dp))
        TextButton(onClick = { navController.popBackStack() }) { Text("Volver") }
    }
}
