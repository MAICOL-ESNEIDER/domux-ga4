// LoginScreen.kt — pantalla de inicio de sesión. Es la MISMA pantalla para los 3
// roles (Administrador, Residente, Guardia): el backend le dice a la app qué rol
// tiene el usuario, y a partir de ahí HomeScreen decide qué mostrarle.

package com.dracknoval.domux

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.dracknoval.domux.data.FileLogger
import com.dracknoval.domux.data.LoginRequest
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.launch

@Composable
fun LoginScreen(navController: NavController) {
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var result by remember { mutableStateOf("") }
    var loading by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text("Domux", fontSize = 30.sp)
        Text("Gestión de la unidad residencial", fontSize = 14.sp)
        Spacer(Modifier.height(32.dp))

        OutlinedTextField(
            value = email,
            onValueChange = { email = it },
            label = { Text("Correo") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(12.dp))

        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text("Contraseña") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(24.dp))

        Button(
            onClick = {
                if (!email.contains("@") || password.isBlank()) {
                    result = "Escribe un correo válido y tu contraseña"
                    FileLogger.log("Auth", "Intento de inicio de sesión con correo o clave inválidos", "WARN")
                    return@Button
                }
                loading = true
                result = ""
                FileLogger.log("Auth", "Iniciando autenticación para usuario: $email")
                scope.launch {
                    try {
                        val response = RetrofitClient.api.login(LoginRequest(email, password))
                        if (response.isSuccessful) {
                            val user = response.body()?.user
                            if (user == null) {
                                result = " El servidor no envió los datos del usuario"
                                FileLogger.log("Auth", "Respuesta de login exitosa pero cuerpo de usuario nulo", "WARN")
                            } else {
                                // Guardamos la sesión: token, nombre, rol y apartamento.
                                Session.token = response.body()?.token
                                Session.userId = user.id
                                Session.userName = user.name
                                Session.role = user.role
                                Session.apartment = user.apartment

                                FileLogger.log("Auth", "Inicio de sesión exitoso. Usuario: ${user.name}, Rol: ${user.role}")

                                // Vamos al menú y borramos "login" del historial.
                                navController.navigate("home") {
                                    popUpTo("login") { inclusive = true }
                                }
                            }
                        } else {
                            result = "${mensajeDeError(response.code(), response.errorBody()?.string())}"
                            FileLogger.log("Auth", "Error de inicio de sesión: código ${response.code()}", "ERROR")
                        }
                    } catch (e: Exception) {
                        result = "No se pudo conectar con el servidor: ${e.message}"
                        FileLogger.log("Auth", "Excepción en inicio de sesión: ${e.message}", "ERROR")
                    } finally {
                        loading = false
                    }
                }
            },
            enabled = !loading,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(if (loading) "Entrando..." else "Entrar")
        }

        Spacer(Modifier.height(16.dp))

        OutlinedButton(
            onClick = { navController.navigate("logs") },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Ver / Exportar Logs de la App")
        }

        if (result.isNotEmpty()) {
            Spacer(Modifier.height(20.dp))
            Text(result)
        }
    }
}
