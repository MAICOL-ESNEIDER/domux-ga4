package com.dracknoval.domux

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.dracknoval.domux.data.ApartmentData
import com.dracknoval.domux.data.ApartmentOption
import com.dracknoval.domux.data.ParkingSpotData
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.StorageRoomData
import com.dracknoval.domux.data.TowerData
import kotlinx.coroutines.delay
import com.dracknoval.domux.ui.theme.DomuxColor

// Qué ventana está abierta. «editing» vacío significa que se está creando uno nuevo.
private data class TowerForm(val editing: TowerData?)
private data class ApartmentForm(val editing: ApartmentData?)
private data class ParkingForm(val editing: ParkingSpotData?)
private data class StorageForm(val editing: StorageRoomData?)

private enum class RetireKind { TOWER, APARTMENT, PARKING, STORAGE }

private data class RetireRequest(val kind: RetireKind, val id: Int, val name: String)

private val dangerColor = DomuxColor.Bad

private fun plural(count: Int, one: String, many: String): String =
    "$count ${if (count == 1) one else many}"

private fun RetireRequest.title(): String = when (kind) {
    RetireKind.TOWER -> "Retirar torre"
    RetireKind.APARTMENT -> "Retirar apartamento"
    RetireKind.PARKING -> "Retirar parqueadero"
    RetireKind.STORAGE -> "Retirar cuarto útil"
}

private fun RetireRequest.explanation(): String = when (kind) {
    RetireKind.TOWER ->
        "Se retirará «$name». Solo se puede si no tiene apartamentos vigentes. " +
            "No se borra: queda en el historial."
    RetireKind.APARTMENT ->
        "Se retirará «$name». Solo se puede si no tiene residentes activos; sus parqueaderos " +
            "y cuartos útiles quedan libres. No se borra: queda en el historial."
    RetireKind.PARKING ->
        "Se retirará el parqueadero «$name». Solo se puede si no está ocupado. No se borra: " +
            "queda en el historial y su código vuelve a quedar libre."
    RetireKind.STORAGE ->
        "Se retirará el cuarto útil «$name». No se borra: queda en el historial y su código " +
            "vuelve a quedar libre."
}

/**
 * Estructura de la unidad (UI-016, solo administrador): torres, apartamentos, parqueaderos y
 * cuartos útiles. La pantalla solo dibuja lo que le da [StructureViewModel] y le avisa qué
 * hizo la persona; las reglas (códigos únicos, qué se puede retirar) las valida el servidor.
 */
@Composable
fun StructureScreen(navController: NavController, viewModel: StructureViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()
    var selectedTab by remember { mutableIntStateOf(0) }
    var towerForm by remember { mutableStateOf<TowerForm?>(null) }
    var apartmentForm by remember { mutableStateOf<ApartmentForm?>(null) }
    var showFloorForm by remember { mutableStateOf(false) }
    var parkingForm by remember { mutableStateOf<ParkingForm?>(null) }
    var storageForm by remember { mutableStateOf<StorageForm?>(null) }
    var retireRequest by remember { mutableStateOf<RetireRequest?>(null) }

    // Si el servidor rechaza un cambio, el error también se ve dentro de la ventana abierta.
    val dialogError = if (state.messageIsError) state.message else ""
    val selectedTower = state.towers.firstOrNull { it.id == state.selectedTowerId }

    DomuxScreenScaffold(title = "Estructura de la unidad", navController = navController) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            if (!Session.isAdmin) {
                EmptyCard("Solo el administrador puede ver y cambiar la estructura de la unidad.")
                return@Column
            }
            DomuxSectionTabs(
                listOf("Torres", "Apartamentos", "Parqueaderos", "Cuartos útiles"),
                selectedTab
            ) { selectedTab = it }
            DomuxMessageBanner(state.message, state.messageIsError) { viewModel.dismissMessage() }
            if (state.loading || state.busy) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
            when (selectedTab) {
                0 -> TowersTab(
                    towers = state.towers,
                    onCreate = {
                        viewModel.dismissMessage()
                        towerForm = TowerForm(null)
                    },
                    onOpenApartments = { tower ->
                        viewModel.selectTower(tower.id)
                        selectedTab = 1
                    },
                    onEdit = {
                        viewModel.dismissMessage()
                        towerForm = TowerForm(it)
                    },
                    onRetire = { retireRequest = RetireRequest(RetireKind.TOWER, it.id, it.name) }
                )
                1 -> ApartmentsTab(
                    state = state,
                    onSelectTower = { viewModel.selectTower(it) },
                    onSearch = { viewModel.searchApartments(it) },
                    onPage = { viewModel.goToApartmentPage(it) },
                    onCreate = {
                        viewModel.dismissMessage()
                        apartmentForm = ApartmentForm(null)
                    },
                    onCreateFloor = {
                        viewModel.dismissMessage()
                        showFloorForm = true
                    },
                    onEdit = {
                        viewModel.dismissMessage()
                        apartmentForm = ApartmentForm(it)
                    },
                    onRetire = { retireRequest = RetireRequest(RetireKind.APARTMENT, it.id, it.label) }
                )
                2 -> ParkingTab(
                    state = state,
                    onFilter = { viewModel.filterParking(it) },
                    onPage = { viewModel.goToParkingPage(it) },
                    onCreate = {
                        viewModel.dismissMessage()
                        parkingForm = ParkingForm(null)
                    },
                    onEdit = {
                        viewModel.dismissMessage()
                        parkingForm = ParkingForm(it)
                    },
                    onRetire = { retireRequest = RetireRequest(RetireKind.PARKING, it.id, it.code) }
                )
                else -> StorageTab(
                    state = state,
                    onPage = { viewModel.goToStoragePage(it) },
                    onCreate = {
                        viewModel.dismissMessage()
                        storageForm = StorageForm(null)
                    },
                    onEdit = {
                        viewModel.dismissMessage()
                        storageForm = StorageForm(it)
                    },
                    onRetire = { retireRequest = RetireRequest(RetireKind.STORAGE, it.id, it.code) }
                )
            }
        }
    }

    towerForm?.let { form ->
        val editing = form.editing
        TowerFormDialog(
            editing = editing,
            busy = state.busy,
            errorMessage = dialogError,
            onSave = { name, floors ->
                if (editing == null) {
                    viewModel.createTower(name, floors) { towerForm = null }
                } else {
                    viewModel.updateTower(editing.id, name, floors) { towerForm = null }
                }
            },
            onDismiss = { towerForm = null }
        )
    }

    apartmentForm?.let { form ->
        val editing = form.editing
        val tower = if (editing != null) {
            state.towers.firstOrNull { it.id == editing.towerId }
        } else {
            selectedTower
        }
        ApartmentFormDialog(
            towerName = editing?.tower ?: selectedTower?.name.orEmpty(),
            maxFloor = tower?.floors ?: 100,
            editing = editing,
            busy = state.busy,
            errorMessage = dialogError,
            onSave = { code, floor ->
                val towerId = state.selectedTowerId
                if (editing != null) {
                    viewModel.updateApartment(editing.id, code, floor ?: editing.floor) {
                        apartmentForm = null
                    }
                } else if (towerId != null) {
                    viewModel.createApartment(towerId, code, floor) { apartmentForm = null }
                }
            },
            onDismiss = { apartmentForm = null }
        )
    }

    if (showFloorForm && selectedTower != null) {
        FloorFormDialog(
            tower = selectedTower,
            busy = state.busy,
            errorMessage = dialogError,
            onSave = { floor, count ->
                viewModel.createFloor(selectedTower.id, floor, count) { showFloorForm = false }
            },
            onDismiss = { showFloorForm = false }
        )
    }

    parkingForm?.let { form ->
        val editing = form.editing
        ParkingFormDialog(
            editing = editing,
            busy = state.busy,
            errorMessage = dialogError,
            onSave = { code, type, location, apartment ->
                val apartmentId = apartment?.id
                if (editing == null) {
                    viewModel.createParking(code, type, location, apartmentId) { parkingForm = null }
                } else {
                    viewModel.updateParking(editing.id, code, type, location, apartmentId) {
                        parkingForm = null
                    }
                }
            },
            onDismiss = { parkingForm = null }
        )
    }

    storageForm?.let { form ->
        val editing = form.editing
        StorageFormDialog(
            editing = editing,
            busy = state.busy,
            errorMessage = dialogError,
            onSave = { code, apartment ->
                val apartmentId = apartment?.id
                if (editing == null) {
                    viewModel.createStorage(code, apartmentId) { storageForm = null }
                } else {
                    viewModel.updateStorage(editing.id, code, apartmentId) { storageForm = null }
                }
            },
            onDismiss = { storageForm = null }
        )
    }

    retireRequest?.let { request ->
        DomuxConfirmDialog(
            title = request.title(),
            message = request.explanation(),
            confirmLabel = "Retirar",
            danger = true,
            onConfirm = {
                retireRequest = null
                when (request.kind) {
                    RetireKind.TOWER -> viewModel.retireTower(request.id)
                    RetireKind.APARTMENT -> viewModel.retireApartment(request.id)
                    RetireKind.PARKING -> viewModel.retireParking(request.id)
                    RetireKind.STORAGE -> viewModel.retireStorage(request.id)
                }
            },
            onDismiss = { retireRequest = null }
        )
    }
}

// --- Pestañas ------------------------------------------------------------------

@Composable
private fun TowersTab(
    towers: List<TowerData>,
    onCreate: () -> Unit,
    onOpenApartments: (TowerData) -> Unit,
    onEdit: (TowerData) -> Unit,
    onRetire: (TowerData) -> Unit
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        item {
            Button(onClick = onCreate, modifier = Modifier.fillMaxWidth()) { Text("Nueva torre") }
        }
        if (towers.isEmpty()) {
            item { EmptyCard("Todavía no hay torres. Crea la primera para poder registrar apartamentos.") }
        }
        items(towers, key = { it.id }) { tower ->
            DomuxCard(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp)) {
                    Text(tower.name, style = MaterialTheme.typography.titleMedium)
                    Text(
                        "${plural(tower.floors, "piso", "pisos")} · " +
                            plural(tower.apartmentCount, "apartamento", "apartamentos")
                    )
                    Row(Modifier.horizontalScroll(rememberScrollState())) {
                        TextButton(onClick = { onOpenApartments(tower) }) { Text("Ver apartamentos") }
                        TextButton(onClick = { onEdit(tower) }) { Text("Editar") }
                        TextButton(onClick = { onRetire(tower) }) {
                            Text("Retirar", color = dangerColor)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ApartmentsTab(
    state: StructureUiState,
    onSelectTower: (Int) -> Unit,
    onSearch: (String) -> Unit,
    onPage: (Int) -> Unit,
    onCreate: () -> Unit,
    onCreateFloor: () -> Unit,
    onEdit: (ApartmentData) -> Unit,
    onRetire: (ApartmentData) -> Unit
) {
    // El texto se guarda aquí y se manda al servidor cuando la persona deja de escribir.
    var searchText by remember { mutableStateOf(state.apartmentSearch) }
    LaunchedEffect(searchText) {
        delay(300)
        onSearch(searchText)
    }
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (state.towers.isEmpty()) {
                    Text("Primero crea una torre en la pestaña «Torres».")
                } else {
                    Row(
                        modifier = Modifier.horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        state.towers.forEach { tower ->
                            FilterChip(
                                selected = tower.id == state.selectedTowerId,
                                onClick = { onSelectTower(tower.id) },
                                label = { Text(tower.name) }
                            )
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = onCreate, modifier = Modifier.weight(1f)) {
                            Text("Nuevo apartamento")
                        }
                        OutlinedButton(onClick = onCreateFloor, modifier = Modifier.weight(1f)) {
                            Text("Crear un piso")
                        }
                    }
                    OutlinedTextField(
                        value = searchText,
                        onValueChange = { searchText = it },
                        label = { Text("Buscar por código") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    Text(
                        "${plural(state.apartmentPage.total, "apartamento", "apartamentos")} · " +
                            "página ${state.apartmentPage.page} de ${state.apartmentPage.totalPages}"
                    )
                }
            }
        }
        if (state.towers.isNotEmpty() && state.apartments.isEmpty() && !state.loading) {
            item { EmptyCard("No hay apartamentos para mostrar en esta torre.") }
        }
        items(state.apartments, key = { it.id }) { apartment ->
            DomuxCard(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp)) {
                    Text(apartment.label, style = MaterialTheme.typography.titleMedium)
                    Text(
                        "Piso ${apartment.floor} · " +
                            plural(apartment.residentCount, "residente", "residentes")
                    )
                    val parking = apartment.parkingSpots.orEmpty()
                    if (parking.isNotEmpty()) Text("Parqueaderos: ${parking.joinToString(", ")}")
                    val storage = apartment.storageRooms.orEmpty()
                    if (storage.isNotEmpty()) Text("Cuartos útiles: ${storage.joinToString(", ")}")
                    Row(Modifier.horizontalScroll(rememberScrollState())) {
                        TextButton(onClick = { onEdit(apartment) }) { Text("Editar") }
                        TextButton(onClick = { onRetire(apartment) }) {
                            Text("Retirar", color = dangerColor)
                        }
                    }
                }
            }
        }
        item { PagerRow(state.apartmentPage, !state.loading, onPage) }
    }
}

@Composable
private fun ParkingTab(
    state: StructureUiState,
    onFilter: (String?) -> Unit,
    onPage: (Int) -> Unit,
    onCreate: () -> Unit,
    onEdit: (ParkingSpotData) -> Unit,
    onRetire: (ParkingSpotData) -> Unit
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onCreate, modifier = Modifier.fillMaxWidth()) {
                    Text("Nuevo parqueadero")
                }
                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    FilterChip(
                        selected = state.parkingKind == null,
                        onClick = { onFilter(null) },
                        label = { Text("Todos") }
                    )
                    FilterChip(
                        selected = state.parkingKind == "residente",
                        onClick = { onFilter("residente") },
                        label = { Text("Residentes") }
                    )
                    FilterChip(
                        selected = state.parkingKind == "visitante",
                        onClick = { onFilter("visitante") },
                        label = { Text("Visitantes") }
                    )
                }
                Text(
                    "${plural(state.parkingPage.total, "parqueadero", "parqueaderos")} · " +
                        "página ${state.parkingPage.page} de ${state.parkingPage.totalPages}"
                )
            }
        }
        if (state.parkingSpots.isEmpty() && !state.loading) {
            item { EmptyCard("No hay parqueaderos para mostrar.") }
        }
        items(state.parkingSpots, key = { it.id }) { spot ->
            DomuxCard(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp)) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Text(spot.code, style = MaterialTheme.typography.titleMedium)
                        if (spot.isOccupied) DomuxStatusBadge("Ocupado", DomuxBadgeTone.PROGRESS)
                    }
                    Text(
                        "${if (spot.type == "visitante") "Visitantes" else "Residente"} · " +
                            spot.location.orEmpty()
                    )
                    if (spot.type != "visitante") {
                        val owner = spot.apartment
                        Text(if (owner.isNullOrBlank()) "Sin asignar" else "Asignado a $owner")
                    }
                    Row(Modifier.horizontalScroll(rememberScrollState())) {
                        TextButton(onClick = { onEdit(spot) }) { Text("Editar") }
                        TextButton(onClick = { onRetire(spot) }) {
                            Text("Retirar", color = dangerColor)
                        }
                    }
                }
            }
        }
        item { PagerRow(state.parkingPage, !state.loading, onPage) }
    }
}

@Composable
private fun StorageTab(
    state: StructureUiState,
    onPage: (Int) -> Unit,
    onCreate: () -> Unit,
    onEdit: (StorageRoomData) -> Unit,
    onRetire: (StorageRoomData) -> Unit
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onCreate, modifier = Modifier.fillMaxWidth()) {
                    Text("Nuevo cuarto útil")
                }
                Text(
                    "${plural(state.storagePage.total, "cuarto útil", "cuartos útiles")} · " +
                        "página ${state.storagePage.page} de ${state.storagePage.totalPages}"
                )
            }
        }
        if (state.storageRooms.isEmpty() && !state.loading) {
            item { EmptyCard("No hay cuartos útiles para mostrar.") }
        }
        items(state.storageRooms, key = { it.id }) { room ->
            DomuxCard(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp)) {
                    Text(room.code, style = MaterialTheme.typography.titleMedium)
                    val owner = room.apartment
                    Text(if (owner.isNullOrBlank()) "Sin asignar" else "Asignado a $owner")
                    Row(Modifier.horizontalScroll(rememberScrollState())) {
                        TextButton(onClick = { onEdit(room) }) { Text("Editar") }
                        TextButton(onClick = { onRetire(room) }) {
                            Text("Retirar", color = dangerColor)
                        }
                    }
                }
            }
        }
        item { PagerRow(state.storagePage, !state.loading, onPage) }
    }
}

@Composable
private fun EmptyCard(text: String) {
    DomuxCard(Modifier.fillMaxWidth()) {
        Text(text, modifier = Modifier.padding(16.dp))
    }
}

@Composable
private fun PagerRow(page: PageInfo, enabled: Boolean, onPage: (Int) -> Unit) {
    if (page.totalPages <= 1) return
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        TextButton(
            enabled = enabled && page.page > 1,
            onClick = { onPage(page.page - 1) }
        ) { Text("Anterior") }
        Text("Página ${page.page} de ${page.totalPages}")
        TextButton(
            enabled = enabled && page.page < page.totalPages,
            onClick = { onPage(page.page + 1) }
        ) { Text("Siguiente") }
    }
}

@Composable
private fun DialogError(message: String) {
    if (message.isBlank()) return
    Text("⚠ $message", color = dangerColor, style = MaterialTheme.typography.bodySmall)
}

// --- Ventanas para crear y editar ----------------------------------------------------

@Composable
private fun TowerFormDialog(
    editing: TowerData?,
    busy: Boolean,
    errorMessage: String,
    onSave: (name: String, floors: Int) -> Unit,
    onDismiss: () -> Unit
) {
    var name by remember(editing?.id) { mutableStateOf(editing?.name.orEmpty()) }
    var floors by remember(editing?.id) { mutableStateOf(editing?.floors?.toString().orEmpty()) }
    var attempted by remember { mutableStateOf(false) }
    val floorsNumber = floors.toIntOrNull()
    val floorsInvalid = floorsNumber == null || floorsNumber !in 1..100
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (editing == null) "Nueva torre" else "Editar torre") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it.take(60) },
                    label = { Text("Nombre (por ejemplo, Torre 1)") },
                    singleLine = true,
                    isError = attempted && name.isBlank(),
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(
                    value = floors,
                    onValueChange = { floors = it.filter(Char::isDigit).take(3) },
                    label = { Text("Cantidad de pisos (1 a 100)") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    isError = attempted && floorsInvalid,
                    modifier = Modifier.fillMaxWidth()
                )
                DialogError(errorMessage)
            }
        },
        confirmButton = {
            TextButton(
                enabled = !busy,
                onClick = {
                    attempted = true
                    if (name.isBlank() || floorsNumber == null || floorsInvalid) return@TextButton
                    onSave(name.trim(), floorsNumber)
                }
            ) { Text(if (busy) "Guardando..." else "Guardar") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancelar") } }
    )
}

@Composable
private fun ApartmentFormDialog(
    towerName: String,
    maxFloor: Int,
    editing: ApartmentData?,
    busy: Boolean,
    errorMessage: String,
    onSave: (code: String, floor: Int?) -> Unit,
    onDismiss: () -> Unit
) {
    var code by remember(editing?.id) { mutableStateOf(editing?.code.orEmpty()) }
    var floor by remember(editing?.id) { mutableStateOf(editing?.floor?.toString().orEmpty()) }
    var attempted by remember { mutableStateOf(false) }
    val floorNumber = floor.toIntOrNull()
    // Al crear, el piso puede quedar vacío (se toma del código); al editar es obligatorio.
    val floorInvalid = if (floor.isEmpty()) {
        editing != null
    } else {
        floorNumber == null || floorNumber !in 1..maxFloor
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (editing == null) "Nuevo apartamento" else "Editar apartamento") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text("Torre: $towerName")
                OutlinedTextField(
                    value = code,
                    onValueChange = { code = it.take(20) },
                    label = { Text("Código (por ejemplo, 101)") },
                    singleLine = true,
                    isError = attempted && code.isBlank(),
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(
                    value = floor,
                    onValueChange = { floor = it.filter(Char::isDigit).take(3) },
                    label = { Text("Piso (1 a $maxFloor)") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    isError = attempted && floorInvalid,
                    supportingText = {
                        if (editing == null) {
                            Text("Si lo dejas vacío y el código es un número como 301, el piso sale del código (3).")
                        }
                    },
                    modifier = Modifier.fillMaxWidth()
                )
                DialogError(errorMessage)
            }
        },
        confirmButton = {
            TextButton(
                enabled = !busy,
                onClick = {
                    attempted = true
                    if (code.isBlank() || floorInvalid) return@TextButton
                    onSave(code.trim(), floorNumber)
                }
            ) { Text(if (busy) "Guardando..." else "Guardar") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancelar") } }
    )
}

private fun floorCodes(floor: Int, count: Int): String {
    val codes = (1..count).map { "$floor${it.toString().padStart(2, '0')}" }
    return if (codes.size <= 6) {
        codes.joinToString(", ")
    } else {
        codes.take(3).joinToString(", ") + " … " + codes.last()
    }
}

@Composable
private fun FloorFormDialog(
    tower: TowerData,
    busy: Boolean,
    errorMessage: String,
    onSave: (floor: Int, count: Int) -> Unit,
    onDismiss: () -> Unit
) {
    var floor by remember { mutableStateOf("") }
    var count by remember { mutableStateOf("") }
    var attempted by remember { mutableStateOf(false) }
    val floorNumber = floor.toIntOrNull()
    val countNumber = count.toIntOrNull()
    val floorInvalid = floorNumber == null || floorNumber !in 1..tower.floors
    val countInvalid = countNumber == null || countNumber !in 1..99
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Crear un piso de ${tower.name}") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(
                    "Crea de una vez los apartamentos de un piso con códigos seguidos. Por ejemplo, " +
                        "el piso 3 con 4 apartamentos crea 301, 302, 303 y 304. Si alguno ya " +
                        "existe, no se crea ninguno."
                )
                OutlinedTextField(
                    value = floor,
                    onValueChange = { floor = it.filter(Char::isDigit).take(3) },
                    label = { Text("Piso (1 a ${tower.floors})") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    isError = attempted && floorInvalid,
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(
                    value = count,
                    onValueChange = { count = it.filter(Char::isDigit).take(2) },
                    label = { Text("Cantidad de apartamentos (1 a 99)") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    isError = attempted && countInvalid,
                    modifier = Modifier.fillMaxWidth()
                )
                if (floorNumber != null && countNumber != null && !floorInvalid && !countInvalid) {
                    Text("Se crearán: ${floorCodes(floorNumber, countNumber)}")
                }
                DialogError(errorMessage)
            }
        },
        confirmButton = {
            TextButton(
                enabled = !busy,
                onClick = {
                    attempted = true
                    if (floorNumber == null || countNumber == null || floorInvalid || countInvalid) {
                        return@TextButton
                    }
                    onSave(floorNumber, countNumber)
                }
            ) { Text(if (busy) "Creando..." else "Crear apartamentos") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancelar") } }
    )
}

@Composable
private fun ParkingFormDialog(
    editing: ParkingSpotData?,
    busy: Boolean,
    errorMessage: String,
    onSave: (code: String, type: String, location: String, apartment: ApartmentOption?) -> Unit,
    onDismiss: () -> Unit
) {
    val initialApartmentId = editing?.apartmentId
    var code by remember(editing?.id) { mutableStateOf(editing?.code.orEmpty()) }
    var type by remember(editing?.id) { mutableStateOf(editing?.type ?: "residente") }
    var location by remember(editing?.id) { mutableStateOf(editing?.location.orEmpty()) }
    var apartment by remember(editing?.id) {
        mutableStateOf<ApartmentOption?>(
            if (initialApartmentId != null) {
                ApartmentOption(initialApartmentId, editing?.apartment.orEmpty())
            } else {
                null
            }
        )
    }
    var attempted by remember { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (editing == null) "Nuevo parqueadero" else "Editar parqueadero") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    FilterChip(
                        selected = type == "residente",
                        onClick = { type = "residente" },
                        label = { Text("Residente") }
                    )
                    FilterChip(
                        selected = type == "visitante",
                        onClick = {
                            type = "visitante"
                            apartment = null
                        },
                        label = { Text("Visitantes") }
                    )
                }
                OutlinedTextField(
                    value = code,
                    onValueChange = { code = it.take(20) },
                    label = { Text("Código (por ejemplo, P-01)") },
                    singleLine = true,
                    isError = attempted && code.isBlank(),
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(
                    value = location,
                    onValueChange = { location = it.take(120) },
                    label = { Text("Ubicación (por ejemplo, Sótano 1)") },
                    singleLine = true,
                    isError = attempted && location.isBlank(),
                    modifier = Modifier.fillMaxWidth()
                )
                if (type == "residente") {
                    ApartmentPickerField(
                        label = "Apartamento (opcional)",
                        selected = apartment,
                        onSelect = { apartment = it },
                        allowClear = true
                    )
                } else {
                    Text("Un parqueadero de visitantes no se asigna a un apartamento.")
                }
                DialogError(errorMessage)
            }
        },
        confirmButton = {
            TextButton(
                enabled = !busy,
                onClick = {
                    attempted = true
                    if (code.isBlank() || location.isBlank()) return@TextButton
                    onSave(
                        code.trim(),
                        type,
                        location.trim(),
                        if (type == "residente") apartment else null
                    )
                }
            ) { Text(if (busy) "Guardando..." else "Guardar") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancelar") } }
    )
}

@Composable
private fun StorageFormDialog(
    editing: StorageRoomData?,
    busy: Boolean,
    errorMessage: String,
    onSave: (code: String, apartment: ApartmentOption?) -> Unit,
    onDismiss: () -> Unit
) {
    val initialApartmentId = editing?.apartmentId
    var code by remember(editing?.id) { mutableStateOf(editing?.code.orEmpty()) }
    var apartment by remember(editing?.id) {
        mutableStateOf<ApartmentOption?>(
            if (initialApartmentId != null) {
                ApartmentOption(initialApartmentId, editing?.apartment.orEmpty())
            } else {
                null
            }
        )
    }
    var attempted by remember { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (editing == null) "Nuevo cuarto útil" else "Editar cuarto útil") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedTextField(
                    value = code,
                    onValueChange = { code = it.take(20) },
                    label = { Text("Código (por ejemplo, C-01)") },
                    singleLine = true,
                    isError = attempted && code.isBlank(),
                    modifier = Modifier.fillMaxWidth()
                )
                ApartmentPickerField(
                    label = "Apartamento (opcional)",
                    selected = apartment,
                    onSelect = { apartment = it },
                    allowClear = true
                )
                DialogError(errorMessage)
            }
        },
        confirmButton = {
            TextButton(
                enabled = !busy,
                onClick = {
                    attempted = true
                    if (code.isBlank()) return@TextButton
                    onSave(code.trim(), apartment)
                }
            ) { Text(if (busy) "Guardando..." else "Guardar") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancelar") } }
    )
}
