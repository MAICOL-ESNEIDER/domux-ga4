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
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.dracknoval.domux.data.fullName
import com.dracknoval.domux.data.healthSummary

private val householdRelationships = listOf(
    "propietario", "conyuge_pareja", "hijo", "hija", "padre", "madre",
    "hermano", "hermana", "abuelo", "abuela", "tio", "tia", "primo",
    "prima", "yerno", "nuera", "suegro", "suegra", "otro"
)

/** El parentesco como se lee, no como lo guarda el servidor (por ejemplo «conyuge_pareja»). */
internal fun relationshipLabel(code: String): String = when (code) {
    "propietario" -> "Propietario"
    "conyuge_pareja" -> "Cónyuge o pareja"
    "tio" -> "Tío"
    "tia" -> "Tía"
    else -> code.replaceFirstChar { it.uppercase() }
}

/**
 * Ficha del apartamento (HU-020). La administración la edita; el residente solo la ve. La pantalla
 * solo dibuja: los datos, las revisiones y el guardado están en [UnitProfileViewModel].
 */
@Composable
fun UnitProfileScreen(
    navController: NavController,
    apartment: String,
    viewModel: UnitProfileViewModel = viewModel()
) {
    val state by viewModel.state.collectAsState()
    LaunchedEffect(apartment) { viewModel.start(apartment) }

    DomuxScreenScaffold(title = "Ficha del apartamento $apartment", navController = navController) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            // El aviso queda fijo arriba: se ve aunque la persona esté abajo, en los formularios.
            DomuxMessageBanner(
                state.message, state.messageIsError,
                Modifier.padding(start = 20.dp, end = 20.dp, top = 12.dp)
            ) { viewModel.dismissMessage() }
            Column(
                Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState())
                    .padding(20.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                if (state.loading) CircularProgressIndicator()
                if (state.admin) {
                    AdminUnitEditor(state, viewModel, navController)
                } else {
                    state.unit?.let { HouseholdSummary(it) }
                }
                Spacer(Modifier.height(4.dp))
            }
        }
    }
}

@Composable
private fun AdminUnitEditor(state: UnitProfileUiState, viewModel: UnitProfileViewModel, navController: NavController) {
    state.unit?.residents?.forEach { resident ->
        Column {
            Text("Residente: ${resident.name} · ${resident.occupancyType ?: "residente"}")
            Row {
                TextButton(onClick = { navController.navigate("pqrs?residentId=${resident.id}") }) {
                    Text("Crear PQRS a su nombre")
                }
                TextButton(onClick = { navController.navigate("reservations?residentId=${resident.id}") }) {
                    Text("Crear reserva a su nombre")
                }
            }
        }
    }
    // Los parqueaderos y cuartos útiles se asignan en «Estructura de la unidad»; aquí solo se ven.
    Text("Parqueadero: ${state.unit?.parkingIdentifier ?: "No registrado"}")
    Text("Cuarto útil: ${state.unit?.storageIdentifier ?: "No registrado"}")
    Text("Para cambiarlos, usa «Estructura de la unidad» en el menú.", style = MaterialTheme.typography.bodySmall)
    DomuxCheckRow("Tiene seguro de mascotas", state.petInsurance, viewModel::setPetInsurance)
    if (state.petInsurance) {
        OutlinedTextField(
            state.petInsurer, viewModel::onPetInsurer,
            label = { Text("Aseguradora (opcional)") }, singleLine = true, modifier = Modifier.fillMaxWidth()
        )
    }

    Text("Integrantes del hogar", style = MaterialTheme.typography.titleMedium)
    MemberForm(viewModel)
    state.members.forEachIndexed { index, member ->
        TextButton(onClick = { viewModel.removeMember(index) }) {
            Text("Quitar ${member.fullName} · ${relationshipLabel(member.relationship)}")
        }
    }

    Text("Mascotas", style = MaterialTheme.typography.titleMedium)
    PetForm(viewModel)
    state.pets.forEachIndexed { index, pet ->
        TextButton(onClick = { viewModel.removePet(index) }) {
            Text("Quitar ${pet.name} · ${pet.species} · ${pet.healthSummary}")
        }
    }

    Text("Vehículos", style = MaterialTheme.typography.titleMedium)
    VehicleForm(viewModel)
    state.vehicles.forEachIndexed { index, vehicle ->
        TextButton(onClick = { viewModel.removeVehicle(index) }) {
            Text("Quitar ${vehicle.plate} · ${vehicle.makeModel}")
        }
    }

    Button(
        onClick = { viewModel.save() },
        enabled = !state.busy && !state.loading && state.unit != null,
        modifier = Modifier.fillMaxWidth()
    ) { Text(if (state.busy) "Guardando..." else "Guardar ficha del apartamento") }
}

// Los formularios guardan lo que se va escribiendo solo mientras la pantalla está abierta (también
// si se gira el celular); al agregar, el ViewModel revisa los datos y se limpian los campos.

@Composable
private fun MemberForm(viewModel: UnitProfileViewModel) {
    var name by rememberSaveable { mutableStateOf("") }
    var lastName by rememberSaveable { mutableStateOf("") }
    var document by rememberSaveable { mutableStateOf("") }
    var birthDate by rememberSaveable { mutableStateOf("") }
    var phone by rememberSaveable { mutableStateOf("") }
    var relationship by rememberSaveable { mutableStateOf("hijo") }
    var otherRelationship by rememberSaveable { mutableStateOf("") }
    var relationshipMenu by rememberSaveable { mutableStateOf(false) }

    OutlinedTextField(name, { name = it }, label = { Text("Nombre") }, singleLine = true, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(lastName, { lastName = it }, label = { Text("Apellido") }, singleLine = true, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(document, { document = it }, label = { Text("Documento") }, singleLine = true, modifier = Modifier.fillMaxWidth())
    DatePickerField("Fecha de nacimiento", birthDate, { birthDate = it }, allowFutureDates = false)
    DomuxPhoneField(phone, { phone = it }, "Teléfono (opcional)")
    TextButton(onClick = { relationshipMenu = true }) { Text("Parentesco: ${relationshipLabel(relationship)}") }
    DropdownMenu(relationshipMenu, { relationshipMenu = false }) {
        householdRelationships.forEach { option ->
            DropdownMenuItem(
                text = { Text(relationshipLabel(option)) },
                onClick = { relationship = option; relationshipMenu = false }
            )
        }
    }
    if (relationship == "otro") {
        OutlinedTextField(
            otherRelationship, { otherRelationship = it },
            label = { Text("¿Qué parentesco?") }, singleLine = true, modifier = Modifier.fillMaxWidth()
        )
    }
    Button(
        onClick = {
            if (viewModel.addMember(name, lastName, document, birthDate, phone, relationship, otherRelationship)) {
                name = ""; lastName = ""; document = ""; birthDate = ""; phone = ""; otherRelationship = ""
            }
        },
        modifier = Modifier.fillMaxWidth()
    ) { Text("Agregar integrante") }
}

@Composable
private fun PetForm(viewModel: UnitProfileViewModel) {
    var name by rememberSaveable { mutableStateOf("") }
    var species by rememberSaveable { mutableStateOf("") }
    var breed by rememberSaveable { mutableStateOf("") }
    var age by rememberSaveable { mutableStateOf("") }
    // Vacunación y desparasitación (RN-028): si está al día, se pide la fecha de la última.
    var vaccines by rememberSaveable { mutableStateOf(false) }
    var vaccinationDate by rememberSaveable { mutableStateOf("") }
    var deworming by rememberSaveable { mutableStateOf(false) }
    var dewormingDate by rememberSaveable { mutableStateOf("") }

    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        OutlinedTextField(name, { name = it }, label = { Text("Nombre") }, singleLine = true, modifier = Modifier.weight(1f))
        OutlinedTextField(species, { species = it }, label = { Text("Especie") }, singleLine = true, modifier = Modifier.weight(1f))
    }
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        OutlinedTextField(breed, { breed = it }, label = { Text("Raza") }, singleLine = true, modifier = Modifier.weight(1f))
        OutlinedTextField(
            age, { age = it.filter(Char::isDigit).take(3) },
            label = { Text("Edad (años)") }, singleLine = true, modifier = Modifier.weight(1f)
        )
    }
    DomuxCheckRow("Vacunación al día", vaccines) { vaccines = it }
    DatePickerField("Última vacuna", vaccinationDate, { vaccinationDate = it }, allowFutureDates = false)
    DomuxCheckRow("Desparasitación al día", deworming) { deworming = it }
    DatePickerField("Última desparasitación", dewormingDate, { dewormingDate = it }, allowFutureDates = false)
    Button(
        onClick = {
            if (viewModel.addPet(name, species, breed, age, vaccines, vaccinationDate, deworming, dewormingDate)) {
                name = ""; species = ""; breed = ""; age = ""
                vaccines = false; vaccinationDate = ""; deworming = false; dewormingDate = ""
            }
        },
        modifier = Modifier.fillMaxWidth()
    ) { Text("Agregar mascota") }
}

@Composable
private fun VehicleForm(viewModel: UnitProfileViewModel) {
    var plate by rememberSaveable { mutableStateOf("") }
    var type by rememberSaveable { mutableStateOf("carro") }
    var makeModel by rememberSaveable { mutableStateOf("") }
    var year by rememberSaveable { mutableStateOf("") }
    var registeredOwner by rememberSaveable { mutableStateOf("") }
    var color by rememberSaveable { mutableStateOf("") }

    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        listOf("carro" to "Carro", "moto" to "Moto").forEach { (code, label) ->
            FilterChip(selected = type == code, onClick = { type = code }, label = { Text(label) })
        }
    }
    OutlinedTextField(
        plate, { plate = it.uppercase().filter(Char::isLetterOrDigit).take(6) },
        label = { Text("Placa (AAA123 o AAA12A)") }, singleLine = true, modifier = Modifier.fillMaxWidth()
    )
    OutlinedTextField(makeModel, { makeModel = it }, label = { Text("Marca y modelo") }, singleLine = true, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(
        year, { year = it.filter(Char::isDigit).take(4) },
        label = { Text("Año") }, singleLine = true, modifier = Modifier.fillMaxWidth()
    )
    OutlinedTextField(registeredOwner, { registeredOwner = it }, label = { Text("A nombre de") }, singleLine = true, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(color, { color = it }, label = { Text("Color (opcional)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
    Button(
        onClick = {
            if (viewModel.addVehicle(plate, type, makeModel, year, registeredOwner, color)) {
                plate = ""; makeModel = ""; year = ""; registeredOwner = ""; color = ""
            }
        },
        modifier = Modifier.fillMaxWidth()
    ) { Text("Agregar vehículo") }
}
