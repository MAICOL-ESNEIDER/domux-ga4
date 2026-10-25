package com.dracknoval.domux

import android.app.DatePickerDialog
import android.app.TimePickerDialog
import android.net.Uri
import android.util.Base64
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import androidx.compose.foundation.BorderStroke
import androidx.compose.ui.unit.dp
import java.io.ByteArrayOutputStream
import java.util.Calendar

@Composable
fun DatePickerField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    allowPastDates: Boolean = true
) {
    val context = LocalContext.current
    OutlinedButton(
        onClick = {
            val calendar = Calendar.getInstance()
            DatePickerDialog(
                context,
                { _, year, month, day ->
                    onValueChange("%04d-%02d-%02d".format(year, month + 1, day))
                },
                calendar.get(Calendar.YEAR),
                calendar.get(Calendar.MONTH),
                calendar.get(Calendar.DAY_OF_MONTH)
            ).apply {
                if (!allowPastDates) datePicker.minDate = System.currentTimeMillis()
            }.show()
        },
        modifier = Modifier.fillMaxWidth()
    ) {
        Text(if (value.isBlank()) label else "$label: $value")
    }
}

@Composable
fun TimePickerField(label: String, value: String, onValueChange: (String) -> Unit) {
    val context = LocalContext.current
    OutlinedButton(
        onClick = {
            val calendar = Calendar.getInstance()
            TimePickerDialog(
                context,
                { _, hour, minute -> onValueChange("%02d:%02d".format(hour, minute)) },
                calendar.get(Calendar.HOUR_OF_DAY),
                calendar.get(Calendar.MINUTE),
                true
            ).show()
        },
        modifier = Modifier.fillMaxWidth()
    ) {
        Text(if (value.isBlank()) label else "$label: $value")
    }
}

@Composable
fun MediaAttachmentPicker(
    attachmentName: String?,
    onAttachment: (mediaUrl: String, mediaType: String, fileName: String) -> Unit,
    onError: (String) -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
        if (uri != null) {
            scope.launch {
                try {
                    val mimeType = context.contentResolver.getType(uri).orEmpty()
                    val type = when {
                        mimeType.startsWith("image/") -> "image"
                        mimeType.startsWith("video/") -> "video"
                        mimeType.startsWith("audio/") -> "audio"
                        else -> null
                    }
                    if (type == null) {
                        onError("Selecciona una imagen, video o audio.")
                    } else {
                        val encoded = withContext(Dispatchers.IO) { readAsBase64(context, uri) }
                        val dataUrl = "data:$mimeType;base64,$encoded"
                        onAttachment(dataUrl, type, uri.lastPathSegment ?: "Adjunto")
                    }
                } catch (exception: Exception) {
                    onError("No se pudo leer el adjunto: ${exception.message}")
                }
            }
        }
    }
    Column {
        Button(onClick = { launcher.launch("*/*") }) {
            Text(if (attachmentName == null) "Adjuntar imagen, video o audio" else "Cambiar adjunto")
        }
        if (attachmentName != null) {
            Text("Adjunto: $attachmentName", color = MaterialTheme.colorScheme.secondary)
        }
    }
}

@Composable
fun DomuxCard(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, Color(0xFF1E293B)),
        content = content
    )
}

private fun readAsBase64(context: android.content.Context, uri: Uri): String {
    val input = context.contentResolver.openInputStream(uri)
        ?: error("El archivo seleccionado no está disponible")
    input.use { stream ->
        val output = ByteArrayOutputStream()
        val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
        var total = 0
        while (true) {
            val count = stream.read(buffer)
            if (count < 0) break
            total += count
            require(total <= MAX_ATTACHMENT_BYTES) { "El adjunto debe pesar máximo 5 MB" }
            output.write(buffer, 0, count)
        }
        return Base64.encodeToString(output.toByteArray(), Base64.NO_WRAP)
    }
}

private const val MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
