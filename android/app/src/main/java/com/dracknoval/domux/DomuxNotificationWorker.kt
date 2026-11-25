package com.dracknoval.domux

import android.content.Context
import android.util.Log
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import kotlinx.coroutines.CancellationException
import java.io.IOException
import java.util.concurrent.TimeUnit

class DomuxNotificationWorker(
    appContext: Context,
    workerParameters: WorkerParameters
) : CoroutineWorker(appContext, workerParameters) {
    override suspend fun doWork(): Result {
        if (!Session.restore(applicationContext) || Session.token.isNullOrBlank()) {
            return Result.success()
        }

        return try {
            RetrofitClient.initialize(applicationContext)
            when (val responseCode = DomuxNotificationSync.fetchAndShow(applicationContext)) {
                in 200..299 -> Result.success()
                401, 403 -> Result.success()
                408, 429 -> Result.retry()
                in 400..499 -> {
                    Log.w(TAG, "Notification sync returned HTTP $responseCode.")
                    Result.success()
                }
                else -> Result.retry()
            }
        } catch (exception: CancellationException) {
            throw exception
        } catch (exception: Exception) {
            Log.e(TAG, "Notification sync failed.", exception)
            Result.retry()
        }
    }

    companion object {
        private const val TAG = "DomuxNotifications"
        private const val WORK_NAME = "domux_notification_sync"

        fun enqueuePeriodic(context: Context) {
            val request = PeriodicWorkRequestBuilder<DomuxNotificationWorker>(
                15,
                TimeUnit.MINUTES
            ).setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build()
            ).build()

            WorkManager.getInstance(context.applicationContext).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                request
            )
        }
    }
}

object DomuxNotificationSync {
    suspend fun fetchAndShow(context: Context): Int {
        RetrofitClient.initialize(context.applicationContext)
        val response = RetrofitClient.api.getNotifications(Session.bearer())
        if (!response.isSuccessful) return response.code()

        val notifications = response.body()?.notifications
            ?: throw IOException("El servidor devolvió una lista de notificaciones vacía.")
        val lastShownId = DomuxNotifier.lastShownNotificationId(context)
        notifications.asSequence()
            .filter { !it.isRead && it.id > lastShownId }
            .sortedBy { it.id }
            .forEach { notification ->
                DomuxNotifier.showSystemNotification(
                    context = context,
                    id = notification.id,
                    title = notification.title,
                    body = notification.message,
                    route = DomuxLocalNotifications.routeForNotification(notification.type)
                )
            }
        return response.code()
    }
}
