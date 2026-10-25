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
    var announcements by remember { mutableStateOf<List<Announcement>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var title by remember { mutableStateOf("") }
    var detail by remember { mutableStateOf("") }
    var eventDate by remember { mutableStateOf("") }
    var eventTime by remember { mutableStateOf("") }
    var mediaUrl by remember { mutableStateOf<String?>(null) }
    var mediaType by remember { mutableStateOf<String?>(null) }
    var mediaName by remember { mutableStateOf<String?>(null) }
    var message by remember { mutableStateOf("") }
    var confirmation by remember { mutableStateOf<Announcement?>(null) }
    var publishing by remember { mutableStateOf(false) }
    var attemptedSubmit by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    suspend fun load() {
        loading = true
        try {
            val response = RetrofitClient.api.getAnnouncements(Session.bearer())
            if (response.isSuccessful) announcements = response.body()?.announcements.orEmpty()
            else message = mensajeDeError(response.code(), response.errorBody()?.string())
        } catch (exception: Exception) {
            message = "No se pudieron cargar los anuncios: ${exception.message}"
        } finally {
            loading = false
        }
    }

    LaunchedEffect(Unit) { load() }

    Column(Modifier.fillMaxSize().padding(18.dp)) {
        Text("Anuncios de la unidad", fontSize = 23.sp, color = MaterialTheme.colorScheme.primary)
        if (message.isNotBlank()) Text(message, color = MaterialTheme.colorScheme.error)
        if (Session.isAdmin) {
            DomuxCard(Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
                Column(Modifier.padding(12.dp)) {
                    Text("Publicar anuncio", style = MaterialTheme.typography.titleMedium)
                    OutlinedTextField(
                        title, { title = it }, label = { Text("Título *") },
                        isError = attemptedSubmit && title.trim().isEmpty(),
                        supportingText = { if (attemptedSubmit && title.trim().isEmpty()) Text("El título es obligatorio") },
                        singleLine = true, modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        detail, { detail = it }, label = { Text("Mensaje *") },
                        isError = attemptedSubmit && detail.trim().isEmpty(),
                        supportingText = { if (attemptedSubmit && detail.trim().isEmpty()) Text("El mensaje es obligatorio") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    DatePickerField("Fecha del evento", eventDate, { eventDate = it })
                    TimePickerField("Hora del evento", eventTime, { eventTime = it })
                    MediaAttachmentPicker(mediaName, { url, type, name ->
                        mediaUrl = url; mediaType = type; mediaName = name
                    }, { message = it })
                    Button(
                        enabled = !publishing,
                        onClick = {
                            attemptedSubmit = true
                            if (title.trim().isEmpty() || detail.trim().isEmpty()) {
                                message = "El título y el mensaje son obligatorios."
                                return@Button
                            }
                            publishing = true
                            scope.launch {
                                try {
                                    val response = RetrofitClient.api.createAnnouncement(
                                        Session.bearer(),
                                        CreateAnnouncementRequest(
                                            title.trim(), detail.trim(),
                                            eventDate.ifBlank { null }, eventTime.ifBlank { null },
                                            mediaUrl, mediaType
                                        )
                                    )
                                    if (response.isSuccessful) {
                                        title = ""; detail = ""; eventDate = ""; eventTime = ""
                                        mediaUrl = null; mediaType = null; mediaName = null
                                        attemptedSubmit = false
                                        message = "Anuncio publicado."
                                        load()
                                    } else message = mensajeDeError(response.code(), response.errorBody()?.string())
                                } catch (exception: Exception) {
                                    message = "No se pudo publicar: ${exception.message}"
                                } finally {
                                    publishing = false
                                }
                            }
                        },
                        modifier = Modifier.fillMaxWidth()
                    ) { Text(if (publishing) "Publicando..." else "Publicar") }
                }
            }
        }
        if (loading) CircularProgressIndicator()
        else LazyColumn(Modifier.weight(1f)) {
            items(announcements, key = { it.id }) { announcement ->
                DomuxCard(Modifier.fillMaxWidth().padding(vertical = 5.dp)) {
                    Column(Modifier.padding(13.dp)) {
                        Text(announcement.title, style = MaterialTheme.typography.titleMedium)
                        Text(announcement.message)
                        if (announcement.eventDate != null || announcement.eventTime != null) {
                            Text("Evento: ${announcement.eventDate.orEmpty()} ${announcement.eventTime.orEmpty()}")
                        }
                        if (announcement.mediaUrl != null) {
                            Text("Adjunto: ${announcement.mediaType ?: "archivo"}", color = MaterialTheme.colorScheme.secondary)
                        }
                        Text(
                            "Por ${announcement.authorName ?: "Administración"} · ${announcement.createdAt.orEmpty()}",
                            style = MaterialTheme.typography.bodySmall
                        )
                        if (Session.isAdmin) {
                            TextButton(onClick = { confirmation = announcement }) { Text("Eliminar anuncio") }
                        }
                    }
                }
            }
        }
        TextButton(onClick = { navController.popBackStack() }) { Text("Volver") }
    }

    confirmation?.let { item ->
        AlertDialog(
            onDismissRequest = { confirmation = null },
            title = { Text("Eliminar anuncio") },
            text = { Text("¿Estás seguro de eliminar “${item.title}”?") },
            confirmButton = {
                TextButton(onClick = {
                    confirmation = null
                    scope.launch {
                        try {
                            val response = RetrofitClient.api.deleteAnnouncement(Session.bearer(), item.id)
                            message = if (response.isSuccessful) "Anuncio eliminado."
                            else mensajeDeError(response.code(), response.errorBody()?.string())
                            if (response.isSuccessful) load()
                        } catch (exception: Exception) {
                            message = "No se pudo eliminar el anuncio: ${exception.message}"
                        }
                    }
                }) { Text("Eliminar") }
            },
            dismissButton = { TextButton(onClick = { confirmation = null }) { Text("Cancelar") } }
        )
    }
}
