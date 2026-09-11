// CreateUserScreen.kt — SOLO el Administrador puede crear cuentas nuevas, de
// Residente o de Guardia de seguridad. Mismo patrón de formulario que GA3.

package com.dracknoval.domux

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.dracknoval.domux.data.CreateUserRequest
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.launch

@Composable
fun CreateUserScreen(navController: NavController) {
    var nombre by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var rol by remember { mutableStateOf("RESIDENT") } // "RESIDENT" o "GUARD"
    var apartamento by remember { mutableStateOf("") }
    var enviando by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    Column(modifier = Modifier.fillMaxSize().padding(24.dp)) {
        Text("Crear usuario", fontSize = 22.sp)
        Spacer(Modifier.height(16.dp))

        Text("Rol")
        Row {
            FilterChip(
                selected = rol == "RESIDENT",
                onClick = { rol = "RESIDENT" },
                label = { Text("Residente") },
                modifier = Modifier.padding(end = 8.dp)
            )
            FilterChip(
                selected = rol == "GUARD",
                onClick = { rol = "GUARD" },
                label = { Text("Guardia") }
            )
        }
        Spacer(Modifier.height(12.dp))

        OutlinedTextField(
            value = nombre, onValueChange = { nombre = it },
            label = { Text("Nombre completo") }, singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = email, onValueChange = { email = it },
            label = { Text("Correo") }, singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = password, onValueChange = { password = it },
            label = { Text("Contraseña temporal") }, singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(8.dp))

        // El apartamento solo aplica si el nuevo usuario es Residente.
        if (rol == "RESIDENT") {
            OutlinedTextField(
                value = apartamento, onValueChange = { apartamento = it },
                label = { Text("Torre / Apartamento") }, singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(8.dp))
        }

        Button(
            onClick = {
                if (nombre.isBlank() || !email.contains("@") || password.isBlank() ||
                    (rol == "RESIDENT" && apartamento.isBlank())
                ) {
                    result = "Completa todos los campos correctamente"
                    return@Button
                }
                enviando = true
                result = ""
                scope.launch {
                    try {
                        val resp = RetrofitClient.api.createUser(
                            Session.bearer(),
                            CreateUserRequest(
                                name = nombre,
                                email = email,
                                password = password,
                                role = rol,
                                apartment = if (rol == "RESIDENT") apartamento else null
                            )
                        )
                        result = if (resp.isSuccessful) {
                            nombre = ""; email = ""; password = ""; apartamento = ""
                            "✅ Usuario creado correctamente"
                        } else {
                            "❌ ${mensajeDeError(resp.code(), resp.errorBody()?.string())}"
                        }
                    } catch (e: Exception) {
                        result = "⚠️ ${e.message}"
                    } finally {
                        enviando = false
                    }
                }
            },
            enabled = !enviando,
            modifier = Modifier.fillMaxWidth()
        ) { Text(if (enviando) "Creando..." else "Crear usuario") }

        if (result.isNotEmpty()) { Spacer(Modifier.height(12.dp)); Text(result) }

        Spacer(Modifier.height(12.dp))
        TextButton(onClick = { navController.popBackStack() }) { Text("Volver") }
    }
}
