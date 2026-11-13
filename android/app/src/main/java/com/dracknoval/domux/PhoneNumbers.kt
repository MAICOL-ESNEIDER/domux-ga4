package com.dracknoval.domux

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType

/**
 * Los teléfonos de Colombia, con la misma regla del servidor: 10 números (un celular empieza por 3
 * y un fijo por 60) y el indicativo +57 al inicio si la persona lo escribe. Se guardan solo los
 * números: «+57 300 123 4567» queda «3001234567».
 */
internal const val PHONE_HINT = "10 números. Puedes escribir +57 al inicio."

private val phoneText = Regex("""\+?[\d\s().-]+""")

/** Los 10 números del teléfono, "" si está vacío o null si no es un teléfono de Colombia. */
internal fun colombianPhoneDigits(value: String): String? {
    val text = value.trim()
    if (text.isEmpty()) return ""
    if (text.length > 30 || !phoneText.matches(text)) return null
    var digits = text.filter(Char::isDigit)
    if (text.startsWith("+")) {
        if (!digits.startsWith("57")) return null
        digits = digits.drop(2)
    } else if (digits.length == 12 && digits.startsWith("57")) {
        digits = digits.drop(2)
    }
    return digits.takeIf { it.length == 10 && (it.startsWith("3") || it.startsWith("60")) }
}

/** Lo que está mal en el teléfono, en palabras, o null si está bien (o vacío). */
internal fun phoneProblem(value: String, label: String = "El teléfono"): String? {
    val text = value.trim()
    if (colombianPhoneDigits(text) != null) return null
    if (text.startsWith("+") && !text.filter(Char::isDigit).startsWith("57")) {
        return "Solo se aceptan teléfonos de Colombia (+57)."
    }
    return "$label debe tener 10 números: un celular empieza por 3 y un fijo por 60. Puedes escribir +57 al inicio."
}

/** El teléfono listo para enviar: solo sus números si es válido; si no, tal cual (el servidor dice el error). */
internal fun phoneToSend(value: String): String = colombianPhoneDigits(value) ?: value.trim()

/**
 * Campo de teléfono: abre el teclado de números y dice la regla debajo. Si llega [error], el campo
 * se marca en rojo y lo dice en lugar de la regla.
 */
@Composable
internal fun DomuxPhoneField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String = "Teléfono",
    error: String? = null,
    modifier: Modifier = Modifier
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        singleLine = true,
        isError = error != null,
        supportingText = { Text(error ?: PHONE_HINT) },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone, imeAction = ImeAction.Next),
        modifier = modifier.fillMaxWidth()
    )
}
