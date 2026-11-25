package com.dracknoval.domux

import android.util.Patterns
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Visibility
import androidx.compose.material.icons.rounded.VisibilityOff
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext
import androidx.navigation.NavController
import com.dracknoval.domux.data.ChangePasswordRequest
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

@Composable
fun ForcePasswordChangeScreen(navController: NavController) {
    var currentPassword by remember { mutableStateOf("") }
    var newPassword by remember { mutableStateOf("") }
    var confirmPassword by remember { mutableStateOf("") }
    var recoveryEmail by remember { mutableStateOf("") }
    var attemptedSubmit by remember { mutableStateOf(false) }
    var saving by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var currentPasswordVisible by remember { mutableStateOf(false) }
    var newPasswordVisible by remember { mutableStateOf(false) }
    var confirmPasswordVisible by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    BackHandler(enabled = true) {}

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Spacer(Modifier.height(8.dp))
        DomuxBrandMark(size = 64.dp)
        Text("DOMUX", fontSize = 27.sp, fontWeight = FontWeight.Bold, letterSpacing = 3.sp)
        Text("Actualiza tu contraseña para continuar", color = Color(0xFF94A3B8))

        OutlinedTextField(
            value = currentPassword,
            onValueChange = { currentPassword = it },
            label = { Text("Contraseña temporal actual") },
            singleLine = true,
            isError = attemptedSubmit && currentPassword.isBlank(),
            supportingText = {
                if (attemptedSubmit && currentPassword.isBlank()) {
                    Text("La contraseña actual es obligatoria")
                }
            },
            visualTransformation = if (currentPasswordVisible) VisualTransformation.None else PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrectEnabled = false),
            trailingIcon = {
                val image = if (currentPasswordVisible) Icons.Rounded.Visibility else Icons.Rounded.VisibilityOff
                IconButton(onClick = { currentPasswordVisible = !currentPasswordVisible }) {
                    Icon(image, "Toggle password visibility")
                }
            },
            enabled = !saving,
            modifier = Modifier.fillMaxWidth()
        )
        OutlinedTextField(
            value = newPassword,
            onValueChange = { newPassword = it },
            label = { Text("Nueva contraseña personal") },
            singleLine = true,
            isError = attemptedSubmit && !validStrongPassword(newPassword),
            supportingText = {
                Text("Mínimo 8 caracteres, mayúscula, minúscula, número y símbolo.")
            },
            visualTransformation = if (newPasswordVisible) VisualTransformation.None else PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrectEnabled = false),
            trailingIcon = {
                val image = if (newPasswordVisible) Icons.Rounded.Visibility else Icons.Rounded.VisibilityOff
                IconButton(onClick = { newPasswordVisible = !newPasswordVisible }) {
                    Icon(image, "Toggle password visibility")
                }
            },
            enabled = !saving,
            modifier = Modifier.fillMaxWidth()
        )
        OutlinedTextField(
            value = confirmPassword,
            onValueChange = { confirmPassword = it },
            label = { Text("Confirmar nueva contraseña") },
            singleLine = true,
            isError = attemptedSubmit &&
                (confirmPassword.isBlank() || confirmPassword != newPassword),
            supportingText = {
                if (attemptedSubmit &&
                    (confirmPassword.isBlank() || confirmPassword != newPassword)
                ) {
                    Text("Las contraseñas no coinciden")
                }
            },
            visualTransformation = if (confirmPasswordVisible) VisualTransformation.None else PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrectEnabled = false),
            trailingIcon = {
                val image = if (confirmPasswordVisible) Icons.Rounded.Visibility else Icons.Rounded.VisibilityOff
                IconButton(onClick = { confirmPasswordVisible = !confirmPasswordVisible }) {
                    Icon(image, "Toggle password visibility")
                }
            },
            enabled = !saving,
            modifier = Modifier.fillMaxWidth()
        )
        OutlinedTextField(
            value = recoveryEmail,
            onValueChange = { recoveryEmail = it },
            label = { Text("Correo de recuperación (opcional)") },
            singleLine = true,
            isError = attemptedSubmit && recoveryEmail.isNotBlank() &&
                !isValidRecoveryEmail(recoveryEmail, Session.email),
            supportingText = {
                if (attemptedSubmit && recoveryEmail.isNotBlank() &&
                    !isValidRecoveryEmail(recoveryEmail, Session.email)
                ) {
                    Text("Ingresa un correo válido distinto al correo principal.")
                }
            },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
            enabled = !saving,
            modifier = Modifier.fillMaxWidth()
        )
        Text(
            "Se usará para respaldo si pierdes acceso a tu correo principal",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.fillMaxWidth()
        )

        if (message.isNotBlank()) {
            Text(message, color = MaterialTheme.colorScheme.error)
        }
        Button(
            enabled = !saving,
            onClick = {
                attemptedSubmit = true
                val normalizedRecoveryEmail = recoveryEmail.trim()
                if (currentPassword.isBlank()) {
                    message = "Escribe tu contraseña temporal actual."
                    return@Button
                }
                if (!validStrongPassword(newPassword)) {
                    message = "La nueva contraseña no cumple los requisitos."
                    return@Button
                }
                if (confirmPassword != newPassword) {
                    message = "Confirma correctamente tu nueva contraseña."
                    return@Button
                }
                if (normalizedRecoveryEmail.isNotEmpty() &&
                    !isValidRecoveryEmail(normalizedRecoveryEmail, Session.email)
                ) {
                    message = "Ingresa un correo de recuperación válido y distinto al principal."
                    return@Button
                }

                saving = true
                message = ""
                scope.launch {
                    try {
                        val response = RetrofitClient.api.changePassword(
                            Session.bearer(),
                            ChangePasswordRequest(
                                currentPassword = currentPassword,
                                newPassword = newPassword,
                                recoveryEmail = normalizedRecoveryEmail.takeIf { it.isNotEmpty() }
                            )
                        )
                        if (response.isSuccessful) {
                            Session.mustChangePassword = false
                            Session.persist(context)
                            navController.navigate("home") {
                                popUpTo("force_password_change") { inclusive = true }
                                launchSingleTop = true
                            }
                        } else {
                            message = mensajeDeError(
                                response.code(),
                                response.errorBody()?.string()
                            )
                        }
                    } catch (exception: Exception) {
                        if (exception is CancellationException) throw exception
                        message = "No se pudo actualizar la contraseña: ${exception.message}"
                    } finally {
                        saving = false
                    }
                }
            },
            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
        ) {
            if (saving) CircularProgressIndicator()
            else Text("Guardar y continuar")
        }
    }
}

private fun isValidRecoveryEmail(value: String, primaryEmail: String?): Boolean =
    value.length <= 120 &&
        Patterns.EMAIL_ADDRESS.matcher(value).matches() &&
        !value.equals(primaryEmail?.trim(), ignoreCase = true)
