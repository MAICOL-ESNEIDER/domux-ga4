// HomeScreen.kt — el MENÚ que se ve después de iniciar sesión. Es UNA sola pantalla
// (mismo archivo para los 3 roles), y decide qué botones mostrar según Session.role.
// Es el mismo patrón de "if (Session.isAdmin)" de la GA3, extendido a 3 roles.

package com.dracknoval.domux

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.dracknoval.domux.data.FileLogger
import com.dracknoval.domux.data.Session

@Composable
fun HomeScreen(navController: NavController) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        // Saludo y rol, usando lo que guardamos en Session durante el login.
        Text("Hola, ${Session.userName ?: "usuario"}", fontSize = 24.sp)
        Text(
            when {
                Session.isAdmin -> "Rol: Administrador"
                Session.isResident -> "Rol: Residente" + (Session.apartment?.let { " · $it" } ?: "")
                Session.isGuard -> "Rol: Guardia de seguridad"
                else -> "Rol: desconocido"
            }
        )
        Spacer(Modifier.height(32.dp))

        // ----- Opciones visibles para TODOS los roles autenticados -----
        Button(onClick = { navController.navigate("announcements") }, modifier = Modifier.fillMaxWidth()) {
            Text("Anuncios de la unidad")
        }
        Spacer(Modifier.height(12.dp))

        // ----- Solo Administrador -----
        if (Session.isAdmin) {
            Button(onClick = { navController.navigate("pqrs") }, modifier = Modifier.fillMaxWidth()) {
                Text("Ver PQRS de residentes")
            }
            Spacer(Modifier.height(12.dp))
            Button(onClick = { navController.navigate("reservations") }, modifier = Modifier.fillMaxWidth()) {
                Text("Ver reservas de zonas comunes")
            }
            Spacer(Modifier.height(12.dp))
            Button(onClick = { navController.navigate("registry") }, modifier = Modifier.fillMaxWidth()) {
                Text("Ver registros de portería")
            }
            Spacer(Modifier.height(12.dp))
            Button(onClick = { navController.navigate("createUser") }, modifier = Modifier.fillMaxWidth()) {
                Text("Crear usuario (residente o guardia)")
            }
            Spacer(Modifier.height(12.dp))
        }

        // ----- Solo Residente -----
        if (Session.isResident) {
            Button(onClick = { navController.navigate("pqrs") }, modifier = Modifier.fillMaxWidth()) {
                Text("Mis PQRS")
            }
            Spacer(Modifier.height(12.dp))
            Button(onClick = { navController.navigate("reservations") }, modifier = Modifier.fillMaxWidth()) {
                Text("Reservar zona común")
            }
            Spacer(Modifier.height(12.dp))
            Button(onClick = { navController.navigate("registry") }, modifier = Modifier.fillMaxWidth()) {
                Text("Mis notificaciones (paquetes y visitas)")
            }
            Spacer(Modifier.height(12.dp))
        }

        // ----- Solo Guardia -----
        if (Session.isGuard) {
            Button(onClick = { navController.navigate("registry") }, modifier = Modifier.fillMaxWidth()) {
                Text("Registrar paquete / visitante")
            }
            Spacer(Modifier.height(12.dp))
        }

        // ----- Acceso a los logs de la app -----
        OutlinedButton(
            onClick = { navController.navigate("logs") },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Ver / Exportar Logs de la App")
        }
        Spacer(Modifier.height(12.dp))

        Spacer(Modifier.height(12.dp))
        OutlinedButton(
            onClick = {
                FileLogger.log("Auth", "Cierre de sesión de usuario: ${Session.userName}")
                Session.clear()
                navController.navigate("login") { popUpTo(0) }
            },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Cerrar sesión")
        }
    }
}
