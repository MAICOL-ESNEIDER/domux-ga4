package com.dracknoval.domux

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties

@Composable
fun MediaAttachmentChip(mediaUrl: String?, mediaType: String?) {
    if (mediaUrl.isNullOrBlank()) return
    val (icon, label) = when (mediaType?.lowercase()) {
        "image" -> "IMG" to "Imagen adjunta"
        "video" -> "VID" to "Video adjunto"
        "audio" -> "AUD" to "Audio adjunto"
        else -> "FILE" to "Archivo adjunto"
    }
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        contentColor = MaterialTheme.colorScheme.secondary,
        shape = RoundedCornerShape(50),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline)
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 11.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(icon, fontSize = 10.sp)
            Spacer(Modifier.width(7.dp))
            Text(label, style = MaterialTheme.typography.labelMedium)
        }
    }
}

@Composable
fun DomuxConfirmDialog(
    title: String,
    message: String,
    confirmLabel: String = "Confirmar",
    danger: Boolean = false,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit
) {
    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 24.dp),
            shape = RoundedCornerShape(24.dp),
            color = Color(0xFF091426),
            border = BorderStroke(1.dp, Color(0xFF1E334D))
        ) {
            Column(
                modifier = Modifier.padding(22.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Text(title, style = MaterialTheme.typography.titleLarge)
                Text(message, color = Color(0xFFCBD5E1), style = MaterialTheme.typography.bodyMedium)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    TextButton(onClick = onDismiss) { Text("Cancelar") }
                    Button(
                        onClick = onConfirm,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (danger) Color(0xFF450A0A) else Color(0xFF152C4A),
                            contentColor = if (danger) Color(0xFFF87171) else Color(0xFF38BDF8)
                        )
                    ) {
                        Text(confirmLabel)
                    }
                }
            }
        }
    }
}

@Composable
fun DomuxBentoCard(
    title: String,
    detail: String,
    icon: String,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    Surface(
        modifier = modifier.clickable(onClick = onClick),
        color = Color(0xFF0F1E33),
        shape = RoundedCornerShape(20.dp),
        border = BorderStroke(1.dp, Color(0xFF1E334D))
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Box(
                modifier = Modifier
                    .size(42.dp)
                    .background(Color(0xFF152C4A), RoundedCornerShape(13.dp)),
                contentAlignment = Alignment.Center
            ) {
                Text(icon, color = Color(0xFF38BDF8), fontSize = 19.sp)
            }
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(title, color = Color(0xFF94A3B8), style = MaterialTheme.typography.labelMedium)
                Text(detail, color = Color(0xFFF8FAFC), style = MaterialTheme.typography.titleSmall)
            }
        }
    }
}

@Composable
fun DomuxStatusBadge(label: String, tone: DomuxBadgeTone = DomuxBadgeTone.SUCCESS) {
    val (background, foreground, outline) = when (tone) {
        DomuxBadgeTone.SUCCESS -> Triple(Color(0xFF064E3B), Color(0xFF34D399), Color(0xFF065F46))
        DomuxBadgeTone.PROGRESS -> Triple(Color(0xFF451A03), Color(0xFFFBBF24), Color(0xFF78350F))
        DomuxBadgeTone.ALERT -> Triple(Color(0xFF450A0A), Color(0xFFF87171), Color(0xFF7F1D1D))
    }
    Surface(
        color = background,
        contentColor = foreground,
        shape = CircleShape,
        border = BorderStroke(1.dp, outline)
    ) {
        Text(label, modifier = Modifier.padding(horizontal = 11.dp, vertical = 6.dp), fontSize = 11.sp)
    }
}

enum class DomuxBadgeTone { SUCCESS, PROGRESS, ALERT }

@Composable
fun DomuxBrandMark(size: Dp = 54.dp) {
    Surface(
        modifier = Modifier.size(size),
        shape = RoundedCornerShape(17.dp),
        color = Color.Transparent
    ) {
        Box(
            modifier = Modifier.background(
                Brush.linearGradient(
                    listOf(Color(0xFF22D3EE), Color(0xFF818CF8), Color(0xFFA855F7))
                )
            ),
            contentAlignment = Alignment.Center
        ) {
            Text(
                "D",
                color = Color.White,
                fontSize = (size.value * 0.52f).sp,
                fontWeight = FontWeight.Bold
            )
        }
    }
}
