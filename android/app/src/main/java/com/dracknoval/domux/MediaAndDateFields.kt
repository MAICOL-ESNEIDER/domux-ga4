package com.dracknoval.domux

import android.app.DatePickerDialog
import android.app.TimePickerDialog
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.dracknoval.domux.ui.theme.DomuxColor
import java.util.Calendar

// La app no guarda archivos en el celular: el Excel (exportar listas, respaldo e importar el censo)
// se maneja solo en la web de administración, desde el computador.

/**
 * Botón que abre el calendario del celular y devuelve la fecha como AAAA-MM-DD, para que nadie
 * tenga que escribirla a mano. [allowFutureDates] en false sirve para fechas que ya pasaron,
 * como un nacimiento o la última vacuna.
 */
@Composable
fun DatePickerField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    allowPastDates: Boolean = true,
    allowFutureDates: Boolean = true
) {
    val context = LocalContext.current
    OutlinedButton(
        onClick = {
            val calendar = Calendar.getInstance()
            DatePickerDialog(
                context,
                { _, year, month, day ->
                    onValueChange("%04d-%02d-%02d".format(year, month + 1, day))
                },
                calendar.get(Calendar.YEAR),
                calendar.get(Calendar.MONTH),
                calendar.get(Calendar.DAY_OF_MONTH)
            ).apply {
                if (!allowPastDates) datePicker.minDate = System.currentTimeMillis()
                if (!allowFutureDates) datePicker.maxDate = System.currentTimeMillis()
            }.show()
        },
        modifier = Modifier.fillMaxWidth()
    ) {
        Text(if (value.isBlank()) label else "$label: $value")
    }
}

@Composable
fun TimePickerField(label: String, value: String, onValueChange: (String) -> Unit) {
    val context = LocalContext.current
    OutlinedButton(
        onClick = {
            val calendar = Calendar.getInstance()
            TimePickerDialog(
                context,
                { _, hour, minute -> onValueChange("%02d:%02d".format(hour, minute)) },
                calendar.get(Calendar.HOUR_OF_DAY),
                calendar.get(Calendar.MINUTE),
                true
            ).show()
        },
        modifier = Modifier.fillMaxWidth()
    ) {
        Text(if (value.isBlank()) label else "$label: $value")
    }
}

@Composable
fun DomuxCard(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = DomuxColor.Card),
        border = BorderStroke(1.dp, DomuxColor.Line),
        content = content
    )
}
