package com.dracknoval.domux

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

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
