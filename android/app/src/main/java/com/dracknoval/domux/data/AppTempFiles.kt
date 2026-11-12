package com.dracknoval.domux.data

import android.content.Context
import java.io.File

/**
 * Los archivos temporales de la app: los adjuntos que se abren para ver o escuchar, la foto o el
 * video que se acaba de tomar con la cámara (antes de reducirlo y enviarlo) y la imagen del QR que
 * se comparte. Viven solo en la carpeta privada de la app (no en la galería ni en Descargas)
 * y se borran al cerrar el visor, al cerrar sesión y al abrir la app: en el celular no queda
 * ningún dato de la unidad.
 */
object AppTempFiles {
    private const val MEDIA_FOLDER = "media-temp"
    private const val SHARED_FOLDER = "shared"
    private const val CAPTURE_FOLDER = "capture"

    /** La carpeta donde el visor escribe un video, un audio o un PDF mientras está abierto. */
    fun mediaFolder(context: Context): File = File(context.cacheDir, MEDIA_FOLDER).apply { mkdirs() }

    /**
     * La carpeta donde la cámara deja la foto o el video que se acaba de tomar. Es privada: lo que
     * se graba para DOMUX no aparece en la galería, y se borra apenas se lee.
     */
    fun captureFolder(context: Context): File = File(context.cacheDir, CAPTURE_FOLDER).apply { mkdirs() }

    /** Borra todo lo temporal; se llama al cerrar sesión y al abrir la app. */
    fun clearAll(context: Context) {
        File(context.cacheDir, MEDIA_FOLDER).deleteRecursively()
        File(context.cacheDir, SHARED_FOLDER).deleteRecursively()
        File(context.cacheDir, CAPTURE_FOLDER).deleteRecursively()
    }
}
