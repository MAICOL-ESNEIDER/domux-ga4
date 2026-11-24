package com.dracknoval.domux.data

import android.content.Context
import com.dracknoval.domux.BuildConfig
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

object RetrofitClient {
    private val serviceClient = OkHttpClient.Builder()
        .connectTimeout(45, TimeUnit.SECONDS)
        .readTimeout(45, TimeUnit.SECONDS)
        .writeTimeout(45, TimeUnit.SECONDS)
        .build()

    private fun normalizeUrl(url: String): String {
        val withoutBrackets = url.trim().replace("[", "").replace("]", "")
        return if (withoutBrackets.endsWith("/")) withoutBrackets else "$withoutBrackets/"
    }

    val baseUrl: String = normalizeUrl(BuildConfig.BASE_URL)

    val api: ApiService = Retrofit.Builder()
        .baseUrl(baseUrl)
        .client(serviceClient)
        .addConverterFactory(GsonConverterFactory.create())
        .build()
        .create(ApiService::class.java)

    fun initialize(context: Context) {
        // No-op for now, kept for backward compatibility with initialization sequence
    }
}
