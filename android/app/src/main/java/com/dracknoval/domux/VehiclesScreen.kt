package com.dracknoval.domux

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.dracknoval.domux.data.RegisterVehicleEntryRequest
import com.dracknoval.domux.data.ResidentVehicleItem
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.Visit
import com.dracknoval.domux.data.VisitorSpotItem
import com.dracknoval.domux.data.VisitorVehicleEntryData
import kotlinx.coroutines.delay

// Opciones del parqueadero al registrar una entrada. Los parqueaderos reales tienen id desde 1.
private const val AUTO_SPOT = 0
private const val NO_SPOT = -1

/** Un texto de placa limpio: mayúsculas, sin espacios ni guiones, máximo 7 caracteres. */
private fun cleanPlate(text: String): String =
    text.uppercase().filter { it.isLetterOrDigit() }.take(7)

/**
 * Portería vehicular (HU-035 a HU-041): tablero de parqueaderos de visitantes, entrada y salida de
 * sus vehículos, movimientos de vehículos de residentes e historial. El guardia registra; la
 * administración consulta. La pantalla solo dibuja lo que le da [VehiclesViewModel].
 */
@Composable
fun VehiclesScreen(navController: NavController, viewModel: VehiclesViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()
    val isGuard = Session.isGuard
    val tabs = if (isGuard) {
        listOf("Parqueaderos", "Registrar entrada", "Residentes", "Historial")
    } else {
        listOf("Parqueaderos", "Residentes", "Historial")
    }
    var selectedTab by remember { mutableIntStateOf(0) }
    val tab = selectedTab.coerceIn(tabs.indices)
    var pendingExit by remember { mutableStateOf<VisitorVehicleEntryData?>(null) }

    DomuxScreenScaffold(title = "Vehículos", navController = navController) { scaffoldPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(scaffoldPadding)
                .padding(horizontal = 16.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            DomuxSectionTabs(tabs, tab) { selectedTab = it }
            if (state.message.isNotBlank()) {
                DomuxMessageBanner(state.message, state.messageIsError) { viewModel.dismissMessage() }
            }
            if (state.boardLoading || state.entriesLoading || state.residentLoading) {
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
            }
            when (tabs[tab]) {
                "Parqueaderos" -> SpotBoardSection(
                    modifier = Modifier.weight(1f),
                    state = state,
                    isGuard = isGuard,
                    onRefresh = { viewModel.refreshBoard() },
                    onExit = { pendingExit = it }
                )

                "Registrar entrada" -> VehicleEntrySection(
                    modifier = Modifier.weight(1f),
                    state = state,
                    onSearchVisits = { viewModel.loadCandidates(it) },
                    onRegister = { viewModel.registerEntry(it) },
                    onMessage = { viewModel.showNotice(it) }
                )

                "Residentes" -> ResidentVehiclesSection(
                    modifier = Modifier.weight(1f),
                    state = state,
                    isGuard = isGuard,
                    onSearch = { viewModel.searchResidentVehicles(it) },
                    onMovement = { vehicle, type -> viewModel.registerResidentMovement(vehicle, type) }
                )

                else -> VehicleHistorySection(
                    modifier = Modifier.weight(1f),
                    state = state,
                    isGuard = isGuard,
                    onFilter = { inside, overdue -> viewModel.setEntriesFilter(inside, overdue) },
                    onPlate = { viewModel.setEntriesPlate(it) },
                    onRefresh = { viewModel.refreshEntries() },
                    onLoadMore = { viewModel.loadMoreEntries() },
                    onExit = { pendingExit = it }
                )
            }
        }
    }

    pendingExit?.let { entry ->
        DomuxConfirmDialog(
            title = "Registrar salida del vehículo",
            message = "¿Registrar la salida del vehículo ${entry.plate}?" +
                (entry.spotCode?.let { " El parqueadero $it quedará libre." } ?: ""),
            confirmLabel = "Registrar salida",
            onConfirm = {
                pendingExit = null
                viewModel.registerExit(entry)
            },
            onDismiss = { pendingExit = null }
        )
    }

    // El parqueadero elegido ya estaba ocupado o no quedan libres (HU-039).
    state.spotConflict?.let { conflict ->
        val suggested = conflict.suggestedSpot
        AlertDialog(
            onDismissRequest = { viewModel.dismissConflict() },
            title = { Text("Parqueadero no disponible") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(conflict.message)
                    if (suggested != null) {
                        TextButton(enabled = !state.busy, onClick = { viewModel.retryWithoutSpot() }) {
                            Text("Registrar sin parqueadero")
                        }
                    }
                }
            },
            confirmButton = {
                if (suggested != null) {
                    TextButton(enabled = !state.busy, onClick = { viewModel.retryWithSuggestedSpot() }) {
                        Text("Usar el ${suggested.code}")
                    }
                } else {
                    TextButton(enabled = !state.busy, onClick = { viewModel.retryWithoutSpot() }) {
                        Text("Registrar sin parqueadero")
                    }
                }
            },
            dismissButton = { TextButton(onClick = { viewModel.dismissConflict() }) { Text("Cancelar") } }
        )
    }
}

// ---------------------------------------------------------------------------
// Tablero de parqueaderos (HU-037)
// ---------------------------------------------------------------------------

@Composable
private fun SpotBoardSection(
    modifier: Modifier,
    state: VehiclesUiState,
    isGuard: Boolean,
    onRefresh: () -> Unit,
    onExit: (VisitorVehicleEntryData) -> Unit
) {
    val board = state.board
    LazyColumn(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        item {
            DomuxCard(Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.padding(14.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    Text("Parqueaderos de visitantes", style = MaterialTheme.typography.titleMedium)
                    if (board == null) {
                        Text(if (state.boardLoading) "Cargando parqueaderos..." else "No se pudo cargar el tablero.")
                    } else {
                        Text("Libres: ${board.free} · Ocupados: ${board.occupied} · Total: ${board.total}")
                        if (board.overdue > 0) {
                            DomuxStatusBadge(
                                "${board.overdue} vehículo(s) con más de ${board.maxDays} días",
                                DomuxBadgeTone.ALERT
                            )
                        }
                        val suggested = board.spots.orEmpty().firstOrNull { it.id == board.suggestedSpotId }
                        if (suggested != null) {
                            Text("Sugerido para el próximo vehículo: ${suggested.code}")
                        } else if (board.total > 0) {
                            Text("No quedan parqueaderos libres.")
                        }
                    }
                    TextButton(onClick = onRefresh) { Text("Actualizar tablero") }
                }
            }
        }
        if (board != null) {
            if (board.total == 0) {
                item {
                    Text("Aún no hay parqueaderos de visitantes. El administrador los crea en Estructura.")
                }
            }
            items(board.spots.orEmpty(), key = { "spot-${it.id}" }) { spot ->
                SpotCard(spot, board.suggestedSpotId == spot.id, isGuard, state.busy, onExit)
            }
            val withoutSpot = board.withoutSpot.orEmpty()
            if (withoutSpot.isNotEmpty()) {
                item {
                    Text(
                        "Vehículos adentro sin parqueadero",
                        style = MaterialTheme.typography.titleSmall,
                        modifier = Modifier.padding(top = 6.dp)
                    )
                }
                items(withoutSpot, key = { "no-spot-${it.id}" }) { entry ->
                    VehicleEntryCard(entry, isGuard, state.busy, onExit)
                }
            }
        }
    }
}

@Composable
private fun SpotCard(
    spot: VisitorSpotItem,
    suggested: Boolean,
    isGuard: Boolean,
    busy: Boolean,
    onExit: (VisitorVehicleEntryData) -> Unit
) {
    val entry = spot.entry
    DomuxCard(Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(5.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    "Parqueadero ${spot.code}",
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.weight(1f)
                )
                when {
                    entry != null && entry.isOverdue -> DomuxStatusBadge("Vencido", DomuxBadgeTone.ALERT)
                    spot.isOccupied -> DomuxStatusBadge("Ocupado", DomuxBadgeTone.PROGRESS)
                    else -> DomuxStatusBadge("Libre", DomuxBadgeTone.SUCCESS)
                }
            }
            spot.location?.takeIf { it.isNotBlank() }?.let {
                Text(it, style = MaterialTheme.typography.bodySmall)
            }
            if (!spot.isOccupied && suggested) {
                Text("Es el que se sugiere al próximo vehículo.", style = MaterialTheme.typography.bodySmall)
            }
            if (entry != null) {
                VehicleEntryDetails(entry, showSpot = false)
                if (isGuard) {
                    TextButton(onClick = { onExit(entry) }, enabled = !busy) { Text("Registrar salida") }
                }
            }
        }
    }
}

/** Las líneas de una entrada de vehículo: placa, visita, apartamento y cuánto lleva adentro. */
@Composable
private fun VehicleEntryDetails(entry: VisitorVehicleEntryData, showSpot: Boolean) {
    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Text("Placa ${entry.plate}", style = MaterialTheme.typography.titleSmall)
        Text("Visita: ${entry.visitorName.orEmpty()} · ${entry.residentName.orEmpty()} · ${entry.apartment.orEmpty()}")
        if (showSpot) {
            Text(
                if (entry.spotCode != null) {
                    "Parqueadero: ${entry.spotCode}" + (entry.spotLocation?.let { " ($it)" } ?: "")
                } else {
                    "Sin parqueadero"
                }
            )
        }
        Text("Entró: ${entry.enteredAt.orEmpty()}")
        if (entry.exitedAt != null) {
            Text("Salió: ${entry.exitedAt} · estuvo ${durationText(entry.parkedMinutes)}")
        } else {
            Text("Lleva adentro: ${durationText(entry.parkedMinutes)} (máximo ${entry.maxDays} días)")
        }
    }
}

@Composable
private fun VehicleEntryCard(
    entry: VisitorVehicleEntryData,
    isGuard: Boolean,
    busy: Boolean,
    onExit: (VisitorVehicleEntryData) -> Unit
) {
    DomuxCard(Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(5.dp)
        ) {
            when {
                !entry.isInside -> DomuxStatusBadge("Salió", DomuxBadgeTone.SUCCESS)
                entry.isOverdue -> DomuxStatusBadge("Pasó los ${entry.maxDays} días", DomuxBadgeTone.ALERT)
                else -> DomuxStatusBadge("Adentro", DomuxBadgeTone.PROGRESS)
            }
            VehicleEntryDetails(entry, showSpot = true)
            if (isGuard && entry.isInside) {
                TextButton(onClick = { onExit(entry) }, enabled = !busy) { Text("Registrar salida") }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Entrada de un vehículo visitante (HU-035, HU-036 y HU-039)
// ---------------------------------------------------------------------------

@Composable
private fun VehicleEntrySection(
    modifier: Modifier,
    state: VehiclesUiState,
    onSearchVisits: (String) -> Unit,
    onRegister: (RegisterVehicleEntryRequest) -> Unit,
    onMessage: (String) -> Unit
) {
    var plate by rememberSaveable { mutableStateOf("") }
    var visitSearch by rememberSaveable { mutableStateOf("") }
    var selectedVisit by remember { mutableStateOf<Visit?>(null) }
    // AUTO_SPOT = el primero libre; NO_SPOT = sin parqueadero; otro valor = id del parqueadero elegido.
    var spotChoice by rememberSaveable { mutableStateOf(AUTO_SPOT) }
    var attempted by rememberSaveable { mutableStateOf(false) }
    var handled by rememberSaveable { mutableStateOf(state.entryRegistrations) }

    // Las visitas autorizadas que se pueden elegir, con una pausa para no consultar en cada letra.
    LaunchedEffect(visitSearch) {
        if (visitSearch.isNotBlank()) delay(300)
        onSearchVisits(visitSearch)
    }
    // Cuando una entrada se registra bien (aunque sea desde la ventana de conflicto), el formulario se limpia.
    LaunchedEffect(state.entryRegistrations) {
        if (state.entryRegistrations != handled) {
            handled = state.entryRegistrations
            plate = ""
            visitSearch = ""
            selectedVisit = null
            spotChoice = AUTO_SPOT
            attempted = false
        }
    }
    val freeSpots = state.board?.spots.orEmpty().filter { !it.isOccupied }
    val suggestedCode = freeSpots.firstOrNull { it.id == state.board?.suggestedSpotId }?.code
    // Si el parqueadero elegido se ocupó mientras tanto, se vuelve a la opción automática.
    LaunchedEffect(freeSpots) {
        if (spotChoice > 0 && freeSpots.none { it.id == spotChoice }) spotChoice = AUTO_SPOT
    }

    Column(
        modifier = modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        DomuxCard(Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Text("Registrar entrada de vehículo", style = MaterialTheme.typography.titleMedium)
                OutlinedTextField(
                    value = plate,
                    onValueChange = { plate = cleanPlate(it) },
                    label = { Text("Placa *") },
                    isError = attempted && plate.isBlank(),
                    supportingText = {
                        if (attempted && plate.isBlank()) Text("La placa es obligatoria") else Text("Ejemplo: ABC123")
                    },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )

                // El vehículo pertenece a una visita autorizada (RN-010).
                val visit = selectedVisit
                if (visit == null) {
                    Text("Visita del conductor *", style = MaterialTheme.typography.labelLarge)
                    OutlinedTextField(
                        value = visitSearch,
                        onValueChange = { visitSearch = it },
                        label = { Text("Buscar por nombre, residente o apartamento") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    if (state.candidates.isEmpty()) {
                        Text(
                            if (state.candidatesLoading) {
                                "Buscando visitas..."
                            } else {
                                "No hay visitas autorizadas con esos datos. Primero registra la visita y que el " +
                                    "residente (o una llamada) la autorice."
                            },
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    state.candidates.take(8).forEach { candidate ->
                        TextButton(
                            onClick = { selectedVisit = candidate },
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Column(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalAlignment = Alignment.Start
                            ) {
                                Text(candidate.visitorName)
                                Text(
                                    "${candidate.residentName.orEmpty()} · ${candidate.apartment.orEmpty()} · " +
                                        if (candidate.enteredAt != null) "ya entró" else "aún no ha entrado",
                                    style = MaterialTheme.typography.bodySmall
                                )
                            }
                        }
                    }
                    if (state.candidates.size > 8) {
                        Text(
                            "Hay más visitas: escribe para filtrar.",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    if (attempted) {
                        Text("Elige la visita a la que pertenece el vehículo.", style = MaterialTheme.typography.bodySmall)
                    }
                } else {
                    Text("Visita del conductor", style = MaterialTheme.typography.labelLarge)
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(visit.visitorName)
                            Text(
                                "${visit.residentName.orEmpty()} · ${visit.apartment.orEmpty()}",
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                        TextButton(onClick = { selectedVisit = null }) { Text("Cambiar") }
                    }
                }

                // Parqueadero: por defecto el primero libre (HU-036); el guardia puede elegir otro o ninguno.
                Text("Parqueadero", style = MaterialTheme.typography.labelLarge)
                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    FilterChip(
                        selected = spotChoice == AUTO_SPOT,
                        onClick = { spotChoice = AUTO_SPOT },
                        label = { Text(if (suggestedCode != null) "Automático ($suggestedCode)" else "Automático") }
                    )
                    freeSpots.forEach { spot ->
                        FilterChip(
                            selected = spotChoice == spot.id,
                            onClick = { spotChoice = spot.id },
                            label = { Text(spot.code) }
                        )
                    }
                    FilterChip(
                        selected = spotChoice == NO_SPOT,
                        onClick = { spotChoice = NO_SPOT },
                        label = { Text("Sin parqueadero") }
                    )
                }
                if (freeSpots.isEmpty() && state.board != null) {
                    Text(
                        "No quedan parqueaderos libres: puedes registrar la entrada sin parqueadero.",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
                Button(
                    onClick = {
                        attempted = true
                        val chosen = selectedVisit
                        if (plate.isBlank() || chosen == null) {
                            onMessage("Escribe la placa y elige la visita a la que pertenece el vehículo.")
                        } else {
                            onRegister(
                                RegisterVehicleEntryRequest(
                                    plate = plate,
                                    visitId = chosen.id,
                                    spotId = spotChoice.takeIf { it > 0 },
                                    withoutSpot = if (spotChoice == NO_SPOT) true else null
                                )
                            )
                        }
                    },
                    enabled = !state.busy,
                    modifier = Modifier.fillMaxWidth()
                ) { Text("Registrar entrada") }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Vehículos de residentes (HU-040)
// ---------------------------------------------------------------------------

@Composable
private fun ResidentVehiclesSection(
    modifier: Modifier,
    state: VehiclesUiState,
    isGuard: Boolean,
    onSearch: (String) -> Unit,
    onMovement: (ResidentVehicleItem, String) -> Unit
) {
    var text by rememberSaveable { mutableStateOf("") }
    val canSearch = text.trim().length >= VehiclesViewModel.MIN_PLATE_SEARCH
    // Con menos de 2 caracteres no se muestran resultados viejos de una búsqueda anterior.
    val shown = if (canSearch) state.residentVehicles else emptyList<ResidentVehicleItem>()
    // Se busca sola cuando hay al menos 2 caracteres y la persona deja de escribir.
    LaunchedEffect(text) {
        if (canSearch) {
            delay(400)
            onSearch(text)
        }
    }
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        OutlinedTextField(
            value = text,
            onValueChange = { text = cleanPlate(it) },
            label = { Text("Placa del vehículo del residente") },
            supportingText = { Text("Escribe al menos 2 caracteres. Basta con una parte de la placa.") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            if (shown.isEmpty()) {
                item {
                    Text(
                        when {
                            !canSearch -> "Escribe la placa para buscar el vehículo de un residente."
                            state.residentLoading -> "Buscando..."
                            state.residentSearched -> "No hay vehículos de residentes con esa placa."
                            else -> "Buscando..."
                        }
                    )
                }
            }
            items(shown, key = { "resident-vehicle-${it.id}" }) { vehicle ->
                ResidentVehicleCard(vehicle, isGuard, state.busy, onMovement)
            }
        }
    }
}

@Composable
private fun ResidentVehicleCard(
    vehicle: ResidentVehicleItem,
    isGuard: Boolean,
    busy: Boolean,
    onMovement: (ResidentVehicleItem, String) -> Unit
) {
    DomuxCard(Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(5.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(vehicle.plate, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                DomuxStatusBadge(
                    if (vehicle.isInside) "Adentro" else "Afuera",
                    if (vehicle.isInside) DomuxBadgeTone.PROGRESS else DomuxBadgeTone.SUCCESS
                )
            }
            Text(
                listOf(vehicle.type, vehicle.makeModel, vehicle.year.takeIf { it > 0 }?.toString(), vehicle.color)
                    .filter { !it.isNullOrBlank() }
                    .joinToString(" · ")
            )
            Text("Propietario: ${vehicle.registeredOwner} · ${vehicle.apartment.orEmpty()}")
            Text(
                if (vehicle.lastMovementType != null) {
                    "Último movimiento: ${vehicle.lastMovementType} · ${vehicle.lastMovementAt.orEmpty()}"
                } else {
                    "Sin movimientos registrados"
                },
                style = MaterialTheme.typography.bodySmall
            )
            if (isGuard) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextButton(onClick = { onMovement(vehicle, "entrada") }, enabled = !busy) {
                        Text("Registrar entrada")
                    }
                    TextButton(onClick = { onMovement(vehicle, "salida") }, enabled = !busy) {
                        Text("Registrar salida")
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Historial de entradas (HU-041)
// ---------------------------------------------------------------------------

@Composable
private fun VehicleHistorySection(
    modifier: Modifier,
    state: VehiclesUiState,
    isGuard: Boolean,
    onFilter: (insideOnly: Boolean, overdueOnly: Boolean) -> Unit,
    onPlate: (String) -> Unit,
    onRefresh: () -> Unit,
    onLoadMore: () -> Unit,
    onExit: (VisitorVehicleEntryData) -> Unit
) {
    var plate by rememberSaveable { mutableStateOf("") }
    LaunchedEffect(plate) {
        if (plate.isNotBlank()) delay(300)
        onPlate(plate)
    }
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        OutlinedTextField(
            value = plate,
            onValueChange = { plate = cleanPlate(it) },
            label = { Text("Buscar por placa") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Row(
            modifier = Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            FilterChip(
                selected = !state.entriesInsideOnly && !state.entriesOverdueOnly,
                onClick = { onFilter(false, false) },
                label = { Text("Todos") }
            )
            FilterChip(
                selected = state.entriesInsideOnly && !state.entriesOverdueOnly,
                onClick = { onFilter(true, false) },
                label = { Text("Adentro") }
            )
            FilterChip(
                selected = state.entriesOverdueOnly,
                onClick = { onFilter(false, true) },
                label = { Text("Pasaron el tiempo máximo") }
            )
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            if (state.entriesPage.total > 0) {
                Text(
                    "Mostrando ${state.entries.size} de ${state.entriesPage.total}",
                    style = MaterialTheme.typography.bodySmall
                )
            } else {
                Text("", style = MaterialTheme.typography.bodySmall)
            }
            TextButton(onClick = onRefresh) { Text("Actualizar") }
        }
        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            if (state.entries.isEmpty()) {
                item {
                    Text(
                        if (state.entriesLoading) "Cargando historial..."
                        else "No hay entradas de vehículos con esos filtros."
                    )
                }
            }
            items(state.entries, key = { "entry-${it.id}" }) { entry ->
                VehicleEntryCard(entry, isGuard, state.busy, onExit)
            }
            if (state.entriesPage.page < state.entriesPage.totalPages) {
                item {
                    TextButton(
                        onClick = onLoadMore,
                        enabled = !state.entriesLoadingMore,
                        modifier = Modifier.fillMaxWidth()
                    ) { Text(if (state.entriesLoadingMore) "Cargando..." else "Ver más entradas") }
                }
            }
        }
    }
}
