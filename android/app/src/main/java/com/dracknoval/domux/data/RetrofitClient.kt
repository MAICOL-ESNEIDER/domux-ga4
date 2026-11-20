package com.dracknoval.domux.data

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import com.dracknoval.domux.BuildConfig
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.io.IOException
import java.util.concurrent.TimeUnit

object RetrofitClient {
    private const val TAG = "RetrofitClient"
    private const val PREFERENCES_NAME = "domux_network_prefs"
    private const val SERVER_URL_KEY = "server_url"
    private const val DEFAULT_BASE_URL = "https://domux-backend.onrender.com/"
    private const val USB_REVERSE_URL = "http://127.0.0.1:5000/"

    @Volatile
    private var preferences: SharedPreferences? = null

    private val serviceClient = OkHttpClient.Builder().build()
    private val healthClient = OkHttpClient.Builder()
        .callTimeout(1500, TimeUnit.MILLISECONDS)
        .build()

    private data class ClientState(val baseUrl: String, val api: ApiService)

    private fun normalizeUrl(url: String): String {
        val withoutBrackets = url.trim().replace("[", "").replace("]", "")
        return if (withoutBrackets.endsWith("/")) withoutBrackets else "$withoutBrackets/"
    }

    private fun buildApi(url: String): ApiService = Retrofit.Builder()
        .baseUrl(url)
        .client(serviceClient)
        .addConverterFactory(GsonConverterFactory.create())
        .build()
        .create(ApiService::class.java)

    private fun createInitialState(): ClientState {
        val configuredUrl = normalizeUrl(BuildConfig.BASE_URL)
        return try {
            ClientState(configuredUrl, buildApi(configuredUrl))
        } catch (exception: IllegalArgumentException) {
            Log.w(TAG, "Invalid configured BASE_URL; using the default server.", exception)
            ClientState(DEFAULT_BASE_URL, buildApi(DEFAULT_BASE_URL))
        }
    }

    private val initialState = createInitialState()

    @Volatile
    var baseUrl: String = initialState.baseUrl
        private set

    @Volatile
    private var apiInstance: ApiService = initialState.api

    val api: ApiService
        get() = apiInstance

    val fallbackUrls: List<String>
        get() = BuildConfig.DOMUX_FALLBACK_URLS.split(",")
            .map { it.trim() }
            .filter { it.isNotEmpty() }

    fun initialize(context: Context) {
        preferences = context.applicationContext.getSharedPreferences(
            PREFERENCES_NAME,
            Context.MODE_PRIVATE
        )
    }

    suspend fun resolveBestServerUrl(candidates: List<String>): String {
        val savedUrl = preferences?.getString(SERVER_URL_KEY, null)
            ?.takeIf { it.isNotBlank() }
        val urls = (listOfNotNull(savedUrl, USB_REVERSE_URL, BuildConfig.BASE_URL) + candidates)
            .map(::normalizeUrl)
            .distinct()

        for (url in urls) {
            if (isServerAvailable(url)) {
                if (activate(url)) return baseUrl
            }
        }

        activate(BuildConfig.BASE_URL)
        return baseUrl
    }

    suspend fun testAndSaveServerUrl(url: String): Boolean {
        val normalizedUrl = normalizeUrl(url)
        if (!isServerAvailable(normalizedUrl)) return false
        if (!activate(normalizedUrl)) return false

        val prefs = preferences
            ?: throw IllegalStateException("RetrofitClient.initialize(context) must be called first.")
        prefs.edit().putString(SERVER_URL_KEY, normalizedUrl).apply()
        return true
    }

    private suspend fun isServerAvailable(url: String): Boolean = withContext(Dispatchers.IO) {
        try {
            val request = Request.Builder()
                .url("${normalizeUrl(url)}api/health")
                .get()
                .build()
            healthClient.newCall(request).execute().use { response ->
                response.code() == 200
            }
        } catch (exception: CancellationException) {
            throw exception
        } catch (exception: IOException) {
            false
        } catch (exception: IllegalArgumentException) {
            Log.w(TAG, "Skipping invalid server URL: $url", exception)
            false
        }
    }

    @Synchronized
    private fun activate(url: String): Boolean {
        val normalizedUrl = normalizeUrl(url)
        return try {
            val newApi = buildApi(normalizedUrl)
            apiInstance = newApi
            baseUrl = normalizedUrl
            true
        } catch (exception: IllegalArgumentException) {
            Log.w(TAG, "Skipping invalid Retrofit base URL: $normalizedUrl", exception)
            false
        }
    }
}
