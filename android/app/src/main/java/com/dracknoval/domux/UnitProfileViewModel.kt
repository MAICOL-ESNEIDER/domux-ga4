package com.dracknoval.domux

import androidx.lifecycle.viewModelScope
import com.dracknoval.domux.data.HouseholdMemberData
import com.dracknoval.domux.data.PetData
import com.dracknoval.domux.data.ResidentialUnitData
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.SaveResidentialUnitRequest
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.data.VehicleData
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

private val datePattern = Regex("\\d{4}-\\d{2}-\\d{2}")

// Placa colombiana: carro AAA123 o moto AAA12A.
private val platePattern = Regex("[A-Z]{3}\\d{3}|[A-Z]{3}\\d{2}[A-Z]")

/** Todo lo que la ficha del apartamento necesita para dibujarse (HU-020). */
data class UnitProfileUiState(
    val apartment: String = "",
    // La administración edita la ficha; el residente solo la ve.
    val admin: Boolean = false,
    val unit: ResidentialUnitData? = null,
    // Lo que la administración va armando; se guarda todo junto con «Guardar ficha».
    val petInsurance: Boolean = false,
    val petInsurer: String = "",
    val members: List<HouseholdMemberData> = emptyList(),
    val pets: List<PetData> = emptyList(),
    val vehicles: List<VehicleData> = emptyList(),
    val loading: Boolean = true,
    val busy: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false
)

/**
 * ViewModel de la ficha del apartamento (HU-020): carga el hogar, revisa cada integrante,
 * mascota o vehículo antes de ponerlo en la lista y guarda la ficha completa en el servidor.
 */
class UnitProfileViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(UnitProfileUiState())
    val state: StateFlow<UnitProfileUiState> = _state.asStateFlow()

    override fun postMessage(text: String, isError: Boolean) {
        _state.update { it.copy(message = text, messageIsError = isError) }
    }

    override fun setBusy(busy: Boolean) {
        _state.update { it.copy(busy = busy) }
    }

    fun dismissMessage() {
        _state.update { it.copy(message = "") }
    }

    private var startedFor: String? = null

    /** La pantalla lo llama con el apartamento de la ruta; solo carga la primera vez. */
    fun start(apartment: String) {
        if (startedFor == apartment) return
        startedFor = apartment
        _state.update { it.copy(apartment = apartment, admin = Session.isAdmin) }
        load()
    }

    fun load() {
        val current = _state.value
        viewModelScope.launch {
            _state.update { it.copy(loading = true) }
            val response = attempt("No se pudo cargar la ficha") {
                if (current.admin) api.getUnit(auth(), current.apartment) else api.getMyUnit(auth())
            }
            response?.body()?.unit?.let(::applyUnit)
            _state.update { it.copy(loading = false) }
        }
    }

    // Se recargan las listas con los ids que dio el servidor, para que el próximo guardado no
    // retire y vuelva a crear lo mismo.
    private fun applyUnit(unit: ResidentialUnitData) {
        _state.update {
            it.copy(
                unit = unit,
                petInsurance = unit.petInsurance,
                petInsurer = unit.petInsurer.orEmpty(),
                members = unit.members,
                pets = unit.pets,
                vehicles = unit.vehicles
            )
        }
    }

    fun setPetInsurance(value: Boolean) {
        _state.update { it.copy(petInsurance = value) }
    }

    fun onPetInsurer(value: String) {
        _state.update { it.copy(petInsurer = value) }
    }

    /** Pone el integrante en la lista si los datos están completos; devuelve si lo agregó. */
    fun addMember(
        name: String,
        lastName: String,
        documentId: String,
        birthDate: String,
        phone: String,
        relationship: String,
        otherRelationship: String
    ): Boolean {
        if (name.isBlank() || documentId.isBlank() || !birthDate.trim().matches(datePattern) ||
            (relationship == "otro" && otherRelationship.isBlank())
        ) {
            showError("Completa nombre, documento, fecha de nacimiento (AAAA-MM-DD) y parentesco.")
            return false
        }
        val member = HouseholdMemberData(
            name = name.trim(),
            lastName = lastName.trim().takeIf(String::isNotEmpty),
            documentId = documentId.trim(),
            birthDate = birthDate.trim(),
            phone = phone.trim().takeIf(String::isNotEmpty),
            relationship = relationship,
            otherRelationship = otherRelationship.trim().takeIf { relationship == "otro" && it.isNotEmpty() }
        )
        _state.update { it.copy(members = it.members + member) }
        showSuccess(addedReminder("Integrante agregado"))
        return true
    }

    fun removeMember(index: Int) {
        _state.update { it.copy(members = it.members.filterIndexed { i, _ -> i != index }) }
    }

    /** Pone la mascota en la lista si los datos están completos; devuelve si la agregó. */
    fun addPet(
        name: String,
        species: String,
        breed: String,
        ageText: String,
        vaccinesUpToDate: Boolean,
        vaccinationDate: String,
        dewormingUpToDate: Boolean,
        dewormingDate: String
    ): Boolean {
        val age = ageText.toIntOrNull()
        val lastVaccination = vaccinationDate.trim().takeIf(String::isNotEmpty)
        val lastDeworming = dewormingDate.trim().takeIf(String::isNotEmpty)
        val problem = when {
            name.isBlank() || species.isBlank() || breed.isBlank() || age == null || age > 100 ->
                "Completa nombre, especie, raza y una edad válida."
            listOfNotNull(lastVaccination, lastDeworming).any { !it.matches(datePattern) } ->
                "Escribe las fechas de la mascota como AAAA-MM-DD."
            // Vacunación y desparasitación (RN-028): si está al día, se pide la fecha de la última.
            (vaccinesUpToDate && lastVaccination == null) || (dewormingUpToDate && lastDeworming == null) ->
                "Si está al día, escribe la fecha de la última vacuna o desparasitación."
            else -> null
        }
        if (problem != null || age == null) {
            showError(problem ?: "Completa nombre, especie, raza y una edad válida.")
            return false
        }
        val pet = PetData(
            name = name.trim(),
            species = species.trim(),
            breed = breed.trim(),
            ageYears = age,
            vaccinesUpToDate = vaccinesUpToDate,
            lastVaccinationDate = lastVaccination,
            dewormingUpToDate = dewormingUpToDate,
            lastDewormingDate = lastDeworming
        )
        _state.update { it.copy(pets = it.pets + pet) }
        showSuccess(addedReminder("Mascota agregada"))
        return true
    }

    fun removePet(index: Int) {
        _state.update { it.copy(pets = it.pets.filterIndexed { i, _ -> i != index }) }
    }

    /** Pone el vehículo en la lista si los datos están completos; devuelve si lo agregó. */
    fun addVehicle(
        plate: String,
        type: String,
        makeModel: String,
        yearText: String,
        registeredOwner: String,
        color: String
    ): Boolean {
        val cleanPlate = plate.trim().uppercase()
        val year = yearText.toIntOrNull()
        if (!cleanPlate.matches(platePattern) || makeModel.isBlank() || year == null || registeredOwner.isBlank()) {
            showError("Revisa placa (AAA123 o AAA12A), marca y modelo, año y a nombre de quién está el vehículo.")
            return false
        }
        val vehicle = VehicleData(
            plate = cleanPlate,
            type = type,
            makeModel = makeModel.trim(),
            year = year,
            registeredOwner = registeredOwner.trim(),
            color = color.trim().takeIf(String::isNotEmpty)
        )
        _state.update { it.copy(vehicles = it.vehicles + vehicle) }
        showSuccess(addedReminder("Vehículo agregado"))
        return true
    }

    fun removeVehicle(index: Int) {
        _state.update { it.copy(vehicles = it.vehicles.filterIndexed { i, _ -> i != index }) }
    }

    fun save() {
        val current = _state.value
        if (current.unit == null) return
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudo guardar la ficha") {
                    api.saveUnit(
                        auth(),
                        SaveResidentialUnitRequest(
                            apartment = current.apartment,
                            petInsurance = current.petInsurance,
                            petInsurer = current.petInsurer.trim().takeIf { current.petInsurance && it.isNotEmpty() },
                            members = current.members,
                            pets = current.pets,
                            vehicles = current.vehicles
                        )
                    )
                }
            } ?: return@launch
            response.body()?.unit?.let(::applyUnit)
            showSuccess("Ficha del hogar guardada.")
        }
    }

    // Lo agregado queda en la lista de la pantalla; en el servidor solo queda al guardar la ficha.
    private fun addedReminder(what: String) = "$what. Toca «Guardar ficha del apartamento» para que quede guardado."
}
