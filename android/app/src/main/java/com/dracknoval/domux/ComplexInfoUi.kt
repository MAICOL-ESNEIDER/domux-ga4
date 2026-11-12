package com.dracknoval.domux

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.dracknoval.domux.data.ComplexInfoStore

/**
 * El logo de la unidad (HU-077). Mientras la administración no suba uno se muestra la marca de DOMUX.
 * Con [describe] en falso el logo no se lee en voz alta (cuando el nombre ya está escrito al lado).
 */
@Composable
fun ComplexLogo(size: Dp = 48.dp, describe: Boolean = true) {
    val logo = ComplexInfoStore.logo
    if (logo == null) {
        DomuxBrandMark(size = size)
        return
    }
    Image(
        bitmap = logo,
        contentDescription = if (describe) "Logo de ${ComplexInfoStore.displayName}" else null,
        modifier = Modifier
            .size(size)
            .clip(RoundedCornerShape(12.dp))
            .background(Color.White),
        contentScale = ContentScale.Fit
    )
}

/** Abre el marcador del teléfono con el número de la portería: no llama sola, la persona confirma. */
fun dialPortal(context: Context, phone: String) {
    val number = phone.filter { it.isDigit() || it == '+' }
    if (number.isEmpty()) return
    try {
        context.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:$number")))
    } catch (_: ActivityNotFoundException) {
        // Un equipo sin aplicación de teléfono (algunas tablets): no hay a dónde mandar el número.
    }
}
