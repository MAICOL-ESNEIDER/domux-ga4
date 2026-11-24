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
import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import androidx.core.content.ContextCompat
import androidx.exifinterface.media.ExifInterface
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import coil.compose.AsyncImage
import coil.request.ImageRequest
import androidx.compose.ui.layout.ContentScale
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
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
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

private fun pickerDateMillis(value: String): Long? =
    SimpleDateFormat("yyyy-MM-dd", Locale.US).apply {
        isLenient = false
    }.parse(value)?.time

@Composable
fun DatePickerField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    allowPastDates: Boolean = false,
    minDate: String? = null,
    maxDate: String? = null
) {
    val context = LocalContext.current
    OutlinedButton(
        onClick = {
            val selectedDate = value.takeIf(String::isNotBlank)?.let(::pickerDateMillis)
            val calendar = Calendar.getInstance().apply {
                selectedDate?.let { time = Date(it) }
            }
            DatePickerDialog(
                context,
                { _, year, month, day ->
                    onValueChange("%04d-%02d-%02d".format(year, month + 1, day))
                },
                calendar.get(Calendar.YEAR),
                calendar.get(Calendar.MONTH),
                calendar.get(Calendar.DAY_OF_MONTH)
            ).apply {
                minDate?.let(::pickerDateMillis)?.let { datePicker.minDate = it }
                if (!allowPastDates) {
                    val today = Calendar.getInstance().apply {
                        set(Calendar.HOUR_OF_DAY, 0)
                        set(Calendar.MINUTE, 0)
                        set(Calendar.SECOND, 0)
                        set(Calendar.MILLISECOND, 0)
                    }
                    datePicker.minDate = maxOf(datePicker.minDate, today.timeInMillis)
                }
                maxDate?.let(::pickerDateMillis)?.let { datePicker.maxDate = it }
            }.show()
        },
        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
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
    MediaAttachmentPickerFiltered(attachmentName, onAttachment, null, onError)
}

@Composable
fun MediaAttachmentPicker(
    attachmentName: String?,
    onAttachment: (mediaUrl: String, mediaType: String, fileName: String) -> Unit,
    mimeTypeFilter: String,
    onError: (String) -> Unit
) {
    MediaAttachmentPickerFiltered(attachmentName, onAttachment, mimeTypeFilter, onError)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MediaAttachmentPickerFiltered(
    attachmentName: String?,
    onAttachment: (mediaUrl: String, mediaType: String, fileName: String) -> Unit,
    mimeTypeFilter: String?,
    onError: (String) -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var showDialog by remember { mutableStateOf(false) }
    var currentCameraUri by remember { mutableStateOf<Uri?>(null) }
    
    val galleryLauncher = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri: Uri? ->
        if (uri != null) {
            scope.launch {
                try {
                    val encoded = withContext(Dispatchers.IO) { processImageUriToCompressedBase64(context, uri) }
                    if (encoded != null) {
                        onAttachment("data:image/jpeg;base64,$encoded", "image", "imagen_galeria.jpg")
                    } else {
                        onError("No se pudo procesar la imagen.")
                    }
                } catch (exception: Exception) {
                    onError("No se pudo leer la imagen: ${exception.message}")
                }
            }
        }
    }
    
    val fileLauncher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
        if (uri != null) {
            scope.launch {
                try {
                    val mimeType = context.contentResolver.getType(uri).orEmpty()
                    val type = when {
                        mimeType.startsWith("video/") -> "video"
                        mimeType.startsWith("audio/") -> "audio"
                        else -> "document"
                    }
                    val fileName = withContext(Dispatchers.IO) {
                        context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
                            val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                            if (cursor.moveToFirst() && nameIndex >= 0) cursor.getString(nameIndex) else null
                        } ?: uri.lastPathSegment ?: "Archivo adjunto"
                    }
                    val encoded = withContext(Dispatchers.IO) { readAsBase64(context, uri) }
                    val dataUrl = "data:$mimeType;base64,$encoded"
                    onAttachment(dataUrl, type, fileName)
                } catch (exception: Exception) {
                    onError("No se pudo leer el archivo: ${exception.message}")
                }
            }
        }
    }
    
    val cameraLauncher = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { success ->
        if (success && currentCameraUri != null) {
            scope.launch {
                try {
                    val encoded = withContext(Dispatchers.IO) { processImageUriToCompressedBase64(context, currentCameraUri!!) }
                    if (encoded != null) {
                        onAttachment("data:image/jpeg;base64,$encoded", "image", "foto_camara.jpg")
                    } else {
                        onError("No se pudo procesar la foto.")
                    }
                } catch (exception: Exception) {
                    onError("Error al procesar la captura: ${exception.message}")
                }
            }
        }
    }
    
    val cameraPermissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) {
            val file = File(context.cacheDir, "camera_capture_${System.currentTimeMillis()}.jpg")
            val uri = androidx.core.content.FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
            currentCameraUri = uri
            cameraLauncher.launch(uri)
        } else {
            onError("Se requiere permiso de cámara para tomar fotos.")
        }
    }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Button(
            onClick = { showDialog = true },
            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
        ) {
            Text(if (attachmentName == null) "Adjuntar foto, video o archivo" else "Cambiar adjunto")
        }
        
        if (attachmentName != null) {
            DomuxCard(Modifier.fillMaxWidth()) {
                Row(
                    modifier = Modifier.padding(12.dp).fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text("Adjunto: $attachmentName", modifier = Modifier.weight(1f))
                    TextButton(onClick = { onAttachment("", "", "") }) {
                        Text("Quitar", color = MaterialTheme.colorScheme.error)
                    }
                }
            }
        }
    }

    if (showDialog) {
        ModalBottomSheet(
            onDismissRequest = { showDialog = false },
            sheetState = rememberModalBottomSheetState()
        ) {
            Column(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Text("Seleccionar archivo", style = MaterialTheme.typography.titleMedium)
                
                Button(
                    onClick = {
                        showDialog = false
                        if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                            val file = File(context.cacheDir, "camera_capture_${System.currentTimeMillis()}.jpg")
                            val uri = androidx.core.content.FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
                            currentCameraUri = uri
                            cameraLauncher.launch(uri)
                        } else {
                            cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
                        }
                    },
                    modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)
                ) { Text("📷 Tomar foto (Cámara)") }
                
                Button(
                    onClick = {
                        showDialog = false
                        galleryLauncher.launch(androidx.activity.result.PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageAndVideo))
                    },
                    modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)
                ) { Text("🖼 Elegir de Galería") }
                
                Button(
                    onClick = {
                        showDialog = false
                        fileLauncher.launch(arrayOf(mimeTypeFilter ?: "*/*"))
                    },
                    modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)
                ) { Text("📄 Seleccionar archivo (PDF / Audio)") }
                
                Spacer(Modifier.height(16.dp))
            }
        }
    }
}

fun processImageUriToCompressedBase64(context: android.content.Context, uri: Uri): String? {
    val inputStream = context.contentResolver.openInputStream(uri) ?: return null
    val bytes = inputStream.readBytes()
    inputStream.close()
    
    val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
    
    var scale = 1
    while (options.outWidth / scale > 1280 || options.outHeight / scale > 1280) {
        scale *= 2
    }
    
    val decodeOptions = BitmapFactory.Options().apply { inSampleSize = scale }
    var bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, decodeOptions) ?: return null
    
    try {
        val exifStream = context.contentResolver.openInputStream(uri)
        if (exifStream != null) {
            val exif = ExifInterface(exifStream)
            val orientation = exif.getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
            val matrix = Matrix()
            when (orientation) {
                ExifInterface.ORIENTATION_ROTATE_90 -> matrix.postRotate(90f)
                ExifInterface.ORIENTATION_ROTATE_180 -> matrix.postRotate(180f)
                ExifInterface.ORIENTATION_ROTATE_270 -> matrix.postRotate(270f)
            }
            if (!matrix.isIdentity) {
                val rotated = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
                if (rotated != bitmap) {
                    bitmap.recycle()
                    bitmap = rotated
                }
            }
            exifStream.close()
        }
    } catch (e: Exception) {
        // Ignorar errores EXIF y continuar
    }
    
    val outputStream = ByteArrayOutputStream()
    bitmap.compress(Bitmap.CompressFormat.JPEG, 75, outputStream)
    bitmap.recycle()
    
    return Base64.encodeToString(outputStream.toByteArray(), Base64.NO_WRAP)
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
    Button(
        onClick = { launcher.launch("*/*") },
        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
    ) {
        Text(label)
    }
}

@Composable
fun DomuxCard(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = Color(0xFF0F1E33)),
        border = BorderStroke(1.dp, Color(0xFF1E334D)),
        content = content
    )
}

fun readAsBase64(context: android.content.Context, uri: Uri): String {
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
