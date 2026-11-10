package com.dracknoval.domux

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.dracknoval.domux.data.GuardOption
import com.dracknoval.domux.data.GuardShiftRequest
import com.dracknoval.domux.data.PushRegistration
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/**
 * Cambio de guardia en la tablet de portería (HU-010). El guardia que entra elige su nombre y
 * escribe su PIN de 4 dígitos, sin cerrar sesión ni escribir su correo y su contraseña.
 *
 * Si el PIN es correcto el servidor entrega la sesión del nuevo guardia y aquí se guarda en lugar
 * de la anterior; desde ese momento todo lo que se registre queda a nombre del nuevo guardia.
 * [onShiftDone] avisa a quien abrió la ventana para que la cierre y recargue sus listas.
 */
@Composable
fun GuardShiftDialog(
    onDismiss: () -> Unit,
    onShiftDone: (message: String) -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var guards by remember { mutableStateOf<List<GuardOption>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var busy by remember { mutableStateOf(false) }
    var guardId by remember { mutableStateOf<Int?>(null) }
    var pin by remember { mutableStateOf("") }
    var attempted by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        try {
            val response = RetrofitClient.api.getGuards(Session.bearer())
            if (response.isSuccessful) {
                guards = response.body()?.guards.orEmpty()
            } else {
                error = mensajeDeError(response.code(), response.errorBody()?.string())
            }
        } catch (exception: CancellationException) {
            throw exception
        } catch (exception: Exception) {
            error = "No se pudo cargar la lista de guardias: ${exception.message.orEmpty()}"
        } finally {
            loading = false
        }
    }

    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text("Cambiar de guardia") },
        text = {
            Column(
                modifier = Modifier
                    .heightIn(max = 420.dp)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text("Guardia actual: ${Session.userName.orEmpty()}")
                Text("Elige quién recibe el turno y escribe su PIN de 4 dígitos.")
                if (loading) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                if (!loading && guards.isEmpty() && error == null) {
                    Text(
                        "Ningún guardia tiene PIN todavía. El administrador lo asigna en " +
                            "«Gestión de usuarios»."
                    )
                }
                guards.forEach { guard ->
                    FilterChip(
                        selected = guardId == guard.id,
                        onClick = { guardId = guard.id },
                        label = { Text(guard.name) }
                    )
                }
                if (guards.isNotEmpty()) {
                    OutlinedTextField(
                        value = pin,
                        onValueChange = { pin = it.filter(Char::isDigit).take(4) },
                        label = { Text("PIN de 4 dígitos") },
                        singleLine = true,
                        visualTransformation = PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                        isError = attempted && pin.length != 4,
                        supportingText = {
                            if (attempted && pin.length != 4) Text("El PIN tiene exactamente 4 dígitos.")
                        },
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                error?.let {
                    Text(
                        it,
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                enabled = !busy && guards.isNotEmpty(),
                onClick = {
                    attempted = true
                    val chosen = guardId
                    if (chosen == null) {
                        error = "Elige el guardia que recibe el turno."
                        return@TextButton
                    }
                    if (pin.length != 4) return@TextButton
                    busy = true
                    error = null
                    scope.launch {
                        try {
                            val response = RetrofitClient.api.guardShift(
                                Session.bearer(),
                                GuardShiftRequest(chosen, pin)
                            )
                            if (response.isSuccessful) {
                                val body = response.body()
                                val newToken = body?.token
                                val newUser = body?.user
                                if (newToken.isNullOrBlank() || newUser == null) {
                                    error = "El servidor no envió los datos del nuevo turno."
                                } else {
                                    Session.token = newToken
                                    Session.updateFrom(newUser)
                                    Session.persist(context)
                                    // El aviso push de este equipo pasa a ser del guardia que entra.
                                    PushRegistration.registerAfterAuthentication(context.applicationContext)
                                    pin = ""
                                    onShiftDone("Turno registrado: ${newUser.name}.")
                                }
                            } else {
                                error = mensajeDeError(response.code(), response.errorBody()?.string())
                            }
                        } catch (exception: CancellationException) {
                            throw exception
                        } catch (exception: Exception) {
                            error = "No se pudo cambiar de guardia: ${exception.message.orEmpty()}"
                        } finally {
                            busy = false
                        }
                    }
                }
            ) { Text(if (busy) "Verificando..." else "Cambiar de guardia") }
        },
        dismissButton = {
            TextButton(enabled = !busy, onClick = onDismiss) { Text("Cancelar") }
        }
    )
}
