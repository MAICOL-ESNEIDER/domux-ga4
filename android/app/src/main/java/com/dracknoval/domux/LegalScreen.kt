package com.dracknoval.domux

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.dracknoval.domux.data.LegalBlock
import com.dracknoval.domux.data.LegalDocument
import com.dracknoval.domux.data.LegalDocumentSummary
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.ui.theme.DomuxColor

/**
 * Documentos legales: política de datos, términos, cookies y los demás. Con [slug] vacío muestra la
 * lista y con el nombre de un documento muestra su texto. Son públicos: se abren desde el inicio de
 * sesión (sin el menú de abajo, porque todavía no hay sesión) y desde «Más» o «Mi hogar» (con el
 * menú de siempre). La pantalla solo dibuja: los datos están en [LegalViewModel].
 */
@Composable
fun LegalScreen(navController: NavController, slug: String, viewModel: LegalViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()
    LaunchedEffect(slug) { viewModel.start(slug) }
    // Sin sesión el menú de abajo llevaría a pantallas que piden iniciar sesión, así que no se dibuja.
    val signedIn = !Session.token.isNullOrBlank()
    val document = state.document

    DomuxScreenScaffold(title = "Legal y privacidad", navController = navController, showMenu = signedIn) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 18.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            DomuxMessageBanner(state.message, state.messageIsError) { viewModel.dismissMessage() }
            when {
                state.loading -> CircularProgressIndicator()
                slug.isEmpty() && state.documents.isNotEmpty() -> LegalList(state.documents) { opened ->
                    navController.navigate("legal?slug=${opened.slug}")
                }
                slug.isNotEmpty() && document != null -> LegalReader(document)
                else -> OutlinedButton(
                    onClick = { viewModel.load() },
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 48.dp)
                ) {
                    Text("Reintentar")
                }
            }
        }
    }
}

/** La lista de documentos: cada uno con su estado («Vigente» o «En preparación») y lo que dice de él. */
@Composable
private fun LegalList(documents: List<LegalDocumentSummary>, onOpen: (LegalDocumentSummary) -> Unit) {
    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Text(
            "Estos documentos explican cómo se cuidan tus datos y las reglas para usar DOMUX.",
            color = DomuxColor.TextMuted,
            style = MaterialTheme.typography.bodyMedium
        )
        documents.forEach { document ->
            DomuxCard(Modifier.fillMaxWidth().clickable(role = Role.Button) { onOpen(document) }) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(document.title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                        LegalStatusBadge(document.status)
                    }
                    Text(document.summary)
                    val version = versionLine(document.version, document.effectiveFrom)
                    if (version.isNotEmpty()) {
                        Text(version, color = DomuxColor.TextMuted, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
    }
}

/** El texto de un documento: su título, su estado y luego sus títulos, párrafos y listas en orden. */
@Composable
private fun LegalReader(document: LegalDocument) {
    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Text(
            document.title,
            style = MaterialTheme.typography.titleLarge,
            modifier = Modifier.semantics { heading() }
        )
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            LegalStatusBadge(document.status)
            val version = versionLine(document.version, document.effectiveFrom)
            if (version.isNotEmpty()) {
                Text(version, color = DomuxColor.TextMuted, style = MaterialTheme.typography.bodySmall)
            }
        }
        Text(document.summary, color = DomuxColor.TextSoft)
        document.blocks.orEmpty().forEach { block -> LegalBlockText(block) }
    }
}

/** Dibuja un trozo del texto según su clase: título, párrafo o lista (con viñetas o numerada). */
@Composable
private fun LegalBlockText(block: LegalBlock) {
    when (block.type) {
        "heading" -> Text(
            block.text.orEmpty(),
            style = if ((block.level ?: 2) >= 3) MaterialTheme.typography.titleSmall else MaterialTheme.typography.titleMedium,
            modifier = Modifier
                .padding(top = 8.dp)
                .semantics { heading() }
        )
        "paragraph" -> Text(block.text.orEmpty())
        "list" -> Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            block.items.orEmpty().forEachIndexed { index, item ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(if (block.ordered == true) "${index + 1}." else "•")
                    Text(item, modifier = Modifier.weight(1f))
                }
            }
        }
        // Una clase de bloque que esta versión de la app no conoce se omite, en vez de romper la pantalla.
        else -> Unit
    }
}

/** «Vigente» (ya rige) o «En preparación» (todavía no tiene su texto final). */
@Composable
private fun LegalStatusBadge(status: String) {
    if (status == "vigente") {
        DomuxStatusBadge("Vigente", DomuxBadgeTone.SUCCESS)
    } else {
        DomuxStatusBadge("En preparación", DomuxBadgeTone.PROGRESS)
    }
}

/** «Versión 1.0 · desde 01/12/2026»; queda vacío mientras el documento no tiene una versión publicada. */
private fun versionLine(version: String?, effectiveFrom: String?): String =
    listOfNotNull(
        version?.takeIf { it.isNotBlank() }?.let { "Versión $it" },
        effectiveFrom?.takeIf { it.isNotBlank() }?.let { "desde ${humanDate(it)}" }
    ).joinToString(" · ")
