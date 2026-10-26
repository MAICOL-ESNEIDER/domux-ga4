package com.dracknoval.domux

import android.util.Log
import com.dracknoval.domux.data.NotificationItem
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
        val id = data["notificationId"]?.toIntOrNull()
            ?: message.messageId?.hashCode()?.let { if (it == Int.MIN_VALUE) 1 else kotlin.math.abs(it) }
            ?.takeIf { it > 0 } ?: System.currentTimeMillis().toInt()
        DomuxLocalNotifications.show(
            applicationContext,
            NotificationItem(
                id = id,
                userId = 0,
                title = title,
                message = body,
                type = type,
                isRead = false,
                createdAt = null
            ),
            route = route,
            highPriority = type == "visit"
        )
    }
}
