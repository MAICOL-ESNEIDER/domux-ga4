// RetrofitClient.kt — crea y configura UNA sola instancia de Retrofit para toda la app.
// "object" en Kotlin = singleton: existe una única copia, accesible como RetrofitClient.api
// (mismo patrón exacto de GA1-GA3).

package com.dracknoval.domux.data

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

object RetrofitClient {

    // ---------------------------------------------------------------------
    // BASE_URL: elige UNA de estas tres opciones según dónde esté corriendo
    // tu backend Flask. Solo debe haber UNA línea activa (las otras comentadas).
    // ---------------------------------------------------------------------

    // URL del backend desplegado en Render. Esta es la opción activa para que la app
    // apunte al servicio en la nube y no a localhost ni a rutas locales del proyecto.
    private const val BASE_URL = "https://domux-backend.onrender.com/"

    // Si en algún momento quieres volver al backend local, cambia esta línea por:
    // private const val BASE_URL = "http://10.0.2.2:5000/"

    // Interceptor: "espía" cada petición y respuesta y las escribe en Logcat
    // (filtra por "OkHttp" en Logcat para verlas).
    private val logging = HttpLoggingInterceptor().apply {
        level = HttpLoggingInterceptor.Level.BODY
    }

    private val client = OkHttpClient.Builder()
        .addInterceptor(logging)
        .build()

    val api: ApiService = Retrofit.Builder()
        .baseUrl(BASE_URL)
        .client(client)
        .addConverterFactory(GsonConverterFactory.create())
        .build()
        .create(ApiService::class.java)
}
