package com.dracknoval.domux.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Paleta simple para Domux (tonos verde/azulados, sin depender de recursos extra).
private val LightColors = lightColorScheme(
    primary = Color(0xFF2E6F55),
    secondary = Color(0xFF4C6B5A),
    tertiary = Color(0xFF3A5A78)
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF8FD9B6),
    secondary = Color(0xFFB2CCBD),
    tertiary = Color(0xFFA9C6E8)
)

@Composable
fun DomuxAppTheme(
    darkTheme: Boolean = false,
    content: @Composable () -> Unit
) {
    val colorScheme = if (darkTheme) DarkColors else LightColors
    MaterialTheme(
        colorScheme = colorScheme,
        content = content
    )
}
