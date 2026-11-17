// RecentAccounts.kt — «Cuentas recientes en este celular» del inicio de sesión (HU-001).
// Solo guarda lo que la persona pidió recordar al entrar: el correo y el nombre, cifrados con una
// llave que vive en el celular. Nunca la contraseña.

package com.dracknoval.domux.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Una cuenta recordada en este celular: solo el correo y el nombre. */
data class RecentAccount(val email: String, val name: String) {
    /** El nombre que se muestra: si no hay nombre, la parte del correo antes de la @. */
    val displayName: String get() = name.ifBlank { email.substringBefore("@") }

    /** Las iniciales del círculo de la lista: «Laura Restrepo Gil» → «LR». */
    val initials: String
        get() {
            val words = displayName.split(Regex("[\\s._-]+")).filter { it.isNotBlank() }
            val letters = when {
                words.size > 1 -> "${words[0].first()}${words[1].first()}"
                words.size == 1 -> words[0].take(2)
                else -> ""
            }
            return letters.uppercase()
        }
}

/**
 * Las reglas de la lista, sin nada de Android: la cuenta más reciente va de primera, el mismo correo
 * no se repite (sin importar mayúsculas) y caben como máximo [MAX_ACCOUNTS].
 */
object RecentAccountsRules {
    const val MAX_ACCOUNTS = 5

    fun remember(list: List<RecentAccount>, account: RecentAccount): List<RecentAccount> =
        (listOf(account) + forget(list, account.email)).take(MAX_ACCOUNTS)

    fun forget(list: List<RecentAccount>, email: String): List<RecentAccount> =
        list.filterNot { it.email.equals(email, ignoreCase = true) }

    /** «Deshacer»: la cuenta quitada vuelve al mismo puesto que tenía. */
    fun restore(list: List<RecentAccount>, account: RecentAccount, index: Int): List<RecentAccount> {
        val rest = forget(list, account.email)
        val position = index.coerceIn(0, rest.size)
        return (rest.take(position) + account + rest.drop(position)).take(MAX_ACCOUNTS)
    }
}

/**
 * Guarda la lista cifrada con su propia llave del AndroidKeyStore (distinta de la de la sesión).
 * Cerrar sesión no la borra: cada cuenta se quita con su X en el inicio de sesión.
 *
 * Es una comodidad, no algo necesario para entrar: si el celular no deja leer o guardar la lista
 * (llave perdida, datos dañados), la lista se borra completa y el ingreso sigue como siempre, con
 * el correo escrito a mano. Por eso aquí se atrapa cualquier error y no solo los de cifrado.
 */
object RecentAccountsStore {
    private const val TAG = "DomuxCuentas"
    private const val preferencesName = "domux_cuentas_recientes"
    private const val valueKey = "encrypted_accounts"
    private const val keyAlias = "domux_accounts_aes_key"
    private const val gcmTagBits = 128
    private const val ivLength = 12

    fun read(context: Context): List<RecentAccount> {
        val encoded = preferences(context).getString(valueKey, null) ?: return emptyList()
        return try {
            parse(decrypt(encoded))
        } catch (exception: Exception) {
            Log.w(TAG, "La lista de cuentas no se pudo leer; se borra.", exception)
            clear(context)
            emptyList()
        }
    }

    /** Pone la cuenta de primera y devuelve cómo quedó la lista. */
    fun remember(context: Context, account: RecentAccount): List<RecentAccount> =
        save(context, RecentAccountsRules.remember(read(context), account))

    /** Quita la cuenta de este celular y devuelve cómo quedó la lista. */
    fun forget(context: Context, email: String): List<RecentAccount> =
        save(context, RecentAccountsRules.forget(read(context), email))

    /** Vuelve a poner una cuenta quitada en el puesto que tenía. */
    fun restore(context: Context, account: RecentAccount, index: Int): List<RecentAccount> =
        save(context, RecentAccountsRules.restore(read(context), account, index))

    private fun save(context: Context, accounts: List<RecentAccount>): List<RecentAccount> {
        if (accounts.isEmpty()) {
            clear(context)
            return accounts
        }
        return try {
            preferences(context).edit().putString(valueKey, encrypt(toJson(accounts))).apply()
            accounts
        } catch (exception: Exception) {
            // Si no se puede guardar lo que se pidió (por ejemplo, después de quitar una cuenta),
            // no queda nada guardado: es mejor volver a escribir el correo que conservar de más.
            Log.w(TAG, "No se pudo guardar la lista de cuentas; se borra.", exception)
            clear(context)
            emptyList()
        }
    }

    private fun clear(context: Context) {
        preferences(context).edit().remove(valueKey).apply()
    }

    private fun preferences(context: Context) =
        context.getSharedPreferences(preferencesName, Context.MODE_PRIVATE)

    private fun toJson(accounts: List<RecentAccount>): String {
        val array = JSONArray()
        accounts.forEach { array.put(JSONObject().put("correo", it.email).put("nombre", it.name)) }
        return array.toString()
    }

    private fun parse(json: String): List<RecentAccount> {
        val array = JSONArray(json)
        return (0 until array.length())
            .mapNotNull { index -> array.optJSONObject(index) }
            .map { RecentAccount(it.optString("correo").trim(), it.optString("nombre").trim()) }
            .filter { it.email.contains("@") }
            .take(RecentAccountsRules.MAX_ACCOUNTS)
    }

    private fun encrypt(value: String): String {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        val encrypted = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        return Base64.encodeToString(cipher.iv + encrypted, Base64.NO_WRAP)
    }

    private fun decrypt(encoded: String): String {
        val payload = Base64.decode(encoded, Base64.NO_WRAP)
        require(payload.size > ivLength) { "La lista cifrada está incompleta." }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(
            Cipher.DECRYPT_MODE,
            getOrCreateKey(),
            GCMParameterSpec(gcmTagBits, payload.copyOfRange(0, ivLength))
        )
        return String(cipher.doFinal(payload.copyOfRange(ivLength, payload.size)), Charsets.UTF_8)
    }

    private fun getOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(keyAlias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                keyAlias,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            ).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build()
        )
        return generator.generateKey()
    }
}
