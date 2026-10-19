// FileLogger.kt — gestor singleton para registrar eventos y llamadas HTTP en un
// archivo físico real (domux_app.log) ubicado en el almacenamiento interno de la app.

package com.dracknoval.domux.data

import android.content.Context
import android.content.Intent
import android.util.Log
import androidx.core.content.FileProvider
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object FileLogger {

    private const val LOG_FILE_NAME = "domux_app.log"
    private var logFile: File? = null
    private val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())

    // Inicializa el archivo de logs usando el contexto de la aplicación.
    fun init(context: Context) {
        if (logFile == null) {
            val dir = context.filesDir
            if (!dir.exists()) {
                dir.mkdirs()
            }
            logFile = File(dir, LOG_FILE_NAME)
            if (!logFile!!.exists()) {
                logFile!!.createNewFile()
            }
            log("App", "=== Sesión iniciada / Aplicación arrancada ===")
        }
    }

    // Registra un mensaje con etiqueta y nivel, agregando marca de tiempo.
    @Synchronized
    fun log(tag: String, message: String, level: String = "INFO") {
        val timestamp = dateFormat.format(Date())
        val logLine = "[$timestamp] [$level/$tag]: $message\n"

        // Mostrar también en Logcat para desarrollo
        when (level.uppercase()) {
            "ERROR" -> Log.e(tag, message)
            "WARN" -> Log.w(tag, message)
            else -> Log.i(tag, message)
        }

        // Escribir físicamente en el archivo domux_app.log
        try {
            logFile?.let { file ->
                file.appendText(logLine)
            }
        } catch (e: Exception) {
            Log.e("FileLogger", "Error escribiendo en archivo de log: ${e.message}")
        }
    }

    // Lee todo el contenido actual del archivo de logs.
    fun readLogs(): String {
        return try {
            val text = logFile?.readText()
            if (text.isNullOrBlank()) {
                "El archivo de logs está vacío."
            } else {
                text
            }
        } catch (e: Exception) {
            "Error al leer el archivo de logs: ${e.message}"
        }
    }

    // Limpia/vacía el archivo de logs.
    @Synchronized
    fun clearLogs() {
        try {
            logFile?.writeText("")
            log("App", "=== Registros limpiados por el usuario ===")
        } catch (e: Exception) {
            Log.e("FileLogger", "Error al limpiar el archivo de logs: ${e.message}")
        }
    }

    // Devuelve la referencia al archivo físico de logs.
    fun getLogFile(): File? = logFile

    // Abre el menú del sistema para compartir/exportar el archivo de logs (.log / .txt).
    fun shareLogFile(context: Context) {
        val file = logFile
        if (file == null || !file.exists() || file.length() == 0L) {
            log("FileLogger", "Intento de compartir archivo vacío o inexistente", "WARN")
            return
        }

        try {
            val authority = "${context.packageName}.fileprovider"
            val contentUri = FileProvider.getUriForFile(context, authority, file)

            val shareIntent = Intent(Intent.ACTION_SEND).apply {
                type = "text/plain"
                putExtra(Intent.EXTRA_SUBJECT, "Archivo de Logs - Domux App")
                putExtra(Intent.EXTRA_TEXT, "Adjunto archivo de logs generado por la aplicación Domux.")
                putExtra(Intent.EXTRA_STREAM, contentUri)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }

            context.startActivity(Intent.createChooser(shareIntent, "Compartir / Exportar archivo de logs"))
            log("App", "El usuario inició la exportación del archivo de logs")
        } catch (e: Exception) {
            log("FileLogger", "Error al compartir archivo de logs: ${e.message}", "ERROR")
        }
    }

}
