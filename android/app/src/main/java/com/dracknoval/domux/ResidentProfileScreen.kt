package com.dracknoval.domux

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
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
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.dracknoval.domux.data.ResidentialUnitData
import com.dracknoval.domux.data.UserData
import com.dracknoval.domux.data.fullName
import com.dracknoval.domux.data.healthSummary

/**
 * «Mi perfil» del residente (HU-019). La pantalla solo dibuja: los datos y el guardado están en
 * [ResidentProfileViewModel].
 */
@Composable
fun ResidentProfileScreen(navController: NavController, viewModel: ResidentProfileViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()

    DomuxScreenScaffold(title = "Mi perfil", navController = navController) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            // El aviso queda fijo arriba: se ve aunque la persona esté abajo, en el botón de guardar.
            DomuxMessageBanner(
                state.message, state.messageIsError,
                Modifier.padding(start = 20.dp, end = 20.dp, top = 12.dp)
            ) { viewModel.dismissMessage() }
            ProfileContent(state, viewModel, navController, Modifier.weight(1f))
        }
    }
}

@Composable
private fun ProfileContent(
    state: ResidentProfileUiState,
    viewModel: ResidentProfileViewModel,
    navController: NavController,
    modifier: Modifier = Modifier
) {
    Column(
        modifier
            .fillMaxWidth()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        if (state.loading) CircularProgressIndicator()
        state.user?.let { profile ->
            ProfileSummary(profile)
            Text("Datos que puedes actualizar", style = MaterialTheme.typography.titleMedium)
            OutlinedTextField(
                state.email, viewModel::onEmail,
                label = { Text("Correo") }, singleLine = true, modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                state.phone, viewModel::onPhone,
                label = { Text("Teléfono") }, singleLine = true, modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                state.socialNetworks, viewModel::onSocialNetworks,
                label = { Text("Redes sociales (opcional)") }, modifier = Modifier.fillMaxWidth()
            )
            Button(
                onClick = { viewModel.save() },
                enabled = !state.busy,
                modifier = Modifier.fillMaxWidth()
            ) { Text(if (state.busy) "Guardando..." else "Guardar cambios") }
            Text(
                "Para cambiar apartamento, tipo de residente, parentesco, documento, mascotas o vehículos, " +
                    "solicítalo a administración mediante una PQRS o en la oficina.",
                style = MaterialTheme.typography.bodyMedium
            )
            TextButton(onClick = { navController.navigate("pqrs") }) {
                Text("Crear PQRS para solicitar un cambio")
            }
        }
        state.unit?.let { HouseholdSummary(it) }
        Spacer(Modifier.height(6.dp))
    }
}

@Composable
private fun ProfileSummary(profile: UserData) {
    DomuxCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(profile.fullName ?: profile.name, style = MaterialTheme.typography.titleMedium)
            Text("Documento: ${profile.documentId.orEmpty()}")
            Text("Apartamento: ${profile.apartment ?: "Sin asignar"}")
            Text("Tipo de residente: ${profile.occupancyType ?: "—"}")
            Text("Rol: ${roleLabel(profile.role)}")
        }
    }
}

/** Lo que la unidad tiene registrado del hogar, solo para leer (Mi perfil y la ficha del residente). */
@Composable
internal fun HouseholdSummary(unit: ResidentialUnitData) {
    Text("Información del hogar", style = MaterialTheme.typography.titleLarge)
    unit.residents.forEach { resident ->
        Text("${resident.name} · ${resident.occupancyType ?: "residente"}")
    }
    Text("Parqueadero: ${unit.parkingIdentifier ?: "No registrado"}")
    Text("Cuarto útil: ${unit.storageIdentifier ?: "No registrado"}")
    Text("Seguro de mascotas: ${if (unit.petInsurance) unit.petInsurer ?: "Sí" else "No"}")
    unit.members.forEach { member ->
        DomuxCard(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp)) {
                Text(member.fullName, style = MaterialTheme.typography.titleSmall)
                Text("Parentesco: ${member.otherRelationship ?: relationshipLabel(member.relationship)}")
                Text("Fecha de nacimiento: ${member.birthDate}")
            }
        }
    }
    unit.pets.forEach { pet ->
        Text("Mascota: ${pet.name} · ${pet.species} · ${pet.breed} · ${pet.ageYears} años · ${pet.healthSummary}")
    }
    unit.vehicles.forEach { vehicle ->
        Text("Vehículo: ${vehicle.type} ${vehicle.plate} · ${vehicle.makeModel} · ${vehicle.year}")
    }
}
