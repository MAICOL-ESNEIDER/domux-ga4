package com.dracknoval.domux

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat

object DomuxNotifier {
    const val CHANNEL_ID = "domux_alerts"

    private const val preferencesName = "domux_system_notifications"
    private const val lastNotificationIdKey = "last_notification_id"
    private const val recentNotificationIdsKey = "recent_notification_ids"
    private const val maxRememberedIds = 300

    fun createNotificationChannel(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return

        val channel = NotificationChannel(
            CHANNEL_ID,
            "Alertas y Notificaciones DOMUX",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "Alertas de reservas, PQRS, paquetes, visitas y anuncios."
            enableVibration(true)
            vibrationPattern = longArrayOf(0, 250, 150, 250)
            setSound(
                RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION),
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_NOTIFICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build()
            )
        }
        context.getSystemService(NotificationManager::class.java)
            ?.createNotificationChannel(channel)
    }

    fun lastShownNotificationId(context: Context): Int =
        context.getSharedPreferences(preferencesName, Context.MODE_PRIVATE)
            .getInt(lastNotificationIdKey, -1)

    @Synchronized
    fun showSystemNotification(
        context: Context,
        id: Int,
        title: String,
        body: String,
        route: String = "notifications",
        highPriority: Boolean = true,
        isLatestNotificationId: Boolean = true
    ): Boolean {
        if (id <= 0) return false
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            return false
        }
        val manager = NotificationManagerCompat.from(context)
        if (!manager.areNotificationsEnabled()) return false

        createNotificationChannel(context)
        val preferences = context.getSharedPreferences(preferencesName, Context.MODE_PRIVATE)
        val notificationId = id.toString()
        val lastShownId = preferences.getInt(lastNotificationIdKey, -1)
        val recentIds = preferences.getStringSet(recentNotificationIdsKey, emptySet())
            .orEmpty()
            .toMutableSet()
        if (notificationId in recentIds || (isLatestNotificationId && id <= lastShownId)) {
            return true
        }

        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra(MainActivity.EXTRA_NOTIFICATION_ROUTE, route)
            putExtra("notification_id", id)
        }
        val pendingIntent = PendingIntent.getActivity(
            context,
            id,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .setPriority(
                if (highPriority) NotificationCompat.PRIORITY_HIGH
                else NotificationCompat.PRIORITY_DEFAULT
            )
            .setDefaults(NotificationCompat.DEFAULT_ALL)
            .build()

        try {
            manager.notify(id, notification)
        } catch (_: SecurityException) {
            return false
        }

        recentIds.add(notificationId)
        val rememberedIds = recentIds
            .sortedByDescending { it.toIntOrNull() ?: 0 }
            .take(maxRememberedIds)
            .toSet()
        val editor = preferences.edit()
            .putStringSet(recentNotificationIdsKey, rememberedIds)
        if (isLatestNotificationId && id > lastShownId) {
            editor.putInt(lastNotificationIdKey, id)
        }
        editor.apply()
        return true
    }
}
