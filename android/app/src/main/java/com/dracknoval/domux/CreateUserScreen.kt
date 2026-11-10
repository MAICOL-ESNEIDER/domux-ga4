package com.dracknoval.domux

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.navigation.NavController
import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat
import com.dracknoval.domux.data.ApartmentOption
import com.dracknoval.domux.data.CreateUserRequest
import com.dracknoval.domux.data.ExcelFileResponse
import com.dracknoval.domux.data.ImportCensusRequest
import com.dracknoval.domux.data.ResetPasswordRequest
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.SetPinRequest
import com.dracknoval.domux.data.UpdateUserRequest
import com.dracknoval.domux.data.UserData
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import android.net.Uri
import java.text.ParsePosition
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale

private val occupancyOptions = listOf(
    "propietario" to "Propietario",
    "arrendatario" to "Arrendatario",
    "residente" to "Residente"
)
private val passwordSpecialChars = setOf('@', '$', '!', '%', '*', '?', '&', '#', '.', '_', '-')

private fun ageFromIsoDate(value: String): Int? {
    val format = SimpleDateFormat("yyyy-MM-dd", Locale.US).apply { isLenient = false }
    val position = ParsePosition(0)
    val birthDate = format.parse(value, position)
    if (birthDate == null || position.index != value.length) return null
    val birth = Calendar.getInstance().apply { time = birthDate }
    val today = Calendar.getInstance()
    var age = today.get(Calendar.YEAR) - birth.get(Calendar.YEAR)
    val birthdayHasNotOccurred =
        today.get(Calendar.MONTH) < birth.get(Calendar.MONTH) ||
            (today.get(Calendar.MONTH) == birth.get(Calendar.MONTH) &&
                today.get(Calendar.DAY_OF_MONTH) < birth.get(Calendar.DAY_OF_MONTH))
    if (birthdayHasNotOccurred) age--
    return age.takeIf { it >= 0 }
}

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
    var birthDate by remember { mutableStateOf("") }
    var parentalConsent by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }
    var lastName by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var documentId by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var role by remember { mutableStateOf("RESIDENT") }
    // El residente se vincula a un apartamento que ya existe en la estructura de la unidad (HU-017).
    var apartment by remember { mutableStateOf<ApartmentOption?>(null) }
    var occupancyType by remember { mutableStateOf("propietario") }
    var editUser by remember { mutableStateOf<UserData?>(null) }
    var resetUser by remember { mutableStateOf<UserData?>(null) }
    var resetPassword by remember { mutableStateOf("") }
    // PIN de 4 dígitos del guardia (HU-010): a quién se le está asignando y lo que se escribe.
    var pinUser by remember { mutableStateOf<UserData?>(null) }
    var pinValue by remember { mutableStateOf("") }
    var pinBusy by remember { mutableStateOf(false) }
    var pinError by remember { mutableStateOf("") }
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
                listOf("Usuarios ($totalUsers)", "Crear usuario", "Censo Excel"),
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
                    ApartmentPickerField(
                        label = "Apartamento *",
                        selected = apartment,
                        onSelect = { apartment = it },
                        errorText = if (attemptedSubmit && apartment == null) {
                            "Elige el apartamento del residente."
                        } else {
                            null
                        }
                    )
                    DatePickerField(
                        "Fecha de nacimiento (AAAA-MM-DD)",
                        birthDate,
                        { birthDate = it },
                        allowPastDates = true
                    )
                    if (ageFromIsoDate(birthDate)?.let { it < 18 } == true) {
                        Text(
                            "Usuario menor de 18 años: por defecto tendrá cuenta en Modo Consulta (sin crear reservas ni PQRS).",
                            color = MaterialTheme.colorScheme.error
                        )
                        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                            Checkbox(
                                checked = parentalConsent,
                                onCheckedChange = { parentalConsent = it }
                            )
                            Text("Cuenta con autorización de los padres/acudientes para solicitar reservas")
                        }
                    }
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
                            (role == "RESIDENT" && apartment == null) ||
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
                                        if (role == "RESIDENT") apartment?.id else null,
                                        lastName.trim(), phone.trim(), documentId.trim(), occupancyType,
                                        role == "RESIDENT" && consentConfirmed,
                                        birthDate.trim().takeIf { it.isNotEmpty() },
                                        role == "RESIDENT" && parentalConsent
                                    )
                                )
                                if (response.isSuccessful) {
                                    name = ""; lastName = ""; email = ""; phone = ""; documentId = ""
                                    password = ""; apartment = null
                                    consentConfirmed = false
                                    birthDate = ""
                                    parentalConsent = false
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
            } else if (selectedTab == 0) {
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
                                if (user.isMinor) {
                                    DomuxStatusBadge(
                                        if (user.parentalConsent) "Menor (Con permiso parental)"
                                        else "Menor (Modo consulta)",
                                        if (user.parentalConsent) DomuxBadgeTone.PROGRESS
                                        else DomuxBadgeTone.ALERT
                                    )
                                    user.age?.let { Text("Edad: $it años") }
                                }
                                Text(user.email)
                                Text("Teléfono: ${user.phone.orEmpty()} · Documento: ${user.documentId.orEmpty()}")
                                Text("Rol: ${user.role} · Apto: ${user.apartment ?: "—"}")
                                Text(
                                    "Tenencia: ${occupancyOptions.firstOrNull { it.first == user.occupancyType }?.second ?: "—"} · " +
                                        if (user.isActive) "Activo" else "Inactivo"
                                )
                                if (user.role == "GUARD") {
                                    Text(if (user.hasPin) "PIN de turno: asignado" else "PIN de turno: sin asignar")
                                }
                                Row(Modifier.horizontalScroll(rememberScrollState())) {
                                    TextButton(onClick = { editUser = user }) { Text("Editar") }
                                    TextButton(onClick = {
                                        resetUser = user
                                        resetPassword = ""
                                    }) { Text("Restablecer contraseña") }
                                    if (user.role == "GUARD") {
                                        TextButton(onClick = {
                                            pinUser = user
                                            pinValue = ""
                                            pinError = ""
                                        }) { Text(if (user.hasPin) "Cambiar PIN" else "Asignar PIN") }
                                    }
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
            } else if (selectedTab == 2) {
                CensusExcelPanel {
                    loadUsers(1)
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
        val initialApartmentId = user.apartmentId
        var eApartment by remember(user.id) {
            mutableStateOf<ApartmentOption?>(
                if (initialApartmentId != null) {
                    ApartmentOption(initialApartmentId, user.apartment.orEmpty())
                } else {
                    null
                }
            )
        }
        var eRole by remember(user.id) { mutableStateOf(user.role) }
        var eOccupancy by remember(user.id) { mutableStateOf(user.occupancyType ?: "propietario") }
        var eActive by remember(user.id) { mutableStateOf(user.isActive) }
        var eConsent by remember(user.id) { mutableStateOf(false) }
        var eBirthDate by remember(user.id) { mutableStateOf(user.birthDate.orEmpty()) }
        var eParentalConsent by remember(user.id) { mutableStateOf(user.parentalConsent) }
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
                        ApartmentPickerField(
                            label = "Apartamento *",
                            selected = eApartment,
                            onSelect = { eApartment = it },
                            errorText = if (attemptedEdit && eApartment == null) {
                                "Elige el apartamento del residente."
                            } else {
                                null
                            }
                        )
                        DatePickerField(
                            "Fecha de nacimiento (AAAA-MM-DD)",
                            eBirthDate,
                            { eBirthDate = it },
                            allowPastDates = true
                        )
                        if (ageFromIsoDate(eBirthDate)?.let { it < 18 } == true) {
                            Text(
                                "Usuario menor de 18 años: por defecto tendrá cuenta en Modo Consulta (sin crear reservas ni PQRS).",
                                color = MaterialTheme.colorScheme.error
                            )
                            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                                Checkbox(
                                    eParentalConsent,
                                    { eParentalConsent = it }
                                )
                                Text("Cuenta con autorización de los padres/acudientes para solicitar reservas")
                            }
                        }
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
                        !eEmail.trim().contains("@") || (eRole == "RESIDENT" && eApartment == null) ||
                        (eRole == "RESIDENT" && user.role != "RESIDENT" && !eConsent)
                    ) {
                        message = "Completa los campos obligatorios."
                        return@TextButton
                    }
                    pendingUserUpdate = user.id to UpdateUserRequest(
                        eName.trim(), eLastName.trim(), eEmail.trim().lowercase(),
                        ePhone.trim(), eDocument.trim(), eRole,
                        if (eRole == "RESIDENT") eApartment?.id else null,
                        eOccupancy.takeIf { eRole == "RESIDENT" }, eActive,
                        true.takeIf { eRole == "RESIDENT" && user.role != "RESIDENT" },
                        eBirthDate.trim().takeIf { it.isNotEmpty() },
                        eParentalConsent.takeIf { eRole == "RESIDENT" }
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

    pinUser?.let { user ->
        AlertDialog(
            onDismissRequest = { if (!pinBusy) pinUser = null },
            title = { Text(if (user.hasPin) "Cambiar PIN del guardia" else "Asignar PIN al guardia") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        "PIN de 4 dígitos para ${user.fullName ?: user.name}. Lo usará en la tablet " +
                            "de portería al recibir el turno. Después no se puede ver: solo cambiarlo."
                    )
                    OutlinedTextField(
                        value = pinValue,
                        onValueChange = { pinValue = it.filter(Char::isDigit).take(4) },
                        label = { Text("PIN de 4 dígitos") },
                        singleLine = true,
                        visualTransformation = androidx.compose.ui.text.input.PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                        modifier = Modifier.fillMaxWidth()
                    )
                    if (pinError.isNotBlank()) {
                        Text(
                            pinError,
                            color = MaterialTheme.colorScheme.error,
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
            },
            confirmButton = {
                TextButton(
                    enabled = !pinBusy,
                    onClick = {
                        if (pinValue.length != 4) {
                            pinError = "El PIN tiene exactamente 4 dígitos."
                            return@TextButton
                        }
                        pinBusy = true
                        pinError = ""
                        scope.launch {
                            try {
                                val response = RetrofitClient.api.setGuardPin(
                                    Session.bearer(), user.id, SetPinRequest(pinValue)
                                )
                                if (response.isSuccessful) {
                                    pinUser = null
                                    pinValue = ""
                                    message = "PIN guardado."
                                    loadUsers()
                                } else {
                                    pinError = mensajeDeError(response.code(), response.errorBody()?.string())
                                }
                            } catch (exception: Exception) {
                                if (isCancellation(exception)) {
                                    if (exception is CancellationException) throw exception else return@launch
                                }
                                pinError = "No se pudo guardar el PIN: ${exception.message}"
                            } finally {
                                pinBusy = false
                            }
                        }
                    }
                ) { Text(if (pinBusy) "Guardando..." else "Guardar PIN") }
            },
            dismissButton = {
                TextButton(enabled = !pinBusy, onClick = { pinUser = null }) { Text("Cancelar") }
            }
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
private fun CensusExcelPanel(onImportComplete: suspend () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var message by remember { mutableStateOf("") }
    var messageIsError by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var pendingTemplate by remember { mutableStateOf<ExcelFileResponse?>(null) }
    val storagePermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        val file = pendingTemplate
        pendingTemplate = null
        if (granted && file != null) {
            try {
                saveBase64FileToDownloads(
                    context,
                    file.fileName,
                    file.base64,
                    file.mimeType
                        ?: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                message = "Plantilla guardada exitosamente en Descargas."
                messageIsError = false
            } catch (exception: Exception) {
                message = "No se pudo guardar la plantilla: ${exception.message}"
                messageIsError = true
            }
        } else {
            message = "Se requiere permiso de almacenamiento para guardar en Descargas."
            messageIsError = true
        }
        busy = false
    }

    DomuxCard(Modifier.fillMaxSize()) {
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text("Censo Excel", style = MaterialTheme.typography.titleMedium)
            Text("Descarga la plantilla o importa el censo de residentes de una unidad.")
            Button(
                enabled = !busy,
                onClick = {
                    busy = true
                    message = ""
                    scope.launch {
                        var waitingForPermission = false
                        try {
                            val response = RetrofitClient.api.getCensusTemplate(Session.bearer())
                            if (response.isSuccessful) {
                                val file = response.body()
                                    ?: error("El servidor devolvió una plantilla vacía.")
                                if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q &&
                                    ContextCompat.checkSelfPermission(
                                        context,
                                        Manifest.permission.WRITE_EXTERNAL_STORAGE
                                    ) != PackageManager.PERMISSION_GRANTED
                                ) {
                                    pendingTemplate = file
                                    waitingForPermission = true
                                    storagePermissionLauncher.launch(Manifest.permission.WRITE_EXTERNAL_STORAGE)
                                } else {
                                    saveBase64FileToDownloads(
                                        context,
                                        file.fileName,
                                        file.base64,
                                        file.mimeType
                                            ?: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                    )
                                    message = "Plantilla guardada exitosamente en Descargas."
                                    messageIsError = false
                                }
                            } else {
                                message = mensajeDeError(response.code(), response.errorBody()?.string())
                                messageIsError = true
                            }
                        } catch (exception: Exception) {
                            if (isCancellation(exception)) {
                                if (exception is CancellationException) throw exception
                                return@launch
                            }
                            message = "No se pudo descargar la plantilla: ${exception.message}"
                            messageIsError = true
                        } finally {
                            if (!waitingForPermission) busy = false
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("Descargar plantilla Excel de ejemplo")
            }
            ExcelFilePickerButton(
                onFileSelected = { base64, fileName ->
                    busy = true
                    message = ""
                    scope.launch {
                        try {
                            val response = RetrofitClient.api.importCensus(
                                Session.bearer(),
                                ImportCensusRequest(base64, fileName)
                            )
                            if (response.isSuccessful) {
                                val result = response.body()
                                    ?: error("El servidor devolvió un resumen vacío.")
                                message = buildString {
                                    append(result.message ?: "Importación del censo procesada.")
                                    append("\nResidentes creados: ${result.createdUsers}")
                                    append("\nResidentes actualizados: ${result.updatedUsers}")
                                    append("\nUnidades procesadas: ${result.unitsProcessed}")
                                    result.errors.orEmpty().takeIf { it.isNotEmpty() }?.let { warnings ->
                                        append("\nAdvertencias:")
                                        warnings.forEach { append("\n• $it") }
                                    }
                                }
                                messageIsError = false
                                onImportComplete()
                            } else {
                                message = mensajeDeError(response.code(), response.errorBody()?.string())
                                messageIsError = true
                            }
                        } catch (exception: Exception) {
                            if (isCancellation(exception)) {
                                if (exception is CancellationException) throw exception
                                return@launch
                            }
                            message = "No se pudo importar el censo: ${exception.message}"
                            messageIsError = true
                        } finally {
                            busy = false
                        }
                    }
                },
                onError = {
                    message = it
                    messageIsError = true
                }
            )
            if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            if (message.isNotBlank()) {
                Text(
                    message,
                    color = if (messageIsError) MaterialTheme.colorScheme.error else Color(0xFF34D399)
                )
            }
        }
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
