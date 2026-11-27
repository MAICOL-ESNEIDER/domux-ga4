package com.dracknoval.domux

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.dracknoval.domux.data.PackageItem
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Visit
import com.dracknoval.domux.data.VisitorVehicleEntryData
import com.dracknoval.domux.ui.theme.DomuxColor
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Lo de hoy en la portería: quién entró, qué paquetes llegaron y se entregaron y qué vehículos entraron. */
data class GuardActivityUiState(
    val visits: List<Visit> = emptyList(),
    val received: List<PackageItem> = emptyList(),
    val delivered: List<PackageItem> = emptyList(),
    val vehicles: List<VisitorVehicleEntryData> = emptyList(),
    val loading: Boolean = true,
    val busy: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false
)

class GuardActivityViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(GuardActivityUiState())
    val state: StateFlow<GuardActivityUiState> = _state.asStateFlow()

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
            val today = colombiaToday()
            val visits = attempt("No se pudieron cargar las visitas de hoy") {
                api.getVisitsSummary(auth(), dateFrom = today, pageSize = 50)
            }?.body()?.visits.orEmpty()
            val waiting = attempt("No se pudieron cargar los paquetes") {
                api.getPackagesSummary(auth(), status = "pendiente", pageSize = 50)
            }?.body()?.packages.orEmpty()
            val delivered = attempt("No se pudieron cargar los paquetes entregados") {
                api.getPackagesSummary(auth(), status = "entregado", pageSize = 50)
            }?.body()?.packages.orEmpty()
            val vehicles = attempt("No se pudieron cargar los vehículos") {
                api.getVehicleEntries(auth(), pageSize = 50)
            }?.body()?.vehicleEntries.orEmpty()
            _state.update {
                it.copy(
                    loading = false,
                    visits = visits.filter { visit -> isToday(visit.enteredAt, today) || isToday(visit.exitedAt, today) },
                    received = waiting.filter { item -> isToday(item.arrivedAt, today) },
                    delivered = delivered.filter { item -> isToday(item.deliveredAt, today) },
                    vehicles = vehicles.filter { entry -> isToday(entry.enteredAt, today) || isToday(entry.exitedAt, today) }
                )
            }
        }
    }
}

/** Si un momento del servidor («2026-11-27 14:30») es de hoy. */
fun isToday(moment: String?, today: String = colombiaToday()): Boolean = moment?.startsWith(today) == true

@Composable
fun GuardActivityScreen(navController: NavController, viewModel: GuardActivityViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()
    DomuxScreenScaffold(title = "Entradas y entregas de hoy", navController = navController) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            if (state.message.isNotBlank()) {
                DomuxMessageBanner(state.message, state.messageIsError) { viewModel.dismissMessage() }
            }
            if (state.loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            OutlinedButton(onClick = { viewModel.refresh() }, modifier = Modifier.fillMaxWidth()) { Text("Actualizar") }

            ActivitySection("Visitas que entraron o salieron (${state.visits.size})", state.visits.isEmpty(), "Hoy no ha entrado nadie.") {
                state.visits.forEach { visit ->
                    ActivityLine(
                        visit.visitorName,
                        listOfNotNull(
                            visit.apartment,
                            visit.enteredAt?.let { "entró ${whenText(it)}" },
                            visit.exitedAt?.let { "salió ${whenText(it)}" }
                        ).joinToString(" · ")
                    )
                }
            }
            ActivitySection("Paquetes recibidos (${state.received.size})", state.received.isEmpty(), "Hoy no han llegado paquetes.") {
                state.received.forEach { item ->
                    ActivityLine(
                        item.description.orEmpty().ifBlank { "Paquete" },
                        listOfNotNull(item.apartment, item.carrier, item.arrivedAt?.let { "llegó ${whenText(it)}" }).joinToString(" · ")
                    )
                }
            }
            ActivitySection("Paquetes entregados (${state.delivered.size})", state.delivered.isEmpty(), "Hoy no se han entregado paquetes.") {
                state.delivered.forEach { item ->
                    ActivityLine(
                        item.description.orEmpty().ifBlank { "Paquete" },
                        listOfNotNull(
                            item.apartment,
                            item.deliveredTo?.let { "a $it" },
                            item.deliveredAt?.let { whenText(it) }
                        ).joinToString(" · ")
                    )
                }
            }
            ActivitySection("Vehículos de visitantes (${state.vehicles.size})", state.vehicles.isEmpty(), "Hoy no han entrado vehículos de visitantes.") {
                state.vehicles.forEach { entry ->
                    ActivityLine(
                        entry.plate,
                        listOfNotNull(
                            entry.apartment,
                            entry.spotCode?.let { "parqueadero $it" },
                            entry.enteredAt?.let { "entró ${whenText(it)}" },
                            entry.exitedAt?.let { "salió ${whenText(it)}" }
                        ).joinToString(" · ")
                    )
                }
            }
        }
    }
}

@Composable
private fun ActivitySection(title: String, empty: Boolean, emptyText: String, content: @Composable () -> Unit) {
    DomuxCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            if (empty) Text(emptyText, color = DomuxColor.TextMuted) else content()
        }
    }
}

@Composable
private fun ActivityLine(title: String, detail: String) {
    Column {
        Text(title, style = MaterialTheme.typography.bodyLarge)
        if (detail.isNotBlank()) Text(detail, style = MaterialTheme.typography.bodySmall, color = DomuxColor.TextMuted)
    }
}
