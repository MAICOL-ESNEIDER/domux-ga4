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
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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

/**
 * «Datos de la unidad y zonas comunes» de la administración en la app: lo mismo que la web tiene en
 * «Datos de la unidad» y «Zonas comunes y reglas» (nombre, NIT, dirección y teléfono de portería; y
 * por cada zona su horario, aforo y anticipación, y cerrarla o reabrirla). El logo se cambia en la web.
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
                attempt("No se pudieron guardar las reglas de ${zone.name}") { api.updateCommonAreaRules(auth(), zone.id, changes) }
            } ?: return@launch
            showSuccess("Reglas de ${zone.name} guardadas.")
            onSuccess()
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
            Text(
                "Crear o retirar zonas y el resto de reglas (días de mantenimiento, franjas seguidas) se hace en la web, en «Zonas comunes y reglas».",
                style = MaterialTheme.typography.bodySmall,
                color = DomuxColor.TextMuted
            )
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
                                zone.capacity?.let { "aforo $it" },
                                "reservar con ${zone.minAdvanceDays} a ${zone.maxAdvanceDays} días"
                            ).joinToString(" · "),
                            style = MaterialTheme.typography.bodySmall
                        )
                        zone.closedReason?.takeIf { zone.isClosed }?.let { Text("Motivo: $it", style = MaterialTheme.typography.bodySmall) }
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(onClick = { editing = zone }, enabled = !state.busy) { Text("Cambiar reglas") }
                            if (zone.isClosed) {
                                Button(onClick = { viewModel.openZone(zone) }, enabled = !state.busy) { Text("Reabrir") }
                            } else {
                                TextButton(onClick = { closing = zone }, enabled = !state.busy) { Text("Cerrar") }
                            }
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

@Composable
private fun ZoneRulesDialog(zone: CommonArea, busy: Boolean, onDismiss: () -> Unit, onSave: (Map<String, Any?>) -> Unit) {
    var open by remember(zone.id) { mutableStateOf(zone.openTime.orEmpty()) }
    var close by remember(zone.id) { mutableStateOf(zone.closeTime.orEmpty()) }
    var capacity by remember(zone.id) { mutableStateOf(zone.capacity?.toString().orEmpty()) }
    var minDays by remember(zone.id) { mutableStateOf(zone.minAdvanceDays.toString()) }
    var maxDays by remember(zone.id) { mutableStateOf(zone.maxAdvanceDays.toString()) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Reglas de ${zone.name}") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                TimePickerField("Abre a las", open) { open = it }
                TimePickerField("Cierra a las", close) { close = it }
                NumberField("Aforo (vacío = sin límite)", capacity) { capacity = it }
                NumberField("Días mínimos de anticipación", minDays) { minDays = it }
                NumberField("Días máximos de anticipación", maxDays) { maxDays = it }
            }
        },
        confirmButton = {
            TextButton(enabled = !busy, onClick = {
                onSave(
                    buildMap {
                        if (open.isNotBlank()) put("openTime", open)
                        if (close.isNotBlank()) put("closeTime", close)
                        put("capacity", capacity.toIntOrNull())
                        minDays.toIntOrNull()?.let { put("minAdvanceDays", it) }
                        maxDays.toIntOrNull()?.let { put("maxAdvanceDays", it) }
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
