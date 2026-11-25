package com.dracknoval.domux

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.navigation.NavController
import com.dracknoval.domux.data.ChangePasswordRequest
import com.dracknoval.domux.data.ResidentProfileUpdateRequest
import com.dracknoval.domux.data.ResidentialUnitData
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.UserData
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

@Composable
fun ResidentProfileScreen(navController: NavController) {
    var user by remember { mutableStateOf<UserData?>(null) }
    var unit by remember { mutableStateOf<ResidentialUnitData?>(null) }
    var email by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var socialNetworks by remember { mutableStateOf("") }
    var loading by remember { mutableStateOf(true) }
    var busy by remember { mutableStateOf(false) }
    var currentPassword by remember { mutableStateOf("") }
    var newPassword by remember { mutableStateOf("") }
    var passwordBusy by remember { mutableStateOf(false) }
    var attemptedPasswordChange by remember { mutableStateOf(false) }
    var currentPasswordVisible by remember { mutableStateOf(false) }
    var newPasswordVisible by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var messageIsError by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    suspend fun loadProfile() {
        loading = true
        try {
            val response = RetrofitClient.api.getProfile(Session.bearer())
            if (!response.isSuccessful) {
                message = mensajeDeError(response.code(), response.errorBody()?.string())
                return
            }
            user = response.body()?.user
            email = user?.email.orEmpty()
            phone = user?.phone.orEmpty()
            socialNetworks = user?.socialNetworks.orEmpty()
            val unitResponse = RetrofitClient.api.getMyUnit(Session.bearer())
            if (unitResponse.isSuccessful) unit = unitResponse.body()?.unit
            else message = mensajeDeError(unitResponse.code(), unitResponse.errorBody()?.string())
        } catch (exception: Exception) {
            if (exception is CancellationException) throw exception
            message = "No se pudo cargar el perfil: ${exception.message}"
        } finally {
            loading = false
        }
    }
    LaunchedEffect(Unit) { loadProfile() }

    DomuxScreenScaffold(title = "Mi perfil", navController = navController) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            DomuxFeedbackBanner(message, isError = messageIsError) { message = "" }
            if (loading) CircularProgressIndicator()
            user?.let { profile ->
            DomuxCard(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(profile.fullName ?: profile.name, style = MaterialTheme.typography.titleMedium)
                    Text("Documento: ${profile.documentId.orEmpty()}")
                    Text("Apartamento: ${profile.apartment ?: "Sin asignar"}")
                    Text("Tipo de residente: ${profile.occupancyType?.toDomuxDisplayLabel() ?: "—"}")
                    Text("Rol: ${profile.role.toDomuxDisplayLabel()}")
                    profile.recoveryEmail?.takeIf { it.isNotBlank() }?.let {
                        Text("Correo de recuperación: $it")
                    }
                }
            }
            Text("Datos que puedes actualizar", style = MaterialTheme.typography.titleMedium)
            OutlinedTextField(email, { email = it }, label = { Text("Correo") }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(
                value = phone,
                onValueChange = { input ->
                    phone = input.filter { ch -> ch.isDigit() }.take(10)
                },
                label = { Text("Teléfono") },
                isError = phone.isNotEmpty() && phone.length != 10,
                supportingText = { Text("10 dígitos (ej. 3001234567)") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                socialNetworks, { socialNetworks = it }, label = { Text("Redes sociales (opcional)") },
                modifier = Modifier.fillMaxWidth()
            )
            Button(
                enabled = !busy,
                onClick = {
                    if (phone.length != 10) {
                        message = "El teléfono debe tener exactamente 10 dígitos."
                        return@Button
                    }
                    busy = true
                    message = ""
                    scope.launch {
                        try {
                            val response = RetrofitClient.api.updateProfile(
                                Session.bearer(),
                                ResidentProfileUpdateRequest(
                                    phone = phone,
                                    email = email,
                                    socialNetworks = socialNetworks
                                )
                            )
                            if (response.isSuccessful) {
                                user = response.body()?.user
                                message = "Tus datos fueron actualizados exitosamente."
                                messageIsError = false
                            } else {
                                message = mensajeDeError(response.code(), response.errorBody()?.string())
                                messageIsError = true
                            }
                        } catch (exception: Exception) {
                            if (exception is CancellationException) throw exception
                            message = "No se pudo guardar el perfil: ${exception.message}"
                            messageIsError = true
                        } finally {
                            busy = false
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth()
            ) { Text(if (busy) "Guardando..." else "Guardar cambios") }

            Text(
                "Para cambiar apartamento, tipo de residente, parentesco, documento, mascotas o vehículos, " +
                    "solicítalo a administración mediante una PQRS o en la oficina.",
                style = MaterialTheme.typography.bodyMedium
            )
            TextButton(onClick = { navController.navigate("pqrs") }) {
                Text("Crear PQRS para solicitar un cambio")
            }
            DomuxCard(Modifier.fillMaxWidth()) {
                Column(
                    Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Text("Cambiar mi contraseña", style = MaterialTheme.typography.titleMedium)
                    OutlinedTextField(
                        value = currentPassword,
                        onValueChange = { currentPassword = it },
                        label = { Text("Contraseña actual") },
                        isError = attemptedPasswordChange && currentPassword.isBlank(),
                        singleLine = true,
                        visualTransformation = if (currentPasswordVisible) VisualTransformation.None else PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrectEnabled = false),
                        trailingIcon = {
                            val image = if (currentPasswordVisible) Icons.Rounded.Visibility else Icons.Rounded.VisibilityOff
                            IconButton(onClick = { currentPasswordVisible = !currentPasswordVisible }) {
                                Icon(image, "Toggle password visibility")
                            }
                        },
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = newPassword,
                        onValueChange = { newPassword = it },
                        label = { Text("Nueva contraseña") },
                        isError = attemptedPasswordChange && !validStrongPassword(newPassword),
                        supportingText = {
                            Text("Mínimo 8 caracteres, mayúscula, minúscula, número y símbolo.")
                        },
                        singleLine = true,
                        visualTransformation = if (newPasswordVisible) VisualTransformation.None else PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrectEnabled = false),
                        trailingIcon = {
                            val image = if (newPasswordVisible) Icons.Rounded.Visibility else Icons.Rounded.VisibilityOff
                            IconButton(onClick = { newPasswordVisible = !newPasswordVisible }) {
                                Icon(image, "Toggle password visibility")
                            }
                        },
                        modifier = Modifier.fillMaxWidth()
                    )
                    Button(
                        enabled = !passwordBusy,
                        onClick = {
                            attemptedPasswordChange = true
                            if (currentPassword.isBlank() || !validStrongPassword(newPassword)) {
                                message = "Revisa la contraseña actual y los requisitos de la nueva contraseña."
                                return@Button
                            }
                            passwordBusy = true
                            message = ""
                            scope.launch {
                                try {
                                    val response = RetrofitClient.api.changePassword(
                                        Session.bearer(),
                                        ChangePasswordRequest(currentPassword, newPassword)
                                    )
                                    if (response.isSuccessful) {
                                        message = response.body()?.message
                                            ?: "Contraseña actualizada exitosamente."
                                        messageIsError = false
                                        currentPassword = ""
                                        newPassword = ""
                                        attemptedPasswordChange = false
                                    } else {
                                        message = mensajeDeError(response.code(), response.errorBody()?.string())
                                        messageIsError = true
                                    }
                                } catch (exception: Exception) {
                                    if (exception is CancellationException) throw exception
                                    message = "No se pudo actualizar la contraseña: ${exception.message}"
                                    messageIsError = true
                                } finally {
                                    passwordBusy = false
                                }
                            }
                        },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(if (passwordBusy) "Actualizando..." else "Actualizar contraseña")
                    }
                }
            }
        }
            unit?.let { profile ->
            Text("Información del hogar", style = MaterialTheme.typography.titleLarge)
            profile.residents.forEach { resident ->
                Text(
                    "${resident.name} · ${(resident.occupancyType ?: "residente").toDomuxDisplayLabel()}"
                )
            }
            Text("Parqueadero: ${profile.parkingIdentifier ?: "No registrado"}")
            profile.storageIdentifier?.takeIf(String::isNotBlank)?.let { storage ->
                Text("Cuarto útil: $storage")
            }
            profile.members.forEach { member ->
                DomuxCard(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(12.dp)) {
                        Text("${member.name} ${member.lastName.orEmpty()}".trim(), style = MaterialTheme.typography.titleSmall)
                        Text(
                            "Parentesco: ${(member.otherRelationship ?: member.relationship).toDomuxDisplayLabel()}"
                        )
                        Text("Fecha de nacimiento: ${member.birthDate}")
                    }
                }
            }
            if (profile.pets.isNotEmpty()) {
                Text("Mascotas registradas", style = MaterialTheme.typography.titleMedium)
                profile.pets.forEach { pet ->
                    Text("• ${pet.name} (${pet.species.toDomuxDisplayLabel()})")
                }
            }
            if (profile.vehicles.isNotEmpty()) {
                Text("Vehículos registrados", style = MaterialTheme.typography.titleMedium)
                profile.vehicles.forEach { vehicle ->
                    Text("• ${vehicle.type.toDomuxDisplayLabel()}: ${vehicle.plate}")
                }
            }
        }
            Spacer(Modifier.height(6.dp))
        }
    }
}
