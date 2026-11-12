package com.dracknoval.domux

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.google.zxing.BarcodeFormat
import com.journeyapps.barcodescanner.BarcodeEncoder

// Piezas que comparten las pantallas de portería: paquetes, visitas y vehículos.

/** Estadías que el guardia puede elegir con un toque (HU-031): el texto y los minutos. */
private val STAY_OPTIONS: List<Pair<String, Int?>> = listOf(
    "Sin definir" to null,
    "30 min" to 30,
    "1 h" to 60,
    "2 h" to 120,
    "4 h" to 240,
    "8 h" to 480,
    "1 día" to 1440
)

/** Una duración en minutos escrita para leerla rápido: «45 min», «2 h 15 min» o «1 d 3 h». */
fun durationText(minutes: Int): String {
    if (minutes < 60) return "$minutes min"
    if (minutes < 24 * 60) {
        val hours = minutes / 60
        val rest = minutes % 60
        return if (rest == 0) "$hours h" else "$hours h $rest min"
    }
    val days = minutes / (24 * 60)
    val hours = (minutes % (24 * 60)) / 60
    return if (hours == 0) "$days d" else "$days d $hours h"
}

/** Elige la estadía prevista de una visita; null es «sin definir» (HU-031). */
@Composable
fun StayChips(selectedMinutes: Int?, onSelect: (Int?) -> Unit) {
    // Si la visita ya traía una estadía que no está en la lista, se agrega para no perderla.
    val extra = selectedMinutes?.takeIf { minutes -> STAY_OPTIONS.none { it.second == minutes } }
    val options = if (extra == null) STAY_OPTIONS else STAY_OPTIONS + (durationText(extra) to extra)
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("Estadía prevista (opcional)", style = MaterialTheme.typography.labelLarge)
        Row(
            modifier = Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            options.forEach { (label, minutes) ->
                FilterChip(
                    selected = selectedMinutes == minutes,
                    onClick = { onSelect(minutes) },
                    label = { Text(label) }
                )
            }
        }
    }
}

/** La imagen de un QR lista para mostrar y compartir; null si no se pudo generar. */
@Composable
fun rememberQrBitmap(data: String?): Bitmap? = remember(data) {
    if (data.isNullOrBlank()) {
        null
    } else {
        try {
            BarcodeEncoder().encodeBitmap(data, BarcodeFormat.QR_CODE, 640, 640)
        } catch (exception: Exception) {
            null
        }
    }
}

/** Muestra el QR sobre fondo blanco (así lo lee cualquier cámara); [modifier] puede alinearlo. */
@Composable
fun QrImage(bitmap: Bitmap?, description: String, modifier: Modifier = Modifier, size: Dp = 220.dp) {
    if (bitmap == null) {
        Text(
            "No se pudo generar la imagen del QR.",
            color = Color(0xFFF87171),
            style = MaterialTheme.typography.bodySmall
        )
        return
    }
    Image(
        bitmap = bitmap.asImageBitmap(),
        contentDescription = description,
        modifier = modifier.size(size)
    )
}
