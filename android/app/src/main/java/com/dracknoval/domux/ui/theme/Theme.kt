package com.dracknoval.domux.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val DomuxColors = darkColorScheme(
    primary = Color(0xFF0EA5E9),
    secondary = Color(0xFF06B6D4),
    tertiary = Color(0xFF22D3EE),
    background = Color(0xFF07111F),
    surface = Color(0xFF081725),
    surfaceVariant = Color(0xFF1E293B),
    onPrimary = Color(0xFF00131C),
    onBackground = Color(0xFFE2E8F0),
    onSurface = Color(0xFFE2E8F0),
    onSurfaceVariant = Color(0xFFCBD5E1),
    error = Color(0xFFEF4444)
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
