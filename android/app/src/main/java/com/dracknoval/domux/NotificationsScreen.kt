package com.dracknoval.domux

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.dracknoval.domux.data.NotificationItem

/**
 * Bandeja de notificaciones (HU-064). La pantalla solo dibuja: los datos y las acciones están en
 * [NotificationsViewModel].
 */
@Composable
fun NotificationsScreen(navController: NavController, viewModel: NotificationsViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()

    DomuxScreenScaffold(title = "Notificaciones", navController = navController) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            if (state.message.isNotBlank()) {
                DomuxMessageBanner(state.message, state.messageIsError) { viewModel.dismissMessage() }
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(
                    selected = !state.unreadOnly,
                    onClick = { viewModel.setUnreadOnly(false) },
                    label = { Text("Todas") }
                )
                FilterChip(
                    selected = state.unreadOnly,
                    onClick = { viewModel.setUnreadOnly(true) },
                    label = { Text("Sin leer (${state.unreadCount})") }
                )
                Spacer(Modifier.weight(1f))
                if (state.unreadCount > 0) {
                    TextButton(onClick = { viewModel.markAllRead() }, enabled = !state.busy) { Text("Marcar todas") }
                }
            }
            when {
                state.loading && state.items.isEmpty() -> CircularProgressIndicator()
                state.visible.isEmpty() -> Text(
                    if (state.unreadOnly) "No tienes notificaciones sin leer." else "No tienes notificaciones todavía."
                )
                else -> LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(state.visible, key = { it.id }) { item ->
                        NotificationCard(item, busy = state.busy) { viewModel.markRead(item) }
                    }
                }
            }
        }
    }
}

@Composable
private fun NotificationCard(item: NotificationItem, busy: Boolean, onMarkRead: () -> Unit) {
    DomuxCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(item.title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                if (!item.isRead) DomuxStatusBadge("Sin leer", DomuxBadgeTone.PROGRESS)
            }
            Text(item.message)
            Text(item.createdAt.orEmpty(), style = MaterialTheme.typography.bodySmall)
            if (!item.isRead) {
                TextButton(onClick = onMarkRead, enabled = !busy) { Text("Marcar como leída") }
            }
        }
    }
}
