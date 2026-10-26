package com.dracknoval.domux.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val DomuxColors = darkColorScheme(
    primary = Color(0xFF38BDF8),
    secondary = Color(0xFF22D3EE),
    tertiary = Color(0xFF818CF8),
    background = Color(0xFF0B172A),
    surface = Color(0xFF091426),
    surfaceVariant = Color(0xFF0F1E33),
    outline = Color(0xFF1E334D),
    onPrimary = Color(0xFF07111F),
    onBackground = Color(0xFFF1F5F9),
    onSurface = Color(0xFFF1F5F9),
    onSurfaceVariant = Color(0xFFCBD5E1),
    error = Color(0xFFF87171)
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
