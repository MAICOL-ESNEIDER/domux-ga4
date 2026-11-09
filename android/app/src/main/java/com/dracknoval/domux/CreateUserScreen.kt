package com.dracknoval.domux

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.dracknoval.domux.data.CreateUserRequest
import com.dracknoval.domux.data.ResetPasswordRequest
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.UpdateUserRequest
import com.dracknoval.domux.data.UserData
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import android.net.Uri

private val occupancyOptions = listOf(
    "propietario" to "Propietario",
    "arrendatario" to "Arrendatario",
    "residente" to "Residente"
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

private fun nextFilter(value: Boolean?): Boolean? = when (value) {
    null -> true
    true -> false
    false -> null
}

private fun filterLabel(value: Boolean?): String = when (value) {
    null -> "Todos"
    true -> "Sí"
    false -> "No"
}

private fun isCancellation(e: Throwable): Boolean =
    e is CancellationException ||
        e.message?.contains("left the composition", ignoreCase = true) == true

@Composable
fun CreateUserScreen(navController: NavController) {
    var users by remember { mutableStateOf<List<UserData>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var busy by remember { mutableStateOf(false) }
    var attemptedSubmit by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var userSearch by remember { mutableStateOf("") }
    var apartmentFrom by remember { mutableStateOf("") }
    var apartmentTo by remember { mutableStateOf("") }
    var minAge by remember { mutableStateOf("") }
    var maxAge by remember { mutableStateOf("") }
    var occupancyFilter by remember { mutableStateOf("") }
    var activeFilter by remember { mutableStateOf<Boolean?>(null) }
    var petsFilter by remember { mutableStateOf<Boolean?>(null) }
    var vehiclesFilter by remember { mutableStateOf<Boolean?>(null) }
    var parkingFilter by remember { mutableStateOf<Boolean?>(null) }
    var storageFilter by remember { mutableStateOf<Boolean?>(null) }
    var currentPage by remember { mutableIntStateOf(1) }
    var totalPages by remember { mutableIntStateOf(1) }
    var totalUsers by remember { mutableIntStateOf(0) }
    var selectedTab by remember { mutableIntStateOf(0) }
    var showAdvancedFilters by remember { mutableStateOf(false) }
    var consentConfirmed by remember { mutableStateOf(false) }
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
    var pendingUserUpdate by remember { mutableStateOf<Pair<Int, UpdateUserRequest>?>(null) }
    var pendingPasswordReset by remember { mutableStateOf<Pair<Int, String>?>(null) }
    val scope = rememberCoroutineScope()

    suspend fun loadUsers(page: Int = currentPage) {
        loading = true
        try {
            val response = RetrofitClient.api.getUsers(
                auth = Session.bearer(),
                page = page,
                search = userSearch.trim().takeIf(String::isNotEmpty),
                occupancyType = occupancyFilter.takeIf(String::isNotEmpty),
                apartmentFrom = apartmentFrom.takeIf(String::isNotBlank),
                apartmentTo = apartmentTo.takeIf(String::isNotBlank),
                hasPets = petsFilter?.toString(),
                hasVehicles = vehiclesFilter?.toString(),
                hasParking = parkingFilter?.toString(),
                hasStorage = storageFilter?.toString(),
                minAge = minAge.takeIf(String::isNotBlank),
                maxAge = maxAge.takeIf(String::isNotBlank),
                isActive = activeFilter?.toString()
            )
            if (response.isSuccessful) {
                val result = response.body()
                users = result?.users.orEmpty()
                currentPage = result?.page ?: page
                totalPages = (result?.totalPages ?: 1).coerceAtLeast(1)
                totalUsers = result?.total ?: 0
            }
            else message = mensajeDeError(response.code(), response.errorBody()?.string())
        } catch (exception: Exception) {
            if (isCancellation(exception)) {
                if (exception is CancellationException) throw exception else return
            }
            message = "No se pudo cargar la lista de usuarios: ${exception.message}"
        } finally {
            loading = false
        }
    }

    LaunchedEffect(
        userSearch, apartmentFrom, apartmentTo, minAge, maxAge,
        occupancyFilter, activeFilter, petsFilter, vehiclesFilter, parkingFilter, storageFilter
    ) {
        delay(350)
        loadUsers(1)
    }

    DomuxScreenScaffold(title = "Gestión de usuarios", navController = navController) { padding ->
        Column(
            modifier = Modifier.fillMaxSize().padding(padding).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            DomuxSectionTabs(
                listOf("Usuarios ($totalUsers)", "Crear usuario"),
                selectedTab
            ) { selectedTab = it }
            if (message.isNotBlank()) DomuxFeedbackBanner(message) { message = "" }
            if (selectedTab == 1) {
                Column(
                    Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                ) {
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
                    Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                        Checkbox(checked = consentConfirmed, onCheckedChange = { consentConfirmed = it })
                        Text("El residente autorizó el tratamiento de sus datos para gestionar la vivienda.")
                    }
                    if (attemptedSubmit && !consentConfirmed) {
                        Text("Confirma la autorización del residente.", color = MaterialTheme.colorScheme.error)
                    }
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
                            (role == "RESIDENT" && !consentConfirmed) ||
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
                                        lastName.trim(), phone.trim(), documentId.trim(), occupancyType,
                                        role == "RESIDENT" && consentConfirmed
                                    )
                                )
                                if (response.isSuccessful) {
                                    name = ""; lastName = ""; email = ""; phone = ""; documentId = ""
                                    password = ""; apartment = ""
                                    consentConfirmed = false
                                    attemptedSubmit = false
                                    message = "Usuario creado exitosamente."
                                    selectedTab = 0
                                    loadUsers(1)
                                } else message = mensajeDeError(response.code(), response.errorBody()?.string())
                            } catch (exception: Exception) {
                                if (isCancellation(exception)) {
                                    if (exception is CancellationException) throw exception else return@launch
                                }
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
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    item {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedTextField(
                                value = userSearch,
                                onValueChange = { userSearch = it },
                                label = { Text("Buscar por nombre, correo, teléfono, documento o apartamento") },
                                singleLine = true,
                                modifier = Modifier.fillMaxWidth()
                            )
                            TextButton(onClick = { showAdvancedFilters = !showAdvancedFilters }) {
                                Text(
                                    if (showAdvancedFilters) "Ocultar filtros avanzados"
                                    else "Mostrar filtros avanzados"
                                )
                            }
                            if (showAdvancedFilters) {
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    OutlinedTextField(
                                        value = apartmentFrom,
                                        onValueChange = { apartmentFrom = it },
                                        label = { Text("Apto desde") },
                                        singleLine = true,
                                        modifier = Modifier.weight(1f)
                                    )
                                    OutlinedTextField(
                                        value = apartmentTo,
                                        onValueChange = { apartmentTo = it },
                                        label = { Text("Apto hasta") },
                                        singleLine = true,
                                        modifier = Modifier.weight(1f)
                                    )
                                }
                                Row(
                                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                                ) {
                                    occupancyOptions.forEach { (value, label) ->
                                        FilterChip(
                                            selected = occupancyFilter == value,
                                            onClick = {
                                                occupancyFilter = if (occupancyFilter == value) "" else value
                                            },
                                            label = { Text(label) }
                                        )
                                    }
                                }
                                Row(
                                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                                ) {
                                    FilterChip(
                                        selected = activeFilter == true,
                                        onClick = { activeFilter = nextFilter(activeFilter) },
                                        label = { Text("Estado: ${filterLabel(activeFilter)}") }
                                    )
                                    FilterChip(
                                        selected = petsFilter == true,
                                        onClick = { petsFilter = nextFilter(petsFilter) },
                                        label = { Text("Mascotas: ${filterLabel(petsFilter)}") }
                                    )
                                    FilterChip(
                                        selected = vehiclesFilter == true,
                                        onClick = { vehiclesFilter = nextFilter(vehiclesFilter) },
                                        label = { Text("Vehículos: ${filterLabel(vehiclesFilter)}") }
                                    )
                                }
                                Row(
                                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                                ) {
                                    FilterChip(
                                        selected = parkingFilter == true,
                                        onClick = { parkingFilter = nextFilter(parkingFilter) },
                                        label = { Text("Parqueadero: ${filterLabel(parkingFilter)}") }
                                    )
                                    FilterChip(
                                        selected = storageFilter == true,
                                        onClick = { storageFilter = nextFilter(storageFilter) },
                                        label = { Text("Cuarto útil: ${filterLabel(storageFilter)}") }
                                    )
                                }
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    OutlinedTextField(
                                        value = minAge,
                                        onValueChange = { minAge = it.filter(Char::isDigit) },
                                        label = { Text("Edad mínima") },
                                        singleLine = true,
                                        modifier = Modifier.weight(1f)
                                    )
                                    OutlinedTextField(
                                        value = maxAge,
                                        onValueChange = { maxAge = it.filter(Char::isDigit) },
                                        label = { Text("Edad máxima") },
                                        singleLine = true,
                                        modifier = Modifier.weight(1f)
                                    )
                                }
                            }
                            Text("$totalUsers usuarios - página $currentPage de $totalPages")
                        }
                    }
                    if (loading) {
                        item {
                            LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                        }
                    }
                    if (!loading && users.isEmpty()) {
                        item {
                            DomuxCard(Modifier.fillMaxWidth()) {
                                Text(
                                    "No se encontraron usuarios.",
                                    modifier = Modifier.padding(16.dp)
                                )
                            }
                        }
                    }
                    items(users, key = { it.id }) { user ->
                        DomuxCard(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(14.dp)) {
                                Text(user.fullName ?: user.name, style = MaterialTheme.typography.titleMedium)
                                Text(user.email)
                                Text("Teléfono: ${user.phone.orEmpty()} · Documento: ${user.documentId.orEmpty()}")
                                Text("Rol: ${user.role} · Apto: ${user.apartment ?: "—"}")
                                Text(
                                    "Tenencia: ${occupancyOptions.firstOrNull { it.first == user.occupancyType }?.second ?: "—"} · " +
                                        if (user.isActive) "Activo" else "Inactivo"
                                )
                                Row {
                                    TextButton(onClick = { editUser = user }) { Text("Editar") }
                                    TextButton(onClick = {
                                        resetUser = user
                                        resetPassword = ""
                                    }) { Text("Restablecer contraseña") }
                                    if (user.role == "RESIDENT" && !user.apartment.isNullOrBlank()) {
                                        TextButton(onClick = {
                                            navController.navigate("unitProfile/${Uri.encode(user.apartment)}")
                                        }) { Text("Ficha del hogar") }
                                    }
                                }
                            }
                        }
                    }
                    item {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            TextButton(
                                enabled = currentPage > 1 && !loading,
                                onClick = { scope.launch { loadUsers(currentPage - 1) } }
                            ) { Text("Anterior") }
                            TextButton(
                                enabled = currentPage < totalPages && !loading,
                                onClick = { scope.launch { loadUsers(currentPage + 1) } }
                            ) { Text("Siguiente") }
                        }
                    }
                }
            }
        }
    }

    editUser?.let { user ->
        var eName by remember(user.id) {
            mutableStateOf(
                user.firstName?.takeIf { it.isNotBlank() }
                    ?: user.name.removeSuffix(user.lastName.orEmpty()).trim()
            )
        }
        var eLastName by remember(user.id) { mutableStateOf(user.lastName.orEmpty()) }
        var eEmail by remember(user.id) { mutableStateOf(user.email) }
        var ePhone by remember(user.id) { mutableStateOf(user.phone.orEmpty()) }
        var eDocument by remember(user.id) { mutableStateOf(user.documentId.orEmpty()) }
        var eApartment by remember(user.id) { mutableStateOf(user.apartment.orEmpty()) }
        var eRole by remember(user.id) { mutableStateOf(user.role) }
        var eOccupancy by remember(user.id) { mutableStateOf(user.occupancyType ?: "propietario") }
        var eActive by remember(user.id) { mutableStateOf(user.isActive) }
        var eConsent by remember(user.id) { mutableStateOf(false) }
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
                        if (user.role != "RESIDENT") {
                            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                                Checkbox(eConsent, { eConsent = it })
                                Text("El residente autorizó el tratamiento de sus datos.")
                            }
                        }
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
                        !eEmail.trim().contains("@") || (eRole == "RESIDENT" && eApartment.trim().isEmpty()) ||
                        (eRole == "RESIDENT" && user.role != "RESIDENT" && !eConsent)
                    ) {
                        message = "Completa los campos obligatorios."
                        return@TextButton
                    }
                    pendingUserUpdate = user.id to UpdateUserRequest(
                        eName.trim(), eLastName.trim(), eEmail.trim().lowercase(),
                        ePhone.trim(), eDocument.trim(), eRole,
                        eApartment.trim().takeIf { eRole == "RESIDENT" },
                        eOccupancy.takeIf { eRole == "RESIDENT" }, eActive,
                        true.takeIf { eRole == "RESIDENT" && user.role != "RESIDENT" }
                    )
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
                    pendingPasswordReset = user.id to resetPassword
                }) { Text("Continuar") }
            },
            dismissButton = { TextButton(onClick = { resetUser = null }) { Text("Cancelar") } }
        )
    }

    pendingUserUpdate?.let { (userId, update) ->
        DomuxConfirmDialog(
            title = "Confirmar cambios del usuario",
            message = "Se guardarán los cambios realizados en este perfil. ¿Deseas continuar?",
            confirmLabel = "Confirmar y guardar",
            onConfirm = {
                pendingUserUpdate = null
                scope.launch {
                    try {
                        val response = RetrofitClient.api.updateUser(Session.bearer(), userId, update)
                        message = if (response.isSuccessful) "Usuario actualizado."
                        else mensajeDeError(response.code(), response.errorBody()?.string())
                        if (response.isSuccessful) {
                            editUser = null
                            loadUsers()
                        }
                    } catch (exception: Exception) {
                        if (isCancellation(exception)) {
                            if (exception is CancellationException) throw exception else return@launch
                        }
                        message = "No se pudo actualizar: ${exception.message}"
                    }
                }
            },
            onDismiss = { pendingUserUpdate = null }
        )
    }

    pendingPasswordReset?.let { (userId, newPassword) ->
        DomuxConfirmDialog(
            title = "Confirmar restablecimiento",
            message = "La contraseña de este usuario será reemplazada. Esta acción no se puede deshacer.",
            confirmLabel = "Restablecer",
            danger = true,
            onConfirm = {
                pendingPasswordReset = null
                scope.launch {
                    try {
                        val response = RetrofitClient.api.resetUserPassword(
                            Session.bearer(), userId, ResetPasswordRequest(newPassword)
                        )
                        message = if (response.isSuccessful) "Contraseña restablecida."
                        else mensajeDeError(response.code(), response.errorBody()?.string())
                        if (response.isSuccessful) resetUser = null
                    } catch (exception: Exception) {
                        if (isCancellation(exception)) {
                            if (exception is CancellationException) throw exception else return@launch
                        }
                        message = "No se pudo restablecer la contraseña: ${exception.message}"
                    }
                }
            },
            onDismiss = { pendingPasswordReset = null }
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
