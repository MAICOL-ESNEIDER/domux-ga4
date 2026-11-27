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
import android.graphics.ImageDecoder
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
import androidx.compose.runtime.saveable.rememberSaveable
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
                false
            ).show()
        },
        modifier = Modifier.fillMaxWidth()
    ) {
        val displayValue = if (value.isNotBlank()) formatTimeAmPm(value) else value
        Text(if (value.isBlank()) label else "$label: $displayValue")
    }
}

fun formatTimeAmPm(time24: String): String {
    return try {
        val format24 = SimpleDateFormat("HH:mm", Locale.getDefault())
        val format12 = SimpleDateFormat("hh:mm a", Locale.getDefault())
        val date = format24.parse(time24)
        date?.let { format12.format(it) } ?: time24
    } catch (e: Exception) {
        time24
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
    var showDialog by rememberSaveable { mutableStateOf(false) }
    var currentCameraUriString by rememberSaveable { mutableStateOf<String?>(null) }
    var currentCameraUri = currentCameraUriString?.let { Uri.parse(it) }
    
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
                    val mimeType = context.contentResolver.getType(uri).orEmpty().lowercase()
                    val fileName = withContext(Dispatchers.IO) {
                        context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
                            val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                            if (cursor.moveToFirst() && nameIndex >= 0) cursor.getString(nameIndex) else null
                        } ?: uri.lastPathSegment ?: "Archivo adjunto"
                    }
                    val isImage = mimeType.startsWith("image/") || 
                                  fileName.endsWith(".jpg", true) || 
                                  fileName.endsWith(".jpeg", true) || 
                                  fileName.endsWith(".png", true) || 
                                  fileName.endsWith(".webp", true) || 
                                  fileName.endsWith(".heic", true)
                                  
                    if (isImage) {
                        val encoded = withContext(Dispatchers.IO) { processImageUriToCompressedBase64(context, uri) }
                        if (encoded != null) {
                            val finalMime = if (mimeType.isNotBlank()) mimeType else "image/jpeg"
                            onAttachment("data:$finalMime;base64,$encoded", "image", fileName)
                        } else {
                            onError("No se pudo procesar la imagen.")
                        }
                    } else {
                        val type = when {
                            mimeType.startsWith("video/") -> "video"
                            mimeType.startsWith("audio/") -> "audio"
                            else -> "document"
                        }
                        val encoded = withContext(Dispatchers.IO) { readAsBase64(context, uri) }
                        val dataUrl = "data:$mimeType;base64,$encoded"
                        onAttachment(dataUrl, type, fileName)
                    }
                } catch (exception: Throwable) {
                    onError("No se pudo leer el archivo: ${exception.message}")
                }
            }
        }
    }
    
    val cameraLauncher = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { success ->
        if (success && currentCameraUri != null) {
            scope.launch {
                try {
                    val uri = currentCameraUri!!
                    val fileExistsAndValid = withContext(Dispatchers.IO) {
                        context.contentResolver.openFileDescriptor(uri, "r")?.use {
                            it.statSize > 0
                        } ?: false
                    }
                    if (!fileExistsAndValid) {
                        onError("La foto capturada está vacía o no existe.")
                        return@launch
                    }
                    val encoded = withContext(Dispatchers.IO) { processImageUriToCompressedBase64(context, uri) }
                    if (encoded != null) {
                        onAttachment("data:image/jpeg;base64,$encoded", "image", "foto_camara.jpg")
                    } else {
                        onError("No se pudo procesar la foto.")
                    }
                } catch (exception: Throwable) {
                    onError("Error al procesar la captura: ${exception.message}")
                }
            }
        }
    }
    
    val cameraPermissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) {
            val file = File(context.cacheDir, "camera_capture_${System.currentTimeMillis()}.jpg")
            val uri = androidx.core.content.FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
            currentCameraUriString = uri.toString()
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
                            currentCameraUriString = uri.toString()
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
    try {
        var width = 0
        var height = 0
        val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        context.contentResolver.openInputStream(uri)?.use { inputStream ->
            BitmapFactory.decodeStream(inputStream, null, options)
            width = options.outWidth
            height = options.outHeight
        }
        
        var bitmap: Bitmap? = null
        if (width <= 0 || height <= 0) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                val source = ImageDecoder.createSource(context.contentResolver, uri)
                bitmap = ImageDecoder.decodeBitmap(source) { decoder, info, _ ->
                    decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
                    decoder.isMutableRequired = true
                    var scale = 1
                    while (info.size.width / scale > 1280 || info.size.height / scale > 1280) {
                        scale *= 2
                    }
                    decoder.setTargetSize(info.size.width / scale, info.size.height / scale)
                }
            } else {
                throw Exception("Formato de imagen no soportado o archivo corrupto.")
            }
        } else {
            var scale = 1
            while (width / scale > 1280 || height / scale > 1280) {
                scale *= 2
            }
            
            val decodeOptions = BitmapFactory.Options().apply { 
                inSampleSize = scale 
                inPreferredConfig = Bitmap.Config.RGB_565
            }
            
            bitmap = context.contentResolver.openInputStream(uri)?.use { inputStream ->
                BitmapFactory.decodeStream(inputStream, null, decodeOptions)
            } ?: throw Exception("No se pudo decodificar la imagen.")
        }
        
        var finalBitmap = bitmap ?: return null
        
        try {
            context.contentResolver.openInputStream(uri)?.use { exifStream ->
                val exif = ExifInterface(exifStream)
                val orientation = exif.getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
                val matrix = Matrix()
                when (orientation) {
                    ExifInterface.ORIENTATION_ROTATE_90 -> matrix.postRotate(90f)
                    ExifInterface.ORIENTATION_ROTATE_180 -> matrix.postRotate(180f)
                    ExifInterface.ORIENTATION_ROTATE_270 -> matrix.postRotate(270f)
                }
                if (!matrix.isIdentity) {
                    val rotated = Bitmap.createBitmap(finalBitmap, 0, 0, finalBitmap.width, finalBitmap.height, matrix, true)
                    if (rotated !== finalBitmap) {
                        finalBitmap.recycle()
                        finalBitmap = rotated
                    }
                }
            }
        } catch (e: Exception) {
            // Ignorar errores EXIF y continuar
        }
        
        val outputStream = ByteArrayOutputStream()
        try {
            finalBitmap.compress(Bitmap.CompressFormat.JPEG, 75, outputStream)
            if (outputStream.size() > 1_500_000) {
                outputStream.reset()
                finalBitmap.compress(Bitmap.CompressFormat.JPEG, 60, outputStream)
            }
            return Base64.encodeToString(outputStream.toByteArray(), Base64.NO_WRAP)
        } finally {
            finalBitmap.recycle()
        }
    } catch (e: OutOfMemoryError) {
        throw Exception("La imagen es demasiado grande para procesarla.")
    } catch (e: Throwable) {
        throw Exception("No se pudo leer la imagen: ${e.message}")
    }
}

fun saveBase64FileToDownloads(
    context: android.content.Context,
    fileName: String,
    base64Data: String,
    mimeType: String = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
): String {
    val safeFileName = fileName.replace("Reporte_Legal", "Respaldo_Historico", ignoreCase = true).substringAfterLast('/').substringAfterLast('\\').trim()
    require(safeFileName.isNotEmpty()) { "El nombre del archivo no es válido." }
    val fileBytes = Base64.decode(base64Data, Base64.DEFAULT)
    var finalUri: Uri? = null
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
            finalUri = uri
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
        val file = File(downloads, safeFileName)
        FileOutputStream(file).use { it.write(fileBytes) }
        finalUri = androidx.core.content.FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
    }
    showDownloadCompletedNotification(context, safeFileName, finalUri, mimeType)
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
