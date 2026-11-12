package com.dracknoval.domux.data

import android.content.Context
import java.io.File

/**
 * Los archivos temporales de la app: los adjuntos que se abren para ver o escuchar y la imagen del
 * QR que se comparte. Viven solo en la carpeta privada de la app (no en la galería ni en Descargas)
 * y se borran al cerrar el visor, al cerrar sesión y al abrir la app: en el celular no queda
 * ningún dato de la unidad.
 */
object AppTempFiles {
    private const val MEDIA_FOLDER = "media-temp"
    private const val SHARED_FOLDER = "shared"

    /** La carpeta donde el visor escribe un video, un audio o un PDF mientras está abierto. */
    fun mediaFolder(context: Context): File = File(context.cacheDir, MEDIA_FOLDER).apply { mkdirs() }

    /** Borra todo lo temporal; se llama al cerrar sesión y al abrir la app. */
    fun clearAll(context: Context) {
        File(context.cacheDir, MEDIA_FOLDER).deleteRecursively()
        File(context.cacheDir, SHARED_FOLDER).deleteRecursively()
    }
}
