package com.dracknoval.domux.data

object Session {
    var token: String? = null
    var userId: Int? = null
    var userName: String? = null
    var lastName: String? = null
    var email: String? = null
    var role: String? = null
    var apartment: String? = null

    val isAdmin: Boolean get() = role == "ADMIN"
    val isResident: Boolean get() = role == "RESIDENT"
    val isGuard: Boolean get() = role == "GUARD"

    fun bearer(): String = token?.let { "Bearer ".plus(it) } ?: ""

    fun clear() {
        token = null
        userId = null
        userName = null
        lastName = null
        email = null
        role = null
        apartment = null
    }
}
