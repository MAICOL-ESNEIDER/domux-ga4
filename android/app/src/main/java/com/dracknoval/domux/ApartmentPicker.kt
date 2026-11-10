package com.dracknoval.domux

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.dracknoval.domux.data.ApartmentData
import com.dracknoval.domux.data.ApartmentOption
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.TowerData
import com.dracknoval.domux.data.mensajeDeError
import com.dracknoval.domux.data.toOption
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay

/**
 * Selector de apartamento (HU-017). Un residente, un parqueadero o un cuarto útil se vinculan a un
 * apartamento que ya existe en la estructura de la unidad: no se escribe a mano. Al tocarlo se
 * abre una ventana donde se elige la torre, se busca por código y se toca el apartamento.
 *
 * [selected] es el apartamento elegido (o null si todavía no hay). Con [allowClear] aparece un
 * botón para quitarlo (por ejemplo, para dejar un parqueadero sin asignar). [errorText] se muestra
 * en rojo debajo del botón cuando quien lo usa detecta que falta elegir uno.
 */
@Composable
fun ApartmentPickerField(
    label: String,
    selected: ApartmentOption?,
    onSelect: (ApartmentOption?) -> Unit,
    allowClear: Boolean = false,
    errorText: String? = null
) {
    var open by remember { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        OutlinedButton(
            onClick = { open = true },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(if (selected == null) label else "$label: ${selected.label}")
        }
        if (allowClear && selected != null) {
            TextButton(onClick = { onSelect(null) }) { Text("Quitar apartamento") }
        }
        if (errorText != null) {
            Text(
                errorText,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall
            )
        }
    }
    if (open) {
        ApartmentPickerDialog(
            onPick = {
                onSelect(it)
                open = false
            },
            onDismiss = { open = false }
        )
    }
}

@Composable
private fun ApartmentPickerDialog(
    onPick: (ApartmentOption) -> Unit,
    onDismiss: () -> Unit
) {
    var towers by remember { mutableStateOf<List<TowerData>>(emptyList()) }
    var towersLoaded by remember { mutableStateOf(false) }
    var towerId by remember { mutableStateOf<Int?>(null) }
    var search by remember { mutableStateOf("") }
    var page by remember { mutableIntStateOf(1) }
    var totalPages by remember { mutableIntStateOf(1) }
    var apartments by remember { mutableStateOf<List<ApartmentData>>(emptyList()) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    // Primero se traen las torres; la primera queda elegida para que ya salgan apartamentos.
    LaunchedEffect(Unit) {
        try {
            val response = RetrofitClient.structureApi.getTowers(Session.bearer())
            if (response.isSuccessful) {
                towers = response.body()?.towers.orEmpty()
                towerId = towers.firstOrNull()?.id
            } else {
                error = mensajeDeError(response.code(), response.errorBody()?.string())
            }
        } catch (exception: CancellationException) {
            throw exception
        } catch (exception: Exception) {
            error = "No se pudieron cargar las torres: ${exception.message.orEmpty()}"
        } finally {
            towersLoaded = true
        }
    }

    // Cada vez que cambia la torre, la búsqueda o la página se vuelven a pedir los apartamentos.
    LaunchedEffect(towerId, search, page) {
        val currentTower = towerId ?: return@LaunchedEffect
        if (search.isNotEmpty()) delay(300)
        loading = true
        error = null
        try {
            val response = RetrofitClient.structureApi.getApartments(
                auth = Session.bearer(),
                towerId = currentTower,
                search = search.trim().ifEmpty { null },
                page = page
            )
            if (response.isSuccessful) {
                val body = response.body()
                apartments = body?.apartments.orEmpty()
                totalPages = (body?.totalPages ?: 1).coerceAtLeast(1)
            } else {
                apartments = emptyList()
                error = mensajeDeError(response.code(), response.errorBody()?.string())
            }
        } catch (exception: CancellationException) {
            throw exception
        } catch (exception: Exception) {
            apartments = emptyList()
            error = "No se pudieron cargar los apartamentos: ${exception.message.orEmpty()}"
        } finally {
            loading = false
        }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Elegir apartamento") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (towersLoaded && towers.isEmpty() && error == null) {
                    Text("Todavía no hay torres. Créalas primero en «Estructura de la unidad».")
                }
                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    towers.forEach { tower ->
                        FilterChip(
                            selected = tower.id == towerId,
                            onClick = {
                                towerId = tower.id
                                page = 1
                            },
                            label = { Text(tower.name) }
                        )
                    }
                }
                if (towers.isNotEmpty()) {
                    OutlinedTextField(
                        value = search,
                        onValueChange = {
                            search = it
                            page = 1
                        },
                        label = { Text("Buscar por código") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                if (loading) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                error?.let {
                    Text(
                        it,
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
                Column(
                    modifier = Modifier
                        .heightIn(max = 280.dp)
                        .verticalScroll(rememberScrollState())
                ) {
                    apartments.forEach { apartment ->
                        TextButton(
                            onClick = { onPick(apartment.toOption()) },
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text(
                                "${apartment.code} · piso ${apartment.floor}",
                                modifier = Modifier.fillMaxWidth()
                            )
                        }
                    }
                    if (!loading && towers.isNotEmpty() && apartments.isEmpty() && error == null) {
                        Text("No hay apartamentos para mostrar en esta torre.")
                    }
                }
                if (totalPages > 1) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        TextButton(
                            enabled = page > 1 && !loading,
                            onClick = { page -= 1 }
                        ) { Text("Anterior") }
                        Text("$page de $totalPages")
                        TextButton(
                            enabled = page < totalPages && !loading,
                            onClick = { page += 1 }
                        ) { Text("Siguiente") }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Cerrar") } }
    )
}
