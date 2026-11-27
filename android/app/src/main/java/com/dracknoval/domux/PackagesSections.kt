@file:OptIn(ExperimentalLayoutApi::class)

package com.dracknoval.domux

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.dracknoval.domux.data.ComplexInfoStore
import com.dracknoval.domux.data.PackageItem
import com.dracknoval.domux.data.PickupCodeData
import com.dracknoval.domux.data.RegisterPackageRequest
import com.dracknoval.domux.data.ResidentSummary
import com.dracknoval.domux.data.Session
import kotlinx.coroutines.delay
import com.dracknoval.domux.ui.theme.DomuxColor

// Pantallas de paquetes: lista, registro, entrega con código y código de entrega del residente
// (HU-047, HU-048 y HU-049). Reciben el estado ya listo y avisan con lambdas; la lógica está
// en PackagesViewModel.

/** Transportadoras frecuentes: un toque llena el campo (se puede escribir cualquier otra). */
private val COMMON_CARRIERS = listOf(
    "Servientrega", "Coordinadora", "Interrapidísimo", "Envía", "TCC", "Deprisa",
    "4-72", "DHL", "Rappi", "Mercado Libre"
)

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PackageListSection(
    modifier: Modifier,
    state: PackagesUiState,
    canRegister: Boolean,
    onStatusFilter: (String?) -> Unit,
    onSearch: (String) -> Unit,
    onRefresh: () -> Unit,
    onScan: () -> Unit,
    onTypePin: () -> Unit,
    onDeliver: (PackageItem) -> Unit,
    onStatusChange: (PackageItem, String) -> Unit,
    onMoveToTrash: (PackageItem) -> Unit,
    onRestore: (PackageItem) -> Unit,
    onCreatePickupCode: (PackageItem) -> Unit,
    // El texto con el que abre la caja de búsqueda (lo deja puesto el buscador general).
    initialSearch: String = ""
) {
    // El texto del buscador vive aquí y el ViewModel recibe el valor ya aplicado, con una pausa
    // de 300 ms para no consultar al servidor en cada letra.
    var searchText by rememberSaveable { mutableStateOf(initialSearch) }
    LaunchedEffect(searchText) {
        if (searchText.isNotBlank()) delay(300)
        onSearch(searchText)
    }
    val filters = buildList<Pair<String, String?>> {
        add("Todos" to null)
        add("En portería" to "pendiente")
        // «Por llegar» solo existe para los paquetes de la unidad: los de los residentes llegan directo a portería.
        if (!Session.isResident) add("Por llegar" to "por_llegar")
        add("Entregados" to "entregado")
        if (canRegister) add("Archivados" to "archivados")
    }
    // Paquetes que llevan más de 48 horas (o las que fije la unidad) esperando en la portería (HU-049, RN-018).
    val rules = ComplexInfoStore.rules
    val unclaimed = state.packages.filter { !it.isDeleted && it.claimAlert != null }
    val unclaimedRed = unclaimed.count { it.claimAlert == "rojo" }
    val filtering = state.statusFilter != null || searchText.isNotBlank()

    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        // El buscador con el botón «Filtros»: el estado del paquete se elige en la hoja.
        val activeFilters = buildList {
            state.statusFilter?.let { status ->
                val label = filters.firstOrNull { it.second == status }?.first ?: status
                add(DomuxActiveFilter("Estado: $label") { onStatusFilter(null) })
            }
        }
        DomuxSearchFilterBar(
            active = activeFilters,
            onClearFilters = { onStatusFilter(null) },
            search = searchText,
            onSearch = { searchText = it },
            searchLabel = "Buscar paquete",
            searchHint = "Residente, apartamento, guía o paquete",
            sheetTitle = "Filtros de paquetes"
        ) {
            DomuxFilterGroup("Estado") {
                filters.forEach { (label, value) ->
                    DomuxFilterOption(label, state.statusFilter == value) { onStatusFilter(value) }
                }
            }
        }
        if (unclaimed.isNotEmpty()) {
            DomuxMessageBanner(
                message = if (canRegister) {
                    "${unclaimed.size} paquete(s) llevan más de ${rules.orangeHours} horas sin reclamar" +
                        if (unclaimedRed > 0) " ($unclaimedRed con más de ${rules.redHours} horas)." else "."
                } else {
                    "Tienes ${unclaimed.size} paquete(s) esperando en la portería hace más de ${rules.orangeHours} horas."
                },
                isError = true
            )
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            TextButton(onClick = onRefresh) { Text("Actualizar registros") }
            if (canRegister) {
                TextButton(onClick = onScan, enabled = !state.busy) { Text("Escanear código de entrega") }
                // Si el QR no se puede leer (pantalla rota, poca luz), el guardia escribe el PIN.
                TextButton(onClick = onTypePin, enabled = !state.busy) { Text("Escribir PIN de entrega") }
            }
        }
        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            if (state.packages.isEmpty()) {
                item {
                    DomuxCard(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                        Column(
                            modifier = Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Text(
                                when {
                                    state.loading -> "Cargando paquetes..."
                                    state.statusFilter == "archivados" ->
                                        "No hay paquetes archivados. Los paquetes no se borran: " +
                                            "quedan guardados aquí y se pueden sacar de «Archivados»."
                                    filtering -> "No hay paquetes que coincidan con el filtro o búsqueda actual."
                                    else -> "Aún no hay paquetes registrados en el sistema."
                                },
                                color = MaterialTheme.colorScheme.onSurface
                            )
                            if (filtering && !state.loading) {
                                TextButton(onClick = {
                                    searchText = ""
                                    onStatusFilter(null)
                                }) { Text("Limpiar filtros y ver todos") }
                            }
                        }
                    }
                }
            }
            items(state.packages, key = { "package-${it.id}" }) { item ->
                PackageCard(
                    item = item,
                    // La administración solo maneja los paquetes de la unidad; los de los residentes solo los consulta.
                    canRegister = canRegister && (!Session.isAdmin || item.forUnit),
                    busy = state.busy,
                    onDeliver = { onDeliver(item) },
                    onStatusChange = { onStatusChange(item, it) },
                    onMoveToTrash = { onMoveToTrash(item) },
                    onRestore = { onRestore(item) },
                    onCreatePickupCode = { onCreatePickupCode(item) }
                )
            }
        }
    }
}

@Composable
private fun PackageCard(
    item: PackageItem,
    canRegister: Boolean,
    busy: Boolean,
    onDeliver: () -> Unit,
    onStatusChange: (String) -> Unit,
    onMoveToTrash: () -> Unit,
    onRestore: () -> Unit,
    onCreatePickupCode: () -> Unit
) {
    DomuxCard(Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Text(item.description.orEmpty(), style = MaterialTheme.typography.titleMedium)
            Text("Para: ${item.residentName.orEmpty()} · ${item.apartment.orEmpty()}")
            // Transportadora y número de guía (HU-047).
            val shipping = listOfNotNull(
                item.carrier?.takeIf { it.isNotBlank() },
                item.trackingNumber?.takeIf { it.isNotBlank() }?.let { "Guía $it" }
            )
            if (shipping.isNotEmpty()) {
                Text("Envío: ${shipping.joinToString(" · ")}")
            }
            val statusLabel = when (item.status) {
                "por_llegar" -> "Por llegar"
                "pendiente" -> "En portería"
                else -> "Entregado"
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(whenText(item.createdAt), style = MaterialTheme.typography.bodySmall)
                if (item.isDeleted) {
                    DomuxStatusBadge("Archivado", DomuxBadgeTone.PROGRESS)
                } else {
                    DomuxStatusBadge(
                        statusLabel,
                        if (item.status == "entregado") DomuxBadgeTone.SUCCESS
                        else DomuxBadgeTone.PROGRESS
                    )
                }
            }
            // Cuánto lleva esperando y la alerta naranja y roja (48 y 72 horas por defecto, HU-049).
            if (item.status == "pendiente" && !item.isDeleted) {
                item.hoursWaiting?.let { hours ->
                    Text(
                        "En portería hace ${durationText(hours * 60)}",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
                when (item.claimAlert) {
                    "rojo" -> DomuxStatusBadge("Más de ${ComplexInfoStore.rules.redHours} h sin reclamar", DomuxBadgeTone.ALERT)
                    "naranja" -> DomuxStatusBadge("Más de ${ComplexInfoStore.rules.orangeHours} h sin reclamar", DomuxBadgeTone.PROGRESS)
                }
                if (item.hasPickupCode) {
                    DomuxStatusBadge("Código de entrega generado", DomuxBadgeTone.SUCCESS)
                }
            }
            if (item.eventDate != null || item.eventTime != null) {
                Text("Registro: ${item.eventDate.orEmpty()} ${item.eventTime.orEmpty()}")
            }
            MediaAttachmentChip(item.mediaUrl, item.mediaType, "Foto del paquete")
            if (item.status == "entregado" && !item.deliveredTo.isNullOrBlank()) {
                Text("Recibido por: ${item.deliveredTo}")
            }
            if (canRegister) {
                if (item.isDeleted) {
                    // Los paquetes nunca se borran para siempre (DEC-090): solo se sacan de «Archivados».
                    TextButton(onClick = onRestore, enabled = !busy) { Text("Sacar de archivados") }
                } else {
                    // Solo lo que espera la unidad se anuncia «por llegar» y se recibe después; un paquete
                    // de un residente ya queda guardado en portería al registrarlo, sin que él lo acepte.
                    if (item.status == "por_llegar" && item.forUnit) {
                        TextButton(onClick = { onStatusChange("pendiente") }, enabled = !busy) {
                            Text("Ya llegó: recibir en portería")
                        }
                    }
                    if (item.status != "entregado") {
                        TextButton(onClick = onDeliver, enabled = !busy) { Text("Marcar entregado") }
                    }
                    TextButton(onClick = onMoveToTrash, enabled = !busy) { Text("Archivar") }
                }
            } else if (item.status == "pendiente" && !item.isDeleted) {
                // El residente genera el código para que otra persona recoja su paquete (HU-048).
                Text(
                    if (item.hasPickupCode) {
                        "Si generas un código nuevo, el anterior deja de servir."
                    } else {
                        "¿Va a recogerlo otra persona? Genera un código y compártelo con ella."
                    },
                    style = MaterialTheme.typography.bodySmall
                )
                TextButton(onClick = onCreatePickupCode, enabled = !busy) {
                    Text(if (item.hasPickupCode) "Generar código nuevo" else "Generar código de entrega")
                }
            }
        }
    }
}

/**
 * Ventana de entrega del guardia (HU-048). Si el paquete se encontró escaneando un código, el QR ya
 * está leído; si no, el guardia puede escribir el PIN de 6 dígitos que le dicte quien recoge. Sin
 * PIN se entiende que lo recoge su dueño y cualquier código generado se anula.
 */
@Composable
fun DeliveryDialog(
    target: DeliveryTarget,
    busy: Boolean,
    error: String?,
    onConfirm: (receivedBy: String, pin: String) -> Unit,
    onDismiss: () -> Unit
) {
    var receiver by rememberSaveable { mutableStateOf("") }
    var pin by rememberSaveable { mutableStateOf("") }
    val item = target.item
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Confirmar entrega") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text("¿A quién se entregó ${item.description.orEmpty()}?")
                Text(
                    "Para: ${item.residentName.orEmpty()} · ${item.apartment.orEmpty()}",
                    style = MaterialTheme.typography.bodySmall
                )
                if (target.scannedCode != null) {
                    Text("✓ Código de entrega correcto. Escribe el nombre de quien recibe.")
                } else if (item.hasPickupCode) {
                    Text(
                        "El residente generó un código de entrega. Si recoge otra persona, pídele el PIN " +
                            "de 6 dígitos (o escanea su QR). Sin PIN se entiende que " +
                            "lo recoge el residente y el código se anula.",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
                OutlinedTextField(
                    value = receiver,
                    onValueChange = { receiver = it },
                    label = { Text("Nombre de quien recibe") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                if (target.scannedCode == null && item.hasPickupCode) {
                    OutlinedTextField(
                        value = pin,
                        onValueChange = { pin = it.filter(Char::isDigit).take(6) },
                        label = { Text("PIN de entrega (si recoge otra persona)") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                if (!error.isNullOrBlank()) {
                    Text("⚠ $error", color = DomuxColor.Bad, style = MaterialTheme.typography.bodySmall)
                }
            }
        },
        confirmButton = {
            TextButton(
                enabled = receiver.isNotBlank() && !busy,
                onClick = { onConfirm(receiver, pin) }
            ) { Text("Registrar entrega") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancelar") }
        }
    )
}

/**
 * Entregar con el PIN cuando el QR no se puede leer (HU-048): el guardia escribe los 6 dígitos que
 * le dicta quien recoge y DOMUX busca de qué paquete es. Después se confirma la entrega como siempre.
 */
@Composable
fun PickupPinDialog(
    busy: Boolean,
    error: String?,
    onSearch: (pin: String) -> Unit,
    onDismiss: () -> Unit
) {
    var pin by rememberSaveable { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Entregar con PIN") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    "Pídele a quien recoge el PIN de 6 dígitos del código de entrega. Sirve cuando el QR no se puede leer.",
                    style = MaterialTheme.typography.bodySmall
                )
                OutlinedTextField(
                    value = pin,
                    onValueChange = { pin = it.filter(Char::isDigit).take(6) },
                    label = { Text("PIN de 6 dígitos") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                    modifier = Modifier.fillMaxWidth()
                )
                if (!error.isNullOrBlank()) {
                    Text("⚠ $error", color = DomuxColor.Bad, style = MaterialTheme.typography.bodySmall)
                }
            }
        },
        confirmButton = {
            TextButton(enabled = pin.length == 6 && !busy, onClick = { onSearch(pin) }) { Text("Buscar paquete") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancelar") } }
    )
}

/** El código de entrega recién generado: QR y PIN, con botones para compartirlos (HU-048). */
@Composable
fun PickupCodeDialog(item: PackageItem, code: PickupCodeData, onDismiss: () -> Unit) {
    val context = LocalContext.current
    val bitmap = rememberQrBitmap(code.qrData)
    var shareError by remember { mutableStateOf<String?>(null) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Código de entrega") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    "Compártelo con quien va a recoger «${item.description.orEmpty()}». La portería le " +
                        "pedirá el QR o el PIN.",
                    style = MaterialTheme.typography.bodyMedium
                )
                QrImage(bitmap, "Código QR de entrega del paquete")
                Text("PIN: ${code.pin}", style = MaterialTheme.typography.headlineMedium)
                Text(
                    "Solo se muestra ahora. Sirve para una entrega y se anula si se digita mal 5 veces; " +
                        "si lo pierdes, genera uno nuevo.",
                    style = MaterialTheme.typography.bodySmall
                )
                shareError?.let {
                    Text("⚠ $it", color = DomuxColor.Bad, style = MaterialTheme.typography.bodySmall)
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    TextButton(onClick = {
                        shareError = if (bitmap == null) {
                            "No se pudo generar la imagen del QR."
                        } else {
                            shareQrImage(
                                context, bitmap, "Compartir código de entrega",
                                "Código para recoger mi paquete en la portería. Si el QR no se puede " +
                                    "escanear, el PIN es ${code.pin}."
                            )
                        }
                    }) { Text("Compartir QR") }
                    TextButton(onClick = {
                        shareError = shareText(
                            context, "Compartir PIN",
                            "PIN para recoger mi paquete en la portería: ${code.pin}"
                        )
                    }) { Text("Compartir PIN") }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Cerrar") } }
    )
}

@Composable
fun PackageRegistrationSection(
    modifier: Modifier,
    busy: Boolean,
    onMessage: (String) -> Unit,
    onRegister: (request: RegisterPackageRequest, onSuccess: () -> Unit) -> Unit,
    onRegistered: () -> Unit,
    // La administración solo registra paquetes de la unidad: sin residente y, casi siempre, «por llegar».
    forUnit: Boolean = false
) {
    var resident by remember { mutableStateOf<ResidentSummary?>(null) }
    var description by rememberSaveable { mutableStateOf("") }
    var carrier by rememberSaveable { mutableStateOf("") }
    var tracking by rememberSaveable { mutableStateOf("") }
    var status by rememberSaveable { mutableStateOf(if (forUnit) "por_llegar" else "pendiente") }
    var date by rememberSaveable { mutableStateOf("") }
    var time by rememberSaveable { mutableStateOf("") }
    var mediaUrl by remember { mutableStateOf<String?>(null) }
    var mediaType by remember { mutableStateOf<String?>(null) }
    var mediaName by remember { mutableStateOf<String?>(null) }
    var attempted by rememberSaveable { mutableStateOf(false) }
    var confirming by remember { mutableStateOf(false) }

    Column(
        modifier = modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        DomuxCard(Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                if (forUnit) {
                    Text("Paquete para la unidad", style = MaterialTheme.typography.titleMedium)
                    Text(
                        "Repuestos, materiales, plantas, herramientas u otras cosas para las zonas comunes. " +
                            "La portería lo verá como esperado y lo recibirá. Los paquetes de los residentes los registra la portería.",
                        style = MaterialTheme.typography.bodySmall
                    )
                } else {
                    Text("Registrar paquete", style = MaterialTheme.typography.titleMedium)
                    DomuxResidentSearchField(resident, { resident = it })
                }
                OutlinedTextField(
                    value = description,
                    onValueChange = { description = it },
                    label = { Text("Descripción *") },
                    isError = attempted && description.isBlank(),
                    supportingText = {
                        if (attempted && description.isBlank()) Text("La descripción es obligatoria")
                    },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                // Transportadora y guía (HU-047): ayudan a ubicar el paquete y a reclamarlo.
                OutlinedTextField(
                    value = carrier,
                    onValueChange = { carrier = it },
                    label = { Text("Transportadora (opcional)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    COMMON_CARRIERS.forEach { name ->
                        FilterChip(
                            selected = carrier.trim().equals(name, ignoreCase = true),
                            onClick = { carrier = name },
                            label = { Text(name) }
                        )
                    }
                }
                OutlinedTextField(
                    value = tracking,
                    onValueChange = { tracking = it },
                    label = { Text("Número de guía (opcional)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                if (forUnit) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterChip(
                            selected = status == "pendiente",
                            onClick = { status = "pendiente" },
                            label = { Text("Ya está en portería") }
                        )
                        FilterChip(
                            selected = status == "por_llegar",
                            onClick = { status = "por_llegar" },
                            label = { Text("Por llegar") }
                        )
                    }
                } else {
                    // El paquete de un residente queda guardado en portería al registrarlo: no necesita su
                    // aceptación. La app le avisa para que pase a recogerlo.
                    Text(
                        "Queda guardado en portería y la app le avisa al residente para que pase a recogerlo.",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
                DatePickerField("Fecha del paquete", date, { date = it })
                TimePickerField("Hora del paquete", time) { time = it }
                MediaAttachmentPicker(
                    mediaName,
                    { url, type, name ->
                        mediaUrl = url
                        mediaType = type
                        mediaName = name
                    },
                    onMessage,
                    kinds = AttachmentKinds.PHOTO,
                    onClear = { mediaUrl = null; mediaType = null; mediaName = null }
                )
                Button(
                    onClick = {
                        attempted = true
                        if ((!forUnit && resident == null) || description.isBlank()) {
                            onMessage(
                                if (forUnit) "Escribe qué es lo que llega." else "Selecciona residente y escribe la descripción del paquete."
                            )
                        } else {
                            confirming = true
                        }
                    },
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth()
                ) { Text("Registrar paquete") }
            }
        }
    }

    if (confirming) {
        DomuxConfirmDialog(
            title = "¿Estás seguro de confirmar esta acción?",
            message = "¿Estás seguro de guardar este paquete?",
            confirmLabel = "Confirmar",
            onConfirm = {
                confirming = false
                val target = resident
                if (forUnit || target != null) {
                    val request = RegisterPackageRequest(
                        residentId = if (forUnit) null else target?.id,
                        // Los de los residentes siempre quedan en portería.
                        description = description.trim(),
                        mediaUrl = mediaUrl,
                        mediaType = mediaType,
                        eventDate = date.ifBlank { null },
                        eventTime = time.ifBlank { null },
                        status = if (forUnit) status else "pendiente",
                        carrier = carrier.trim().ifEmpty { null },
                        trackingNumber = tracking.trim().ifEmpty { null }
                    )
                    onRegister(request) {
                        // Salió bien: el formulario queda limpio y se vuelve a la lista.
                        resident = null
                        description = ""
                        carrier = ""
                        tracking = ""
                        date = ""
                        time = ""
                        mediaUrl = null
                        mediaType = null
                        mediaName = null
                        attempted = false
                        onRegistered()
                    }
                }
            },
            onDismiss = { confirming = false }
        )
    }
}
