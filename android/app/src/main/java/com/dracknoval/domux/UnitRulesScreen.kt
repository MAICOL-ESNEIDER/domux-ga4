package com.dracknoval.domux

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.dracknoval.domux.ui.theme.DomuxColor

/** Una regla con número: cómo se llama, en qué se mide y entre qué valores puede quedar (los mismos del servidor). */
private data class RuleField(val key: String, val label: String, val unit: String, val min: Int, val max: Int)

private data class RuleGroup(val title: String, val note: String, val fields: List<RuleField>)

private val ruleGroups = listOf(
    RuleGroup(
        "PQRS", "El plazo corre en días hábiles: no cuentan sábados, domingos ni festivos.",
        listOf(
            RuleField("pqrsTermDays", "Plazo para responder una PQRS", "días hábiles", 1, 90),
            RuleField("pqrsWarningDays", "Aviso amarillo (días por vencer)", "días hábiles", 1, 30)
        )
    ),
    RuleGroup(
        "Paquetes", "Cuántas horas puede esperar un paquete en portería antes de avisar.",
        listOf(
            RuleField("packageOrangeHours", "Aviso naranja de un paquete sin reclamar", "horas", 1, 720),
            RuleField("packageRedHours", "Aviso rojo de un paquete sin reclamar", "horas", 2, 1440),
            RuleField("deliveredArchiveDays", "Días para archivar un paquete entregado", "días", 1, 90)
        )
    ),
    RuleGroup(
        "Visitas y códigos QR", "Límites para las visitas y los QR que crean los residentes.",
        listOf(
            RuleField("visitMaxStayDays", "Estadía máxima de una visita", "días", 1, 90),
            RuleField("qrMaxPeople", "Personas por QR", "personas", 1, 20),
            RuleField("qrMaxValidDays", "Vigencia máxima de un QR", "días", 1, 90),
            RuleField("autoQrMinStayDays", "Estadía desde la que el QR se crea solo", "días", 1, 30)
        )
    ),
    RuleGroup(
        "Parqueaderos de visitantes", "Cuánto tiempo y cuántos vehículos caben.",
        listOf(
            RuleField("visitorParkingMaxDays", "Tiempo máximo de un vehículo visitante", "días", 1, 30),
            RuleField("motosPerCarSpot", "Motos por parqueadero de carro", "motos", 1, 10)
        )
    )
)

/**
 * Reglas de la unidad (solo administración): los mismos plazos y límites que se cambian en la web. Lo que
 * se guarda rige desde ese momento en toda la app y la web. La pantalla solo dibuja lo que le da
 * [UnitRulesViewModel].
 */
@Composable
fun UnitRulesScreen(navController: NavController, viewModel: UnitRulesViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()

    DomuxScreenScaffold(title = "Reglas de la unidad", navController = navController) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            if (state.loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            DomuxMessageBanner(state.message, state.messageIsError) { viewModel.dismissMessage() }
            Text(
                "Cambia los plazos y límites de tu unidad según el manual de convivencia o lo que decida el consejo. " +
                    "Cada cambio rige desde que lo guardas, también para lo que ya existe.",
                color = DomuxColor.TextSoft,
                style = MaterialTheme.typography.bodyMedium
            )
            state.updatedLine?.let {
                Text(it, color = DomuxColor.TextMuted, style = MaterialTheme.typography.bodySmall)
            }

            ruleGroups.forEach { group ->
                Text(
                    group.title,
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.semantics { heading() }
                )
                Text(group.note, color = DomuxColor.TextMuted, style = MaterialTheme.typography.bodySmall)
                DomuxCard(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        group.fields.forEach { field ->
                            RuleNumberField(field, state, viewModel)
                        }
                    }
                }
                if (group.title == "PQRS") CategoryTerms(state, viewModel)
            }

            Button(
                onClick = { viewModel.save() },
                enabled = !state.busy && state.changed,
                modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)
            ) { Text(if (state.busy) "Guardando..." else "Guardar cambios") }
        }
    }
}

@Composable
private fun RuleNumberField(field: RuleField, state: UnitRulesUiState, viewModel: UnitRulesViewModel) {
    val default = state.defaults[field.key]
    val custom = field.key in state.customized
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        OutlinedTextField(
            value = state.values[field.key].orEmpty(),
            onValueChange = { viewModel.setValue(field.key, it) },
            label = { Text(field.label) },
            suffix = { Text(field.unit) },
            supportingText = {
                Text(
                    "Entre ${field.min} y ${field.max}" +
                        (default?.let { " · valor de DOMUX: $it" } ?: "") +
                        if (custom) " · cambiada por la administración" else ""
                )
            },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            modifier = Modifier.fillMaxWidth()
        )
        val shown = state.values[field.key].orEmpty()
        if (default != null && shown != default.toString()) {
            OutlinedButton(
                onClick = { viewModel.useDefault(field.key) },
                modifier = Modifier.fillMaxWidth().heightIn(min = 44.dp)
            ) { Text("Poner el valor de DOMUX ($default)") }
        }
    }
}

/** Plazo propio de cada tipo de PQRS; vacío significa que usa el plazo general. */
@Composable
private fun CategoryTerms(state: UnitRulesUiState, viewModel: UnitRulesViewModel) {
    Text(
        "Plazo propio por tipo (opcional)",
        style = MaterialTheme.typography.titleSmall,
        modifier = Modifier.semantics { heading() }
    )
    DomuxCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(
                "Déjalo vacío para que ese tipo use el plazo general.",
                color = DomuxColor.TextMuted,
                style = MaterialTheme.typography.bodySmall
            )
            pqrsTermCategories.forEach { category ->
                OutlinedTextField(
                    value = state.categoryValues[category].orEmpty(),
                    onValueChange = { viewModel.setCategory(category, it) },
                    label = { Text(category) },
                    suffix = { Text("días hábiles") },
                    supportingText = { Text("Entre 1 y 90") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth()
                )
            }
        }
    }
}
