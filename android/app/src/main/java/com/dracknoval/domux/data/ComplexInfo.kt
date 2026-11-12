package com.dracknoval.domux.data

import android.graphics.BitmapFactory
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Los datos de la unidad residencial (HU-077) como los guardó la administración en la web.
 * Lo que la administración no escribió viene vacío (null).
 */
data class ComplexInfo(
    val name: String? = null,
    val nit: String? = null,
    val address: String? = null,
    val portalPhone: String? = null,
    val hasLogo: Boolean = false,
    // Cambia solo cuando cambia el logo: así no se descarga de nuevo si sigue igual.
    val logoVersion: String? = null,
    val updatedAt: String? = null
)

data class ComplexInfoResponse(val unit: ComplexInfo?)

/** El nombre que se muestra mientras la administración no haya guardado el de la unidad. */
const val DEFAULT_COMPLEX_NAME = "Altos de DOMUX"

/**
 * Guarda en memoria los datos de la unidad y su logo para que cualquier pantalla los dibuje.
 * Se piden al abrir el inicio; si no hay conexión se siguen mostrando los últimos que se tenían.
 */
object ComplexInfoStore {
    var info by mutableStateOf<ComplexInfo?>(null)
        private set

    var logo by mutableStateOf<ImageBitmap?>(null)
        private set

    private var logoVersion: String? = null

    /** El nombre de la unidad, o el de siempre si la administración aún no lo guardó. */
    val displayName: String
        get() = info?.name?.trim().orEmpty().ifBlank { DEFAULT_COMPLEX_NAME }

    /** Vuelve a pedir los datos al servidor y, solo si el logo cambió, también el logo. */
    suspend fun refresh() {
        try {
            val response = RetrofitClient.api.getComplexInfo(Session.bearer())
            val received = response.body()?.unit
            if (!response.isSuccessful || received == null) return
            info = received
            if (!received.hasLogo) {
                logo = null
                logoVersion = null
            } else if (logo == null || received.logoVersion != logoVersion) {
                loadLogo(received.logoVersion)
            }
        } catch (exception: CancellationException) {
            throw exception
        } catch (_: Exception) {
            // Sin conexión o con un error del servidor: se siguen mostrando los últimos datos.
        }
    }

    private suspend fun loadLogo(version: String?) {
        val image = RetrofitClient.api.getComplexLogo(Session.bearer())
        if (!image.isSuccessful) return
        // Leer la imagen y decodificarla no se hace en el hilo de la pantalla.
        val decoded = withContext(Dispatchers.IO) {
            image.body()?.bytes()?.let { bytes -> BitmapFactory.decodeByteArray(bytes, 0, bytes.size) }
        } ?: return
        logo = decoded.asImageBitmap()
        logoVersion = version
    }

    /** Olvida todo (al cerrar la sesión). */
    fun clear() {
        info = null
        logo = null
        logoVersion = null
    }
}
