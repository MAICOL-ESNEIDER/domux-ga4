package com.dracknoval.domux.data

import android.content.Context
import android.util.Base64
import android.util.Log
import org.json.JSONObject
import java.security.GeneralSecurityException
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties

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

    fun persist(context: Context) {
        val payload = JSONObject()
            .put("token", token)
            .put("userId", userId)
            .put("userName", userName)
            .put("lastName", lastName)
            .put("email", email)
            .put("role", role)
            .put("apartment", apartment)
            .toString()
        SessionStorage.write(context, payload)
    }

    fun restore(context: Context): Boolean {
        val payload = try {
            SessionStorage.read(context)
        } catch (exception: GeneralSecurityException) {
            Log.e("DomuxSession", "Stored session could not be decrypted.", exception)
            SessionStorage.clear(context)
            null
        } catch (exception: IllegalArgumentException) {
            Log.e("DomuxSession", "Stored session data is malformed.", exception)
            SessionStorage.clear(context)
            null
        }
        if (payload.isNullOrBlank()) return false
        return try {
            val session = JSONObject(payload)
            token = session.optString("token").takeIf { it.isNotBlank() }
            userId = session.optInt("userId").takeIf { it > 0 }
            userName = session.optString("userName").takeIf { it.isNotBlank() }
            lastName = session.optString("lastName").takeIf { it.isNotBlank() }
            email = session.optString("email").takeIf { it.isNotBlank() }
            role = session.optString("role").takeIf { it.isNotBlank() }
            apartment = session.optString("apartment").takeIf { it.isNotBlank() }
            if (token != null && userId != null && role != null) true else {
                clear()
                SessionStorage.clear(context)
                false
            }
        } catch (exception: org.json.JSONException) {
            Log.e("DomuxSession", "Stored session JSON is invalid.", exception)
            clear()
            SessionStorage.clear(context)
            false
        }
    }

    fun clear() {
        token = null
        userId = null
        userName = null
        lastName = null
        email = null
        role = null
        apartment = null
    }

    fun clear(context: Context) {
        clear()
        SessionStorage.clear(context)
    }

    fun updateFrom(user: UserData) {
        userId = user.id
        userName = user.name
        lastName = user.lastName
        email = user.email
        role = user.role
        apartment = user.apartment
    }
}

private object SessionStorage {
    private const val preferencesName = "domux_secure_session"
    private const val sessionKey = "encrypted_session"
    private const val keyAlias = "domux_session_aes_key"
    private const val gcmTagBits = 128

    fun write(context: Context, value: String) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        val encrypted = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        val encoded = Base64.encodeToString(cipher.iv + encrypted, Base64.NO_WRAP)
        check(
            context.getSharedPreferences(preferencesName, Context.MODE_PRIVATE)
                .edit().putString(sessionKey, encoded).commit()
        ) { "Could not persist encrypted session." }
    }

    fun read(context: Context): String? {
        val encoded = context.getSharedPreferences(preferencesName, Context.MODE_PRIVATE)
            .getString(sessionKey, null) ?: return null
        val payload = Base64.decode(encoded, Base64.NO_WRAP)
        val ivLength = 12
        require(payload.size > ivLength) { "Encrypted session is truncated." }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(
            Cipher.DECRYPT_MODE,
            getOrCreateKey(),
            GCMParameterSpec(gcmTagBits, payload.copyOfRange(0, ivLength))
        )
        return String(cipher.doFinal(payload.copyOfRange(ivLength, payload.size)), Charsets.UTF_8)
    }

    fun clear(context: Context) {
        check(
            context.getSharedPreferences(preferencesName, Context.MODE_PRIVATE)
                .edit().remove(sessionKey).commit()
        ) { "Could not clear encrypted session." }
    }

    private fun getOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val existing = keyStore.getKey(keyAlias, null) as? SecretKey
        if (existing != null) return existing
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
