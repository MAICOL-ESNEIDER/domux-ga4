// PqrsScreen.kt — Peticiones, Quejas, Reclamos y Sugerencias.
// Si el usuario es Residente: puede crear una PQRS y ve solo las suyas.
// Si el usuario es Administrador: ve TODAS las PQRS y puede responderlas.
// El backend decide qué devolver según el rol del token (no lo decide la app).

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
import com.dracknoval.domux.data.CreatePqrsRequest
import com.dracknoval.domux.data.Pqrs
import com.dracknoval.domux.data.RespondPqrsRequest
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.launch

@Composable
fun PqrsScreen(navController: NavController) {
    var cargando by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var lista by remember { mutableStateOf<List<Pqrs>>(emptyList()) }
    val scope = rememberCoroutineScope()

    // Formulario para crear (solo Residente).
    var asunto by remember { mutableStateOf("") }
    var mensaje by remember { mutableStateOf("") }
    var enviando by remember { mutableStateOf(false) }
    var resultForm by remember { mutableStateOf("") }

    suspend fun cargar() {
        cargando = true
        error = null
        try {
            val resp = RetrofitClient.api.getPqrs(Session.bearer())
            if (resp.isSuccessful) {
                lista = resp.body()?.pqrs ?: emptyList()
            } else {
                error = mensajeDeError(resp.code(), resp.errorBody()?.string())
            }
        } catch (e: Exception) {
            error = "⚠️ Sin conexión con el servidor: ${e.message}"
        } finally {
            cargando = false
        }
    }

    LaunchedEffect(Unit) { cargar() }

    Column(modifier = Modifier.fillMaxSize().padding(24.dp)) {
        Text(if (Session.isAdmin) "PQRS de los residentes" else "Mis PQRS", fontSize = 22.sp)
        Spacer(Modifier.height(12.dp))

        when {
            cargando -> Box(Modifier.fillMaxWidth().padding(24.dp)) { CircularProgressIndicator() }
            error != null -> Text("❌ $error")
            lista.isEmpty() -> Text("No hay PQRS registradas todavía.")
            else -> {
                LazyColumn(modifier = Modifier.weight(1f)) {
                    items(lista) { p ->
                        // Cada PQRS es un mini-formulario si eres admin (para responder),
                        // o solo lectura si eres residente.
                        var status by remember(p.id) { mutableStateOf(p.status) }
                        var respuesta by remember(p.id) { mutableStateOf(p.adminResponse ?: "") }
                        var respondiendo by remember(p.id) { mutableStateOf(false) }

                        Card(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                if (Session.isAdmin) {
                                    Text("De: ${p.residentName ?: "residente"}", fontSize = 12.sp)
                                }
                                Text(p.subject, fontSize = 17.sp)
                                Spacer(Modifier.height(4.dp))
                                Text(p.message)
                                Spacer(Modifier.height(4.dp))
                                Text("Estado: ${p.status}", fontSize = 12.sp)
                                if (!p.adminResponse.isNullOrBlank()) {
                                    Spacer(Modifier.height(4.dp))
                                    Text("Respuesta: ${p.adminResponse}", fontSize = 13.sp)
                                }

                                // Solo el admin puede cambiar estado / responder.
                                if (Session.isAdmin) {
                                    Spacer(Modifier.height(8.dp))
                                    OutlinedTextField(
                                        value = respuesta, onValueChange = { respuesta = it },
                                        label = { Text("Respuesta") },
                                        modifier = Modifier.fillMaxWidth()
                                    )
                                    Spacer(Modifier.height(6.dp))
                                    Row {
                                        listOf("en_proceso", "resuelta").forEach { opcion ->
                                            FilterChip(
                                                selected = status == opcion,
                                                onClick = { status = opcion },
                                                label = { Text(opcion) },
                                                modifier = Modifier.padding(end = 6.dp)
                                            )
                                        }
                                    }
                                    Spacer(Modifier.height(6.dp))
                                    Button(
                                        onClick = {
                                            respondiendo = true
                                            scope.launch {
                                                try {
                                                    val resp = RetrofitClient.api.respondPqrs(
                                                        Session.bearer(), p.id,
                                                        RespondPqrsRequest(status, respuesta)
                                                    )
                                                    if (resp.isSuccessful) cargar()
                                                } catch (_: Exception) {
                                                } finally {
                                                    respondiendo = false
                                                }
                                            }
                                        },
                                        enabled = !respondiendo,
                                        modifier = Modifier.fillMaxWidth()
                                    ) { Text(if (respondiendo) "Guardando..." else "Guardar respuesta") }
                                }
                            }
                        }
                    }
                }
            }
        }

        // Solo el Residente puede crear una PQRS nueva.
        if (Session.isResident) {
            HorizontalDivider(Modifier.padding(vertical = 12.dp))
            Text("Nueva PQRS", fontSize = 16.sp)
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = asunto, onValueChange = { asunto = it },
                label = { Text("Asunto") }, singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = mensaje, onValueChange = { mensaje = it },
                label = { Text("Describe tu petición, queja, reclamo o sugerencia") },
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(8.dp))
            Button(
                onClick = {
                    if (asunto.isBlank() || mensaje.isBlank()) {
                        resultForm = "Completa el asunto y el mensaje"
                        return@Button
                    }
                    enviando = true
                    resultForm = ""
                    scope.launch {
                        try {
                            val resp = RetrofitClient.api.createPqrs(
                                Session.bearer(), CreatePqrsRequest(asunto, mensaje)
                            )
                            if (resp.isSuccessful) {
                                asunto = ""; mensaje = ""
                                resultForm = "✅ PQRS enviada"
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
            ) { Text(if (enviando) "Enviando..." else "Enviar PQRS") }
            if (resultForm.isNotEmpty()) { Spacer(Modifier.height(8.dp)); Text(resultForm) }
        }

        Spacer(Modifier.height(12.dp))
        TextButton(onClick = { navController.popBackStack() }) { Text("Volver") }
    }
}
