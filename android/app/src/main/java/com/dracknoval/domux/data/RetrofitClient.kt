// RetrofitClient.kt — crea y configura UNA sola instancia de Retrofit para toda la app.
// "object" en Kotlin = singleton: existe una única copia, accesible como RetrofitClient.api
// (mismo patrón exacto de GA1-GA3).

package com.dracknoval.domux.data

import com.dracknoval.domux.BuildConfig
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

object RetrofitClient {

    // Sanitiza la URL para asegurar que empiece con http:// o https:// y termine en /
    private val baseUrl: String
        get() {
            var url = BuildConfig.BASE_URL.trim()
            if (!url.startsWith("http://") && !url.startsWith("https://")) {
                url = "http://$url"
            }
            if (!url.endsWith("/")) {
                url = "$url/"
            }
            return url
        }

    // El cuerpo de las peticiones solo se registra en la variante dev para Logcat.
    private val logging = HttpLoggingInterceptor().apply {
        level = if (BuildConfig.FLAVOR.contains("dev")) {
            HttpLoggingInterceptor.Level.BODY
        } else {
            HttpLoggingInterceptor.Level.NONE
        }
    }

    // Interceptor personalizado que registra cada petición y respuesta en el archivo domux_app.log
    private val fileLoggingInterceptor = Interceptor { chain ->
        val request = chain.request()
        val startNs = System.nanoTime()
        FileLogger.log("HTTP", "--> ${request.method} ${request.url}")

        val response: okhttp3.Response
        try {
            response = chain.proceed(request)
        } catch (e: Exception) {
            FileLogger.log("HTTP", "<-- FALLÓ ${request.method} ${request.url}: ${e.message}", "ERROR")
            throw e
        }

        val tookMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startNs)
        FileLogger.log("HTTP", "<-- ${response.code} ${response.message} ${request.url} (${tookMs}ms)")
        response
    }

    private val client = OkHttpClient.Builder()
        .addInterceptor(fileLoggingInterceptor)
        .addInterceptor(logging)
        .connectTimeout(60, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .build()

    val api: ApiService by lazy {
        FileLogger.log("Retrofit", "Inicializando cliente con URL base: $baseUrl")
        Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ApiService::class.java)
    }
}
