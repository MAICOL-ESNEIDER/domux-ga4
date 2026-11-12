package com.dracknoval.domux

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import androidx.core.content.FileProvider
import java.io.File
import java.io.FileOutputStream

/**
 * Compartir por WhatsApp, correo u otra app (HU-027 y HU-048).
 *
 * Las funciones devuelven null si salió bien, o el texto del error para mostrarlo en pantalla.
 */

/** Comparte un texto (por ejemplo el PIN de entrega de un paquete). */
fun shareText(context: Context, chooserTitle: String, text: String): String? {
    return try {
        val send = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, text)
        }
        context.startActivity(Intent.createChooser(send, chooserTitle).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        null
    } catch (exception: Exception) {
        "No se pudo compartir: ${exception.message}"
    }
}

/**
 * Comparte la imagen de un QR con un texto que la acompaña. La imagen se guarda en la carpeta
 * temporal de la app (res/xml/file_paths.xml) y se entrega con un FileProvider: así la otra
 * app puede leerla sin que DOMUX pida permiso de almacenamiento.
 */
fun shareQrImage(context: Context, bitmap: Bitmap, chooserTitle: String, text: String): String? {
    return try {
        val folder = File(context.cacheDir, "shared").apply { mkdirs() }
        val file = File(folder, "qr-domux.png")
        FileOutputStream(file).use { output -> bitmap.compress(Bitmap.CompressFormat.PNG, 100, output) }
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        val send = Intent(Intent.ACTION_SEND).apply {
            type = "image/png"
            putExtra(Intent.EXTRA_STREAM, uri)
            putExtra(Intent.EXTRA_TEXT, text)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        context.startActivity(Intent.createChooser(send, chooserTitle).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        null
    } catch (exception: Exception) {
        "No se pudo compartir el QR: ${exception.message}"
    }
}
