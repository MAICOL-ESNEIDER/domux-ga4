package com.dracknoval.domux

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.dracknoval.domux.data.CreateUserRequest
import com.dracknoval.domux.data.ResetPasswordRequest
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.UpdateUserRequest
import com.dracknoval.domux.data.UserData
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.launch

private val occupancyOptions = listOf(
    "propietario" to "Propietario",
    "arrendatario" to "Arrendatario",
    "arrendador" to "Arrendador",
    "visitante" to "Visitante"
)
private val passwordSpecialChars = setOf('@', '$', '!', '%', '*', '?', '&', '#', '.', '_', '-')

private fun validStrongPassword(value: String): Boolean =
    value.length >= 8 &&
        value.any { it in 'A'..'Z' } &&
        value.any { it in 'a'..'z' } &&
        value.any { it in '0'..'9' } &&
        value.any { it in passwordSpecialChars } &&
        value.all {
            it in 'A'..'Z' || it in 'a'..'z' || it in '0'..'9' ||
                it in passwordSpecialChars
        }

@Composable
fun CreateUserScreen(navController: NavController) {
    var users by remember { mutableStateOf<List<UserData>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var busy by remember { mutableStateOf(false) }
    var attemptedSubmit by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    var lastName by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var documentId by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var role by remember { mutableStateOf("RESIDENT") }
    var apartment by remember { mutableStateOf("") }
    var occupancyType by remember { mutableStateOf("propietario") }
    var editUser by remember { mutableStateOf<UserData?>(null) }
    var resetUser by remember { mutableStateOf<UserData?>(null) }
    var resetPassword by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    suspend fun loadUsers() {
        loading = true
        try {
            val response = RetrofitClient.api.getUsers(Session.bearer())
            if (response.isSuccessful) users = response.body()?.users.orEmpty()
            else message = mensajeDeError(response.code(), response.errorBody()?.string())
        } catch (exception: Exception) {
            message = "No se pudo cargar la lista de usuarios: ${exception.message}"
        } finally {
            loading = false
        }
    }

    LaunchedEffect(Unit) { loadUsers() }

    Column(Modifier.fillMaxSize().padding(20.dp)) {
        Text("Gestión de usuarios", fontSize = 24.sp, color = MaterialTheme.colorScheme.primary)
        Spacer(Modifier.height(12.dp))
        if (message.isNotBlank()) Text(message, color = MaterialTheme.colorScheme.error)

        DomuxCard(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp)) {
                Text("Crear usuario", style = MaterialTheme.typography.titleMedium)
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    listOf("RESIDENT", "GUARD", "ADMIN").forEach { option ->
                        FilterChip(
                            selected = role == option,
                            onClick = { role = option },
                            label = { Text(if (option == "RESIDENT") "Residente" else if (option == "GUARD") "Guardia" else "Admin") }
                        )
                    }
                }
                UserInput(name, { name = it }, "Nombre", required = true, showMissingError = attemptedSubmit)
                UserInput(lastName, { lastName = it }, "Apellido", required = true, showMissingError = attemptedSubmit)
                UserInput(email, { email = it }, "Correo", required = true, showMissingError = attemptedSubmit)
                UserInput(phone, { phone = it }, "Teléfono", required = true, showMissingError = attemptedSubmit)
                UserInput(documentId, { documentId = it }, "Documento", required = true, showMissingError = attemptedSubmit)
                UserInput(password, { password = it }, "Contraseña temporal", required = true, password = true, showMissingError = attemptedSubmit)
                Text(
                    "Mínimo 8 caracteres, mayúscula, minúscula, número y símbolo.",
                    style = MaterialTheme.typography.bodySmall
                )
                if (role == "RESIDENT") {
                    UserInput(apartment, { apartment = it }, "Apartamento", required = true, showMissingError = attemptedSubmit)
                    Text("Tipo de tenencia")
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        occupancyOptions.forEach { (value, label) ->
                            FilterChip(
                                selected = occupancyType == value,
                                onClick = { occupancyType = value },
                                label = { Text(label) }
                            )
                        }
                    }
                }
                Spacer(Modifier.height(8.dp))
                Button(
                    enabled = !busy,
                    onClick = {
                        attemptedSubmit = true
                        if (listOf(name, lastName, email, phone, documentId).any { it.trim().isEmpty() } ||
                            (role == "RESIDENT" && apartment.trim().isEmpty()) ||
                            !email.trim().contains("@") || !validStrongPassword(password)
                        ) {
                            message = "Completa todos los campos obligatorios y revisa la contraseña."
                            return@Button
                        }
                        busy = true
                        message = ""
                        scope.launch {
                            try {
                                val response = RetrofitClient.api.createUser(
                                    Session.bearer(),
                                    CreateUserRequest(
                                        name.trim(), email.trim().lowercase(), password, role,
                                        apartment.trim().takeIf { role == "RESIDENT" },
                                        lastName.trim(), phone.trim(), documentId.trim(), occupancyType
                                    )
                                )
                                if (response.isSuccessful) {
                                    name = ""; lastName = ""; email = ""; phone = ""; documentId = ""
                                    password = ""; apartment = ""
                                    attemptedSubmit = false
                                    message = "Usuario creado."
                                    loadUsers()
                                } else message = mensajeDeError(response.code(), response.errorBody()?.string())
                            } catch (exception: Exception) {
                                message = "No se pudo crear el usuario: ${exception.message}"
                            } finally {
                                busy = false
                            }
                        }
                    },
                    modifier = Modifier.fillMaxWidth()
                ) { Text(if (busy) "Guardando..." else "Crear usuario") }
            }
        }

        Spacer(Modifier.height(16.dp))
        Text("Usuarios registrados", style = MaterialTheme.typography.titleLarge)
        if (loading) {
            CircularProgressIndicator()
        } else {
            LazyColumn(Modifier.weight(1f)) {
                items(users, key = { it.id }) { user ->
                    DomuxCard(Modifier.fillMaxWidth().padding(vertical = 5.dp)) {
                        Column(Modifier.padding(14.dp)) {
                            Text("${user.name} ${user.lastName.orEmpty()}".trim(), style = MaterialTheme.typography.titleMedium)
                            Text(user.email)
                            Text("Teléfono: ${user.phone.orEmpty()} · Documento: ${user.documentId.orEmpty()}")
                            Text("Rol: ${user.role} · Apto: ${user.apartment ?: "—"}")
                            Text("Tenencia: ${occupancyOptions.firstOrNull { it.first == user.occupancyType }?.second ?: "—"} · ${if (user.isActive) "Activo" else "Inactivo"}")
                            Row {
                                TextButton(onClick = { editUser = user }) { Text("Editar") }
                                TextButton(onClick = { resetUser = user; resetPassword = "" }) { Text("Restablecer contraseña") }
                            }
                        }
                    }
                }
            }
        }
        TextButton(onClick = { navController.popBackStack() }) { Text("Volver") }
    }

    editUser?.let { user ->
        var eName by remember(user.id) { mutableStateOf(user.name) }
        var eLastName by remember(user.id) { mutableStateOf(user.lastName.orEmpty()) }
        var eEmail by remember(user.id) { mutableStateOf(user.email) }
        var ePhone by remember(user.id) { mutableStateOf(user.phone.orEmpty()) }
        var eDocument by remember(user.id) { mutableStateOf(user.documentId.orEmpty()) }
        var eApartment by remember(user.id) { mutableStateOf(user.apartment.orEmpty()) }
        var eRole by remember(user.id) { mutableStateOf(user.role) }
        var eOccupancy by remember(user.id) { mutableStateOf(user.occupancyType ?: "propietario") }
        var eActive by remember(user.id) { mutableStateOf(user.isActive) }
        var attemptedEdit by remember(user.id) { mutableStateOf(false) }
        AlertDialog(
            onDismissRequest = { editUser = null },
            title = { Text("Editar usuario") },
            text = {
                Column(Modifier.heightIn(max = 480.dp).verticalScroll(rememberScrollState())) {
                    UserInput(eName, { eName = it }, "Nombre", true, showMissingError = attemptedEdit)
                    UserInput(eLastName, { eLastName = it }, "Apellido", true, showMissingError = attemptedEdit)
                    UserInput(eEmail, { eEmail = it }, "Correo", true, showMissingError = attemptedEdit)
                    UserInput(ePhone, { ePhone = it }, "Teléfono", true, showMissingError = attemptedEdit)
                    UserInput(eDocument, { eDocument = it }, "Documento", true, showMissingError = attemptedEdit)
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        listOf("RESIDENT", "GUARD", "ADMIN").forEach { option ->
                            FilterChip(selected = eRole == option, onClick = { eRole = option }, label = { Text(option) })
                        }
                    }
                    if (eRole == "RESIDENT") {
                        UserInput(eApartment, { eApartment = it }, "Apartamento", true, showMissingError = attemptedEdit)
                        Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                            occupancyOptions.forEach { (value, label) ->
                                FilterChip(selected = eOccupancy == value, onClick = { eOccupancy = value }, label = { Text(label) })
                            }
                        }
                    }
                    Row {
                        Checkbox(eActive, { eActive = it })
                        Text("Cuenta activa", Modifier.padding(top = 12.dp))
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    attemptedEdit = true
                    if (listOf(eName, eLastName, eEmail, ePhone, eDocument).any { it.trim().isEmpty() } ||
                        !eEmail.trim().contains("@") || (eRole == "RESIDENT" && eApartment.trim().isEmpty())
                    ) {
                        message = "Completa los campos obligatorios."
                        return@TextButton
                    }
                    scope.launch {
                        try {
                            val response = RetrofitClient.api.updateUser(
                                Session.bearer(), user.id,
                                UpdateUserRequest(
                                    eName.trim(), eLastName.trim(), eEmail.trim().lowercase(),
                                    ePhone.trim(), eDocument.trim(), eRole,
                                    eApartment.trim().takeIf { eRole == "RESIDENT" },
                                    eOccupancy.takeIf { eRole == "RESIDENT" }, eActive
                                )
                            )
                            message = if (response.isSuccessful) "Usuario actualizado."
                            else mensajeDeError(response.code(), response.errorBody()?.string())
                            if (response.isSuccessful) { editUser = null; loadUsers() }
                        } catch (exception: Exception) {
                            message = "No se pudo actualizar: ${exception.message}"
                        }
                    }
                }) { Text("Guardar") }
            },
            dismissButton = { TextButton(onClick = { editUser = null }) { Text("Cancelar") } }
        )
    }

    resetUser?.let { user ->
        var attemptedReset by remember(user.id) { mutableStateOf(false) }
        AlertDialog(
            onDismissRequest = { resetUser = null },
            title = { Text("Restablecer contraseña") },
            text = {
                Column {
                    Text("Se cambiará la contraseña de ${user.email}.")
                    UserInput(
                        resetPassword, { resetPassword = it }, "Nueva contraseña", true,
                        password = true, showMissingError = attemptedReset
                    )
                    Text("Mínimo 8 caracteres, mayúscula, minúscula, número y símbolo.", style = MaterialTheme.typography.bodySmall)
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    attemptedReset = true
                    if (!validStrongPassword(resetPassword)) {
                        message = "La contraseña no cumple los requisitos."
                        return@TextButton
                    }
                    scope.launch {
                        try {
                            val response = RetrofitClient.api.resetUserPassword(
                                Session.bearer(), user.id, ResetPasswordRequest(resetPassword)
                            )
                            message = if (response.isSuccessful) "Contraseña restablecida."
                            else mensajeDeError(response.code(), response.errorBody()?.string())
                            if (response.isSuccessful) resetUser = null
                        } catch (exception: Exception) {
                            message = "No se pudo restablecer la contraseña: ${exception.message}"
                        }
                    }
                }) { Text("Confirmar") }
            },
            dismissButton = { TextButton(onClick = { resetUser = null }) { Text("Cancelar") } }
        )
    }
}

@Composable
private fun UserInput(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    required: Boolean,
    password: Boolean = false,
    showMissingError: Boolean = false
) {
    val missing = required && showMissingError && value.trim().isEmpty()
    val invalidEmail = label == "Correo" && value.isNotEmpty() && !value.trim().contains("@")
    val invalidPassword = password && value.isNotEmpty() && !validStrongPassword(value)
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        singleLine = true,
        isError = missing || invalidEmail || invalidPassword,
        supportingText = {
            if (missing) Text("$label es obligatorio")
            else if (invalidEmail) Text("Ingresa un correo válido")
            else if (invalidPassword) Text("Usa 8 caracteres con mayúscula, minúscula, número y símbolo")
        },
        visualTransformation = if (password) androidx.compose.ui.text.input.PasswordVisualTransformation()
        else androidx.compose.ui.text.input.VisualTransformation.None,
        modifier = Modifier.fillMaxWidth()
    )
}
