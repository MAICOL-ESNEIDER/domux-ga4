package com.dracknoval.domux

import android.net.Uri
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.dracknoval.domux.data.UserData
import com.dracknoval.domux.ui.theme.DomuxColor

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

private const val PASSWORD_RULE = "Mínimo 8 caracteres, con mayúscula, minúscula, número y símbolo."

/**
 * Gestión de usuarios (HU-011 y HU-012). La pantalla solo dibuja: la lista, los filtros, crear,
 * editar, la contraseña y el PIN están en [UsersViewModel].
 */
@Composable
fun CreateUserScreen(navController: NavController, viewModel: UsersViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()

    DomuxScreenScaffold(title = "Gestión de usuarios", navController = navController) { padding ->
        Column(
            modifier = Modifier.fillMaxSize().padding(padding).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            DomuxSectionTabs(
                listOf("Usuarios (${state.total})", "Crear usuario"),
                state.selectedTab,
                viewModel::selectTab
            )
            DomuxMessageBanner(state.message, state.messageIsError) { viewModel.dismissMessage() }
            when (state.selectedTab) {
                0 -> UsersList(state, viewModel, navController)
                else -> CreateUserForm(state, viewModel)
            }
            // El censo en Excel se importa en la web, desde el computador: la app no guarda archivos.
            Text(
                "Para importar el censo en Excel usa la web de administración desde el computador.",
                style = MaterialTheme.typography.bodySmall,
                color = DomuxColor.TextMuted
            )
        }
    }

    state.editing?.let { EditUserDialog(it, state, viewModel) }
    state.resetting?.let { ResetPasswordDialog(it, state, viewModel) }
    state.pinFor?.let { GuardPinDialog(it, state, viewModel) }
    if (state.pendingUpdate != null) {
        DomuxConfirmDialog(
            title = "Confirmar cambios del usuario",
            message = "Se guardarán los cambios realizados en este perfil. ¿Deseas continuar?",
            confirmLabel = "Confirmar y guardar",
            onConfirm = viewModel::confirmUpdate,
            onDismiss = viewModel::cancelPendingUpdate
        )
    }
    if (state.pendingReset != null) {
        DomuxConfirmDialog(
            title = "Confirmar restablecimiento",
            message = "La contraseña de este usuario será reemplazada. Esta acción no se puede deshacer.",
            confirmLabel = "Restablecer",
            danger = true,
            onConfirm = viewModel::confirmReset,
            onDismiss = viewModel::cancelPendingReset
        )
    }
}

@Composable
private fun CreateUserForm(state: UsersUiState, viewModel: UsersViewModel) {
    val form = state.form
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        DomuxCard(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp)) {
                Text("Crear usuario", style = MaterialTheme.typography.titleMedium)
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    roleOptions.forEach { (value, label) ->
                        FilterChip(
                            selected = form.role == value,
                            onClick = { viewModel.updateForm { it.copy(role = value) } },
                            label = { Text(label) }
                        )
                    }
                }
                UserInput(form.name, { v -> viewModel.updateForm { it.copy(name = v) } }, "Nombre", required = true, showMissingError = form.attempted)
                UserInput(form.lastName, { v -> viewModel.updateForm { it.copy(lastName = v) } }, "Apellido", required = true, showMissingError = form.attempted)
                UserInput(form.email, { v -> viewModel.updateForm { it.copy(email = v) } }, "Correo", required = true, showMissingError = form.attempted)
                UserInput(form.phone, { v -> viewModel.updateForm { it.copy(phone = v) } }, "Teléfono", required = true, showMissingError = form.attempted)
                UserInput(form.documentId, { v -> viewModel.updateForm { it.copy(documentId = v) } }, "Documento", required = true, showMissingError = form.attempted)
                UserInput(
                    form.password, { v -> viewModel.updateForm { it.copy(password = v) } }, "Contraseña temporal",
                    required = true, password = true, showMissingError = form.attempted
                )
                Text(PASSWORD_RULE, style = MaterialTheme.typography.bodySmall)
                if (form.isResident) {
                    ApartmentPickerField(
                        label = "Apartamento *",
                        selected = form.apartment,
                        onSelect = { option -> viewModel.updateForm { it.copy(apartment = option) } },
                        errorText = if (form.attempted && form.apartment == null) "Elige el apartamento del residente." else null
                    )
                    DatePickerField(
                        "Fecha de nacimiento",
                        form.birthDate,
                        { v -> viewModel.updateForm { it.copy(birthDate = v) } },
                        allowFutureDates = false
                    )
                    if (form.isMinor) {
                        Text(
                            "Usuario menor de 18 años: por defecto tendrá cuenta en Modo Consulta (sin crear reservas ni PQRS).",
                            color = MaterialTheme.colorScheme.error
                        )
                        DomuxCheckRow(
                            "Cuenta con autorización de los padres/acudientes para solicitar reservas",
                            form.parentalConsent
                        ) { checked -> viewModel.updateForm { it.copy(parentalConsent = checked) } }
                    }
                    DomuxCheckRow(
                        "El residente autorizó el tratamiento de sus datos para gestionar la vivienda.",
                        form.consentConfirmed
                    ) { checked -> viewModel.updateForm { it.copy(consentConfirmed = checked) } }
                    if (form.attempted && !form.consentConfirmed) {
                        Text("Confirma la autorización del residente.", color = MaterialTheme.colorScheme.error)
                    }
                    Text("Tipo de tenencia")
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        occupancyOptions.forEach { (value, label) ->
                            FilterChip(
                                selected = form.occupancyType == value,
                                onClick = { viewModel.updateForm { it.copy(occupancyType = value) } },
                                label = { Text(label) }
                            )
                        }
                    }
                }
                Spacer(Modifier.height(8.dp))
                Button(
                    enabled = !state.busy,
                    onClick = { viewModel.createUser() },
                    modifier = Modifier.fillMaxWidth()
                ) { Text(if (state.busy) "Guardando..." else "Crear usuario") }
            }
        }
    }
}

@Composable
private fun UsersList(state: UsersUiState, viewModel: UsersViewModel, navController: NavController) {
    val filters = state.filters
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = filters.search,
                    onValueChange = { v -> viewModel.updateFilters { it.copy(search = v) } },
                    label = { Text("Buscar por nombre, correo, teléfono, documento o apartamento") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                TextButton(onClick = viewModel::toggleAdvancedFilters) {
                    Text(if (state.showAdvancedFilters) "Ocultar filtros avanzados" else "Mostrar filtros avanzados")
                }
                if (state.showAdvancedFilters) AdvancedFilters(filters, viewModel)
                Text("${state.total} usuarios - página ${state.page} de ${state.totalPages}")
            }
        }
        if (state.loading) {
            item { LinearProgressIndicator(modifier = Modifier.fillMaxWidth()) }
        }
        if (!state.loading && state.users.isEmpty()) {
            item {
                DomuxCard(Modifier.fillMaxWidth()) {
                    Text("No se encontraron usuarios.", modifier = Modifier.padding(16.dp))
                }
            }
        }
        items(state.users, key = { it.id }) { user ->
            UserCard(user, viewModel, navController)
        }
        item {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                TextButton(
                    enabled = state.page > 1 && !state.loading,
                    onClick = viewModel::previousPage
                ) { Text("Anterior") }
                TextButton(
                    enabled = state.page < state.totalPages && !state.loading,
                    onClick = viewModel::nextPage
                ) { Text("Siguiente") }
            }
        }
    }
}

@Composable
private fun AdvancedFilters(filters: UserFilters, viewModel: UsersViewModel) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedTextField(
            value = filters.apartmentFrom,
            onValueChange = { v -> viewModel.updateFilters { it.copy(apartmentFrom = v) } },
            label = { Text("Apto desde") },
            singleLine = true,
            modifier = Modifier.weight(1f)
        )
        OutlinedTextField(
            value = filters.apartmentTo,
            onValueChange = { v -> viewModel.updateFilters { it.copy(apartmentTo = v) } },
            label = { Text("Apto hasta") },
            singleLine = true,
            modifier = Modifier.weight(1f)
        )
    }
    Row(modifier = Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        occupancyOptions.forEach { (value, label) ->
            FilterChip(
                selected = filters.occupancy == value,
                onClick = { viewModel.updateFilters { it.copy(occupancy = if (it.occupancy == value) "" else value) } },
                label = { Text(label) }
            )
        }
    }
    Row(modifier = Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        FilterChip(
            selected = filters.active == true,
            onClick = { viewModel.updateFilters { it.copy(active = nextFilter(it.active)) } },
            label = { Text("Activo: ${filterLabel(filters.active)}") }
        )
        FilterChip(
            selected = filters.pets == true,
            onClick = { viewModel.updateFilters { it.copy(pets = nextFilter(it.pets)) } },
            label = { Text("Mascotas: ${filterLabel(filters.pets)}") }
        )
        FilterChip(
            selected = filters.vehicles == true,
            onClick = { viewModel.updateFilters { it.copy(vehicles = nextFilter(it.vehicles)) } },
            label = { Text("Vehículos: ${filterLabel(filters.vehicles)}") }
        )
    }
    Row(modifier = Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        FilterChip(
            selected = filters.parking == true,
            onClick = { viewModel.updateFilters { it.copy(parking = nextFilter(it.parking)) } },
            label = { Text("Parqueadero: ${filterLabel(filters.parking)}") }
        )
        FilterChip(
            selected = filters.storage == true,
            onClick = { viewModel.updateFilters { it.copy(storage = nextFilter(it.storage)) } },
            label = { Text("Cuarto útil: ${filterLabel(filters.storage)}") }
        )
    }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedTextField(
            value = filters.minAge,
            onValueChange = { v -> viewModel.updateFilters { it.copy(minAge = v.filter(Char::isDigit).take(3)) } },
            label = { Text("Edad mínima") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            modifier = Modifier.weight(1f)
        )
        OutlinedTextField(
            value = filters.maxAge,
            onValueChange = { v -> viewModel.updateFilters { it.copy(maxAge = v.filter(Char::isDigit).take(3)) } },
            label = { Text("Edad máxima") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            modifier = Modifier.weight(1f)
        )
    }
}

@Composable
private fun UserCard(user: UserData, viewModel: UsersViewModel, navController: NavController) {
    DomuxCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Text(user.fullName ?: user.name, style = MaterialTheme.typography.titleMedium)
            if (user.isMinor) {
                DomuxStatusBadge(
                    if (user.parentalConsent) "Menor (Con permiso parental)" else "Menor (Modo consulta)",
                    if (user.parentalConsent) DomuxBadgeTone.PROGRESS else DomuxBadgeTone.ALERT
                )
                user.age?.let { Text("Edad: $it años") }
            }
            Text(user.email)
            Text("Teléfono: ${user.phone.orEmpty()} · Documento: ${user.documentId.orEmpty()}")
            Text("Rol: ${roleLabel(user.role)} · Apto: ${user.apartment ?: "—"}")
            Text(
                "Tenencia: ${occupancyOptions.firstOrNull { it.first == user.occupancyType }?.second ?: "—"} · " +
                    if (user.isActive) "Activo" else "Inactivo"
            )
            if (user.role == "GUARD") {
                Text(if (user.hasPin) "PIN de turno: asignado" else "PIN de turno: sin asignar")
            }
            Row(Modifier.horizontalScroll(rememberScrollState())) {
                TextButton(onClick = { viewModel.startEdit(user) }) { Text("Editar") }
                TextButton(onClick = { viewModel.startReset(user) }) { Text("Restablecer contraseña") }
                if (user.role == "GUARD") {
                    TextButton(onClick = { viewModel.startPin(user) }) {
                        Text(if (user.hasPin) "Cambiar PIN" else "Asignar PIN")
                    }
                }
                if (user.role == "RESIDENT" && !user.apartment.isNullOrBlank()) {
                    TextButton(onClick = { navController.navigate("unitProfile/${Uri.encode(user.apartment)}") }) {
                        Text("Ficha del hogar")
                    }
                }
            }
        }
    }
}

@Composable
private fun EditUserDialog(user: UserData, state: UsersUiState, viewModel: UsersViewModel) {
    var draft by remember(user.id) { mutableStateOf(UserEditDraft.from(user)) }
    var attempted by remember(user.id) { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = viewModel::cancelEdit,
        title = { Text("Editar usuario") },
        text = {
            Column(Modifier.heightIn(max = 480.dp).verticalScroll(rememberScrollState())) {
                UserInput(draft.name, { v -> draft = draft.copy(name = v) }, "Nombre", true, showMissingError = attempted)
                UserInput(draft.lastName, { v -> draft = draft.copy(lastName = v) }, "Apellido", true, showMissingError = attempted)
                UserInput(draft.email, { v -> draft = draft.copy(email = v) }, "Correo", true, showMissingError = attempted)
                UserInput(draft.phone, { v -> draft = draft.copy(phone = v) }, "Teléfono", true, showMissingError = attempted)
                UserInput(draft.documentId, { v -> draft = draft.copy(documentId = v) }, "Documento", true, showMissingError = attempted)
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    roleOptions.forEach { (value, label) ->
                        FilterChip(selected = draft.role == value, onClick = { draft = draft.copy(role = value) }, label = { Text(label) })
                    }
                }
                if (draft.role == "RESIDENT") {
                    ApartmentPickerField(
                        label = "Apartamento *",
                        selected = draft.apartment,
                        onSelect = { option -> draft = draft.copy(apartment = option) },
                        errorText = if (attempted && draft.apartment == null) "Elige el apartamento del residente." else null
                    )
                    DatePickerField(
                        "Fecha de nacimiento",
                        draft.birthDate,
                        { v -> draft = draft.copy(birthDate = v) },
                        allowFutureDates = false
                    )
                    if (draft.isMinor) {
                        Text(
                            "Usuario menor de 18 años: por defecto tendrá cuenta en Modo Consulta (sin crear reservas ni PQRS).",
                            color = MaterialTheme.colorScheme.error
                        )
                        DomuxCheckRow(
                            "Cuenta con autorización de los padres/acudientes para solicitar reservas",
                            draft.parentalConsent
                        ) { checked -> draft = draft.copy(parentalConsent = checked) }
                    }
                    if (user.role != "RESIDENT") {
                        DomuxCheckRow("El residente autorizó el tratamiento de sus datos.", draft.consent) { checked ->
                            draft = draft.copy(consent = checked)
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                        occupancyOptions.forEach { (value, label) ->
                            FilterChip(
                                selected = draft.occupancyType == value,
                                onClick = { draft = draft.copy(occupancyType = value) },
                                label = { Text(label) }
                            )
                        }
                    }
                }
                DomuxCheckRow("Cuenta activa", draft.active) { checked -> draft = draft.copy(active = checked) }
                if (state.editError.isNotBlank()) {
                    Text(state.editError, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                }
            }
        },
        confirmButton = {
            TextButton(
                enabled = !state.busy,
                onClick = {
                    attempted = true
                    viewModel.requestUpdate(user, draft)
                }
            ) { Text(if (state.busy) "Guardando..." else "Guardar") }
        },
        dismissButton = { TextButton(onClick = viewModel::cancelEdit) { Text("Cancelar") } }
    )
}

@Composable
private fun ResetPasswordDialog(user: UserData, state: UsersUiState, viewModel: UsersViewModel) {
    var newPassword by remember(user.id) { mutableStateOf("") }
    var attempted by remember(user.id) { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = viewModel::cancelReset,
        title = { Text("Restablecer contraseña") },
        text = {
            Column {
                Text("Se cambiará la contraseña de ${user.email}.")
                UserInput(
                    newPassword, { newPassword = it }, "Nueva contraseña", true,
                    password = true, showMissingError = attempted
                )
                Text(PASSWORD_RULE, style = MaterialTheme.typography.bodySmall)
                if (state.resetError.isNotBlank()) {
                    Text(state.resetError, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                }
            }
        },
        confirmButton = {
            TextButton(
                enabled = !state.busy,
                onClick = {
                    attempted = true
                    viewModel.requestReset(user, newPassword)
                }
            ) { Text(if (state.busy) "Guardando..." else "Continuar") }
        },
        dismissButton = { TextButton(onClick = viewModel::cancelReset) { Text("Cancelar") } }
    )
}

@Composable
private fun GuardPinDialog(user: UserData, state: UsersUiState, viewModel: UsersViewModel) {
    var pin by remember(user.id) { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = viewModel::cancelPin,
        title = { Text(if (user.hasPin) "Cambiar PIN del guardia" else "Asignar PIN al guardia") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    "PIN de 4 dígitos para ${user.fullName ?: user.name}. Lo usará en la tablet " +
                        "de portería al recibir el turno. Después no se puede ver: solo cambiarlo."
                )
                OutlinedTextField(
                    value = pin,
                    onValueChange = { pin = it.filter(Char::isDigit).take(4) },
                    label = { Text("PIN de 4 dígitos") },
                    singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                    modifier = Modifier.fillMaxWidth()
                )
                if (state.pinError.isNotBlank()) {
                    Text(state.pinError, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                }
            }
        },
        confirmButton = {
            TextButton(enabled = !state.busy, onClick = { viewModel.savePin(pin) }) {
                Text(if (state.busy) "Guardando..." else "Guardar PIN")
            }
        },
        dismissButton = {
            TextButton(enabled = !state.busy, onClick = viewModel::cancelPin) { Text("Cancelar") }
        }
    )
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
    // La contraseña va oculta; «Mostrar» deja revisarla antes de entregarla.
    var visible by remember { mutableStateOf(false) }
    val missing = required && showMissingError && value.trim().isEmpty()
    val invalidEmail = label == "Correo" && value.isNotEmpty() && !value.trim().contains("@")
    val invalidPassword = password && value.isNotEmpty() && !validStrongPassword(value)
    // El teléfono muestra la regla mientras se escribe y el error solo al intentar guardar.
    val isPhone = label == "Teléfono"
    val phoneError = if (isPhone && showMissingError && value.isNotBlank()) phoneProblem(value) else null
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        singleLine = true,
        isError = missing || invalidEmail || invalidPassword || phoneError != null,
        supportingText = {
            if (missing) Text("$label es obligatorio")
            else if (invalidEmail) Text("Ingresa un correo válido")
            else if (invalidPassword) Text("Usa 8 caracteres con mayúscula, minúscula, número y símbolo")
            else if (phoneError != null) Text(phoneError)
            else if (isPhone) Text(PHONE_HINT)
        },
        visualTransformation = if (password && !visible) PasswordVisualTransformation() else VisualTransformation.None,
        trailingIcon = if (password) {
            { TextButton(onClick = { visible = !visible }) { Text(if (visible) "Ocultar" else "Mostrar") } }
        } else null,
        keyboardOptions = KeyboardOptions(
            keyboardType = when {
                password -> KeyboardType.Password
                label == "Correo" -> KeyboardType.Email
                label == "Teléfono" -> KeyboardType.Phone
                else -> KeyboardType.Text
            }
        ),
        modifier = Modifier.fillMaxWidth()
    )
}
