// AnnouncementsScreen.kt — pestaña de anuncios/avisos de la unidad. Los ven los 3
// roles; solo el Administrador puede publicar uno nuevo (mismo patrón de "lista +
// formulario abajo" que UsersScreen en GA3).

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
import com.dracknoval.domux.data.Announcement
import com.dracknoval.domux.data.CreateAnnouncementRequest
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.launch

@Composable
fun AnnouncementsScreen(navController: NavController) {
    // Los 4 estados de la pantalla, tal como pide la GA4: cargando / con datos / vacío / error.
    var cargando by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var anuncios by remember { mutableStateOf<List<Announcement>>(emptyList()) }

    var titulo by remember { mutableStateOf("") }
    var mensaje by remember { mutableStateOf("") }
    var publicando by remember { mutableStateOf(false) }
    var resultForm by remember { mutableStateOf("") }

    val scope = rememberCoroutineScope()

    suspend fun cargar() {
        cargando = true
        error = null
        try {
            val resp = RetrofitClient.api.getAnnouncements(Session.bearer())
            if (resp.isSuccessful) {
                anuncios = resp.body()?.announcements ?: emptyList()
            } else {
                error = mensajeDeError(resp.code(), resp.errorBody()?.string())
            }
        } catch (e: Exception) {
            error = "⚠️ Sin conexión con el servidor: ${e.message}"
        } finally {
            cargando = false
        }
    }

    // LaunchedEffect(Unit): se ejecuta UNA vez al entrar a la pantalla.
    LaunchedEffect(Unit) { cargar() }

    Column(modifier = Modifier.fillMaxSize().padding(24.dp)) {
        Text("Anuncios de la unidad", fontSize = 22.sp)
        Spacer(Modifier.height(12.dp))

        when {
            cargando -> {
                Box(modifier = Modifier.fillMaxWidth().padding(24.dp)) { CircularProgressIndicator() }
            }
            error != null -> {
                Text("❌ $error")
            }
            anuncios.isEmpty() -> {
                Text("Todavía no hay anuncios publicados.")
            }
            else -> {
                LazyColumn(modifier = Modifier.weight(1f)) {
                    items(anuncios) { a ->
                        Card(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                Text(a.title, fontSize = 17.sp)
                                Spacer(Modifier.height(4.dp))
                                Text(a.message)
                                Spacer(Modifier.height(4.dp))
                                Text(
                                    "Por ${a.authorName ?: "Administración"} · ${a.createdAt ?: ""}",
                                    fontSize = 12.sp
                                )
                            }
                        }
                    }
                }
            }
        }

        // Solo el Administrador puede publicar anuncios nuevos.
        if (Session.isAdmin) {
            HorizontalDivider(Modifier.padding(vertical = 12.dp))
            Text("Publicar un nuevo anuncio", fontSize = 16.sp)
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = titulo, onValueChange = { titulo = it },
                label = { Text("Título") }, singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = mensaje, onValueChange = { mensaje = it },
                label = { Text("Mensaje") },
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(8.dp))
            Button(
                onClick = {
                    if (titulo.isBlank() || mensaje.isBlank()) {
                        resultForm = "Completa título y mensaje"
                        return@Button
                    }
                    publicando = true
                    resultForm = ""
                    scope.launch {
                        try {
                            val resp = RetrofitClient.api.createAnnouncement(
                                Session.bearer(), CreateAnnouncementRequest(titulo, mensaje)
                            )
                            if (resp.isSuccessful) {
                                titulo = ""; mensaje = ""
                                resultForm = "✅ Anuncio publicado"
                                cargar()
                            } else {
                                resultForm = "❌ ${mensajeDeError(resp.code(), resp.errorBody()?.string())}"
                            }
                        } catch (e: Exception) {
                            resultForm = "⚠️ ${e.message}"
                        } finally {
                            publicando = false
                        }
                    }
                },
                enabled = !publicando,
                modifier = Modifier.fillMaxWidth()
            ) { Text(if (publicando) "Publicando..." else "Publicar") }
            if (resultForm.isNotEmpty()) { Spacer(Modifier.height(8.dp)); Text(resultForm) }
        }

        Spacer(Modifier.height(12.dp))
        TextButton(onClick = { navController.popBackStack() }) { Text("Volver") }
    }
}
