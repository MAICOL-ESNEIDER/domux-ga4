// LoginScreen.kt — pantalla de inicio de sesión. Es la MISMA pantalla para los 3
// roles (Administrador, Residente, Guardia): el backend le dice a la app qué rol
// tiene el usuario, y a partir de ahí HomeScreen decide qué mostrarle.

package com.dracknoval.domux

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.dracknoval.domux.data.LoginRequest
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.PushRegistration
import com.dracknoval.domux.data.mensajeDeError
import androidx.compose.ui.platform.LocalContext
import kotlinx.coroutines.launch

@Composable
fun LoginScreen(navController: NavController, onLoginComplete: () -> Unit = {}) {
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var result by remember { mutableStateOf("") }
    var loading by remember { mutableStateOf(false) }
    var attemptedLogin by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        DomuxBrandMark(size = 64.dp)
        Spacer(Modifier.height(14.dp))
        Text("DOMUX", fontSize = 27.sp, fontWeight = FontWeight.Bold, letterSpacing = 3.sp)
        Text("Residential Security OS", color = Color(0xFF94A3B8), fontSize = 13.sp)
        Spacer(Modifier.height(22.dp))
        Surface(
            color = Color(0xFF152C4A),
            shape = RoundedCornerShape(50),
            border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFF1E334D))
        ) {
            Text(
                "SISTEMA INTELIGENTE DE OPERACIÓN RESIDENCIAL",
                modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                color = Color(0xFF38BDF8),
                fontSize = 9.sp,
                fontWeight = FontWeight.SemiBold,
                letterSpacing = 0.7.sp
            )
        }
        Spacer(Modifier.height(20.dp))
        Text(
            buildAnnotatedString {
                append("Tu comunidad, en modo\n")
                withStyle(
                    SpanStyle(
                        brush = Brush.linearGradient(
                            listOf(Color(0xFF22D3EE), Color(0xFF818CF8), Color(0xFFA855F7))
                        ),
                        fontWeight = FontWeight.Bold
                    )
                ) {
                    append("premium.")
                }
            },
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.SemiBold,
            lineHeight = 34.sp,
            modifier = Modifier.padding(bottom = 24.dp)
        )

        OutlinedTextField(
            value = email,
            onValueChange = { email = it },
            label = { Text("Correo") },
            singleLine = true,
            isError = (attemptedLogin && email.trim().isEmpty()) ||
                (email.isNotEmpty() && !email.trim().contains("@")),
            supportingText = {
                if (attemptedLogin && email.trim().isEmpty()) Text("El correo es obligatorio")
                else if (email.isNotEmpty() && !email.trim().contains("@")) Text("Ingresa un correo válido")
            },
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(12.dp))

        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text("Contraseña") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            isError = attemptedLogin && password.trim().isEmpty(),
            supportingText = { if (attemptedLogin && password.trim().isEmpty()) Text("La contraseña es obligatoria") },
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(24.dp))

        Button(
            onClick = {
                attemptedLogin = true
                val normalizedEmail = email.trim().lowercase()
                if (!normalizedEmail.contains("@") || password.trim().isEmpty()) {
                    result = "Escribe un correo válido y tu contraseña"
                    return@Button
                }
                loading = true
                result = ""
                scope.launch {
                    try {
                        val response = RetrofitClient.api.login(LoginRequest(normalizedEmail, password))
                        if (response.isSuccessful) {
                            val user = response.body()?.user
                            if (user == null) {
                                result = "⚠️ El servidor no envió los datos del usuario"
                            } else {
                                val accessToken = response.body()?.token
                                if (accessToken.isNullOrBlank()) {
                                    result = "El servidor no envió el token de sesión."
                                    return@launch
                                }
                                Session.token = accessToken
                                Session.updateFrom(user)
                                Session.persist(context)
                                PushRegistration.registerAfterAuthentication(context.applicationContext)
                                navController.navigate("home") {
                                    popUpTo("login") { inclusive = true }
                                }
                                onLoginComplete()
                            }
                        } else {
                            result = "❌ ${mensajeDeError(response.code(), response.errorBody()?.string())}"
                        }
                    } catch (exception: Exception) {
                        result = "⚠️ No se pudo conectar con el servidor: ${exception.message}"
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

        Spacer(Modifier.height(12.dp))
        Text(
            "Cuentas de prueba: admin@domux.com / Admin123* · guardia@domux.com / Guardia123* · maria@domux.com / Residente123*",
            style = MaterialTheme.typography.bodySmall
        )
        if (result.isNotEmpty()) {
            Spacer(Modifier.height(20.dp))
            Text(result)
        }
    }
}
