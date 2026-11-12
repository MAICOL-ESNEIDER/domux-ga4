package com.dracknoval.domux

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.pdf.PdfRenderer
import android.media.MediaPlayer
import android.os.ParcelFileDescriptor
import android.util.Base64
import android.widget.MediaController
import android.widget.VideoView
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.rememberTransformableState
import androidx.compose.foundation.gestures.transformable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.dracknoval.domux.data.AppTempFiles
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import com.dracknoval.domux.ui.theme.DomuxColor

/**
 * Visor de los adjuntos que llegan del servidor (fotos, videos, audios y documentos PDF de PQRS,
 * reservas, comunicados, paquetes y visitas).
 *
 * El servidor entrega cada adjunto como «data:image/jpeg;base64,…». Aquí se separa, se muestra la
 * foto en miniatura (se toca para verla en grande y acercarla con dos dedos), el video se abre en
 * pantalla completa, el audio tiene su reproductor y el PDF se lee página por página dentro de la
 * app. Nada se guarda en la galería ni en Descargas: un video, un audio o un PDF se escribe en la
 * carpeta temporal privada de la app solo mientras está abierto y se borra al cerrar (ver
 * [AppTempFiles]).
 */

/** Un adjunto ya separado en su tipo (por ejemplo «image/jpeg») y sus bytes. */
class DecodedMedia(val mimeType: String, val bytes: ByteArray)

/** Separa un adjunto «data:tipo;base64,contenido»; null si no tiene esa forma o no es base64. */
fun decodeDataUrl(dataUrl: String?): DecodedMedia? {
    if (dataUrl == null || !dataUrl.startsWith("data:")) return null
    val comma = dataUrl.indexOf(',')
    if (comma < 0) return null
    val header = dataUrl.substring(5, comma)
    if (!header.contains(";base64", ignoreCase = true)) return null
    return try {
        DecodedMedia(
            header.substringBefore(';').trim().lowercase(),
            Base64.decode(dataUrl.substring(comma + 1), Base64.DEFAULT)
        )
    } catch (exception: IllegalArgumentException) {
        null
    }
}

/** La extensión del archivo temporal según su tipo; el reproductor la usa para reconocerlo. */
private fun extensionFor(mimeType: String): String = when (mimeType) {
    "image/jpeg", "image/jpg" -> "jpg"
    "image/png" -> "png"
    "image/webp" -> "webp"
    "video/mp4" -> "mp4"
    "video/3gpp" -> "3gp"
    "video/webm" -> "webm"
    "audio/mp4", "audio/m4a", "audio/x-m4a" -> "m4a"
    "audio/aac", "audio/x-aac" -> "aac"
    "audio/mpeg", "audio/mp3" -> "mp3"
    "audio/ogg", "audio/opus" -> "ogg"
    "audio/wav", "audio/x-wav" -> "wav"
    "audio/3gpp", "audio/amr" -> "3gp"
    "application/pdf" -> "pdf"
    else -> "bin"
}

/** Escribe el adjunto en la carpeta temporal privada; quien lo pide lo borra al terminar. */
private fun writeTemp(context: Context, media: DecodedMedia): File {
    val file = File.createTempFile("adjunto-", "." + extensionFor(media.mimeType), AppTempFiles.mediaFolder(context))
    file.writeBytes(media.bytes)
    return file
}

/** Lee una imagen sin pasar de [maxSide] píxeles por lado, para no gastar memoria con fotos grandes. */
private fun decodeBitmap(bytes: ByteArray, maxSide: Int): Bitmap? {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
    if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
    var sample = 1
    while (bounds.outWidth / (sample * 2) >= maxSide || bounds.outHeight / (sample * 2) >= maxSide) {
        sample *= 2
    }
    return BitmapFactory.decodeByteArray(bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = sample })
}

/** «1:05» a partir de milisegundos. */
internal fun clockText(milliseconds: Int): String {
    val seconds = (milliseconds / 1000).coerceAtLeast(0)
    return "%d:%02d".format(seconds / 60, seconds % 60)
}

/** Lo que pasa mientras un adjunto se prepara en segundo plano. */
private sealed interface Prepared<out T> {
    object Loading : Prepared<Nothing>
    class Ready<T>(val value: T) : Prepared<T>
    object Failed : Prepared<Nothing>
}

/**
 * Muestra un adjunto según su tipo: «image», «video», «audio» o «document» (PDF). [description]
 * es lo que oye quien usa el lector de pantalla (por ejemplo «Foto del paquete»).
 */
@Composable
fun MediaAttachment(mediaUrl: String?, mediaType: String?, description: String = "Foto adjunta") {
    if (mediaUrl.isNullOrBlank()) return
    when (mediaType?.lowercase()) {
        "image" -> ImageAttachment(mediaUrl, description)
        "video" -> VideoAttachment(mediaUrl)
        "audio" -> AudioAttachment(mediaUrl)
        "document" -> DocumentAttachment(mediaUrl)
        else -> AttachmentNotice("Este adjunto no se puede mostrar en la app.")
    }
}

@Composable
private fun AttachmentNotice(text: String) {
    Text(text, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
private fun AttachmentFrame(height: Int, content: @Composable BoxScope.() -> Unit) {
    Box(
        modifier = Modifier
            .widthIn(max = 320.dp)
            .fillMaxWidth()
            .height(height.dp)
            .clip(RoundedCornerShape(14.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant),
        contentAlignment = Alignment.Center,
        content = content
    )
}

// --- Fotos ----------------------------------------------------------------------------------

@Composable
private fun ImageAttachment(dataUrl: String, description: String) {
    val thumbnail by produceState<Prepared<Bitmap>>(Prepared.Loading, dataUrl) {
        value = withContext(Dispatchers.Default) {
            decodeDataUrl(dataUrl)?.let { decodeBitmap(it.bytes, 720) }?.let { Prepared.Ready(it) } ?: Prepared.Failed
        }
    }
    var open by remember(dataUrl) { mutableStateOf(false) }
    when (val current = thumbnail) {
        is Prepared.Loading -> AttachmentFrame(120) { CircularProgressIndicator(Modifier.size(28.dp)) }
        is Prepared.Failed -> AttachmentNotice("No se pudo mostrar la foto.")
        is Prepared.Ready -> Box(
            modifier = Modifier
                .widthIn(max = 320.dp)
                .fillMaxWidth()
                .heightIn(max = 240.dp)
                .clip(RoundedCornerShape(14.dp))
                .clickable(onClickLabel = "Ver la foto en grande") { open = true }
                .semantics { contentDescription = "$description. Toca para verla en grande." }
        ) {
            Image(
                bitmap = current.value.asImageBitmap(),
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxWidth()
            )
        }
    }
    if (open) ImageViewerDialog(dataUrl, description) { open = false }
}

/** La foto en pantalla completa; se acerca y se mueve con dos dedos. */
@Composable
private fun ImageViewerDialog(dataUrl: String, description: String, onClose: () -> Unit) {
    val image by produceState<Prepared<Bitmap>>(Prepared.Loading, dataUrl) {
        value = withContext(Dispatchers.Default) {
            decodeDataUrl(dataUrl)?.let { decodeBitmap(it.bytes, 2048) }?.let { Prepared.Ready(it) } ?: Prepared.Failed
        }
    }
    var scale by remember { mutableFloatStateOf(1f) }
    var offset by remember { mutableStateOf(Offset.Zero) }
    val zoom = rememberTransformableState { zoomChange, panChange, _ ->
        scale = (scale * zoomChange).coerceIn(1f, 5f)
        offset = if (scale == 1f) Offset.Zero else offset + panChange
    }
    FullScreenViewer(onClose) {
        when (val current = image) {
            is Prepared.Loading -> CircularProgressIndicator(Modifier.align(Alignment.Center))
            is Prepared.Failed -> Text(
                "No se pudo abrir la foto.",
                color = Color.White,
                modifier = Modifier.align(Alignment.Center)
            )
            is Prepared.Ready -> Image(
                bitmap = current.value.asImageBitmap(),
                contentDescription = description,
                contentScale = ContentScale.Fit,
                modifier = Modifier
                    .fillMaxSize()
                    .graphicsLayer {
                        scaleX = scale
                        scaleY = scale
                        translationX = offset.x
                        translationY = offset.y
                    }
                    .transformable(zoom)
            )
        }
    }
}

/** Fondo negro en toda la pantalla con el botón para cerrar arriba a la derecha. */
@Composable
private fun FullScreenViewer(onClose: () -> Unit, content: @Composable BoxScope.() -> Unit) {
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Box(
            Modifier
                .fillMaxSize()
                .background(Color.Black)
        ) {
            content()
            IconButton(
                onClick = onClose,
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .padding(8.dp)
                    .size(48.dp)
                    .background(DomuxColor.Scrim, CircleShape)
            ) {
                Icon(painterResource(R.drawable.ic_close), contentDescription = "Cerrar", tint = Color.White)
            }
        }
    }
}

// --- Videos ---------------------------------------------------------------------------------

@Composable
private fun VideoAttachment(dataUrl: String) {
    var open by remember(dataUrl) { mutableStateOf(false) }
    Box(
        modifier = Modifier
            .widthIn(max = 320.dp)
            .fillMaxWidth()
            .height(160.dp)
            .clip(RoundedCornerShape(14.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .clickable(onClickLabel = "Reproducir el video") { open = true }
            .semantics { contentDescription = "Video adjunto. Toca para reproducirlo." },
        contentAlignment = Alignment.Center
    ) {
        Box(
            Modifier
                .size(56.dp)
                .background(DomuxColor.Overlay, CircleShape),
            contentAlignment = Alignment.Center
        ) {
            Icon(painterResource(R.drawable.ic_play), contentDescription = null, tint = Color.White, modifier = Modifier.size(30.dp))
        }
    }
    if (open) VideoViewerDialog(dataUrl) { open = false }
}

/** El video en pantalla completa con los controles del sistema (pausa, adelantar, volumen). */
@Composable
private fun VideoViewerDialog(dataUrl: String, onClose: () -> Unit) {
    val context = LocalContext.current
    val file by produceState<Prepared<File>>(Prepared.Loading, dataUrl) {
        value = withContext(Dispatchers.IO) {
            try {
                decodeDataUrl(dataUrl)?.let { Prepared.Ready(writeTemp(context, it)) } ?: Prepared.Failed
            } catch (exception: Exception) {
                Prepared.Failed
            }
        }
    }
    DisposableEffect(file) {
        val written = file.let { if (it is Prepared.Ready) it.value else null }
        onDispose { written?.delete() }
    }
    FullScreenViewer(onClose) {
        when (val current = file) {
            is Prepared.Loading -> CircularProgressIndicator(Modifier.align(Alignment.Center))
            is Prepared.Failed -> Text(
                "No se pudo abrir el video.",
                color = Color.White,
                modifier = Modifier.align(Alignment.Center)
            )
            is Prepared.Ready -> AndroidView(
                factory = { viewContext ->
                    VideoView(viewContext).apply {
                        val controls = MediaController(viewContext)
                        controls.setAnchorView(this)
                        setMediaController(controls)
                        setOnPreparedListener { player -> player.start() }
                        setVideoPath(current.value.absolutePath)
                    }
                },
                onRelease = { view -> view.stopPlayback() },
                modifier = Modifier
                    .align(Alignment.Center)
                    .fillMaxWidth()
            )
        }
    }
}

// --- Audios ---------------------------------------------------------------------------------

/** Reproductor de un audio dentro de la conversación: reproducir o pausar, avance y tiempo. */
@Composable
private fun AudioAttachment(dataUrl: String) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var player by remember(dataUrl) { mutableStateOf<MediaPlayer?>(null) }
    var tempFile by remember(dataUrl) { mutableStateOf<File?>(null) }
    var preparing by remember(dataUrl) { mutableStateOf(false) }
    var playing by remember(dataUrl) { mutableStateOf(false) }
    var failed by remember(dataUrl) { mutableStateOf(false) }
    var position by remember(dataUrl) { mutableIntStateOf(0) }
    var duration by remember(dataUrl) { mutableIntStateOf(0) }

    DisposableEffect(dataUrl) {
        onDispose {
            player?.release()
            tempFile?.delete()
        }
    }
    LaunchedEffect(playing) {
        while (playing) {
            position = player?.currentPosition ?: 0
            delay(250)
        }
    }

    fun toggle() {
        val current = player
        if (current != null) {
            if (current.isPlaying) {
                current.pause()
                playing = false
            } else {
                current.start()
                playing = true
            }
            return
        }
        if (preparing) return
        preparing = true
        failed = false
        scope.launch {
            val result = withContext(Dispatchers.IO) {
                try {
                    val media = decodeDataUrl(dataUrl) ?: return@withContext null
                    val file = writeTemp(context, media)
                    try {
                        val prepared = MediaPlayer().apply {
                            setDataSource(file.absolutePath)
                            prepare()
                        }
                        file to prepared
                    } catch (exception: Exception) {
                        file.delete()
                        null
                    }
                } catch (exception: Exception) {
                    null
                }
            }
            preparing = false
            if (result == null) {
                failed = true
                return@launch
            }
            val (file, prepared) = result
            tempFile = file
            prepared.setOnCompletionListener { finished ->
                playing = false
                position = 0
                finished.seekTo(0)
            }
            player = prepared
            duration = prepared.duration.coerceAtLeast(0)
            prepared.start()
            playing = true
        }
    }

    Row(
        modifier = Modifier
            .widthIn(max = 320.dp)
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .padding(horizontal = 8.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        FilledIconButton(onClick = { toggle() }, modifier = Modifier.size(48.dp)) {
            if (preparing) {
                CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
            } else {
                Icon(
                    painterResource(if (playing) R.drawable.ic_pause else R.drawable.ic_play),
                    contentDescription = if (playing) "Pausar el audio" else "Reproducir el audio"
                )
            }
        }
        Slider(
            value = if (duration > 0) position.toFloat() / duration else 0f,
            onValueChange = { fraction ->
                player?.let {
                    val target = (fraction * duration).toInt()
                    it.seekTo(target)
                    position = target
                }
            },
            enabled = player != null,
            modifier = Modifier
                .weight(1f)
                .semantics { contentDescription = "Avance del audio" }
        )
        Text(
            when {
                failed -> "No se pudo abrir"
                duration == 0 -> "Audio"
                playing || position > 0 -> clockText(position)
                else -> clockText(duration)
            },
            style = MaterialTheme.typography.labelMedium
        )
    }
}

// --- Documentos PDF -------------------------------------------------------------------------

/** Tarjeta del PDF adjunto; al tocarla se abre dentro de la app, página por página. */
@Composable
private fun DocumentAttachment(dataUrl: String) {
    var open by remember(dataUrl) { mutableStateOf(false) }
    Row(
        modifier = Modifier
            .widthIn(max = 320.dp)
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .clickable(onClickLabel = "Abrir el documento") { open = true }
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Icon(painterResource(R.drawable.ic_description), contentDescription = null, modifier = Modifier.size(28.dp))
        Column(Modifier.weight(1f)) {
            Text("Documento PDF", style = MaterialTheme.typography.titleSmall)
            Text("Toca para leerlo", style = MaterialTheme.typography.bodySmall)
        }
    }
    if (open) PdfViewerDialog(dataUrl) { open = false }
}

/**
 * Un PDF abierto desde la carpeta temporal. El lector de Android solo deja abrir una página a la
 * vez, así que dibujar y cerrar van por turnos; al cerrar se borra el archivo.
 */
private class OpenedPdf(private val file: File) {
    private val descriptor = ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)
    private val renderer = try {
        PdfRenderer(descriptor)
    } catch (exception: Exception) {
        descriptor.close()
        file.delete()
        throw exception
    }
    private val lock = Any()
    private var closed = false

    val pageCount: Int = renderer.pageCount

    /** La página [index] dibujada con [width] píxeles de ancho; null si ya se cerró o falla. */
    fun render(index: Int, width: Int): Bitmap? {
        synchronized(lock) {
            if (closed) return null
            return try {
                val page = renderer.openPage(index)
                try {
                    val height = (width.toFloat() * page.height / page.width).toInt().coerceAtLeast(1)
                    val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
                    bitmap.eraseColor(android.graphics.Color.WHITE)
                    page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                    bitmap
                } finally {
                    page.close()
                }
            } catch (exception: Exception) {
                null
            }
        }
    }

    fun close() {
        synchronized(lock) {
            if (closed) return
            closed = true
            try {
                renderer.close()
            } catch (exception: Exception) {
                // Si no abrió bien no hay nada más que cerrar.
            }
            descriptor.close()
            file.delete()
        }
    }
}

/** El PDF en pantalla completa. Cada página se puede tocar para verla en grande y acercarla. */
@Composable
private fun PdfViewerDialog(dataUrl: String, onClose: () -> Unit) {
    val context = LocalContext.current
    val document by produceState<Prepared<OpenedPdf>>(Prepared.Loading, dataUrl) {
        value = withContext(Dispatchers.IO) {
            try {
                decodeDataUrl(dataUrl)?.let { Prepared.Ready(OpenedPdf(writeTemp(context, it))) } ?: Prepared.Failed
            } catch (exception: Exception) {
                Prepared.Failed
            }
        }
    }
    DisposableEffect(document) {
        val opened = document.let { if (it is Prepared.Ready) it.value else null }
        onDispose { opened?.close() }
    }
    val pageWidth = with(LocalDensity.current) { LocalConfiguration.current.screenWidthDp.dp.roundToPx() }.coerceAtMost(1440)
    var zoomed by remember { mutableStateOf<Bitmap?>(null) }
    FullScreenViewer(onClose) {
        when (val current = document) {
            is Prepared.Loading -> CircularProgressIndicator(Modifier.align(Alignment.Center))
            is Prepared.Failed -> Text(
                "No se pudo abrir el documento.",
                color = Color.White,
                modifier = Modifier.align(Alignment.Center)
            )
            is Prepared.Ready -> LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(start = 8.dp, end = 8.dp, top = 72.dp, bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                items(current.value.pageCount) { index ->
                    PdfPage(current.value, index, current.value.pageCount, pageWidth) { zoomed = it }
                }
            }
        }
    }
    zoomed?.let { page -> ZoomedPageDialog(page) { zoomed = null } }
}

@Composable
private fun PdfPage(document: OpenedPdf, index: Int, total: Int, width: Int, onZoom: (Bitmap) -> Unit) {
    val page by produceState<Prepared<Bitmap>>(Prepared.Loading, document, index) {
        value = withContext(Dispatchers.IO) { document.render(index, width)?.let { Prepared.Ready(it) } ?: Prepared.Failed }
    }
    when (val current = page) {
        is Prepared.Loading -> Box(
            Modifier
                .fillMaxWidth()
                .height(240.dp),
            contentAlignment = Alignment.Center
        ) { CircularProgressIndicator() }
        is Prepared.Failed -> Text("No se pudo mostrar la página ${index + 1}.", color = Color.White)
        is Prepared.Ready -> Image(
            bitmap = current.value.asImageBitmap(),
            contentDescription = "Página ${index + 1} de $total. Toca para verla en grande.",
            contentScale = ContentScale.FillWidth,
            modifier = Modifier
                .fillMaxWidth()
                .clickable(onClickLabel = "Ver la página en grande") { onZoom(current.value) }
        )
    }
}

/** Una página del PDF en grande: se acerca y se mueve con dos dedos. */
@Composable
private fun ZoomedPageDialog(page: Bitmap, onClose: () -> Unit) {
    var scale by remember { mutableFloatStateOf(1f) }
    var offset by remember { mutableStateOf(Offset.Zero) }
    val zoom = rememberTransformableState { zoomChange, panChange, _ ->
        scale = (scale * zoomChange).coerceIn(1f, 5f)
        offset = if (scale == 1f) Offset.Zero else offset + panChange
    }
    FullScreenViewer(onClose) {
        Image(
            bitmap = page.asImageBitmap(),
            contentDescription = "Página del documento",
            contentScale = ContentScale.Fit,
            modifier = Modifier
                .fillMaxSize()
                .graphicsLayer {
                    scaleX = scale
                    scaleY = scale
                    translationX = offset.x
                    translationY = offset.y
                }
                .transformable(zoom)
        )
    }
}
