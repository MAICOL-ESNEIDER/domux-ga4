package com.dracknoval.domux

import android.util.Log
import com.dracknoval.domux.data.PushRegistration
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

class DomuxFirebaseMessagingService : FirebaseMessagingService() {
    override fun onNewToken(token: String) {
        PushRegistration.registerAfterTokenRefresh(applicationContext, token)
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val data = message.data
        val type = data["type"] ?: "general"
        val title = message.notification?.title ?: data["title"] ?: "Aviso de DOMUX"
        val body = message.notification?.body ?: data["message"].orEmpty()
        if (body.isBlank()) {
            Log.w("DomuxPush", "Received an FCM message without a body.")
            return
        }
        val route = data["route"] ?: DomuxLocalNotifications.routeForNotification(type)
        val backendNotificationId = data["notificationId"]?.toIntOrNull()?.takeIf { it > 0 }
        val fallbackId = message.messageId?.hashCode()?.and(Int.MAX_VALUE)?.takeIf { it > 0 }
            ?: (System.currentTimeMillis() % Int.MAX_VALUE).toInt().coerceAtLeast(1)
        DomuxNotifier.showSystemNotification(
            applicationContext,
            id = backendNotificationId ?: fallbackId,
            title = title,
            body = body,
            route = route,
            isLatestNotificationId = backendNotificationId != null
        )
    }
}
