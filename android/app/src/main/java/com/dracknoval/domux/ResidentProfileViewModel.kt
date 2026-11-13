package com.dracknoval.domux

import androidx.lifecycle.viewModelScope
import com.dracknoval.domux.data.ResidentProfileUpdateRequest
import com.dracknoval.domux.data.ResidentialUnitData
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.UserData
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Todo lo que «Mi perfil» necesita para dibujarse (HU-019). */
data class ResidentProfileUiState(
    val user: UserData? = null,
    val unit: ResidentialUnitData? = null,
    // Lo que el residente está escribiendo; se guarda con «Guardar cambios».
    val email: String = "",
    val phone: String = "",
    // Lo que está mal en el teléfono después de tocar «Guardar cambios»; se borra al escribir.
    val phoneError: String? = null,
    val socialNetworks: String = "",
    val loading: Boolean = true,
    val busy: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false
)

/**
 * ViewModel de «Mi perfil» (HU-019): carga los datos del residente y de su hogar, y guarda lo
 * único que él puede cambiar (correo, teléfono y redes sociales). Lo demás lo cambia la
 * administración por una PQRS.
 */
class ResidentProfileViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(ResidentProfileUiState())
    val state: StateFlow<ResidentProfileUiState> = _state.asStateFlow()

    init {
        load()
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

    fun onEmail(value: String) {
        _state.update { it.copy(email = value) }
    }

    fun onPhone(value: String) {
        _state.update { it.copy(phone = value, phoneError = null) }
    }

    fun onSocialNetworks(value: String) {
        _state.update { it.copy(socialNetworks = value) }
    }

    fun load() {
        viewModelScope.launch {
            _state.update { it.copy(loading = true) }
            val profile = attempt("No se pudo cargar el perfil") { api.getProfile(auth()) }?.body()?.user
            if (profile != null) {
                _state.update {
                    it.copy(
                        user = profile,
                        email = profile.email.orEmpty(),
                        phone = profile.phone.orEmpty(),
                        socialNetworks = profile.socialNetworks.orEmpty()
                    )
                }
                val unit = attempt("No se pudo cargar la información del hogar") { api.getMyUnit(auth()) }?.body()?.unit
                if (unit != null) _state.update { it.copy(unit = unit) }
            }
            _state.update { it.copy(loading = false) }
        }
    }

    fun save() {
        val current = _state.value
        phoneProblem(current.phone)?.let { problem ->
            _state.update { it.copy(phoneError = problem) }
            showError(problem)
            return
        }
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudo guardar el perfil") {
                    api.updateProfile(
                        auth(),
                        ResidentProfileUpdateRequest(
                            phone = phoneToSend(current.phone),
                            email = current.email.trim(),
                            socialNetworks = current.socialNetworks.trim()
                        )
                    )
                }
            } ?: return@launch
            response.body()?.user?.let { saved -> _state.update { it.copy(user = saved) } }
            showSuccess("Tus datos quedaron guardados.")
        }
    }
}
