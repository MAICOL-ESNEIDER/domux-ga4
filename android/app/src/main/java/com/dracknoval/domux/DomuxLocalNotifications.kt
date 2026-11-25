package com.dracknoval.domux

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import com.dracknoval.domux.data.NotificationItem

object DomuxLocalNotifications {
    private const val channelId = "domux_residential_updates"
    private const val criticalChannelId = "domux_critical_updates"
    private const val recentNotificationIdsKey = "recent_notification_ids"

    fun createChannel(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "Avisos de Domux",
                NotificationManager.IMPORTANCE_DEFAULT
            ).apply {
                description = "Avisos residenciales nuevos"
            }
            context.getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
            val criticalChannel = NotificationChannel(
                criticalChannelId,
                "Avisos urgentes de portería",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Visitantes esperando autorización"
            }
            context.getSystemService(NotificationManager::class.java)
                .createNotificationChannel(criticalChannel)
        }
    }

    fun show(
        context: Context,
        notification: NotificationItem,
        route: String = routeForNotification(notification.type),
        highPriority: Boolean = true
    ): Boolean = DomuxNotifier.showSystemNotification(
        context,
        notification.id,
        notification.title,
        notification.message,
        route,
        highPriority
    )

    fun markSeen(context: Context, notificationId: Int): Boolean {
        val preferences = context.getSharedPreferences("domux_local_notifications", Context.MODE_PRIVATE)
        val seen = preferences.getStringSet(recentNotificationIdsKey, emptySet())
            .orEmpty()
            .toMutableSet()
        val id = notificationId.toString()
        if (id in seen) return false
        seen.add(id)
        val recent = seen.sortedByDescending { it.toLongOrNull() ?: 0L }.take(300).toSet()
        check(preferences.edit().putStringSet(recentNotificationIdsKey, recent).commit()) {
            "Could not persist notification de-duplication state."
        }
        return true
    }

    fun routeForNotification(type: String): String = when (type) {
        "pqrs" -> "pqrs"
        "reservation" -> "reservations"
        "package", "visit" -> "registry"
        "announcement" -> "announcements"
        else -> "notifications"
    }
}
