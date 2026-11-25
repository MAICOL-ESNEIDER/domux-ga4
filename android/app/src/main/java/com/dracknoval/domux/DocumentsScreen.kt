package com.dracknoval.domux

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.dracknoval.domux.data.DocumentOption
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.UnitDocument
import com.dracknoval.domux.ui.theme.DomuxColor
import java.util.Locale
import kotlin.math.roundToInt

/**
 * Documentos de la unidad (DEC-032): el manual de convivencia, las reglas, los presupuestos aprobados, los
 * históricos de gastos y las actas. Cada persona ve solo los que la administración le marcó; se tocan y se
 * leen dentro de la app, sin guardar nada en el celular. La administración los sube en la web, y aquí los
 * ve todos con a quién se los muestra. La pantalla solo dibuja lo que le da [DocumentsViewModel].
 */
@Composable
fun DocumentsScreen(navController: NavController, viewModel: DocumentsViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()
    val groups = groupDocuments(state.documents, state.categories)
    val audienceNames = state.audiences.associate { it.key to it.label }

    DomuxScreenScaffold(title = "Documentos de la unidad", navController = navController) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            if (state.message.isNotBlank()) {
                DomuxMessageBanner(state.message, state.messageIsError) { viewModel.dismissMessage() }
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    if (state.documents.isNotEmpty()) documentCountText(state.documents.size) else "",
                    style = MaterialTheme.typography.bodySmall
                )
                TextButton(onClick = { viewModel.refresh() }) { Text("Actualizar") }
            }
            if (state.loading) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
            LazyColumn(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                if (state.documents.isEmpty() && !state.loading) {
                    item {
                        Text(
                            if (Session.isAdmin) {
                                "Todavía no hay documentos. Súbelos desde la web de administración, en «Documentos de la unidad»."
                            } else {
                                "La administración todavía no ha publicado documentos para ti."
                            }
                        )
                    }
                }
                groups.forEach { (label, documents) ->
                    item(key = "group-$label") {
                        Text(
                            label,
                            style = MaterialTheme.typography.titleSmall,
                            color = DomuxColor.TextMuted,
                            modifier = Modifier
                                .padding(top = 6.dp)
                                .semantics { heading() }
                        )
                    }
                    items(documents, key = { "document-${it.id}" }) { document ->
                        DocumentCard(
                            document = document,
                            audienceNames = audienceNames,
                            opening = state.opening == document.id,
                            enabled = state.opening == null,
                            onOpen = { viewModel.open(document) }
                        )
                    }
                }
            }
        }
    }

    state.viewer?.let { opened ->
        AttachmentViewerDialog(opened.dataUrl, opened.mediaType, opened.title) { viewModel.closeViewer() }
    }
}

@Composable
private fun DocumentCard(
    document: UnitDocument,
    audienceNames: Map<String, String>,
    opening: Boolean,
    enabled: Boolean,
    onOpen: () -> Unit
) {
    val isPdf = document.kind == "pdf"
    val details = listOfNotNull(
        if (isPdf) "PDF" else "Imagen",
        fileSizeText(document.sizeBytes),
        document.createdAt?.takeIf { it.isNotBlank() }?.let { "Publicado el ${humanDate(it)}" }
    ).filter { it.isNotBlank() }.joinToString(" · ")
    DomuxCard(
        Modifier
            .fillMaxWidth()
            .clickable(enabled = enabled, role = Role.Button, onClickLabel = "Abrir ${document.title}", onClick = onOpen)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 64.dp)
                .padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Icon(
                painterResource(if (isPdf) R.drawable.ic_description else R.drawable.ic_image),
                contentDescription = null,
                tint = DomuxColor.Primary,
                modifier = Modifier.size(28.dp)
            )
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(document.title, style = MaterialTheme.typography.titleMedium)
                document.description?.takeIf { it.isNotBlank() }?.let {
                    Text(it, style = MaterialTheme.typography.bodyMedium)
                }
                Text(details, style = MaterialTheme.typography.bodySmall, color = DomuxColor.TextMuted)
                // Solo la administración sabe a quién se lo muestra (los demás no reciben ese dato).
                document.visibleTo?.let { audiences ->
                    Text(
                        if (audiences.isEmpty()) {
                            "Solo la administración lo ve"
                        } else {
                            "Lo ven: " + audiences.joinToString(", ") { audienceNames[it] ?: it }
                        },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.secondary
                    )
                }
            }
            if (opening) {
                CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp)
            }
        }
    }
}

/**
 * Los documentos agrupados por tipo, en el orden de los tipos que manda el servidor (el manual de
 * convivencia primero y «Otros» al final). Dentro de cada tipo siguen los más nuevos primero.
 */
internal fun groupDocuments(
    documents: List<UnitDocument>,
    categories: List<DocumentOption>
): List<Pair<String, List<UnitDocument>>> {
    val order = categories.map { it.key }
    return documents
        .groupBy { it.category ?: "otro" }
        .toList()
        .sortedBy { (key, _) -> order.indexOf(key).let { if (it < 0) Int.MAX_VALUE else it } }
        .map { (key, items) ->
            (categories.firstOrNull { it.key == key }?.label ?: items.first().categoryLabel ?: "Otros") to items
        }
}

/** «1 documento» o «3 documentos». */
internal fun documentCountText(count: Int): String = if (count == 1) "1 documento" else "$count documentos"

/** El tamaño de un archivo con palabras: «340 KB» o «1,2 MB». */
internal fun fileSizeText(bytes: Int): String {
    if (bytes <= 0) return ""
    if (bytes < 1024 * 1024) return "${(bytes / 1024.0).roundToInt().coerceAtLeast(1)} KB"
    return String.format(Locale.forLanguageTag("es-CO"), "%.1f MB", bytes / (1024.0 * 1024.0))
}
