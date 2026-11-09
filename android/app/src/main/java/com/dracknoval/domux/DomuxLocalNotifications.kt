package com.dracknoval.domux

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
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
        highPriority: Boolean = false
    ): Boolean {
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            return false
        }
        if (!markSeen(context, notification.id)) return true

        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra(MainActivity.EXTRA_NOTIFICATION_ROUTE, route)
            putExtra("notification_id", notification.id)
        }
        val pendingIntent = PendingIntent.getActivity(
            context,
            notification.id,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val builder = NotificationCompat.Builder(
            context,
            if (highPriority) criticalChannelId else channelId
        )
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(notification.title)
            .setContentText(notification.message)
            .setStyle(NotificationCompat.BigTextStyle().bigText(notification.message))
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setPriority(
                if (highPriority) NotificationCompat.PRIORITY_HIGH else NotificationCompat.PRIORITY_DEFAULT
            )

        NotificationManagerCompat.from(context).notify(notification.id, builder.build())
        return true
    }

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
