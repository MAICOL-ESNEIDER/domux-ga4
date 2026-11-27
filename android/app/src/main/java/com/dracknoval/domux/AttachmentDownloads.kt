// AttachmentDownloads.kt — el permiso de descarga de un adjunto. Quien sube un archivo decide si
// los demás lo pueden guardar; sin ese permiso el archivo solo se ve dentro de la app.

package com.dracknoval.domux

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.dracknoval.domux.ui.theme.DomuxColor
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Lo que la persona marcó al adjuntar: si permite que los demás descarguen ese archivo. El botón
 * de adjuntar lo anota aquí y quien arma el envío al servidor lo recoge con [take]. Solo vive en
 * memoria mientras se envía; guarda como mucho los últimos adjuntos elegidos.
 */
object DownloadPermissions {
    private const val MAX_ENTRIES = 4
    private val allowed = LinkedHashSet<String>()

    @Synchronized
    fun set(mediaUrl: String, allow: Boolean) {
        allowed.remove(mediaUrl)
        if (!allow) return
        allowed.add(mediaUrl)
        while (allowed.size > MAX_ENTRIES) allowed.remove(allowed.first())
    }

    /** True si la persona permitió descargar [mediaUrl]; lo olvida al entregarlo. */
    @Synchronized
    fun take(mediaUrl: String?): Boolean = mediaUrl != null && allowed.remove(mediaUrl)
}

/** La casilla con la que quien adjunta decide si los demás pueden descargar el archivo. */
@Composable
fun DownloadPermissionCheckbox(checked: Boolean, onChange: (Boolean) -> Unit) {
    Column {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier
                .heightIn(min = 48.dp)
                .toggleable(value = checked, role = Role.Checkbox, onValueChange = onChange)
        ) {
            Checkbox(checked = checked, onCheckedChange = null)
            Text("Permitir que quien lo reciba lo descargue", style = MaterialTheme.typography.bodyMedium)
        }
        Text(
            "Si no lo marcas, el archivo solo se puede ver. Tú decides y respondes por lo que compartes.",
            style = MaterialTheme.typography.bodySmall,
            color = DomuxColor.TextMuted
        )
    }
}

/**
 * Botón «Guardar en el celular». Abre el selector de Android para que la persona elija dónde
 * guardar el archivo; la app no necesita permiso de almacenamiento ni guarda copias por su cuenta.
 */
@Composable
fun SaveAttachmentButton(dataUrl: String) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var notice by remember(dataUrl) { mutableStateOf("") }
    var failed by remember(dataUrl) { mutableStateOf(false) }
    var saving by remember(dataUrl) { mutableStateOf(false) }
    val mimeType = remember(dataUrl) {
        dataUrl.substringAfter("data:", "").substringBefore(';').substringBefore(',').trim().lowercase()
            .ifEmpty { "application/octet-stream" }
    }
    val createFile = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument(mimeType)) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        saving = true
        scope.launch {
            try {
                val saved = withContext(Dispatchers.IO) {
                    val media = decodeDataUrl(dataUrl) ?: return@withContext false
                    val output = context.contentResolver.openOutputStream(uri) ?: return@withContext false
                    output.use { it.write(media.bytes) }
                    true
                }
                failed = !saved
                notice = if (saved) "Archivo guardado." else "No se pudo guardar el archivo."
            } catch (exception: CancellationException) {
                throw exception
            } catch (exception: Exception) {
                failed = true
                notice = "No se pudo guardar el archivo."
            } finally {
                saving = false
            }
        }
    }
    Column {
        TextButton(
            enabled = !saving,
            onClick = {
                notice = ""
                try {
                    createFile.launch("DOMUX-adjunto." + extensionFor(mimeType))
                } catch (exception: Exception) {
                    failed = true
                    notice = "Este celular no tiene una app para elegir dónde guardar."
                }
            },
            modifier = Modifier.heightIn(min = 48.dp)
        ) { Text(if (saving) "Guardando..." else "Guardar en el celular") }
        if (notice.isNotBlank()) {
            Text(
                notice,
                style = MaterialTheme.typography.bodySmall,
                color = if (failed) MaterialTheme.colorScheme.error else DomuxColor.Ok
            )
        }
    }
}
