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

/** Los valores con los que viene DOMUX mientras la administración no cambie las reglas de la unidad. */
const val DEFAULT_PQRS_TERM_DAYS = 15
const val DEFAULT_PACKAGE_ORANGE_HOURS = 48
const val DEFAULT_PACKAGE_RED_HOURS = 72

/**
 * Las reglas vigentes de la unidad (DEC-032): lo que la administración ajusta en la web cuando la asamblea
 * lo decide. Cada regla puede faltar (servidor viejo o sin conexión); entonces rige el valor de DOMUX.
 */
data class UnitRules(
    // Días hábiles para responder una PQRS, y el plazo propio de algunos tipos («Daño» → 5).
    val pqrsTermDays: Int? = null,
    val pqrsWarningDays: Int? = null,
    val pqrsTermsByCategory: Map<String, Int>? = null,
    // Horas sin reclamar para que un paquete pase a naranja y a rojo.
    val packageOrangeHours: Int? = null,
    val packageRedHours: Int? = null,
    val visitorParkingMaxDays: Int? = null
) {
    /** Los días hábiles que tiene una PQRS de ese tipo para ser respondida. */
    fun termFor(category: String?): Int =
        pqrsTermsByCategory?.get(category) ?: pqrsTermDays ?: DEFAULT_PQRS_TERM_DAYS

    val orangeHours: Int get() = packageOrangeHours ?: DEFAULT_PACKAGE_ORANGE_HOURS
    val redHours: Int get() = packageRedHours ?: DEFAULT_PACKAGE_RED_HOURS
}

data class ComplexInfoResponse(val unit: ComplexInfo?, val rules: UnitRules? = null)

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

    /** Las reglas vigentes de la unidad; mientras no lleguen, las de DOMUX. */
    var rules by mutableStateOf(UnitRules())
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
            response.body()?.rules?.let { rules = it }
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
        rules = UnitRules()
    }
}

/** Lo que responde «Reglas de la unidad» a la administración: las vigentes, las de DOMUX y cuáles se cambiaron. */
data class UnitRulesView(
    val rules: Map<String, Any?>? = null,
    val defaults: Map<String, Any?>? = null,
    val customized: Map<String, Boolean>? = null,
    val updatedAt: String? = null,
    val updatedByName: String? = null,
    val message: String? = null
)
