// RetrofitClient.kt — crea y configura UNA sola instancia de Retrofit para toda la app.
// "object" en Kotlin = singleton: existe una única copia, accesible como RetrofitClient.api
// (mismo patrón exacto de GA1-GA3).

package com.dracknoval.domux.data

import com.dracknoval.domux.BuildConfig

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

object RetrofitClient {

    // ---------------------------------------------------------------------
    // BASE_URL: elige UNA de estas tres opciones según dónde esté corriendo
    // tu backend Flask. Solo debe haber UNA línea activa (las otras comentadas).
    // ---------------------------------------------------------------------

    // OPCIÓN 1 (por defecto, la misma que enseñan las guías GA1-GA3):
    // backend corriendo en tu PC con `python app.py`, emulador de Android Studio.
    // 10.0.2.2 es la dirección que el emulador entiende como "localhost de mi PC".
    // Ahora la URL base se toma desde BuildConfig (definida en app/build.gradle.kts) para facilitar
    // cambiar entre local y el backend desplegado en Render sin editar el código fuente.
    private val BASE_URL = BuildConfig.BASE_URL

    // OPCIÓN 2 (si 10.0.2.2 no te conecta, como pasó en el proyecto de e-commerce):
    // deja el backend en 127.0.0.1 y antes de correr la app ejecuta en una terminal:
    //   adb reverse tcp:5000 tcp:5000
    // luego descomenta la siguiente línea y comenta la de arriba.
    // private const val BASE_URL = "http://127.0.0.1:5000/"

    // OPCIÓN 3 (backend ya desplegado en Render, para probar en un celular físico
    // o para la entrega final): reemplaza por tu URL real de Render (con HTTPS).
    // private const val BASE_URL = "https://domux-backend.onrender.com/"

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
