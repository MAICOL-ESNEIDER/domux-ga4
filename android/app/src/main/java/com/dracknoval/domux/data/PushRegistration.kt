package com.dracknoval.domux.data

import android.content.Context
import android.util.Log
import com.google.firebase.messaging.FirebaseMessaging
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await
import java.util.UUID

object PushRegistration {
    private const val preferencesName = "domux_push_registration"
    private const val deviceIdKey = "device_id"

    fun registerAfterAuthentication(context: Context) {
        kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO).launch {
            try {
                val fcmToken = FirebaseMessaging.getInstance().token.await()
                val response = RetrofitClient.api.registerPushToken(
                    Session.bearer(),
                    PushTokenRequest(fcmToken, deviceId(context))
                )
                check(response.isSuccessful) {
                    "Backend rejected FCM token registration (${response.code()})."
                }
            } catch (exception: Exception) {
                Log.e("DomuxPush", "Could not register FCM after authentication.", exception)
            }
        }
    }

    suspend fun removeCurrentDevice(context: Context) {
        try {
            val fcmToken = FirebaseMessaging.getInstance().token.await()
            val response = RetrofitClient.api.deletePushToken(
                Session.bearer(),
                PushTokenRequest(fcmToken, deviceId(context))
            )
            check(response.isSuccessful) {
                "Backend rejected FCM token removal (${response.code()})."
            }
        } finally {
            FirebaseMessaging.getInstance().deleteToken().await()
        }
    }

    fun registerAfterTokenRefresh(context: Context, fcmToken: String) {
        if (Session.token == null) Session.restore(context)
        if (Session.token == null) return
        kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO).launch {
            try {
                val response = RetrofitClient.api.registerPushToken(
                    Session.bearer(),
                    PushTokenRequest(fcmToken, deviceId(context))
                )
                check(response.isSuccessful) {
                    "Backend rejected refreshed FCM token (${response.code()})."
                }
            } catch (exception: Exception) {
                Log.e("DomuxPush", "Could not register refreshed FCM token.", exception)
            }
        }
    }

    private fun deviceId(context: Context): String {
        val preferences = context.getSharedPreferences(preferencesName, Context.MODE_PRIVATE)
        val existing = preferences.getString(deviceIdKey, null)
        if (existing != null) return existing
        val created = UUID.randomUUID().toString()
        check(preferences.edit().putString(deviceIdKey, created).commit()) {
            "Could not persist device identifier."
        }
        return created
    }
}
