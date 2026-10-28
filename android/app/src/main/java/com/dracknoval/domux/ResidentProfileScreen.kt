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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
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
    var message by remember { mutableStateOf("") }
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
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            DomuxFeedbackBanner(message) { message = "" }
            if (loading) CircularProgressIndicator()
            user?.let { profile ->
            DomuxCard(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(profile.fullName ?: profile.name, style = MaterialTheme.typography.titleMedium)
                    Text("Documento: ${profile.documentId.orEmpty()}")
                    Text("Apartamento: ${profile.apartment ?: "Sin asignar"}")
                    Text("Tipo de residente: ${profile.occupancyType ?: "—"}")
                    Text("Rol: ${profile.role}")
                }
            }
            Text("Datos que puedes actualizar", style = MaterialTheme.typography.titleMedium)
            OutlinedTextField(email, { email = it }, label = { Text("Correo") }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(phone, { phone = it }, label = { Text("Teléfono") }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(
                socialNetworks, { socialNetworks = it }, label = { Text("Redes sociales (opcional)") },
                modifier = Modifier.fillMaxWidth()
            )
            Button(
                enabled = !busy,
                onClick = {
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
                                message = "Perfil actualizado."
                            } else message = mensajeDeError(response.code(), response.errorBody()?.string())
                        } catch (exception: Exception) {
                            if (exception is CancellationException) throw exception
                            message = "No se pudo guardar el perfil: ${exception.message}"
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
        }
            unit?.let { profile ->
            Text("Información del hogar", style = MaterialTheme.typography.titleLarge)
            profile.residents.forEach { resident ->
                Text("${resident.name} · ${resident.occupancyType ?: "residente"}")
            }
            Text("Parqueadero: ${profile.parkingIdentifier ?: "No registrado"}")
            Text("Cuarto útil: ${profile.storageIdentifier ?: "No registrado"}")
            Text("Seguro de mascotas: ${if (profile.petInsurance) profile.petInsurer ?: "Sí" else "No"}")
            Text("Plan funerario: ${if (profile.funeralPlan) profile.funeralProvider ?: "Sí" else "No"}")
            profile.members.forEach { member ->
                DomuxCard(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(12.dp)) {
                        Text("${member.name} ${member.lastName.orEmpty()}".trim(), style = MaterialTheme.typography.titleSmall)
                        Text("Parentesco: ${member.otherRelationship ?: member.relationship}")
                        Text("Fecha de nacimiento: ${member.birthDate}")
                    }
                }
            }
            profile.pets.forEach { pet ->
                Text("Mascota: ${pet.name} · ${pet.species} · ${pet.breed} · ${pet.ageYears} años")
            }
            profile.vehicles.forEach { vehicle ->
                Text("Vehículo: ${vehicle.type} ${vehicle.plate} · ${vehicle.makeModel} · ${vehicle.year}")
            }
        }
            Spacer(Modifier.height(6.dp))
        }
    }
}
