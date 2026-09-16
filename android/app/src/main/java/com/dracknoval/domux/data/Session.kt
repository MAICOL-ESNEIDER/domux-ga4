// Session.kt — guarda EN MEMORIA los datos de la sesión activa (token, nombre, rol),
// para no tener que pasarlos a mano entre pantallas. "object" = una única copia global.
// Mismo patrón de GA2, extendido a 3 roles en vez de un simple booleano isAdmin.

package com.dracknoval.domux.data

object Session {
    var token: String? = null
    var userId: Int? = null
    var userName: String? = null
    var role: String? = null          // "ADMIN" | "RESIDENT" | "GUARD"
    var apartment: String? = null     // solo tiene valor si role == "RESIDENT"

    // Los tres helpers que usan las pantallas para decidir qué mostrar
    // (mismo espíritu del "if (Session.isAdmin)" de la GA3, ahora con 3 roles).
    val isAdmin: Boolean get() = role == "ADMIN"
    val isResident: Boolean get() = role == "RESIDENT"
    val isGuard: Boolean get() = role == "GUARD"

    // El backend exige el encabezado "Authorization: Bearer <token>" en las rutas
    // protegidas. Este método arma ese texto ya listo para enviar.
    fun bearer(): String = token?.let { "Bearer $it" } ?: ""

    // Borra la sesión (se usa al cerrar sesión).
    fun clear() {
        token = null
        userId = null
        userName = null
        role = null
        apartment = null
    }
}
