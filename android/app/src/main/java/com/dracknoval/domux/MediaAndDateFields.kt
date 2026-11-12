package com.dracknoval.domux

import android.app.DatePickerDialog
import android.app.TimePickerDialog
import android.net.Uri
import android.content.ContentValues
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.provider.OpenableColumns
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
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import androidx.compose.foundation.BorderStroke
import androidx.compose.ui.unit.dp
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import java.util.Calendar
import com.dracknoval.domux.ui.theme.DomuxColor

/**
 * Botón que abre el calendario del celular y devuelve la fecha como AAAA-MM-DD, para que nadie
 * tenga que escribirla a mano. [allowFutureDates] en false sirve para fechas que ya pasaron,
 * como un nacimiento o la última vacuna.
 */
@Composable
fun DatePickerField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    allowPastDates: Boolean = true,
    allowFutureDates: Boolean = true
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
                if (!allowFutureDates) datePicker.maxDate = System.currentTimeMillis()
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

fun saveBase64FileToDownloads(
    context: android.content.Context,
    fileName: String,
    base64Data: String,
    mimeType: String = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
): String {
    val safeFileName = fileName.substringAfterLast('/').substringAfterLast('\\').trim()
    require(safeFileName.isNotEmpty()) { "El nombre del archivo no es válido." }
    val fileBytes = Base64.decode(base64Data, Base64.DEFAULT)
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, safeFileName)
            put(MediaStore.Downloads.MIME_TYPE, mimeType)
            put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
        }
        val uri = context.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            ?: error("No se pudo crear el archivo en Descargas.")
        try {
            val output = context.contentResolver.openOutputStream(uri)
                ?: error("No se pudo abrir el archivo en Descargas.")
            output.use { it.write(fileBytes) }
        } catch (exception: Exception) {
            context.contentResolver.delete(uri, null, null)
            throw exception
        }
    } else {
        @Suppress("DEPRECATION")
        val downloads = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
        check(downloads.exists() || downloads.mkdirs()) {
            "No se pudo acceder a la carpeta Descargas."
        }
        FileOutputStream(File(downloads, safeFileName)).use { it.write(fileBytes) }
    }
    return "Descargas/$safeFileName"
}

@Composable
fun ExcelFilePickerButton(
    label: String = "Seleccionar archivo Excel (.xlsx o .csv)",
    onFileSelected: (base64: String, fileName: String) -> Unit,
    onError: (String) -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
        if (uri != null) {
            scope.launch {
                try {
                    val fileName = withContext(Dispatchers.IO) {
                        context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
                            val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                            if (cursor.moveToFirst() && nameIndex >= 0) cursor.getString(nameIndex)
                            else null
                        } ?: uri.lastPathSegment?.substringAfterLast('/')
                    } ?: throw IllegalArgumentException("No se pudo identificar el archivo seleccionado.")
                    if (!fileName.endsWith(".xlsx", ignoreCase = true) &&
                        !fileName.endsWith(".csv", ignoreCase = true)
                    ) {
                        onError("Selecciona un archivo con extensión .xlsx o .csv.")
                    } else {
                        val encoded = withContext(Dispatchers.IO) {
                            val input = context.contentResolver.openInputStream(uri)
                                ?: error("El archivo seleccionado no está disponible.")
                            input.use { stream ->
                                Base64.encodeToString(stream.readBytes(), Base64.NO_WRAP)
                            }
                        }
                        onFileSelected(encoded, fileName)
                    }
                } catch (exception: CancellationException) {
                    throw exception
                } catch (exception: Exception) {
                    onError("No se pudo leer el archivo: ${exception.message}")
                }
            }
        }
    }
    Button(onClick = { launcher.launch("*/*") }) {
        Text(label)
    }
}

@Composable
fun DomuxCard(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = DomuxColor.Card),
        border = BorderStroke(1.dp, DomuxColor.Line),
        content = content
    )
}
