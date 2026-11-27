package com.dracknoval.domux

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.dracknoval.domux.ui.theme.DomuxColor

/**
 * Las acciones secundarias de toda la app (en tarjetas, listas y ventanas) se ven como botones con
 * borde, nunca como texto azul suelto: así se nota que se pueden tocar, en todos los roles.
 *
 * Tiene el mismo nombre que el TextButton de Material para que todas las pantallas del paquete lo
 * usen sin cambiar cada llamada: un archivo que no importe androidx.compose.material3.TextButton usa
 * este. La acción principal de cada pantalla sigue siendo el botón lleno (Button).
 */
@Composable
fun TextButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    content: @Composable RowScope.() -> Unit
) {
    OutlinedButton(
        onClick = onClick,
        modifier = modifier.heightIn(min = 44.dp),
        enabled = enabled,
        shape = RoundedCornerShape(12.dp),
        colors = ButtonDefaults.outlinedButtonColors(
            contentColor = DomuxColor.Primary,
            disabledContentColor = DomuxColor.TextMuted
        ),
        border = BorderStroke(1.dp, if (enabled) DomuxColor.Primary.copy(alpha = 0.55f) else DomuxColor.FieldBorder),
        contentPadding = PaddingValues(horizontal = 14.dp, vertical = 8.dp),
        content = content
    )
}
