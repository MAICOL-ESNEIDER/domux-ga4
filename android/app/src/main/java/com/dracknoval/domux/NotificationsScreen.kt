package com.dracknoval.domux

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.graphics.Color
import androidx.navigation.NavController
import com.dracknoval.domux.data.NotificationItem
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

@Composable
fun NotificationsScreen(navController: NavController) {
    var notifications by remember { mutableStateOf<List<NotificationItem>>(emptyList()) }
    var message by remember { mutableStateOf("") }
    var loading by remember { mutableStateOf(true) }
    var isError by remember { mutableStateOf<Boolean?>(null) }
    val scope = rememberCoroutineScope()

    suspend fun load() {
        loading = true
        try {
            val response = RetrofitClient.api.getNotifications(Session.bearer())
            if (response.isSuccessful) notifications = response.body()?.notifications.orEmpty()
            else message = mensajeDeError(response.code(), response.errorBody()?.string())
        } catch (exception: Exception) {
            if (exception is CancellationException) throw exception
            message = "No se pudieron cargar las notificaciones: ${exception.message}"
            isError = true
        } finally {
            loading = false
        }
    }

    LaunchedEffect(Unit) { load() }

    DomuxScreenScaffold(title = "Notificaciones", navController = navController) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).padding(18.dp)) {
            DomuxFeedbackBanner(message, isError) { message = ""; isError = null }
            
            if (notifications.any { it.isRead }) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                    horizontalArrangement = Arrangement.End
                ) {
                    TextButton(onClick = {
                        scope.launch {
                            try {
                                val response = RetrofitClient.api.clearReadNotifications(Session.bearer())
                                if (response.isSuccessful) {
                                    message = "Notificaciones leídas limpiadas."
                                    isError = false
                                    load()
                                } else {
                                    message = mensajeDeError(response.code(), response.errorBody()?.string())
                                    isError = true
                                }
                            } catch (exception: Exception) {
                                if (exception is CancellationException) throw exception
                                message = "Error al limpiar notificaciones: ${exception.message}"
                                isError = true
                            }
                        }
                    }) {
                        Text("Limpiar leídas")
                    }
                }
            }

            if (loading) CircularProgressIndicator()
            else if (notifications.isEmpty()) Text("No tienes notificaciones todavía.")
            else LazyColumn(Modifier.weight(1f)) {
                items(notifications, key = { it.id }) { item ->
                    DomuxCard(Modifier.fillMaxWidth().padding(vertical = 5.dp)) {
                        Column(Modifier.padding(14.dp)) {
                            Text(item.title, style = MaterialTheme.typography.titleMedium)
                            Text(item.message)
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    "${item.type.toDomuxDisplayLabel()} · ${item.createdAt.orEmpty()}",
                                    style = MaterialTheme.typography.bodySmall
                                )
                                Text(
                                    if (item.isRead) "Leída" else "No leída",
                                    color = if (item.isRead) Color(0xFF94A3B8) else Color(0xFF38BDF8),
                                    style = MaterialTheme.typography.labelSmall
                                )
                            }
                            if (!item.isRead) {
                                TextButton(onClick = {
                                    scope.launch {
                                        try {
                                            val response = RetrofitClient.api.markNotificationRead(
                                                Session.bearer(), item.id
                                            )
                                            if (response.isSuccessful) {
                                                load()
                                            } else {
                                                message = mensajeDeError(response.code(), response.errorBody()?.string())
                                                isError = true
                                            }
                                        } catch (exception: Exception) {
                                            if (exception is CancellationException) throw exception
                                            message = "No se pudo marcar como leída: ${exception.message}"
                                            isError = true
                                        }
                                    }
                                }) { Text("Marcar como leída") }
                            }
                        }
                    }
                }
            }
        }
    }
}
