package com.dracknoval.domux

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.dracknoval.domux.ui.theme.DomuxColor
import kotlinx.coroutines.launch

/** Un filtro que está puesto: cómo se lee («Estado: Abiertas») y qué hacer para quitarlo. */
class DomuxActiveFilter(val label: String, val onRemove: () -> Unit)

/**
 * El buscador de una lista con el botón «Filtros» al lado. Los filtros no ocupan la pantalla: se
 * abren en una hoja desde abajo al tocar el botón. Para que nadie olvide que la lista está
 * filtrada, el botón dice cuántos filtros hay puestos y debajo sale cada uno, con su «quitar».
 *
 * Con [search] en null la lista no tiene buscador y solo sale el botón. [filters] es lo que va
 * dentro de la hoja: se arma con [DomuxFilterGroup] y [DomuxFilterOption].
 */
@Composable
fun DomuxSearchFilterBar(
    active: List<DomuxActiveFilter>,
    onClearFilters: () -> Unit,
    modifier: Modifier = Modifier,
    search: String? = null,
    onSearch: (String) -> Unit = {},
    searchLabel: String = "Buscar",
    searchHint: String = "",
    sheetTitle: String = "Filtros",
    filters: @Composable ColumnScope.() -> Unit
) {
    var open by rememberSaveable { mutableStateOf(false) }
    Column(modifier = modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            // El campo de texto deja un espacio arriba para su etiqueta: se alinean por abajo.
            verticalAlignment = Alignment.Bottom
        ) {
            if (search != null) {
                OutlinedTextField(
                    value = search,
                    onValueChange = onSearch,
                    label = { Text(searchLabel, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                    placeholder = { Text(searchHint, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                    modifier = Modifier.weight(1f)
                )
            }
            DomuxFilterButton(active.size, onClick = { open = true })
        }
        DomuxActiveFilterRow(active, onClearFilters)
    }
    if (open) {
        DomuxFilterSheet(
            title = sheetTitle,
            activeCount = active.size,
            onClear = onClearFilters,
            onClose = { open = false },
            content = filters
        )
    }
}

/** El botón «Filtros»; cuando hay filtros puestos se resalta y dice cuántos son. */
@Composable
fun DomuxFilterButton(activeCount: Int, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val on = activeCount > 0
    OutlinedButton(
        onClick = onClick,
        modifier = modifier
            .height(56.dp)
            .semantics {
                stateDescription = when (activeCount) {
                    0 -> "Sin filtros puestos"
                    1 -> "1 filtro puesto"
                    else -> "$activeCount filtros puestos"
                }
            },
        shape = RoundedCornerShape(12.dp),
        contentPadding = PaddingValues(horizontal = 14.dp),
        border = BorderStroke(1.dp, if (on) DomuxColor.Primary else DomuxColor.FieldBorder),
        colors = ButtonDefaults.outlinedButtonColors(
            containerColor = if (on) DomuxColor.Selected else Color.Transparent,
            contentColor = if (on) DomuxColor.Primary else DomuxColor.Text
        )
    ) {
        Icon(painterResource(R.drawable.ic_filter), contentDescription = null, modifier = Modifier.size(18.dp))
        Spacer(Modifier.width(6.dp))
        Text(if (on) "Filtros · $activeCount" else "Filtros")
    }
}

/** Los filtros que están puestos, cada uno con su «quitar», y «Quitar filtros» para todos. */
@Composable
fun DomuxActiveFilterRow(active: List<DomuxActiveFilter>, onClearFilters: () -> Unit) {
    if (active.isEmpty()) return
    Row(
        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        active.forEach { filter ->
            FilterChip(
                selected = true,
                onClick = filter.onRemove,
                label = { Text(filter.label) },
                trailingIcon = {
                    Icon(
                        painterResource(R.drawable.ic_close),
                        contentDescription = "Quitar este filtro",
                        modifier = Modifier.size(16.dp)
                    )
                }
            )
        }
        if (active.size > 1) {
            TextButton(onClick = onClearFilters) { Text("Quitar filtros") }
        }
    }
}

/**
 * La hoja con las opciones de filtro. Cada cambio se aplica de una vez a la lista; «Ver
 * resultados» solo cierra la hoja.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DomuxFilterSheet(
    title: String,
    activeCount: Int,
    onClear: () -> Unit,
    onClose: () -> Unit,
    content: @Composable ColumnScope.() -> Unit
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val scope = rememberCoroutineScope()
    ModalBottomSheet(
        onDismissRequest = onClose,
        sheetState = sheetState,
        containerColor = DomuxColor.Surface,
        contentColor = DomuxColor.Text
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(start = 20.dp, end = 20.dp, bottom = 20.dp)
                .imePadding(),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            Text(
                title,
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.semantics { heading() }
            )
            content()
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(
                    onClick = onClear,
                    enabled = activeCount > 0,
                    modifier = Modifier.weight(1f).heightIn(min = 48.dp)
                ) { Text("Quitar filtros") }
                Button(
                    onClick = {
                        // Se esconde con su animación y después se quita de la pantalla.
                        scope.launch { sheetState.hide() }.invokeOnCompletion {
                            if (!sheetState.isVisible) onClose()
                        }
                    },
                    modifier = Modifier.weight(1f).heightIn(min = 48.dp)
                ) { Text("Ver resultados") }
            }
        }
    }
}

/** Un grupo de opciones dentro de la hoja de filtros, con su título («Estado», «Categoría»…). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun DomuxFilterGroup(title: String, content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(title, style = MaterialTheme.typography.labelLarge, color = DomuxColor.TextSoft)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) { content() }
    }
}

/** Una opción de un grupo de filtros; la elegida queda resaltada. */
@Composable
fun DomuxFilterOption(label: String, selected: Boolean, onClick: () -> Unit) {
    FilterChip(selected = selected, onClick = onClick, label = { Text(label) })
}
