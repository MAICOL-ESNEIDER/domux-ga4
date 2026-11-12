package com.dracknoval.domux.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

/**
 * El tema oscuro de DOMUX, armado con los colores con nombre de [DomuxColor]. El borde de los
 * campos ([DomuxColor.FieldBorder]) es el «outline» del tema: así toda caja de texto y todo botón
 * con borde se distinguen del fondo. Las líneas que solo separan usan «outlineVariant».
 */
private val DomuxColors = darkColorScheme(
    primary = DomuxColor.Primary,
    onPrimary = DomuxColor.OnPrimary,
    secondary = DomuxColor.Cyan,
    tertiary = DomuxColor.Violet,
    background = DomuxColor.Background,
    onBackground = DomuxColor.Text,
    surface = DomuxColor.Surface,
    onSurface = DomuxColor.Text,
    surfaceVariant = DomuxColor.Card,
    onSurfaceVariant = DomuxColor.TextSoft,
    outline = DomuxColor.FieldBorder,
    outlineVariant = DomuxColor.Line,
    error = DomuxColor.Bad,
    errorContainer = DomuxColor.BadBackground,
    onErrorContainer = DomuxColor.Bad
)

@Composable
fun DomuxAppTheme(
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = DomuxColors,
        content = content
    )
}
