package com.dracknoval.domux

import androidx.lifecycle.ViewModel
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.CancellationException
import retrofit2.Response
import java.io.IOException

/**
 * Base de los ViewModels de la app (portería, PQRS, reservas, perfil, notificaciones...): hace
 * las llamadas al servidor y deja el error en pantalla si algo falla. Cada ViewModel dice cómo
 * guardar el aviso en su propio estado ([postMessage]); la pantalla solo lo dibuja, en verde si
 * salió bien y en rojo si no.
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

    /**
     * Hace la llamada; si falla (HTTP o red) deja el mensaje en pantalla y devuelve null.
     * [onError] decide dónde va el error: por defecto al aviso de la pantalla, pero si hay un
     * diálogo abierto conviene mostrarlo dentro del diálogo, que es lo que la persona está viendo.
     */
    protected suspend fun <T> attempt(
        failure: String,
        onError: (String) -> Unit = { showError(it) },
        request: suspend () -> Response<T>
    ): Response<T>? {
        val response = callRaw(failure, onError, request) ?: return null
        if (response.isSuccessful) return response
        onError(mensajeDeError(response.code(), response.errorBody()?.string()))
        return null
    }

    /**
     * Como [attempt], pero si el servidor responde con un error devuelve la respuesta tal cual:
     * así quien llama puede leer los datos que trae el error (por ejemplo el parqueadero sugerido).
     * Solo si falla la red deja el mensaje en pantalla y devuelve null.
     */
    protected suspend fun <T> callRaw(
        failure: String,
        onError: (String) -> Unit = { showError(it) },
        request: suspend () -> Response<T>
    ): Response<T>? {
        return try {
            request()
        } catch (exception: CancellationException) {
            throw exception
        } catch (exception: IOException) {
            // Sin internet, servidor dormido o la conexión se cortó: el detalle técnico no le sirve a nadie.
            onError("$failure. Revisa tu conexión a internet e inténtalo de nuevo.")
            null
        } catch (exception: Exception) {
            onError("$failure: ${exception.message ?: "error inesperado"}.")
            null
        }
    }
}
