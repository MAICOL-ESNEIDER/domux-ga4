package com.dracknoval.domux

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.dracknoval.domux.data.ExcelFileResponse
import com.dracknoval.domux.data.RetrofitClient
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private const val XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

/** Lo que necesita la tarjeta de respaldo legal para dibujarse. */
data class LegalBackupUiState(
    val busy: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false,
    // Archivo que el servidor acaba de entregar; la tarjeta lo guarda en Descargas y avisa.
    val pendingFile: ExcelFileResponse? = null,
    val pendingNotice: String = "",
    // Sube cada vez que se archiva el historial, para que la pantalla vuelva a cargar su lista.
    val archivedRuns: Int = 0
)

/**
 * ViewModel del respaldo legal en Excel (solo la administración): descarga el reporte legal y
 * archiva el historial finalizado. Lo comparten las pantallas de PQRS y de Reservas.
 */
class LegalBackupViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(LegalBackupUiState())
    val state: StateFlow<LegalBackupUiState> = _state.asStateFlow()

    override fun postMessage(text: String, isError: Boolean) {
        _state.update { it.copy(message = text, messageIsError = isError) }
    }

    override fun setBusy(busy: Boolean) {
        _state.update { it.copy(busy = busy) }
    }

    fun dismissMessage() {
        _state.update { it.copy(message = "") }
    }

    fun exportLegalReport() {
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudo generar el reporte legal") { api.exportLegalReport(auth()) }
            } ?: return@launch
            val file = response.body()
            if (file == null) {
                showError("El servidor devolvió un reporte vacío.")
                return@launch
            }
            _state.update {
                it.copy(
                    pendingFile = file,
                    pendingNotice = "Reporte legal guardado exitosamente en Descargas/${file.fileName}."
                )
            }
        }
    }

    fun archiveHistory() {
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudo archivar el historial") { api.archiveHistory(auth()) }
            } ?: return@launch
            val file = response.body()
            if (file == null) {
                showError("El servidor devolvió un archivo vacío.")
                return@launch
            }
            _state.update {
                it.copy(
                    archivedRuns = it.archivedRuns + 1,
                    pendingFile = file,
                    pendingNotice = "${file.message ?: "Historial archivado."} Archivo guardado en Descargas/${file.fileName}."
                )
            }
        }
    }

    /** La tarjeta ya intentó guardar el archivo: [error] dice por qué falló, o es null si salió bien. */
    fun fileSaved(error: String?) {
        val notice = _state.value.pendingNotice
        _state.update { it.copy(pendingFile = null, pendingNotice = "") }
        if (error == null) showSuccess(notice) else showError(error)
    }
}

/**
 * Tarjeta de «Respaldo Legal y Archivo Excel» de la administración. [archiveLabel] y
 * [archiveMessage] dicen qué se archiva en cada pantalla; [onArchived] avisa a la pantalla para
 * que vuelva a cargar su lista cuando el archivo ya se guardó.
 */
@Composable
fun LegalBackupCard(
    archiveLabel: String,
    archiveMessage: String,
    includeArchived: Boolean,
    onToggleArchived: () -> Unit,
    onArchived: () -> Unit,
    viewModel: LegalBackupViewModel = viewModel()
) {
    val state by viewModel.state.collectAsState()
    val context = LocalContext.current
    var confirmArchive by remember { mutableStateOf(false) }

    LaunchedEffect(state.pendingFile) {
        val file = state.pendingFile ?: return@LaunchedEffect
        val error: String? = try {
            // Decodificar y escribir el Excel puede tardar: se hace fuera del hilo de la pantalla.
            withContext(Dispatchers.IO) {
                saveBase64FileToDownloads(context, file.fileName, file.base64, file.mimeType ?: XLSX_MIME)
            }
            null
        } catch (exception: CancellationException) {
            throw exception
        } catch (exception: Exception) {
            "No se pudo guardar el archivo: ${exception.message}"
        }
        viewModel.fileSaved(error)
    }
    // Cada vez que se archiva, la pantalla vuelve a cargar su lista una sola vez.
    var handledRuns by rememberSaveable { mutableStateOf(state.archivedRuns) }
    LaunchedEffect(state.archivedRuns) {
        if (state.archivedRuns != handledRuns) {
            handledRuns = state.archivedRuns
            onArchived()
        }
    }

    DomuxCard(Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Text("Respaldo Legal y Archivo Excel", style = MaterialTheme.typography.titleSmall)
            if (state.message.isNotBlank()) {
                DomuxMessageBanner(state.message, state.messageIsError) { viewModel.dismissMessage() }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(
                    enabled = !state.busy,
                    onClick = { viewModel.exportLegalReport() },
                    modifier = Modifier.weight(1f)
                ) { Text("Descargar Excel Legal") }
                OutlinedButton(
                    enabled = !state.busy,
                    onClick = { confirmArchive = true },
                    modifier = Modifier.weight(1f)
                ) { Text(archiveLabel) }
            }
            FilterChip(
                selected = includeArchived,
                onClick = onToggleArchived,
                label = { Text("Ver archivadas") }
            )
        }
    }

    if (confirmArchive) {
        DomuxConfirmDialog(
            title = "Archivar y limpiar historial",
            message = archiveMessage,
            confirmLabel = "Archivar y descargar",
            onConfirm = {
                confirmArchive = false
                viewModel.archiveHistory()
            },
            onDismiss = { confirmArchive = false }
        )
    }
}
