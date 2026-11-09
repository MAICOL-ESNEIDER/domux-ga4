package com.dracknoval.domux

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
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
        } finally {
            loading = false
        }
    }

    LaunchedEffect(Unit) { load() }

    DomuxScreenScaffold(title = "Notificaciones", navController = navController) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).padding(18.dp)) {
            DomuxFeedbackBanner(message) { message = "" }
            if (loading) CircularProgressIndicator()
            else if (notifications.isEmpty()) Text("No tienes notificaciones todavía.")
            else LazyColumn(Modifier.weight(1f)) {
                items(notifications, key = { it.id }) { item ->
                    DomuxCard(Modifier.fillMaxWidth().padding(vertical = 5.dp)) {
                        Column(Modifier.padding(14.dp)) {
                            Text(item.title, style = MaterialTheme.typography.titleMedium)
                            Text(item.message)
                            Text("${item.type} · ${item.createdAt.orEmpty()}", style = MaterialTheme.typography.bodySmall)
                            if (!item.isRead) {
                                TextButton(onClick = {
                                    scope.launch {
                                        try {
                                            val response = RetrofitClient.api.markNotificationRead(
                                                Session.bearer(), item.id
                                            )
                                            if (response.isSuccessful) load()
                                            else message = mensajeDeError(response.code(), response.errorBody()?.string())
                                        } catch (exception: Exception) {
                                            if (exception is CancellationException) throw exception
                                            message = "No se pudo marcar como leída: ${exception.message}"
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
