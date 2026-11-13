package com.dracknoval.domux

import androidx.lifecycle.viewModelScope
import com.dracknoval.domux.data.ApartmentOption
import com.dracknoval.domux.data.CreateUserRequest
import com.dracknoval.domux.data.ResetPasswordRequest
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.SetPinRequest
import com.dracknoval.domux.data.UpdateUserRequest
import com.dracknoval.domux.data.UserData
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.text.ParsePosition
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale

internal val occupancyOptions = listOf(
    "propietario" to "Propietario",
    "arrendatario" to "Arrendatario",
    "residente" to "Residente"
)

internal val roleOptions = listOf(
    "RESIDENT" to "Residente",
    "GUARD" to "Guardia",
    "ADMIN" to "Administrador"
)

/** El rol en palabras, no en el código interno del servidor («RESIDENT» pasa a «Residente»). */
internal fun roleLabel(role: String?): String =
    roleOptions.firstOrNull { it.first == role }?.second ?: role.orEmpty()

private val passwordSpecialChars = setOf('@', '$', '!', '%', '*', '?', '&', '#', '.', '_', '-')

/** Edad cumplida a hoy de una fecha AAAA-MM-DD; null si la fecha no es válida. */
internal fun ageFromIsoDate(value: String): Int? {
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

/** La misma regla del servidor: 8 o más caracteres con mayúscula, minúscula, número y símbolo. */
internal fun validStrongPassword(value: String): Boolean =
    value.length >= 8 &&
        value.any { it in 'A'..'Z' } &&
        value.any { it in 'a'..'z' } &&
        value.any { it in '0'..'9' } &&
        value.any { it in passwordSpecialChars } &&
        value.all {
            it in 'A'..'Z' || it in 'a'..'z' || it in '0'..'9' ||
                it in passwordSpecialChars
        }

/** Filtros de la lista de usuarios (HU-012). En los de sí o no, null es «Todos». */
data class UserFilters(
    val search: String = "",
    val apartmentFrom: String = "",
    val apartmentTo: String = "",
    val minAge: String = "",
    val maxAge: String = "",
    val occupancy: String = "",
    val active: Boolean? = null,
    val pets: Boolean? = null,
    val vehicles: Boolean? = null,
    val parking: Boolean? = null,
    val storage: Boolean? = null
)

/** El formulario «Crear usuario» (HU-011). La contraseña temporal solo vive aquí, en memoria. */
data class NewUserForm(
    val role: String = "RESIDENT",
    val name: String = "",
    val lastName: String = "",
    val email: String = "",
    val phone: String = "",
    val documentId: String = "",
    val password: String = "",
    // El residente se vincula a un apartamento que ya existe en la estructura de la unidad (HU-017).
    val apartment: ApartmentOption? = null,
    val occupancyType: String = "propietario",
    val birthDate: String = "",
    val parentalConsent: Boolean = false,
    val consentConfirmed: Boolean = false,
    // Se pone en true al tocar «Crear usuario»: desde ahí se marcan los campos que faltan.
    val attempted: Boolean = false
) {
    val isResident: Boolean get() = role == "RESIDENT"
    val isMinor: Boolean get() = ageFromIsoDate(birthDate)?.let { it < 18 } == true

    /** Lo primero que falta o está mal, en palabras; null si se puede crear. */
    fun problem(): String? = when {
        listOf(name, lastName, email, phone, documentId).any { it.isBlank() } ->
            "Completa todos los campos obligatorios."
        !email.trim().contains("@") -> "Revisa el correo: le falta la @."
        phoneProblem(phone) != null -> phoneProblem(phone)
        !validStrongPassword(password) ->
            "La contraseña temporal debe tener 8 caracteres o más, con mayúscula, minúscula, número y símbolo."
        isResident && apartment == null -> "Elige el apartamento del residente."
        isResident && !consentConfirmed -> "Confirma que el residente autorizó el tratamiento de sus datos."
        else -> null
    }
}

/** Lo que se va cambiando en «Editar usuario»; empieza con los datos que ya tiene la persona. */
data class UserEditDraft(
    val name: String,
    val lastName: String,
    val email: String,
    val phone: String,
    val documentId: String,
    val role: String,
    val apartment: ApartmentOption?,
    val occupancyType: String,
    val active: Boolean,
    val consent: Boolean,
    val birthDate: String,
    val parentalConsent: Boolean
) {
    val isMinor: Boolean get() = ageFromIsoDate(birthDate)?.let { it < 18 } == true

    companion object {
        fun from(user: UserData) = UserEditDraft(
            name = user.firstName?.takeIf { it.isNotBlank() }
                ?: user.name.removeSuffix(user.lastName.orEmpty()).trim(),
            lastName = user.lastName.orEmpty(),
            email = user.email,
            phone = user.phone.orEmpty(),
            documentId = user.documentId.orEmpty(),
            role = user.role,
            apartment = user.apartmentId?.let { ApartmentOption(it, user.apartment.orEmpty()) },
            occupancyType = user.occupancyType ?: "propietario",
            active = user.isActive,
            consent = false,
            birthDate = user.birthDate.orEmpty(),
            parentalConsent = user.parentalConsent
        )
    }
}

/** Todo lo que «Gestión de usuarios» necesita para dibujarse (HU-011 y HU-012). */
data class UsersUiState(
    val selectedTab: Int = 0,
    val users: List<UserData> = emptyList(),
    val loading: Boolean = true,
    val page: Int = 1,
    val totalPages: Int = 1,
    val total: Int = 0,
    val filters: UserFilters = UserFilters(),
    val showAdvancedFilters: Boolean = false,
    val form: NewUserForm = NewUserForm(),
    // Ventanas abiertas. Si algo falla, el error se muestra dentro de la ventana, que es lo que se ve.
    val editing: UserData? = null,
    val editError: String = "",
    val pendingUpdate: Pair<Int, UpdateUserRequest>? = null,
    val resetting: UserData? = null,
    val resetError: String = "",
    val pendingReset: Pair<Int, String>? = null,
    val pinFor: UserData? = null,
    val pinError: String = "",
    val busy: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false
)

/**
 * ViewModel de «Gestión de usuarios» (HU-011 y HU-012): lista con filtros y páginas, crear,
 * editar, restablecer contraseña y PIN del guardia. Cada acción deja un aviso verde si salió
 * bien o rojo si no.
 */
class UsersViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(UsersUiState())
    val state: StateFlow<UsersUiState> = _state.asStateFlow()
    private var reloadJob: Job? = null

    init {
        load(1)
    }

    override fun postMessage(text: String, isError: Boolean) {
        _state.update { it.copy(message = text, messageIsError = isError) }
    }

    override fun setBusy(busy: Boolean) {
        _state.update { it.copy(busy = busy) }
    }

    fun dismissMessage() {
        _state.update { it.copy(message = "") }
    }

    fun selectTab(index: Int) {
        _state.update { it.copy(selectedTab = index) }
    }

    // ---- Lista y filtros ----

    fun toggleAdvancedFilters() {
        _state.update { it.copy(showAdvancedFilters = !it.showAdvancedFilters) }
    }

    /** Cambia un filtro; la lista se vuelve a pedir cuando la persona deja de escribir un momento. */
    fun updateFilters(change: (UserFilters) -> UserFilters) {
        _state.update { it.copy(filters = change(it.filters)) }
        reloadJob?.cancel()
        reloadJob = viewModelScope.launch {
            delay(350)
            load(1)
        }
    }

    fun previousPage() = load(_state.value.page - 1)

    fun nextPage() = load(_state.value.page + 1)

    fun load(page: Int = _state.value.page) {
        val filters = _state.value.filters
        viewModelScope.launch {
            _state.update { it.copy(loading = true) }
            val response = attempt("No se pudo cargar la lista de usuarios") {
                api.getUsers(
                    auth = auth(),
                    page = page.coerceAtLeast(1),
                    search = filters.search.trim().takeIf(String::isNotEmpty),
                    occupancyType = filters.occupancy.takeIf(String::isNotEmpty),
                    apartmentFrom = filters.apartmentFrom.trim().takeIf(String::isNotEmpty),
                    apartmentTo = filters.apartmentTo.trim().takeIf(String::isNotEmpty),
                    hasPets = filters.pets?.toString(),
                    hasVehicles = filters.vehicles?.toString(),
                    hasParking = filters.parking?.toString(),
                    hasStorage = filters.storage?.toString(),
                    minAge = filters.minAge.takeIf(String::isNotBlank),
                    maxAge = filters.maxAge.takeIf(String::isNotBlank),
                    isActive = filters.active?.toString()
                )
            }
            val result = response?.body()
            _state.update {
                if (response == null) it.copy(loading = false)
                else it.copy(
                    loading = false,
                    users = result?.users.orEmpty(),
                    page = result?.page ?: page,
                    totalPages = (result?.totalPages ?: 1).coerceAtLeast(1),
                    total = result?.total ?: 0
                )
            }
        }
    }

    // ---- Crear usuario (HU-011) ----

    fun updateForm(change: (NewUserForm) -> NewUserForm) {
        _state.update { it.copy(form = change(it.form)) }
    }

    fun createUser() {
        _state.update { it.copy(form = it.form.copy(attempted = true)) }
        val form = _state.value.form
        val problem = form.problem()
        if (problem != null) {
            showError(problem)
            return
        }
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo crear el usuario") {
                    api.createUser(
                        auth(),
                        CreateUserRequest(
                            name = form.name.trim(),
                            email = form.email.trim().lowercase(),
                            password = form.password,
                            role = form.role,
                            apartmentId = if (form.isResident) form.apartment?.id else null,
                            lastName = form.lastName.trim(),
                            phone = phoneToSend(form.phone),
                            documentId = form.documentId.trim(),
                            occupancyType = form.occupancyType,
                            dataProcessingConsent = form.isResident && form.consentConfirmed,
                            birthDate = form.birthDate.trim().takeIf { form.isResident && it.isNotEmpty() },
                            parentalConsent = form.isResident && form.parentalConsent
                        )
                    )
                }
            } ?: return@launch
            _state.update { it.copy(form = NewUserForm(), selectedTab = 0) }
            showSuccess("Usuario creado. Ya puede entrar con su correo y la contraseña temporal.")
            load(1)
        }
    }

    // ---- Editar usuario ----

    fun startEdit(user: UserData) {
        _state.update { it.copy(editing = user, editError = "") }
    }

    fun cancelEdit() {
        _state.update { it.copy(editing = null, editError = "", pendingUpdate = null) }
    }

    /** Revisa lo editado y, si está bien, pide confirmar antes de guardar. */
    fun requestUpdate(user: UserData, draft: UserEditDraft) {
        val resident = draft.role == "RESIDENT"
        val becomesResident = resident && user.role != "RESIDENT"
        val problem = when {
            listOf(draft.name, draft.lastName, draft.email, draft.phone, draft.documentId).any { it.isBlank() } ->
                "Completa los campos obligatorios."
            !draft.email.trim().contains("@") -> "Revisa el correo: le falta la @."
            phoneProblem(draft.phone) != null -> phoneProblem(draft.phone)
            resident && draft.apartment == null -> "Elige el apartamento del residente."
            becomesResident && !draft.consent -> "Confirma que el residente autorizó el tratamiento de sus datos."
            else -> null
        }
        if (problem != null) {
            _state.update { it.copy(editError = problem) }
            return
        }
        val request = UpdateUserRequest(
            name = draft.name.trim(),
            lastName = draft.lastName.trim(),
            email = draft.email.trim().lowercase(),
            phone = phoneToSend(draft.phone),
            documentId = draft.documentId.trim(),
            role = draft.role,
            apartmentId = if (resident) draft.apartment?.id else null,
            occupancyType = draft.occupancyType.takeIf { resident },
            isActive = draft.active,
            dataProcessingConsent = true.takeIf { becomesResident },
            birthDate = draft.birthDate.trim().takeIf { it.isNotEmpty() },
            parentalConsent = draft.parentalConsent.takeIf { resident }
        )
        _state.update { it.copy(editError = "", pendingUpdate = user.id to request) }
    }

    fun cancelPendingUpdate() {
        _state.update { it.copy(pendingUpdate = null) }
    }

    fun confirmUpdate() {
        val (userId, request) = _state.value.pendingUpdate ?: return
        _state.update { it.copy(pendingUpdate = null) }
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo actualizar el usuario", onError = { error -> _state.update { it.copy(editError = error) } }) {
                    api.updateUser(auth(), userId, request)
                }
            } ?: return@launch
            _state.update { it.copy(editing = null, editError = "") }
            showSuccess("Usuario actualizado.")
            load()
        }
    }

    // ---- Restablecer contraseña ----

    fun startReset(user: UserData) {
        _state.update { it.copy(resetting = user, resetError = "") }
    }

    fun cancelReset() {
        _state.update { it.copy(resetting = null, resetError = "", pendingReset = null) }
    }

    fun requestReset(user: UserData, newPassword: String) {
        if (!validStrongPassword(newPassword)) {
            _state.update {
                it.copy(resetError = "La contraseña debe tener 8 caracteres o más, con mayúscula, minúscula, número y símbolo.")
            }
            return
        }
        _state.update { it.copy(resetError = "", pendingReset = user.id to newPassword) }
    }

    fun cancelPendingReset() {
        _state.update { it.copy(pendingReset = null) }
    }

    fun confirmReset() {
        val (userId, newPassword) = _state.value.pendingReset ?: return
        _state.update { it.copy(pendingReset = null) }
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo restablecer la contraseña", onError = { error -> _state.update { it.copy(resetError = error) } }) {
                    api.resetUserPassword(auth(), userId, ResetPasswordRequest(newPassword))
                }
            } ?: return@launch
            _state.update { it.copy(resetting = null, resetError = "") }
            showSuccess("Contraseña restablecida. Entrégasela a la persona en privado.")
        }
    }

    // ---- PIN del guardia (HU-010) ----

    fun startPin(user: UserData) {
        _state.update { it.copy(pinFor = user, pinError = "") }
    }

    fun cancelPin() {
        if (_state.value.busy) return
        _state.update { it.copy(pinFor = null, pinError = "") }
    }

    fun savePin(pin: String) {
        val user = _state.value.pinFor ?: return
        if (pin.length != 4 || !pin.all(Char::isDigit)) {
            _state.update { it.copy(pinError = "El PIN tiene exactamente 4 dígitos.") }
            return
        }
        _state.update { it.copy(pinError = "") }
        viewModelScope.launch {
            withBusy {
                attempt("No se pudo guardar el PIN", onError = { error -> _state.update { it.copy(pinError = error) } }) {
                    api.setGuardPin(auth(), user.id, SetPinRequest(pin))
                }
            } ?: return@launch
            _state.update { it.copy(pinFor = null) }
            showSuccess("PIN guardado.")
            load()
        }
    }
}
