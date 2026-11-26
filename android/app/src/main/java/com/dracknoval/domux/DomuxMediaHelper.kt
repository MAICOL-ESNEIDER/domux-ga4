package com.dracknoval.domux

import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Base64
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import coil.compose.AsyncImage
import coil.request.ImageRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream

fun saveBytesToDownloads(
    context: Context,
    fileName: String,
    mimeType: String,
    bytes: ByteArray
): Uri? {
    if (bytes.isEmpty()) return null
    val safeFileName = fileName.substringAfterLast('/').substringAfterLast('\\').trim().ifEmpty { "archivo_descargado" }
    
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, safeFileName)
            put(MediaStore.Downloads.MIME_TYPE, mimeType)
            put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
            put(MediaStore.Downloads.IS_PENDING, 1)
        }
        val uri = context.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return null
        return try {
            context.contentResolver.openOutputStream(uri)?.use { it.write(bytes) }
            values.clear()
            values.put(MediaStore.Downloads.IS_PENDING, 0)
            context.contentResolver.update(uri, values, null, null)
            uri
        } catch (e: Exception) {
            context.contentResolver.delete(uri, null, null)
            null
        }
    } else {
        @Suppress("DEPRECATION")
        val downloads = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
        if (!downloads.exists() && !downloads.mkdirs()) return null
        val file = File(downloads, safeFileName)
        return try {
            FileOutputStream(file).use { it.write(bytes) }
            androidx.core.content.FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        } catch (e: Exception) {
            null
        }
    }
}

@Composable
fun DomuxAttachmentPreview(
    mediaUrl: String?,
    mediaType: String?,
    fileName: String = "Archivo adjunto",
    onMessage: (String) -> Unit = {}
) {
    if (mediaUrl.isNullOrBlank()) return

    val context = LocalContext.current
    var showExpanded by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    var isDownloading by remember { mutableStateOf(false) }
    val isImage = mediaType?.lowercase() == "image" || mediaUrl.startsWith("data:image/") || mediaUrl.endsWith(".jpg", true) || mediaUrl.endsWith(".png", true)

    val decodedBytes by androidx.compose.runtime.produceState<ByteArray?>(initialValue = null, key1 = mediaUrl) {
        if (mediaUrl.startsWith("data:")) {
            value = withContext(Dispatchers.IO) {
                try {
                    val base64 = mediaUrl.substringAfter("base64,")
                        .replace("\\s".toRegex(), "")
                    Base64.decode(base64, Base64.DEFAULT)
                } catch (e: Exception) {
                    null
                }
            }
        }
    }
    
    val imageModel = decodedBytes ?: if (mediaUrl.startsWith("/")) "https://domux.onrender.com$mediaUrl" else mediaUrl

    if (isImage) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .height(160.dp)
                .clickable { showExpanded = true },
            shape = RoundedCornerShape(16.dp),
            color = Color(0xFF0F1E33),
            border = BorderStroke(1.dp, Color(0xFF1E334D))
        ) {
            Box(modifier = Modifier.fillMaxSize()) {
                AsyncImage(
                    model = ImageRequest.Builder(context)
                        .data(imageModel)
                        .crossfade(true)
                        .build(),
                    contentDescription = "Miniatura de archivo adjunto",
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxSize()
                )
                Surface(
                    modifier = Modifier.align(Alignment.BottomEnd).padding(8.dp),
                    shape = RoundedCornerShape(50),
                    color = Color(0x80000000)
                ) {
                    Text("🔍 Tocar para ampliar", modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp), color = Color.White, style = MaterialTheme.typography.labelSmall)
                }
            }
        }
        
        if (showExpanded) {
            Dialog(
                onDismissRequest = { showExpanded = false },
                properties = DialogProperties(usePlatformDefaultWidth = false)
            ) {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = Color.Black
                ) {
                    Box(modifier = Modifier.fillMaxSize()) {
                        AsyncImage(
                            model = ImageRequest.Builder(context)
                                .data(imageModel)
                                .crossfade(true)
                                .build(),
                            contentDescription = "Archivo adjunto ampliado",
                            contentScale = ContentScale.Fit,
                            modifier = Modifier.fillMaxSize()
                        )
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(16.dp)
                                .align(Alignment.TopCenter),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Surface(
                                shape = RoundedCornerShape(50),
                                color = Color(0x80000000),
                                modifier = Modifier.clickable { showExpanded = false }
                            ) {
                                Text("✕ Cerrar", modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp), color = Color.White)
                            }
                            if (decodedBytes != null) {
                                Surface(
                                    shape = RoundedCornerShape(50),
                                    color = Color(0xFF10B981),
                                    modifier = Modifier.clickable {
                                        if (isDownloading) return@clickable
                                        isDownloading = true
                                        scope.launch(Dispatchers.IO) {
                                            try {
                                                val uri = saveBytesToDownloads(
                                                    context, 
                                                    fileName.ifBlank { "imagen_adjunta.jpg" },
                                                    "image/jpeg",
                                                    decodedBytes!!
                                                )
                                                withContext(Dispatchers.Main) {
                                                    if (uri != null) {
                                                        onMessage("Guardado en Descargas: $fileName")
                                                    } else {
                                                        onMessage("Error al guardar el archivo.")
                                                    }
                                                    isDownloading = false
                                                }
                                            } catch (e: Exception) {
                                                withContext(Dispatchers.Main) {
                                                    onMessage("Error al descargar: ${e.message}")
                                                    isDownloading = false
                                                }
                                            }
                                        }
                                    }
                                ) {
                                    Text(if (isDownloading) "Guardando..." else "⬇ Descargar", modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp), color = Color.White)
                                }
                            } else if (!mediaUrl.startsWith("data:")) {
                                Surface(
                                    shape = RoundedCornerShape(50),
                                    color = Color(0xFF3B82F6),
                                    modifier = Modifier.clickable {
                                        val intent = android.content.Intent(android.content.Intent.ACTION_VIEW).apply {
                                            data = android.net.Uri.parse(if (mediaUrl.startsWith("/")) "https://domux.onrender.com$mediaUrl" else mediaUrl)
                                        }
                                        try {
                                            context.startActivity(intent)
                                        } catch (e: Exception) {
                                            onMessage("No se pudo abrir el enlace.")
                                        }
                                    }
                                ) {
                                    Text("🔗 Abrir", modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp), color = Color.White)
                                }
                            }
                        }
                    }
                }
            }
        }
    } else {
        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(16.dp),
            color = Color(0xFF0F1E33),
            border = BorderStroke(1.dp, Color(0xFF1E334D))
        ) {
            Row(
                modifier = Modifier.padding(16.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Surface(
                    color = Color(0xFF152C4A),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Text(
                        when (mediaType?.lowercase()) {
                            "video" -> "▶"
                            "audio" -> "♫"
                            else -> "📄"
                        },
                        modifier = Modifier.padding(12.dp),
                        fontSize = 24.sp
                    )
                }
                Column(modifier = Modifier.weight(1f)) {
                    Text(fileName.ifBlank { "Archivo adjunto" }, fontWeight = FontWeight.SemiBold)
                    Text(mediaType?.uppercase() ?: "DOCUMENTO", color = Color(0xFF94A3B8), style = MaterialTheme.typography.bodySmall)
                }
                if (decodedBytes != null) {
                    Button(
                        enabled = !isDownloading,
                        onClick = {
                            isDownloading = true
                            scope.launch(Dispatchers.IO) {
                                try {
                                    val mime = if (mediaUrl.startsWith("data:")) mediaUrl.substringAfter("data:").substringBefore(";") else "*/*"
                                    val uri = saveBytesToDownloads(
                                        context, 
                                        fileName.ifBlank { "archivo_adjunto" },
                                        mime,
                                        decodedBytes!!
                                    )
                                    withContext(Dispatchers.Main) {
                                        if (uri != null) {
                                            onMessage("Guardado en Descargas: $fileName")
                                            val intent = android.content.Intent(android.content.Intent.ACTION_VIEW).apply {
                                                setDataAndType(uri, mime)
                                                addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION)
                                            }
                                            try {
                                                context.startActivity(android.content.Intent.createChooser(intent, "Abrir archivo"))
                                            } catch (e: Exception) {
                                                // ignore
                                            }
                                        } else {
                                            onMessage("Error al guardar el archivo.")
                                        }
                                        isDownloading = false
                                    }
                                } catch (e: Exception) {
                                    withContext(Dispatchers.Main) {
                                        onMessage("Error al descargar: ${e.message}")
                                        isDownloading = false
                                    }
                                }
                            }
                        }
                    ) {
                        Text(if (isDownloading) "..." else "Descargar")
                    }
                }
            }
        }
    }
}
