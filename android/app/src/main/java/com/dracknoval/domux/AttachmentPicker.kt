package com.dracknoval.domux

import android.Manifest
import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Matrix
import android.media.ExifInterface
import android.media.MediaRecorder
import android.net.Uri
import android.os.Build
import android.os.SystemClock
import android.provider.MediaStore
import android.provider.OpenableColumns
import android.util.Base64
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContract
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.dracknoval.domux.data.AppTempFiles
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.InputStream
import java.util.Locale
import com.dracknoval.domux.ui.theme.DomuxColor

/*
 * Adjuntar como en WhatsApp: tomar una foto o grabar un video o un audio en el momento, o elegir de
 * la galería, un audio guardado o un PDF. Los límites se dicen antes de elegir, las fotos se
 * reducen solas y nada de lo que se graba queda en la galería del celular: la cámara y el
 * micrófono escriben en la carpeta temporal privada de la app y el archivo se borra apenas se lee.
 */

/** Lo más que puede pesar un adjunto: lo mismo que acepta el servidor. */
const val MAX_ATTACHMENT_BYTES = 6 * 1024 * 1024
const val MAX_VIDEO_SECONDS = 30
const val MAX_AUDIO_SECONDS = 120
private const val MAX_MB = MAX_ATTACHMENT_BYTES / (1024 * 1024)

// Las fotos se guardan con el lado mayor de 1600 píxeles y calidad 80: se ven bien y pesan poco.
private const val PHOTO_MAX_SIDE = 1600
private const val PHOTO_QUALITY = 80

/** Qué se puede adjuntar en cada lugar. Los PDF solo van en PQRS, reservas y comunicados. */
enum class AttachmentKinds(val buttonText: String) {
    /** Portería (paquetes y visitas): solo fotos. */
    PHOTO("Agregar foto"),

    /** Fotos, videos y audios. */
    MEDIA("Adjuntar foto, video o audio"),

    /** Fotos, videos, audios y documentos PDF. */
    MEDIA_AND_PDF("Adjuntar archivo")
}

private enum class AttachmentOption(val title: String, val hint: String, val icon: Int) {
    PHOTO("Tomar foto", "Se reduce sola para que pese poco.", R.drawable.ic_photo_camera),
    VIDEO("Grabar video", "Hasta $MAX_VIDEO_SECONDS segundos.", R.drawable.ic_videocam),
    GALLERY_PHOTO("Elegir de la galería", "Tus fotos, sin buscar carpetas.", R.drawable.ic_image),
    GALLERY_MEDIA("Galería", "Fotos y videos (el video hasta $MAX_MB MB).", R.drawable.ic_image),
    AUDIO("Grabar audio", "Hasta ${MAX_AUDIO_SECONDS / 60} minutos.", R.drawable.ic_mic),
    AUDIO_FILE("Audio guardado", "Un audio de tu celular, hasta $MAX_MB MB.", R.drawable.ic_music_note),
    PDF("Documento PDF", "Hasta $MAX_MB MB.", R.drawable.ic_description)
}

/** Un problema con el archivo que se le dice tal cual a la persona. */
private class AttachmentProblem(message: String) : Exception(message)

/** Un adjunto listo para mandar al servidor. */
private class ReadyAttachment(val dataUrl: String, val type: String, val name: String)

/**
 * Botón para adjuntar. Al tocarlo muestra las opciones de [kinds]; lo elegido llega por
 * [onAttachment] como «data:tipo;base64,…» con su clase («image», «video», «audio» o
 * «document») y un nombre para mostrar. [onClear] quita el adjunto elegido.
 */
@Composable
fun MediaAttachmentPicker(
    attachmentName: String?,
    onAttachment: (mediaUrl: String, mediaType: String, fileName: String) -> Unit,
    onError: (String) -> Unit,
    kinds: AttachmentKinds = AttachmentKinds.MEDIA,
    onClear: (() -> Unit)? = null
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val hasCamera = remember { context.packageManager.hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY) }
    var showOptions by remember { mutableStateOf(false) }
    var recordingAudio by remember { mutableStateOf(false) }
    var working by remember { mutableStateOf(false) }
    // Lo último que se eligió, para verlo antes de enviar.
    var preview by remember { mutableStateOf<ReadyAttachment?>(null) }
    // Mientras la cámara está abierta la app puede cerrarse: la ruta del archivo se guarda aparte.
    var pendingCapture by rememberSaveable { mutableStateOf<String?>(null) }
    var pendingPermission by rememberSaveable { mutableStateOf<String?>(null) }

    fun process(read: suspend () -> ReadyAttachment) {
        working = true
        scope.launch {
            try {
                val ready = withContext(Dispatchers.IO) { read() }
                preview = ready
                onAttachment(ready.dataUrl, ready.type, ready.name)
            } catch (exception: CancellationException) {
                throw exception
            } catch (problem: AttachmentProblem) {
                onError(problem.message ?: "No se pudo leer el archivo.")
            } catch (exception: Exception) {
                onError("No se pudo leer el archivo. Intenta de nuevo.")
            } finally {
                working = false
            }
        }
    }

    fun capturedFile(): File? {
        val path = pendingCapture
        pendingCapture = null
        return path?.let(::File)
    }

    val takePhoto = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { saved ->
        val file = capturedFile() ?: return@rememberLauncherForActivityResult
        if (!saved || file.length() == 0L) {
            file.delete()
            return@rememberLauncherForActivityResult
        }
        process {
            try {
                photoAttachment({ file.inputStream() }, "Foto tomada")
            } finally {
                file.delete()
            }
        }
    }
    val recordVideo = rememberLauncherForActivityResult(CaptureShortVideo()) { saved ->
        val file = capturedFile() ?: return@rememberLauncherForActivityResult
        if (!saved || file.length() == 0L) {
            file.delete()
            return@rememberLauncherForActivityResult
        }
        process {
            try {
                val bytes = limitedBytes({ file.inputStream() }, file.length()) { size ->
                    "El video quedó de ${megabytes(size)} MB y el máximo es $MAX_MB MB. Graba uno más corto."
                }
                ReadyAttachment(dataUrl("video/mp4", bytes), "video", "Video grabado")
            } finally {
                file.delete()
            }
        }
    }
    val pickVisual = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) process { galleryAttachment(context, uri) }
    }
    val pickAudio = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri != null) process { audioFileAttachment(context, uri) }
    }
    val pickPdf = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) process { pdfAttachment(context, uri) }
    }

    fun startCapture(video: Boolean) {
        val file = try {
            File.createTempFile(if (video) "video-" else "foto-", if (video) ".mp4" else ".jpg", AppTempFiles.captureFolder(context))
        } catch (exception: Exception) {
            onError("No hay espacio en el celular para tomar la foto o el video.")
            return
        }
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        pendingCapture = file.absolutePath
        try {
            if (video) recordVideo.launch(uri) else takePhoto.launch(uri)
        } catch (exception: ActivityNotFoundException) {
            pendingCapture = null
            file.delete()
            onError("Este celular no tiene una app de cámara para hacerlo.")
        }
    }

    fun runAfterPermission(action: String) {
        when (action) {
            "photo" -> startCapture(video = false)
            "video" -> startCapture(video = true)
            "audio" -> recordingAudio = true
        }
    }

    val askPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        val action = pendingPermission ?: return@rememberLauncherForActivityResult
        pendingPermission = null
        if (granted) {
            runAfterPermission(action)
        } else {
            onError(
                if (action == "audio") "Para grabar audios, permite el micrófono para DOMUX en los ajustes del celular."
                else "Para tomar fotos o videos, permite la cámara para DOMUX en los ajustes del celular."
            )
        }
    }

    fun withPermission(action: String) {
        val permission = if (action == "audio") Manifest.permission.RECORD_AUDIO else Manifest.permission.CAMERA
        if (ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED) {
            runAfterPermission(action)
        } else {
            pendingPermission = action
            askPermission.launch(permission)
        }
    }

    fun choose(option: AttachmentOption) {
        showOptions = false
        when (option) {
            AttachmentOption.PHOTO -> withPermission("photo")
            AttachmentOption.VIDEO -> withPermission("video")
            AttachmentOption.AUDIO -> withPermission("audio")
            AttachmentOption.GALLERY_PHOTO ->
                pickVisual.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
            AttachmentOption.GALLERY_MEDIA ->
                pickVisual.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageAndVideo))
            AttachmentOption.AUDIO_FILE -> pickAudio.launch("audio/*")
            AttachmentOption.PDF -> pickPdf.launch(arrayOf("application/pdf"))
        }
    }

    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedButton(onClick = { showOptions = true }, enabled = !working) {
                Icon(painterResource(R.drawable.ic_add), contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text(if (attachmentName == null) kinds.buttonText else "Cambiar adjunto")
            }
            if (working) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp)
        }
        if (attachmentName != null) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "Adjunto: $attachmentName",
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.weight(1f)
                )
                if (onClear != null) {
                    TextButton(onClick = {
                        preview = null
                        onClear()
                    }) { Text("Quitar") }
                }
            }
            preview?.let { MediaAttachment(it.dataUrl, it.type, "Vista previa del adjunto") }
        }
    }

    if (showOptions) {
        AttachmentOptionsDialog(
            options = buildList {
                if (hasCamera) add(AttachmentOption.PHOTO)
                if (kinds == AttachmentKinds.PHOTO) {
                    add(AttachmentOption.GALLERY_PHOTO)
                } else {
                    if (hasCamera) add(AttachmentOption.VIDEO)
                    add(AttachmentOption.GALLERY_MEDIA)
                    add(AttachmentOption.AUDIO)
                    add(AttachmentOption.AUDIO_FILE)
                    if (kinds == AttachmentKinds.MEDIA_AND_PDF) add(AttachmentOption.PDF)
                }
            },
            onChoose = ::choose,
            onDismiss = { showOptions = false }
        )
    }
    if (recordingAudio) {
        AudioRecorderDialog(
            onUse = { url, seconds ->
                recordingAudio = false
                val ready = ReadyAttachment(url, "audio", "Audio grabado (${clockText(seconds * 1000)})")
                preview = ready
                onAttachment(ready.dataUrl, ready.type, ready.name)
            },
            onCancel = { recordingAudio = false },
            onError = { problem ->
                recordingAudio = false
                onError(problem)
            }
        )
    }
}

/** La lista de opciones para adjuntar, con el límite de cada una a la vista. */
@Composable
private fun AttachmentOptionsDialog(
    options: List<AttachmentOption>,
    onChoose: (AttachmentOption) -> Unit,
    onDismiss: () -> Unit
) {
    Dialog(onDismissRequest = onDismiss) {
        Surface(shape = RoundedCornerShape(24.dp), color = MaterialTheme.colorScheme.surface) {
            Column(Modifier.padding(vertical = 16.dp)) {
                Text(
                    "Adjuntar",
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.padding(horizontal = 20.dp, vertical = 4.dp)
                )
                options.forEach { option ->
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(min = 56.dp)
                            .clickable(role = Role.Button, onClickLabel = option.title) { onChoose(option) }
                            .padding(horizontal = 20.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        Box(
                            Modifier
                                .size(40.dp)
                                .background(MaterialTheme.colorScheme.primary.copy(alpha = 0.16f), CircleShape),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                painterResource(option.icon),
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.primary,
                                modifier = Modifier.size(22.dp)
                            )
                        }
                        Column(Modifier.weight(1f)) {
                            Text(option.title, style = MaterialTheme.typography.titleSmall)
                            Text(
                                option.hint,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
                TextButton(
                    onClick = onDismiss,
                    modifier = Modifier
                        .align(Alignment.End)
                        .padding(horizontal = 12.dp)
                ) { Text("Cancelar") }
            }
        }
    }
}

/**
 * Graba un audio con el micrófono (AAC en MP4, como las notas de voz) hasta [MAX_AUDIO_SECONDS]
 * segundos. Se escucha antes de usarlo y el archivo temporal se borra apenas se lee.
 */
@Composable
private fun AudioRecorderDialog(
    onUse: (dataUrl: String, seconds: Int) -> Unit,
    onCancel: () -> Unit,
    onError: (String) -> Unit
) {
    val context = LocalContext.current
    var recorder by remember { mutableStateOf<MediaRecorder?>(null) }
    var output by remember { mutableStateOf<File?>(null) }
    var startedAt by remember { mutableLongStateOf(0L) }
    var elapsed by remember { mutableIntStateOf(0) }
    var recorded by remember { mutableStateOf<String?>(null) }
    var recordedSeconds by remember { mutableIntStateOf(0) }

    fun stop() {
        val active = recorder ?: return
        recorder = null
        val finished = try {
            active.stop()
            true
        } catch (exception: RuntimeException) {
            // Pasa si se detiene antes de que haya sonido grabado.
            false
        }
        active.release()
        val file = output
        output = null
        val bytes = if (finished) file?.readBytes() else null
        file?.delete()
        if (bytes == null || bytes.isEmpty()) {
            onError("El audio quedó vacío. Graba al menos un segundo.")
            return
        }
        recordedSeconds = elapsed.coerceAtLeast(1)
        recorded = dataUrl("audio/mp4", bytes)
    }

    fun start() {
        recorded = null
        val file = try {
            File.createTempFile("audio-", ".m4a", AppTempFiles.mediaFolder(context))
        } catch (exception: Exception) {
            onError("No hay espacio en el celular para grabar el audio.")
            return
        }
        val created = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            MediaRecorder(context)
        } else {
            @Suppress("DEPRECATION")
            MediaRecorder()
        }
        try {
            created.setAudioSource(MediaRecorder.AudioSource.MIC)
            created.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            created.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            created.setAudioChannels(1)
            created.setAudioSamplingRate(44_100)
            created.setAudioEncodingBitRate(64_000)
            created.setMaxDuration(MAX_AUDIO_SECONDS * 1000)
            created.setOutputFile(file.absolutePath)
            created.setOnInfoListener { _, what, _ ->
                if (what == MediaRecorder.MEDIA_RECORDER_INFO_MAX_DURATION_REACHED) stop()
            }
            created.prepare()
            created.start()
        } catch (exception: Exception) {
            created.release()
            file.delete()
            onError("No se pudo usar el micrófono. Cierra otras apps que lo estén usando e intenta de nuevo.")
            return
        }
        recorder = created
        output = file
        startedAt = SystemClock.elapsedRealtime()
        elapsed = 0
    }

    LaunchedEffect(Unit) { start() }
    LaunchedEffect(recorder) {
        while (recorder != null) {
            elapsed = ((SystemClock.elapsedRealtime() - startedAt) / 1000).toInt()
            delay(250)
        }
    }
    DisposableEffect(Unit) {
        onDispose {
            recorder?.let { active ->
                try {
                    active.stop()
                } catch (exception: RuntimeException) {
                    // Ya estaba detenido o no alcanzó a grabar: solo se libera.
                }
                active.release()
            }
            output?.delete()
        }
    }

    val result = recorded
    AlertDialog(
        // Mientras graba no se cierra tocando afuera: se usa «Detener» o «Cancelar».
        onDismissRequest = { if (recorder == null) onCancel() },
        title = { Text(if (result == null) "Grabando audio" else "Audio grabado") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                if (result == null) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Box(
                            Modifier
                                .size(12.dp)
                                .background(DomuxColor.BadNoticeLine, CircleShape)
                        )
                        Text(
                            "${clockText(elapsed * 1000)} de ${clockText(MAX_AUDIO_SECONDS * 1000)}",
                            style = MaterialTheme.typography.titleMedium
                        )
                    }
                    LinearProgressIndicator(
                        progress = { elapsed.toFloat() / MAX_AUDIO_SECONDS },
                        modifier = Modifier.fillMaxWidth()
                    )
                    Text(
                        "Habla cerca del celular. A los ${MAX_AUDIO_SECONDS / 60} minutos se detiene solo.",
                        style = MaterialTheme.typography.bodySmall
                    )
                } else {
                    Text("Escúchalo antes de enviarlo.", style = MaterialTheme.typography.bodySmall)
                    MediaAttachment(result, "audio")
                }
            }
        },
        confirmButton = {
            if (result == null) {
                Button(onClick = { stop() }, enabled = recorder != null) { Text("Detener") }
            } else {
                Button(onClick = { onUse(result, recordedSeconds) }) { Text("Usar este audio") }
            }
        },
        dismissButton = {
            Row {
                if (result != null) TextButton(onClick = { start() }) { Text("Grabar otra vez") }
                TextButton(onClick = onCancel) { Text("Cancelar") }
            }
        }
    )
}

/** Abre la cámara para un video corto y de calidad baja, para que pese poco. */
private class CaptureShortVideo : ActivityResultContract<Uri, Boolean>() {
    override fun createIntent(context: Context, input: Uri): Intent =
        Intent(MediaStore.ACTION_VIDEO_CAPTURE)
            .putExtra(MediaStore.EXTRA_OUTPUT, input)
            .putExtra(MediaStore.EXTRA_DURATION_LIMIT, MAX_VIDEO_SECONDS)
            .putExtra(MediaStore.EXTRA_VIDEO_QUALITY, 0)
            .putExtra(MediaStore.EXTRA_SIZE_LIMIT, MAX_ATTACHMENT_BYTES.toLong())
            .addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION or Intent.FLAG_GRANT_READ_URI_PERMISSION)

    override fun parseResult(resultCode: Int, intent: Intent?): Boolean = resultCode == Activity.RESULT_OK
}

// --- Lectura de archivos (se llama fuera del hilo principal) --------------------------------

/** «6,2» a partir de bytes: así se dice el peso a la persona. */
private fun megabytes(size: Long): String =
    String.format(Locale.US, "%.1f", size / (1024.0 * 1024.0)).replace('.', ',')

private fun dataUrl(mimeType: String, bytes: ByteArray): String =
    "data:$mimeType;base64," + Base64.encodeToString(bytes, Base64.NO_WRAP)

private fun displayName(context: Context, uri: Uri): String? =
    context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
        if (cursor.moveToFirst() && !cursor.isNull(0)) cursor.getString(0) else null
    }

private fun sizeOf(context: Context, uri: Uri): Long? =
    context.contentResolver.query(uri, arrayOf(OpenableColumns.SIZE), null, null, null)?.use { cursor ->
        if (cursor.moveToFirst() && !cursor.isNull(0)) cursor.getLong(0) else null
    }

/** Lee el archivo sin pasar de [MAX_ATTACHMENT_BYTES]; si pesa más, el error dice cuánto (si se sabe). */
private fun limitedBytes(open: () -> InputStream?, knownSize: Long?, tooHeavy: (Long) -> String): ByteArray {
    if (knownSize != null && knownSize > MAX_ATTACHMENT_BYTES) throw AttachmentProblem(tooHeavy(knownSize))
    val input = open() ?: throw AttachmentProblem("No se pudo abrir el archivo.")
    val bytes = input.use { stream ->
        val buffer = ByteArray(64 * 1024)
        val collected = ByteArrayOutputStream()
        while (collected.size() <= MAX_ATTACHMENT_BYTES) {
            val read = stream.read(buffer)
            if (read < 0) break
            collected.write(buffer, 0, read)
        }
        collected.toByteArray()
    }
    if (bytes.size > MAX_ATTACHMENT_BYTES) {
        throw AttachmentProblem(
            if (knownSize != null) tooHeavy(knownSize) else "El archivo pesa más de $MAX_MB MB, que es el máximo."
        )
    }
    if (bytes.isEmpty()) throw AttachmentProblem("El archivo está vacío.")
    return bytes
}

/** Cuánto hay que girar la foto según lo que anotó la cámara (muchas fotos salen acostadas). */
private fun rotationOf(open: () -> InputStream?): Int = try {
    open()?.use { stream ->
        when (ExifInterface(stream).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)) {
            ExifInterface.ORIENTATION_ROTATE_90 -> 90
            ExifInterface.ORIENTATION_ROTATE_180 -> 180
            ExifInterface.ORIENTATION_ROTATE_270 -> 270
            else -> 0
        }
    } ?: 0
} catch (exception: Exception) {
    0
}

/** La foto reducida (lado mayor de 1600 píxeles, JPEG al 80 %), derecha y sin transparencias. */
private fun photoAttachment(open: () -> InputStream?, name: String): ReadyAttachment {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    val first = open() ?: throw AttachmentProblem("No se pudo abrir la foto.")
    first.use { BitmapFactory.decodeStream(it, null, bounds) }
    if (bounds.outWidth <= 0 || bounds.outHeight <= 0) throw AttachmentProblem("Ese archivo no es una foto que se pueda leer.")
    var sample = 1
    while (maxOf(bounds.outWidth, bounds.outHeight) / (sample * 2) >= PHOTO_MAX_SIDE) sample *= 2
    val second = open() ?: throw AttachmentProblem("No se pudo abrir la foto.")
    val decoded = second.use { BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply { inSampleSize = sample }) }
        ?: throw AttachmentProblem("Ese archivo no es una foto que se pueda leer.")
    val rotation = rotationOf(open)
    val longest = maxOf(decoded.width, decoded.height)
    val factor = if (longest > PHOTO_MAX_SIDE) PHOTO_MAX_SIDE.toFloat() / longest else 1f
    val adjusted = if (factor < 1f || rotation != 0) {
        val matrix = Matrix().apply {
            if (factor < 1f) postScale(factor, factor)
            if (rotation != 0) postRotate(rotation.toFloat())
        }
        Bitmap.createBitmap(decoded, 0, 0, decoded.width, decoded.height, matrix, true)
    } else {
        decoded
    }
    // El JPEG no guarda transparencias: lo transparente queda blanco y no negro.
    val opaque = if (adjusted.hasAlpha()) {
        Bitmap.createBitmap(adjusted.width, adjusted.height, Bitmap.Config.ARGB_8888).also { canvasBitmap ->
            Canvas(canvasBitmap).apply {
                drawColor(android.graphics.Color.WHITE)
                drawBitmap(adjusted, 0f, 0f, null)
            }
        }
    } else {
        adjusted
    }
    val bytes = ByteArrayOutputStream().use { stream ->
        opaque.compress(Bitmap.CompressFormat.JPEG, PHOTO_QUALITY, stream)
        stream.toByteArray()
    }
    return ReadyAttachment(dataUrl("image/jpeg", bytes), "image", name)
}

/** Una foto o un video elegido en la galería. */
private fun galleryAttachment(context: Context, uri: Uri): ReadyAttachment {
    val resolver = context.contentResolver
    val mimeType = resolver.getType(uri).orEmpty()
    val name = displayName(context, uri)
    if (mimeType.startsWith("video/")) {
        val bytes = limitedBytes({ resolver.openInputStream(uri) }, sizeOf(context, uri)) { size ->
            "El video pesa ${megabytes(size)} MB y el máximo es $MAX_MB MB. Graba uno nuevo de hasta " +
                "$MAX_VIDEO_SECONDS segundos con «Grabar video» o recórtalo en la galería de tu celular."
        }
        return ReadyAttachment(dataUrl(mimeType, bytes), "video", name ?: "Video de la galería")
    }
    return photoAttachment({ resolver.openInputStream(uri) }, name ?: "Foto de la galería")
}

/** Un audio guardado en el celular (una nota de voz, por ejemplo). */
private fun audioFileAttachment(context: Context, uri: Uri): ReadyAttachment {
    val resolver = context.contentResolver
    val mimeType = resolver.getType(uri).orEmpty()
    if (!mimeType.startsWith("audio/")) throw AttachmentProblem("Ese archivo no es un audio.")
    val bytes = limitedBytes({ resolver.openInputStream(uri) }, sizeOf(context, uri)) { size ->
        "El audio pesa ${megabytes(size)} MB y el máximo es $MAX_MB MB. Elige uno más corto o grábalo con «Grabar audio»."
    }
    return ReadyAttachment(dataUrl(mimeType, bytes), "audio", displayName(context, uri) ?: "Audio guardado")
}

/** Un documento PDF del celular. */
private fun pdfAttachment(context: Context, uri: Uri): ReadyAttachment {
    val resolver = context.contentResolver
    val bytes = limitedBytes({ resolver.openInputStream(uri) }, sizeOf(context, uri)) { size ->
        "El documento pesa ${megabytes(size)} MB y el máximo es $MAX_MB MB."
    }
    val isPdf = bytes.size >= 5 && String(bytes, 0, 5, Charsets.US_ASCII) == "%PDF-"
    if (!isPdf) throw AttachmentProblem("Ese archivo no es un documento PDF.")
    return ReadyAttachment(dataUrl("application/pdf", bytes), "document", displayName(context, uri) ?: "Documento PDF")
}
