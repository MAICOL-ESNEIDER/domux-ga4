// AppPreferences.kt — Las preferencias de la app en este celular.
// Solo guarda comodidades que no son datos de nadie: por ahora, el tamaño del texto. Va en el
// celular y no se manda al servidor.

package com.dracknoval.domux.data

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/**
 * Los tamaños de texto que se pueden elegir. El número ([factor]) se suma al tamaño que ya tenga
 * el celular en sus ajustes, igual que en la web: «Grande» es un 12,5 % más y «Muy grande», un 25 %.
 */
enum class TextSize(val key: String, val label: String, val factor: Float) {
    NORMAL("normal", "Normal", 1f),
    LARGE("grande", "Grande", 1.125f),
    EXTRA_LARGE("muy-grande", "Muy grande", 1.25f);

    companion object {
        /** El tamaño que se guardó con [key]; si no se reconoce, el normal. */
        fun fromKey(key: String?): TextSize = values().firstOrNull { it.key == key } ?: NORMAL
    }
}

/**
 * Lo que la persona eligió en «Preferencias». Se guarda en el celular y se lee al abrir la app
 * ([load]). [textSize] es un estado de Compose: al cambiarlo, toda la app se vuelve a dibujar con
 * el texto nuevo, sin cerrar nada.
 */
object AppPreferences {
    private const val FILE = "domux_preferencias"
    private const val KEY_TEXT_SIZE = "tamano_texto"

    var textSize by mutableStateOf(TextSize.NORMAL)
        private set

    /** Lee lo guardado. Si no hay nada (o no se puede leer), queda todo como viene de fábrica. */
    fun load(context: Context) {
        textSize = try {
            TextSize.fromKey(preferences(context).getString(KEY_TEXT_SIZE, null))
        } catch (exception: Exception) {
            TextSize.NORMAL
        }
    }

    /** Cambia el tamaño del texto de toda la app y lo guarda. El normal no guarda nada. */
    fun saveTextSize(context: Context, size: TextSize) {
        textSize = size
        try {
            val editor = preferences(context).edit()
            if (size == TextSize.NORMAL) editor.remove(KEY_TEXT_SIZE) else editor.putString(KEY_TEXT_SIZE, size.key)
            editor.apply()
        } catch (exception: Exception) {
            // Si el celular no deja guardar, el cambio vale hasta que se cierre la app: no pasa nada más.
        }
    }

    private fun preferences(context: Context) =
        context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
}
