package com.dracknoval.domux

import androidx.lifecycle.ViewModel
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.CancellationException
import retrofit2.Response

/**
 * Base de los ViewModels de portería (paquetes, visitas y vehículos): hace las llamadas al
 * servidor y deja el error en pantalla si algo falla. Cada ViewModel dice cómo guardar el
 * aviso en su propio estado ([postMessage]); la pantalla solo lo dibuja.
 */
abstract class DomuxViewModel : ViewModel() {
    /** El encabezado de autorización con la sesión de quien tiene el turno ahora. */
    protected fun auth(): String = Session.bearer()

    /** Deja el texto como aviso de la pantalla: rojo si es un error, verde si no. */
    protected abstract fun postMessage(text: String, isError: Boolean)

    /** Marca la pantalla como ocupada (o libre) para que los botones no se toquen dos veces. */
    protected abstract fun setBusy(busy: Boolean)

    /** Para que la pantalla deje un aviso propio, por ejemplo un campo obligatorio vacío. */
    fun showNotice(text: String, isError: Boolean = true) = postMessage(text, isError)

    protected fun showError(text: String) = postMessage(text, true)

    protected fun showSuccess(text: String) = postMessage(text, false)

    /** Ejecuta [block] con la pantalla ocupada; vuelve a quedar libre pase lo que pase. */
    protected suspend fun <T> withBusy(block: suspend () -> T): T {
        setBusy(true)
        try {
            return block()
        } finally {
            setBusy(false)
        }
    }

    /** Hace la llamada; si falla (HTTP o red) deja el mensaje en pantalla y devuelve null. */
    protected suspend fun <T> attempt(failure: String, request: suspend () -> Response<T>): Response<T>? {
        val response = callRaw(failure, request) ?: return null
        if (response.isSuccessful) return response
        showError(mensajeDeError(response.code(), response.errorBody()?.string()))
        return null
    }

    /**
     * Como [attempt], pero si el servidor responde con un error devuelve la respuesta tal cual:
     * así quien llama puede leer los datos que trae el error (por ejemplo el parqueadero sugerido).
     * Solo si falla la red deja el mensaje en pantalla y devuelve null.
     */
    protected suspend fun <T> callRaw(failure: String, request: suspend () -> Response<T>): Response<T>? {
        return try {
            request()
        } catch (exception: CancellationException) {
            throw exception
        } catch (exception: Exception) {
            showError("$failure: ${exception.message}")
            null
        }
    }
}
