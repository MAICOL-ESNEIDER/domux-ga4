package com.dracknoval.domux.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Density
import com.dracknoval.domux.data.AppPreferences

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

/**
 * El tema de toda la app. El tamaño del texto que la persona eligió en Preferencias se multiplica
 * por el que ya tenga el celular en sus ajustes: al cambiarlo, todo el texto se vuelve a dibujar.
 */
@Composable
fun DomuxAppTheme(
    content: @Composable () -> Unit
) {
    val density = LocalDensity.current
    val scaled = Density(density.density, density.fontScale * AppPreferences.textSize.factor)
    CompositionLocalProvider(LocalDensity provides scaled) {
        MaterialTheme(
            colorScheme = DomuxColors,
            content = content
        )
    }
}
