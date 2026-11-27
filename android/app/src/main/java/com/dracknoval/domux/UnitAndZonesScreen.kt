@file:OptIn(ExperimentalLayoutApi::class)

package com.dracknoval.domux

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.dracknoval.domux.data.CommonArea
import com.dracknoval.domux.data.ComplexInfo
import com.dracknoval.domux.data.ComplexInfoStore
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.ui.theme.DomuxColor
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import okhttp3.MediaType
import okhttp3.RequestBody
import org.json.JSONObject

/** Un cuerpo JSON que sí lleva los valores vacíos (null), por ejemplo «capacity: null» = sin aforo. */
fun jsonBody(values: Map<String, Any?>): RequestBody {
    val json = JSONObject()
    values.forEach { (key, value) -> json.put(key, value ?: JSONObject.NULL) }
    // La versión de OkHttp que trae Retrofit usa todavía RequestBody.create(MediaType, String).
    return RequestBody.create(MediaType.parse("application/json; charset=utf-8"), json.toString())
}

/**
 * «Datos de la unidad y zonas comunes» de la administración en la app: lo mismo que la web tiene en
 * «Datos de la unidad» y «Zonas comunes y reglas» (nombre, NIT, dirección y teléfono de portería; y
 * todas las reglas de cada zona, crear zonas nuevas, cerrarlas, reabrirlas y retirarlas). El logo se
 * cambia en la web porque se sube como archivo.
 */
data class UnitAndZonesUiState(
    val info: ComplexInfo? = null,
    val zones: List<CommonArea> = emptyList(),
    val loading: Boolean = true,
    val busy: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false
)

class UnitAndZonesViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(UnitAndZonesUiState())
    val state: StateFlow<UnitAndZonesUiState> = _state.asStateFlow()

    init {
        refresh()
    }

    override fun postMessage(text: String, isError: Boolean) {
        _state.update { it.copy(message = text, messageIsError = isError) }
    }

    override fun setBusy(busy: Boolean) {
        _state.update { it.copy(busy = busy) }
    }

    fun dismissMessage() {
        _state.update { it.copy(message = "") }
    }

    fun refresh() {
        viewModelScope.launch {
            _state.update { it.copy(loading = true) }
            val info = attempt("No se pudieron cargar los datos de la unidad") { api.getComplexInfo(auth()) }?.body()?.unit
            val zones = attempt("No se pudieron cargar las zonas comunes") { api.getCommonAreas(auth()) }?.body()?.areas.orEmpty()
            _state.update { it.copy(loading = false, info = info ?: it.info, zones = zones) }
        }
    }

    fun saveInfo(name: String, nit: String, address: String, portalPhone: String) {
        viewModelScope.launch {
            withBusy {
                attempt("No se pudieron guardar los datos de la unidad") {
                    api.updateComplexInfo(
                        auth(),
                        mapOf(
                            "name" to name.trim(),
                            "nit" to nit.trim().ifBlank { null },
                            "address" to address.trim().ifBlank { null },
                            "portalPhone" to phoneToSend(portalPhone).ifBlank { null }
                        )
                    )
                }
            }?.body()?.unit?.let { saved ->
                _state.update { it.copy(info = saved) }
                showSuccess("Datos de la unidad guardados.")
                ComplexInfoStore.refresh()
            }
        }
    }

    fun saveZone(zone: CommonArea, changes: Map<String, Any?>, onSuccess: () -> Unit) {
        viewModelScope.launch {
            withBusy {
                attempt("No se pudieron guardar las reglas de ${zone.name}") {
                    api.updateCommonAreaRules(auth(), zone.id, jsonBody(changes))
                }
            } ?: return@launch
            showSuccess("Reglas de ${changes["name"] ?: zone.name} guardadas.")
            onSuccess()
            refresh()
        }
    }

    fun createZone(changes: Map<String, Any?>, onSuccess: () -> Unit) {
        viewModelScope.launch {
            withBusy { attempt("No se pudo crear la zona") { api.createCommonArea(auth(), jsonBody(changes)) } } ?: return@launch
            showSuccess("Zona «${changes["name"]}» creada. Ya se puede reservar.")
            onSuccess()
            refresh()
        }
    }

    /** Retira la zona (no se borra: deja de ofrecerse). Con reservas próximas el servidor no deja. */
    fun retireZone(zone: CommonArea) {
        viewModelScope.launch {
            withBusy { attempt("No se pudo retirar ${zone.name}") { api.retireCommonArea(auth(), zone.id) } } ?: return@launch
            showSuccess("${zone.name} quedó retirada: ya no se ofrece para reservar.")
            refresh()
        }
    }

    fun closeZone(zone: CommonArea, reason: String, onSuccess: () -> Unit) {
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo cerrar ${zone.name}") { api.closeCommonArea(auth(), zone.id, mapOf("reason" to reason.trim())) }
            } ?: return@launch
            showSuccess("${zone.name} quedó cerrada. Los residentes ven el motivo.")
            onSuccess()
            refresh()
        }
    }

    fun openZone(zone: CommonArea) {
        viewModelScope.launch {
            withBusy { attempt("No se pudo reabrir ${zone.name}") { api.openCommonArea(auth(), zone.id) } } ?: return@launch
            showSuccess("${zone.name} quedó abierta otra vez.")
            refresh()
        }
    }
}

@Composable
fun UnitAndZonesScreen(navController: NavController, viewModel: UnitAndZonesViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()
    var editing by remember { mutableStateOf<CommonArea?>(null) }
    var closing by remember { mutableStateOf<CommonArea?>(null) }
    var creating by remember { mutableStateOf(false) }
    var retiring by remember { mutableStateOf<CommonArea?>(null) }

    DomuxScreenScaffold(title = "Datos de la unidad y zonas", navController = navController) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            if (state.message.isNotBlank()) {
                DomuxMessageBanner(state.message, state.messageIsError) { viewModel.dismissMessage() }
            }
            if (state.loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            UnitInfoCard(state.info, state.busy) { name, nit, address, phone -> viewModel.saveInfo(name, nit, address, phone) }

            Text("Zonas comunes (${state.zones.size})", style = MaterialTheme.typography.titleMedium)
            Button(onClick = { creating = true }, enabled = !state.busy, modifier = Modifier.fillMaxWidth()) {
                Text("Agregar una zona común")
            }
            state.zones.forEach { zone ->
                DomuxCard(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(zone.name, style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
                            if (zone.isClosed) DomuxStatusBadge("Cerrada", DomuxBadgeTone.ALERT)
                            else DomuxStatusBadge("Abierta", DomuxBadgeTone.SUCCESS)
                        }
                        Text(
                            listOfNotNull(
                                "Horario ${clockText(zone.openTime)} a ${clockText(zone.closeTime)}",
                                "franjas de ${zone.slotMinutes} min",
                                zone.capacity?.let { "aforo $it" } ?: "sin aforo",
                                "reservar con ${zone.minAdvanceDays} a ${zone.maxAdvanceDays} días",
                                "hasta ${zone.weeklyLimit} por semana",
                                zone.maintenanceWeekday?.let { "mantenimiento los ${WEEKDAYS[it]}" },
                                if (zone.allowFullDay) "se puede el día completo" else null
                            ).joinToString(" · "),
                            style = MaterialTheme.typography.bodySmall
                        )
                        zone.closedReason?.takeIf { zone.isClosed }?.let { Text("Motivo: $it", style = MaterialTheme.typography.bodySmall) }
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            OutlinedButton(onClick = { editing = zone }, enabled = !state.busy) { Text("Cambiar reglas") }
                            if (zone.isClosed) {
                                Button(onClick = { viewModel.openZone(zone) }, enabled = !state.busy) { Text("Reabrir") }
                            } else {
                                TextButton(onClick = { closing = zone }, enabled = !state.busy) { Text("Cerrar") }
                            }
                            TextButton(onClick = { retiring = zone }, enabled = !state.busy) { Text("Retirar") }
                        }
                    }
                }
            }
        }
    }

    editing?.let { zone ->
        ZoneRulesDialog(zone, state.busy, onDismiss = { editing = null }) { changes ->
            viewModel.saveZone(zone, changes) { editing = null }
        }
    }
    if (creating) {
        ZoneRulesDialog(null, state.busy, onDismiss = { creating = false }) { changes ->
            viewModel.createZone(changes) { creating = false }
        }
    }
    retiring?.let { zone ->
        AlertDialog(
            onDismissRequest = { retiring = null },
            title = { Text("Retirar ${zone.name}") },
            text = {
                Text(
                    "La zona deja de ofrecerse para reservar (no se borra: su historial queda). " +
                        "Si tiene reservas próximas, primero cancélalas desde Reservas."
                )
            },
            confirmButton = {
                TextButton(enabled = !state.busy, onClick = { viewModel.retireZone(zone); retiring = null }) { Text("Retirar") }
            },
            dismissButton = { TextButton(onClick = { retiring = null }) { Text("Cancelar") } }
        )
    }
    closing?.let { zone ->
        var reason by remember(zone.id) { mutableStateOf("") }
        AlertDialog(
            onDismissRequest = { closing = null },
            title = { Text("Cerrar ${zone.name}") },
            text = {
                OutlinedTextField(
                    value = reason,
                    onValueChange = { reason = it.take(200) },
                    label = { Text("Motivo que verán los residentes *") },
                    modifier = Modifier.fillMaxWidth()
                )
            },
            confirmButton = {
                TextButton(enabled = reason.isNotBlank() && !state.busy, onClick = { viewModel.closeZone(zone, reason) { closing = null } }) {
                    Text("Cerrar la zona")
                }
            },
            dismissButton = { TextButton(onClick = { closing = null }) { Text("Cancelar") } }
        )
    }
}

@Composable
private fun UnitInfoCard(info: ComplexInfo?, busy: Boolean, onSave: (String, String, String, String) -> Unit) {
    var name by rememberSaveable(info?.updatedAt) { mutableStateOf(info?.name.orEmpty()) }
    var nit by rememberSaveable(info?.updatedAt) { mutableStateOf(info?.nit.orEmpty()) }
    var address by rememberSaveable(info?.updatedAt) { mutableStateOf(info?.address.orEmpty()) }
    var phone by rememberSaveable(info?.updatedAt) { mutableStateOf(info?.portalPhone.orEmpty()) }
    LaunchedEffect(info) {
        if (info != null && name.isBlank()) {
            name = info.name.orEmpty(); nit = info.nit.orEmpty(); address = info.address.orEmpty(); phone = info.portalPhone.orEmpty()
        }
    }
    DomuxCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Datos de la unidad", style = MaterialTheme.typography.titleMedium)
            OutlinedTextField(name, { name = it.take(120) }, label = { Text("Nombre *") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(nit, { nit = it.take(25) }, label = { Text("NIT (opcional)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(address, { address = it.take(200) }, label = { Text("Dirección (opcional)") }, modifier = Modifier.fillMaxWidth())
            DomuxPhoneField(phone, { phone = it }, error = null)
            Text("El teléfono es el de la portería: lo ven los residentes para llamar.", style = MaterialTheme.typography.bodySmall)
            Button(onClick = { onSave(name, nit, address, phone) }, enabled = !busy && name.isNotBlank(), modifier = Modifier.fillMaxWidth()) {
                Text("Guardar datos de la unidad")
            }
        }
    }
}

private val WEEKDAYS = listOf("lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos")
private val SLOT_MINUTES = listOf(30, 60, 90, 120, 180, 240)

@OptIn(ExperimentalLayoutApi::class)
/** Todas las reglas de una zona. Con zone = null es para crear una nueva (lo vacío queda por defecto). */
@Composable
private fun ZoneRulesDialog(zone: CommonArea?, busy: Boolean, onDismiss: () -> Unit, onSave: (Map<String, Any?>) -> Unit) {
    val key = zone?.id ?: -1
    var name by remember(key) { mutableStateOf(zone?.name.orEmpty()) }
    var open by remember(key) { mutableStateOf(zone?.openTime ?: "08:00") }
    var close by remember(key) { mutableStateOf(zone?.closeTime ?: "22:00") }
    var slot by remember(key) { mutableStateOf(zone?.slotMinutes?.takeIf { it > 0 } ?: 120) }
    var capacity by remember(key) { mutableStateOf(zone?.capacity?.toString().orEmpty()) }
    var minDays by remember(key) { mutableStateOf((zone?.minAdvanceDays ?: 0).toString()) }
    var maxDays by remember(key) { mutableStateOf((zone?.maxAdvanceDays ?: 60).toString()) }
    var cancelDays by remember(key) { mutableStateOf((zone?.cancelDeadlineDays ?: 3).toString()) }
    var weekly by remember(key) { mutableStateOf((zone?.weeklyLimit ?: 2).toString()) }
    var maintenance by remember(key) { mutableStateOf(zone?.maintenanceWeekday) }
    var consecutive by remember(key) { mutableStateOf((zone?.maxConsecutiveSlots ?: 1).toString()) }
    var fullDay by remember(key) { mutableStateOf(zone?.allowFullDay ?: false) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (zone == null) "Nueva zona común" else "Reglas de ${zone.name}") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(name, { name = it.take(100) }, label = { Text("Nombre *") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                TimePickerField("Abre a las", open) { open = it }
                TimePickerField("Cierra a las", close) { close = it }
                Text("Duración de cada franja", style = MaterialTheme.typography.labelLarge)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    SLOT_MINUTES.forEach { minutes ->
                        FilterChip(selected = slot == minutes, onClick = { slot = minutes }, label = { Text("$minutes min") })
                    }
                }
                NumberField("Aforo (vacío = sin límite)", capacity) { capacity = it }
                NumberField("Días mínimos de anticipación (0 a 30)", minDays) { minDays = it }
                NumberField("Días máximos de anticipación (1 a 365)", maxDays) { maxDays = it }
                NumberField("Días antes para cancelar sin problema", cancelDays) { cancelDays = it }
                NumberField("Reservas por semana por apartamento", weekly) { weekly = it }
                NumberField("Franjas seguidas que se pueden reservar", consecutive) { consecutive = it }
                Text("Día de mantenimiento (cerrada)", style = MaterialTheme.typography.labelLarge)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    FilterChip(selected = maintenance == null, onClick = { maintenance = null }, label = { Text("Ninguno") })
                    WEEKDAYS.forEachIndexed { index, day ->
                        FilterChip(selected = maintenance == index, onClick = { maintenance = index }, label = { Text(day) })
                    }
                }
                FilterChip(
                    selected = fullDay,
                    onClick = { fullDay = !fullDay },
                    label = { Text(if (fullDay) "Se puede reservar el día completo" else "No se reserva el día completo") }
                )
            }
        },
        confirmButton = {
            TextButton(enabled = !busy && name.trim().length >= 2, onClick = {
                onSave(
                    buildMap {
                        put("name", name.trim())
                        put("openTime", open)
                        put("closeTime", close)
                        put("slotMinutes", slot)
                        put("capacity", capacity.toIntOrNull())
                        minDays.toIntOrNull()?.let { put("minAdvanceDays", it) }
                        maxDays.toIntOrNull()?.let { put("maxAdvanceDays", it) }
                        cancelDays.toIntOrNull()?.let { put("cancelDeadlineDays", it) }
                        weekly.toIntOrNull()?.let { put("weeklyLimit", it) }
                        consecutive.toIntOrNull()?.let { put("maxConsecutiveSlots", it) }
                        put("maintenanceWeekday", maintenance)
                        put("allowFullDay", fullDay)
                    }
                )
            }) { Text(if (busy) "Guardando..." else "Guardar") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancelar") } }
    )
}

@Composable
private fun NumberField(label: String, value: String, onValue: (String) -> Unit) {
    OutlinedTextField(
        value = value,
        onValueChange = { onValue(it.filter(Char::isDigit).take(4)) },
        label = { Text(label) },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        singleLine = true,
        modifier = Modifier.fillMaxWidth()
    )
}
