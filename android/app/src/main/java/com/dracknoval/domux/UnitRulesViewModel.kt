package com.dracknoval.domux

import androidx.lifecycle.viewModelScope
import com.dracknoval.domux.data.RetrofitClient
import com.dracknoval.domux.data.UnitRulesView
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Los tipos de PQRS que pueden tener su propio plazo (los mismos del servidor). */
val pqrsTermCategories = listOf("Petición", "Queja", "Reclamo", "Sugerencia", "Daño")

/** Todo lo que «Reglas de la unidad» necesita para dibujarse. */
data class UnitRulesUiState(
    val loading: Boolean = true,
    // Lo que está escrito en cada campo (texto, para poder dejarlo vacío mientras se escribe).
    val values: Map<String, String> = emptyMap(),
    val categoryValues: Map<String, String> = emptyMap(),
    // Lo que venía del servidor: sirve para enviar solo lo que cambió.
    val loadedValues: Map<String, String> = emptyMap(),
    val loadedCategories: Map<String, String> = emptyMap(),
    val defaults: Map<String, Int> = emptyMap(),
    val customized: Set<String> = emptySet(),
    val updatedLine: String? = null,
    val busy: Boolean = false,
    val message: String = "",
    val messageIsError: Boolean = false
) {
    val changed: Boolean get() = values != loadedValues || categoryValues != loadedCategories
}

/**
 * Reglas de la unidad en la app de administración: los mismos plazos y límites que se cambian en la web
 * (`/web/reglas`). Cada cambio rige desde que se guarda, en toda la app y la web.
 */
class UnitRulesViewModel : DomuxViewModel() {
    private val api = RetrofitClient.api
    private val _state = MutableStateFlow(UnitRulesUiState())
    val state: StateFlow<UnitRulesUiState> = _state.asStateFlow()

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

    fun load() {
        viewModelScope.launch {
            _state.update { it.copy(loading = true) }
            val response = attempt("No se pudieron cargar las reglas") { api.getUnitRules(auth()) }
            val view = response?.body()
            _state.update { current -> if (view == null) current.copy(loading = false) else apply(current, view) }
        }
    }

    fun setValue(key: String, text: String) {
        val digits = text.filter { it.isDigit() }.take(4)
        _state.update { it.copy(values = it.values + (key to digits)) }
    }

    fun setCategory(category: String, text: String) {
        val digits = text.filter { it.isDigit() }.take(3)
        _state.update { it.copy(categoryValues = it.categoryValues + (category to digits)) }
    }

    /** Pone en el campo el valor de DOMUX (se guarda cuando la persona toca «Guardar»). */
    fun useDefault(key: String) {
        val value = _state.value.defaults[key] ?: return
        setValue(key, value.toString())
    }

    fun save() {
        val current = _state.value
        val body = mutableMapOf<String, Any>()
        current.values.forEach { (key, text) ->
            if (text != current.loadedValues[key]) {
                val number = text.toIntOrNull()
                if (number == null) {
                    showError("Escribe un número en cada regla que cambies.")
                    return
                }
                body[key] = number
            }
        }
        if (current.categoryValues != current.loadedCategories) {
            body["pqrsTermsByCategory"] = current.categoryValues
                .filterValues { it.isNotBlank() }
                .mapValues { it.value.toInt() }
        }
        if (body.isEmpty()) {
            showError("No hay cambios para guardar.")
            return
        }
        viewModelScope.launch {
            val response = withBusy {
                attempt("No se pudieron guardar las reglas") { api.updateUnitRules(auth(), body) }
            } ?: return@launch
            val view = response.body()
            _state.update { if (view == null) it else apply(it, view) }
            showSuccess(view?.message ?: "Reglas de la unidad guardadas.")
        }
    }

    private fun apply(current: UnitRulesUiState, view: UnitRulesView): UnitRulesUiState {
        val rules = view.rules.orEmpty()
        val defaults = view.defaults.orEmpty()
        val values = rules.filterKeys { it != "pqrsTermsByCategory" }
            .mapValues { (it.value as? Number)?.toInt()?.toString().orEmpty() }
        val categories = mutableMapOf<String, String>()
        (rules["pqrsTermsByCategory"] as? Map<*, *>)?.forEach { (key, days) ->
            categories[key.toString()] = (days as? Number)?.toInt()?.toString().orEmpty()
        }
        val line = view.updatedAt?.let { moment ->
            "Último cambio: $moment" + (view.updatedByName?.let { " por $it" } ?: "")
        }
        return current.copy(
            loading = false,
            values = values,
            loadedValues = values,
            categoryValues = categories,
            loadedCategories = categories,
            defaults = defaults.filterKeys { it != "pqrsTermsByCategory" }
                .mapNotNull { (key, value) -> (value as? Number)?.toInt()?.let { key to it } }.toMap(),
            customized = view.customized.orEmpty().filterValues { it }.keys,
            updatedLine = line
        )
    }
}
