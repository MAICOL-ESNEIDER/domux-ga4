// LogsScreen.kt — pantalla para visualizar, refrescar, limpiar y compartir
// el archivo físico de registros (domux_app.log) generado por la aplicación.

package com.dracknoval.domux

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.dracknoval.domux.data.FileLogger

@Composable
fun LogsScreen(navController: NavController) {
    val context = LocalContext.current
    var logText by remember { mutableStateOf(FileLogger.readLogs()) }
    var mensajeState by remember { mutableStateOf("") }

    LaunchedEffect(Unit) {
        FileLogger.log("UI", "El usuario abrió la pantalla de Logs")
        logText = FileLogger.readLogs()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        Text("Archivo de Logs de la App", fontSize = 22.sp)
        Text("Ubicación interna: domux_app.log", fontSize = 12.sp, color = MaterialTheme.colorScheme.secondary)
        Spacer(Modifier.height(12.dp))

        // Tarjeta con scroll vertical y horizontal para ver los logs en formato de consola
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
        ) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(12.dp)
                    .verticalScroll(rememberScrollState())
                    .horizontalScroll(rememberScrollState())
            ) {
                Text(
                    text = logText,
                    fontFamily = FontFamily.Monospace,
                    fontSize = 11.sp
                )
            }
        }

        if (mensajeState.isNotEmpty()) {
            Spacer(Modifier.height(8.dp))
            Text(mensajeState, fontSize = 13.sp)
        }

        Spacer(Modifier.height(12.dp))

        // Fila de acciones para refrescar, compartir y limpiar
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Button(
                onClick = {
                    logText = FileLogger.readLogs()
                    mensajeState = "Registros actualizados"
                },
                modifier = Modifier.weight(1f)
            ) {
                Text("Refrescar", fontSize = 13.sp)
            }

            Button(
                onClick = {
                    FileLogger.shareLogFile(context)
                    mensajeState = "Exportando archivo de logs..."
                },
                modifier = Modifier.weight(1.2f)
            ) {
                Text("Compartir", fontSize = 13.sp)
            }
        }

        Spacer(Modifier.height(8.dp))

        OutlinedButton(
            onClick = {
                FileLogger.clearLogs()
                logText = FileLogger.readLogs()
                mensajeState = "Archivo de logs vaciado"
            },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Limpiar registros")
        }

        Spacer(Modifier.height(8.dp))

        TextButton(
            onClick = { navController.popBackStack() },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Volver")
        }
    }
}
