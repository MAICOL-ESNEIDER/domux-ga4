package com.dracknoval.domux

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.dracknoval.domux.data.HouseholdMemberData
import com.dracknoval.domux.data.PetData
import com.dracknoval.domux.data.ResidentialUnitData
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.SaveResidentialUnitRequest
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.VehicleData
import com.dracknoval.domux.data.mensajeDeError
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

private val householdRelationshipOptions = listOf(
    "hijo" to "Hijo/a",
    "conyuge_pareja" to "Cónyuge",
    "padre" to "Padre/Madre",
    "hermano" to "Hermano/a",
    "otro" to "Otro"
)

@Composable
fun UnitProfileScreen(navController: NavController, apartment: String) {
    val admin = Session.isAdmin
    var unit by remember { mutableStateOf<ResidentialUnitData?>(null) }
    var loading by remember { mutableStateOf(true) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var parking by remember { mutableStateOf("") }
    var storage by remember { mutableStateOf("") }
    var petInsurance by remember { mutableStateOf(false) }
    var petInsurer by remember { mutableStateOf("") }
    var funeralPlan by remember { mutableStateOf(false) }
    var funeralProvider by remember { mutableStateOf("") }
    val members = remember { mutableStateListOf<HouseholdMemberData>() }
    val pets = remember { mutableStateListOf<PetData>() }
    val vehicles = remember { mutableStateListOf<VehicleData>() }
    val scope = rememberCoroutineScope()

    suspend fun load() {
        loading = true
        try {
            val response = if (admin) {
                RetrofitClient.api.getUnit(Session.bearer(), apartment)
            } else RetrofitClient.api.getMyUnit(Session.bearer())
            if (!response.isSuccessful) {
                message = mensajeDeError(response.code(), response.errorBody()?.string())
                return
            }
            val result = response.body()?.unit ?: return
            unit = result
            parking = result.parkingIdentifier.orEmpty()
            storage = result.storageIdentifier.orEmpty()
            petInsurance = result.petInsurance
            petInsurer = result.petInsurer.orEmpty()
            funeralPlan = result.funeralPlan
            funeralProvider = result.funeralProvider.orEmpty()
            members.clear(); members.addAll(result.members)
            pets.clear(); pets.addAll(result.pets)
            vehicles.clear(); vehicles.addAll(result.vehicles)
        } catch (exception: Exception) {
            if (exception is CancellationException) throw exception
            message = "No se pudo cargar la ficha: ${exception.message}"
        } finally {
            loading = false
        }
    }
    LaunchedEffect(apartment) { load() }

    DomuxScreenScaffold(title = "Ficha del apartamento $apartment", navController = navController) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
        DomuxFeedbackBanner(message) { message = "" }
        if (loading) androidx.compose.material3.CircularProgressIndicator()
        if (admin) {
            unit?.residents?.forEach { resident ->
                Column {
                    Text(
                        "Residente: ${resident.name} · " +
                            "${(resident.occupancyType ?: "residente").toDomuxDisplayLabel()}"
                    )
                    Row {
                        TextButton(onClick = {
                            navController.navigate("pqrs?residentId=${resident.id}")
                        }) { Text("Crear PQRS a su nombre") }
                        TextButton(onClick = {
                            navController.navigate("reservations?residentId=${resident.id}")
                        }) { Text("Crear reserva a su nombre") }
                    }
                }
            }
            DomuxCard(Modifier.fillMaxWidth()) {
                Column(
                    Modifier.padding(12.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    Text(
                        "Celda de parqueadero asignada",
                        style = MaterialTheme.typography.titleSmall,
                        color = MaterialTheme.colorScheme.primary
                    )
                    OutlinedTextField(
                        value = parking,
                        onValueChange = { parking = it },
                        label = { Text("Identificador de la celda") },
                        supportingText = { Text("Número asignado por la administración") },
                        modifier = Modifier.fillMaxWidth()
                    )
                }
            }
            OutlinedTextField(storage, { storage = it }, label = { Text("Cuarto útil (identificador)") }, modifier = Modifier.fillMaxWidth())

            Text("Integrantes del hogar", style = MaterialTheme.typography.titleMedium)
            var memberName by remember { mutableStateOf("") }
            var memberLastName by remember { mutableStateOf("") }
            var memberDocument by remember { mutableStateOf("") }
            var memberBirthDate by remember { mutableStateOf("") }
            var memberPhone by remember { mutableStateOf("") }
            var memberRelationship by remember { mutableStateOf("hijo") }
            var otherRelationship by remember { mutableStateOf("") }
            OutlinedTextField(memberName, { memberName = it }, label = { Text("Nombre") }, keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words), singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(memberLastName, { memberLastName = it }, label = { Text("Apellido") }, keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words), singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(memberDocument, { memberDocument = it }, label = { Text("Documento") }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(memberBirthDate, { memberBirthDate = it }, label = { Text("Nacimiento AAAA-MM-DD") }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(
                value = memberPhone,
                onValueChange = { input ->
                    memberPhone = input.filter { ch -> ch.isDigit() }.take(10)
                },
                label = { Text("Teléfono opcional") },
                isError = memberPhone.isNotEmpty() && memberPhone.length != 10,
                supportingText = { Text("10 dígitos (ej. 3001234567)") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            Text("Parentesco")
            Row(
                modifier = Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                householdRelationshipOptions.forEach { (value, label) ->
                    androidx.compose.material3.FilterChip(
                        selected = memberRelationship == value,
                        onClick = { memberRelationship = value },
                        label = { Text(label) }
                    )
                }
            }
            if (memberRelationship == "otro") {
                OutlinedTextField(otherRelationship, { otherRelationship = it }, label = { Text("Especifica parentesco") }, modifier = Modifier.fillMaxWidth())
            }
            Button(onClick = {
                if (memberPhone.isNotEmpty() && memberPhone.length != 10) {
                    message = "El teléfono debe tener exactamente 10 dígitos o estar vacío."
                } else if (memberName.isBlank() || memberDocument.isBlank() ||
                    !memberBirthDate.matches(Regex("\\d{4}-\\d{2}-\\d{2}")) ||
                    (memberRelationship == "otro" && otherRelationship.isBlank())
                ) {
                    message = "Completa nombre, documento, fecha y parentesco."
                } else {
                    members.add(HouseholdMemberData(
                        name = memberName.trim(),
                        lastName = memberLastName.trim().takeIf(String::isNotEmpty),
                        documentId = memberDocument.trim(), birthDate = memberBirthDate,
                        phone = memberPhone.trim().takeIf(String::isNotEmpty),
                        relationship = memberRelationship,
                        otherRelationship = otherRelationship.trim().takeIf(String::isNotEmpty)
                    ))
                    memberName = ""; memberLastName = ""; memberDocument = ""
                    memberBirthDate = ""; memberPhone = ""; otherRelationship = ""
                }
            }, modifier = Modifier.fillMaxWidth()) { Text("Agregar integrante") }
            members.forEachIndexed { index, member ->
                TextButton(onClick = { members.removeAt(index) }) {
                    Text(
                        "Quitar ${member.name} ${member.lastName} · " +
                            member.relationship.toDomuxDisplayLabel()
                    )
                }
            }

            Text("Mascotas", style = MaterialTheme.typography.titleMedium)
            var petName by remember { mutableStateOf("") }
            var petSpecies by remember { mutableStateOf("") }
            var petBreed by remember { mutableStateOf("") }
            var petAge by remember { mutableStateOf("") }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                OutlinedTextField(petName, { petName = it }, label = { Text("Nombre") }, keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words), singleLine = true, modifier = Modifier.weight(1f))
                OutlinedTextField(petSpecies, { petSpecies = it }, label = { Text("Especie") }, keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words), singleLine = true, modifier = Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                OutlinedTextField(petBreed, { petBreed = it }, label = { Text("Raza") }, keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words), singleLine = true, modifier = Modifier.weight(1f))
                OutlinedTextField(petAge, { petAge = it.filter(Char::isDigit) }, label = { Text("Edad") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), singleLine = true, modifier = Modifier.weight(1f))
            }
            Button(onClick = {
                val age = petAge.toIntOrNull()
                if (petName.isBlank() || petSpecies.isBlank() || petBreed.isBlank() || age == null || age > 100) {
                    message = "Completa nombre, especie, raza y una edad válida."
                } else {
                    pets.add(PetData(name = petName.trim(), species = petSpecies.trim(), breed = petBreed.trim(), ageYears = age))
                    petName = ""; petSpecies = ""; petBreed = ""; petAge = ""
                }
            }, modifier = Modifier.fillMaxWidth()) { Text("Agregar mascota") }
            pets.forEachIndexed { index, pet ->
                TextButton(onClick = { pets.removeAt(index) }) {
                    Text("Quitar ${pet.name} · ${pet.species.toDomuxDisplayLabel()}")
                }
            }

            Text("Vehículos", style = MaterialTheme.typography.titleMedium)
            var plate by remember { mutableStateOf("") }
            var vehicleType by remember { mutableStateOf("carro") }
            var makeModel by remember { mutableStateOf("") }
            var vehicleYear by remember { mutableStateOf("") }
            var registeredOwner by remember { mutableStateOf("") }
            var color by remember { mutableStateOf("") }
            Row(
                modifier = Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                listOf("carro", "moto").forEach { type ->
                    androidx.compose.material3.FilterChip(
                        selected = vehicleType == type,
                        onClick = { vehicleType = type },
                        label = { Text(type.toDomuxDisplayLabel()) }
                    )
                }
            }
            OutlinedTextField(plate, { plate = it.uppercase() }, label = { Text("Placa colombiana") }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(makeModel, { makeModel = it }, label = { Text("Marca y modelo") }, keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words), singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(vehicleYear, { vehicleYear = it.filter(Char::isDigit) }, label = { Text("Año") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(registeredOwner, { registeredOwner = it }, label = { Text("A nombre de") }, keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words), singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(color, { color = it }, label = { Text("Color (opcional)") }, keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words), singleLine = true, modifier = Modifier.fillMaxWidth())
            Button(onClick = {
                val year = vehicleYear.toIntOrNull()
                if (!plate.matches(Regex("[A-Z]{3}\\d{3}|[A-Z]{3}\\d{2}[A-Z]")) ||
                    makeModel.isBlank() || year == null || registeredOwner.isBlank()
                ) {
                    message = "Revisa placa, marca/modelo, año y titular del vehículo."
                } else {
                    vehicles.add(VehicleData(
                        plate = plate, type = vehicleType, makeModel = makeModel.trim(), year = year,
                        registeredOwner = registeredOwner.trim(), color = color.trim().takeIf(String::isNotEmpty)
                    ))
                    plate = ""; makeModel = ""; vehicleYear = ""; registeredOwner = ""; color = ""
                }
            }, modifier = Modifier.fillMaxWidth()) { Text("Agregar vehículo") }
            vehicles.forEachIndexed { index, vehicle ->
                TextButton(onClick = { vehicles.removeAt(index) }) { Text("Quitar ${vehicle.plate} · ${vehicle.makeModel}") }
            }
            Button(
                enabled = !busy && !loading && unit != null,
                onClick = {
                    if (members.any { member ->
                            !member.phone.isNullOrEmpty() && member.phone.length != 10
                        }
                    ) {
                        message = "Cada teléfono de integrante debe tener 10 dígitos o estar vacío."
                        return@Button
                    }
                    busy = true
                    message = ""
                    scope.launch {
                        try {
                            val response = RetrofitClient.api.saveUnit(
                                Session.bearer(),
                                SaveResidentialUnitRequest(
                                    apartment = apartment,
                                    parkingIdentifier = parking.trim().takeIf(String::isNotEmpty),
                                    storageIdentifier = storage.trim().takeIf(String::isNotEmpty),
                                    petInsurance = petInsurance,
                                    petInsurer = petInsurer.trim().takeIf(String::isNotEmpty),
                                    funeralPlan = funeralPlan,
                                    funeralProvider = funeralProvider.trim().takeIf(String::isNotEmpty),
                                    members = members.toList(),
                                    pets = pets.toList(),
                                    vehicles = vehicles.toList()
                                )
                            )
                            if (response.isSuccessful) {
                                message = "Ficha del hogar guardada."
                                response.body()?.unit?.let { unit = it }
                            } else message = mensajeDeError(response.code(), response.errorBody()?.string())
                        } catch (exception: Exception) {
                            if (exception is CancellationException) throw exception
                            message = "No se pudo guardar la ficha: ${exception.message}"
                        } finally {
                            busy = false
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth()
            ) { Text(if (busy) "Guardando..." else "Guardar ficha del apartamento") }
        } else {
            unit?.let { profile ->
                Text("Residentes", style = MaterialTheme.typography.titleMedium)
                profile.residents.forEach {
                    DomuxCard(Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(12.dp)) {
                            Text(it.name, style = MaterialTheme.typography.titleSmall)
                            Text((it.occupancyType ?: "residente").toDomuxDisplayLabel())
                        }
                    }
                }
                Text("Celda de parqueadero asignada", style = MaterialTheme.typography.titleMedium)
                DomuxCard(Modifier.fillMaxWidth()) {
                    Text(
                        profile.parkingIdentifier ?: "No hay una celda asignada",
                        Modifier.padding(12.dp)
                    )
                }
                Text("Cuarto útil", style = MaterialTheme.typography.titleMedium)
                DomuxCard(Modifier.fillMaxWidth()) {
                    Text(profile.storageIdentifier ?: "No registrado", Modifier.padding(12.dp))
                }
                Text("Integrantes del hogar", style = MaterialTheme.typography.titleMedium)
                profile.members.forEach {
                    DomuxCard(Modifier.fillMaxWidth()) {
                        Column(
                            Modifier.padding(12.dp),
                            verticalArrangement = Arrangement.spacedBy(3.dp)
                        ) {
                            Text("${it.name} ${it.lastName.orEmpty()}".trim(), style = MaterialTheme.typography.titleSmall)
                            Text("Parentesco: ${(it.otherRelationship ?: it.relationship).toDomuxDisplayLabel()}")
                            Text("Documento: ${it.documentId}")
                            Text("Fecha de nacimiento: ${it.birthDate}")
                            it.phone?.takeIf(String::isNotBlank)?.let { phone -> Text("Teléfono: $phone") }
                        }
                    }
                }
                Text("Mascotas", style = MaterialTheme.typography.titleMedium)
                profile.pets.forEach {
                    DomuxCard(Modifier.fillMaxWidth()) {
                        Column(
                            Modifier.padding(12.dp),
                            verticalArrangement = Arrangement.spacedBy(3.dp)
                        ) {
                            Text(it.name, style = MaterialTheme.typography.titleSmall)
                            Text("Especie: ${it.species.toDomuxDisplayLabel()}")
                            Text("Raza: ${it.breed} · Edad: ${it.ageYears} años")
                        }
                    }
                }
                Text("Vehículos", style = MaterialTheme.typography.titleMedium)
                profile.vehicles.forEach {
                    DomuxCard(Modifier.fillMaxWidth()) {
                        Column(
                            Modifier.padding(12.dp),
                            verticalArrangement = Arrangement.spacedBy(3.dp)
                        ) {
                            Text("${it.type.toDomuxDisplayLabel()} · ${it.plate}", style = MaterialTheme.typography.titleSmall)
                            Text("Marca y modelo: ${it.makeModel} · Año: ${it.year}")
                            Text("A nombre de: ${it.registeredOwner}")
                            it.color?.takeIf(String::isNotBlank)?.let { color -> Text("Color: $color") }
                        }
                    }
                }
            }
        }
        Spacer(Modifier.height(4.dp))
        }
    }
}
