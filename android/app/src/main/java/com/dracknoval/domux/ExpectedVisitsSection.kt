package com.dracknoval.domux

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.dracknoval.domux.data.ExpectedVisitRequest
import com.dracknoval.domux.data.Visit
import com.dracknoval.domux.ui.theme.DomuxColor

/**
 * Técnicos y contratistas que la administración espera para trabajar en las zonas comunes
 * (ascensores, piscina, jardín...). La administración los anuncia con anticipación y ya quedan
 * autorizados; la portería los ve como «esperados» y, cuando llegan, solo registra la entrada.
 */
@Composable
fun ExpectedVisitsSection(
    modifier: Modifier,
    expected: List<Visit>,
    busy: Boolean,
    isAdmin: Boolean,
    onMessage: (String) -> Unit,
    onRegister: (ExpectedVisitRequest, () -> Unit) -> Unit,
    onCancel: (Visit) -> Unit,
    onEntry: (Visit) -> Unit
) {
    var name by rememberSaveable { mutableStateOf("") }
    var work by rememberSaveable { mutableStateOf("") }
    var document by rememberSaveable { mutableStateOf("") }
    var day by rememberSaveable { mutableStateOf("") }
    var hour by rememberSaveable { mutableStateOf("") }
    var attempted by rememberSaveable { mutableStateOf(false) }

    Column(
        modifier = modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        if (isAdmin) {
            DomuxCard(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Anunciar un técnico o contratista", style = MaterialTheme.typography.titleMedium)
                    Text(
                        "Para trabajos en las zonas comunes. Las visitas de los residentes las registra la portería.",
                        style = MaterialTheme.typography.bodySmall,
                        color = DomuxColor.TextMuted
                    )
                    OutlinedTextField(
                        value = name,
                        onValueChange = { name = it.take(120) },
                        label = { Text("Persona o empresa *") },
                        isError = attempted && name.isBlank(),
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = work,
                        onValueChange = { work = it.take(250) },
                        label = { Text("Trabajo que va a hacer *") },
                        supportingText = { Text("Ejemplo: mantenimiento del ascensor de la Torre 1") },
                        isError = attempted && work.isBlank(),
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = document,
                        onValueChange = { document = it.take(40) },
                        label = { Text("Documento (opcional)") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    DatePickerField("Día en que llega *", day, { day = it }, allowPastDates = false)
                    TimePickerField("Hora aproximada (opcional)", hour) { hour = it }
                    Button(
                        onClick = {
                            attempted = true
                            if (name.isBlank() || work.isBlank() || day.isBlank()) {
                                onMessage("Escribe quién viene, qué trabajo hará y el día en que llega.")
                            } else {
                                onRegister(
                                    ExpectedVisitRequest(
                                        visitorName = name.trim(),
                                        description = work.trim(),
                                        expectedDate = day,
                                        expectedTime = hour.ifBlank { null },
                                        visitorDocument = document.trim().ifBlank { null }
                                    )
                                ) {
                                    name = ""; work = ""; document = ""; day = ""; hour = ""; attempted = false
                                }
                            }
                        },
                        enabled = !busy,
                        modifier = Modifier.fillMaxWidth()
                    ) { Text("Avisar a la portería") }
                }
            }
        }

        Text("Esperados por la administración (${expected.size})", style = MaterialTheme.typography.titleMedium)
        if (expected.isEmpty()) {
            Text("No hay técnicos ni contratistas esperados.", color = DomuxColor.TextMuted)
        }
        expected.forEach { visit ->
            DomuxCard(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(visit.visitorName, style = MaterialTheme.typography.titleSmall)
                    visit.description?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
                    Text(
                        listOfNotNull(
                            visit.expectedDate?.let { "Llega el $it" },
                            visit.expectedTime?.let { "a las $it" },
                            visit.visitorDocument?.takeIf { it.isNotBlank() }?.let { "Doc. $it" }
                        ).joinToString(" · "),
                        style = MaterialTheme.typography.bodySmall,
                        color = DomuxColor.TextMuted
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (isAdmin) {
                            OutlinedButton(onClick = { onCancel(visit) }, enabled = !busy) { Text("Cancelar") }
                        } else {
                            Button(onClick = { onEntry(visit) }, enabled = !busy) { Text("Registrar entrada") }
                        }
                    }
                }
            }
        }
    }
}
