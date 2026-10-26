// RetrofitClient.kt — crea y configura UNA sola instancia de Retrofit para toda la app.
// "object" en Kotlin = singleton: existe una única copia, accesible como RetrofitClient.api
// (mismo patrón exacto de GA1-GA3).

package com.dracknoval.domux.data

import com.dracknoval.domux.BuildConfig
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

object RetrofitClient {

    // La URL se define por variante: dev usa el backend local y prod usa Render.
    private val baseUrl = BuildConfig.BASE_URL

    private val client = OkHttpClient.Builder()
        .build()

    val api: ApiService = Retrofit.Builder()
        .baseUrl(baseUrl)
        .client(client)
        .addConverterFactory(GsonConverterFactory.create())
        .build()
        .create(ApiService::class.java)
}
