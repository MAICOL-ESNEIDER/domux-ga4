package com.dracknoval.domux

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.dracknoval.domux.data.SearchResult
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.ui.theme.DomuxColor

/**
 * El buscador general (HU-089), para la administración y la portería: una caja, el filtro «Buscar
 * en» y los resultados agrupados por tipo. Al tocar un resultado se abre la pantalla donde se ve
 * (ver [searchResultRoute]). La pantalla solo dibuja lo que le da [SearchViewModel].
 */
@Composable
fun SearchScreen(navController: NavController, viewModel: SearchViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()
    val focusRequester = remember { FocusRequester() }
    val focusManager = LocalFocusManager.current

    DomuxScreenScaffold(title = "Buscar", navController = navController, showQuickActions = false) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            // Al abrir, el cursor ya está en la caja: se escribe de una vez. Va aquí, junto a la caja,
            // porque el contenido del andamio se arma después y antes la caja todavía no existe.
            LaunchedEffect(Unit) {
                try {
                    focusRequester.requestFocus()
                } catch (exception: IllegalStateException) {
                    // Si la caja aún no está lista, la persona la toca: no pasa nada más.
                }
            }
            OutlinedTextField(
                value = state.text,
                onValueChange = viewModel::setText,
                label = { Text("Buscar") },
                placeholder = {
                    Text(
                        if (Session.isGuard) "Residente, apartamento, placa, paquete o visita"
                        else "Persona, apartamento, placa, radicado...",
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                },
                singleLine = true,
                leadingIcon = { Icon(painterResource(R.drawable.ic_search), contentDescription = null) },
                trailingIcon = {
                    if (state.text.isNotEmpty()) {
                        IconButton(onClick = {
                            viewModel.clear()
                            focusRequester.requestFocus()
                        }) {
                            Icon(painterResource(R.drawable.ic_close), contentDescription = "Borrar lo escrito")
                        }
                    }
                },
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = {
                    viewModel.searchNow()
                    // Se guarda el teclado para que los resultados se vean completos.
                    focusManager.clearFocus()
                }),
                modifier = Modifier
                    .fillMaxWidth()
                    .focusRequester(focusRequester)
            )

            Text(
                "Buscar en",
                style = MaterialTheme.typography.labelMedium,
                color = DomuxColor.TextMuted,
                modifier = Modifier.semantics { heading() }
            )
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                state.places.forEach { place ->
                    FilterChip(
                        selected = state.place == place.value,
                        onClick = { viewModel.setPlace(place.value) },
                        label = { Text(place.label) }
                    )
                }
            }

            DomuxMessageBanner(state.message, state.messageIsError) { viewModel.dismissMessage() }
            if (state.loading) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())

            val hint = when {
                state.text.isBlank() -> "Escribe lo que buscas y elige dónde con «Buscar en»."
                state.tooShort -> "Escribe al menos ${SearchViewModel.MIN_CHARS} letras para buscar."
                state.searched && state.groups.isEmpty() ->
                    "No se encontró nada para «${state.searchedText}». Una placa necesita al menos 3 caracteres."
                else -> null
            }
            if (hint != null) {
                Text(hint, color = DomuxColor.TextMuted)
            }

            LazyColumn(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                state.groups.forEach { group ->
                    val shown = group.items.orEmpty()
                    item(key = "group-${group.type}") {
                        Text(
                            "${group.label} (${shown.size}${if (group.more == true) " o más" else ""})",
                            style = MaterialTheme.typography.titleSmall,
                            color = DomuxColor.TextMuted,
                            modifier = Modifier
                                .padding(top = 6.dp)
                                .semantics { heading() }
                        )
                    }
                    items(shown, key = { "${group.type}-${it.kind.orEmpty()}-${it.id}" }) { result ->
                        val route = searchResultRoute(result)
                        SearchResultCard(
                            result,
                            onOpen = if (route != null) ({ navController.navigate(route) }) else null
                        )
                    }
                    if (group.more == true) {
                        item(key = "more-${group.type}") {
                            Text(
                                if (state.place == "todo") "Hay más. Elige «${group.label}» en «Buscar en» para verlos todos."
                                else "Hay más. Escribe más letras para acotar la búsqueda.",
                                color = DomuxColor.TextMuted,
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                    }
                }
            }
        }
    }
}

/** Un resultado: lo que es y su detalle. Si [onOpen] es null, solo se lee. */
@Composable
private fun SearchResultCard(result: SearchResult, onOpen: (() -> Unit)?) {
    val open = if (onOpen != null) Modifier.clickable(onClickLabel = "abrir", role = Role.Button, onClick = onOpen) else Modifier
    DomuxCard(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 48.dp)
            .then(open)
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(2.dp)
        ) {
            Text(result.title, style = MaterialTheme.typography.titleSmall, maxLines = 2, overflow = TextOverflow.Ellipsis)
            result.subtitle?.takeIf { it.isNotBlank() }?.let {
                Text(it, color = DomuxColor.TextMuted, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
