package com.dracknoval.domux

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
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
                        MediaAttachmentChip(announcement.mediaUrl, announcement.mediaType)
                        Text(
                            "Por ${announcement.authorName ?: "Administración"} · ${announcement.createdAt.orEmpty()}",
                            style = MaterialTheme.typography.bodySmall
                        )
                        if (Session.isAdmin) {
                            DeleteAnnouncementButton(onClick = { confirmation = announcement })
                        }
                    }
                }
            }
        }
        TextButton(onClick = { navController.popBackStack() }) { Text("Volver") }
    }

    confirmation?.let { item ->
        DomuxConfirmDialog(
            title = "Eliminar anuncio",
            message = "¿Estás seguro de eliminar “${item.title}”?",
            confirmLabel = "Eliminar",
            danger = true,
            onConfirm = {
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
            },
            onDismiss = { confirmation = null }
        )
    }
}

@Composable
private fun DeleteAnnouncementButton(onClick: () -> Unit) {
    Surface(
        modifier = Modifier
            .semantics { contentDescription = "Eliminar anuncio" },
        onClick = onClick,
        color = Color(0xFF450A0A),
        contentColor = Color(0xFFF87171),
        shape = RoundedCornerShape(12.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFF7F1D1D))
    ) {
        Canvas(Modifier.padding(10.dp).size(20.dp)) {
            val strokeWidth = 1.8.dp.toPx()
            drawRoundRect(
                color = Color(0xFFF87171),
                topLeft = Offset(size.width * 0.25f, size.height * 0.3f),
                size = Size(size.width * 0.5f, size.height * 0.58f),
                cornerRadius = androidx.compose.ui.geometry.CornerRadius(2.dp.toPx()),
                style = Stroke(strokeWidth)
            )
            drawLine(
                color = Color(0xFFF87171),
                start = Offset(size.width * 0.17f, size.height * 0.22f),
                end = Offset(size.width * 0.83f, size.height * 0.22f),
                strokeWidth = strokeWidth
            )
            drawLine(
                color = Color(0xFFF87171),
                start = Offset(size.width * 0.38f, size.height * 0.12f),
                end = Offset(size.width * 0.62f, size.height * 0.12f),
                strokeWidth = strokeWidth
            )
            drawLine(
                color = Color(0xFFF87171),
                start = Offset(size.width * 0.43f, size.height * 0.43f),
                end = Offset(size.width * 0.43f, size.height * 0.72f),
                strokeWidth = strokeWidth
            )
            drawLine(
                color = Color(0xFFF87171),
                start = Offset(size.width * 0.57f, size.height * 0.43f),
                end = Offset(size.width * 0.57f, size.height * 0.72f),
                strokeWidth = strokeWidth
            )
        }
    }
}
