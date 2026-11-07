package bb.edu.cimh.sia.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.core.content.edit
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Where the refresh token lives between app starts. The access token stays in memory only. */
interface TokenStore {
    fun load(): String?
    fun save(refreshToken: String)
    fun clear()
}

class InMemoryTokenStore(private var token: String? = null) : TokenStore {
    override fun load(): String? = token
    override fun save(refreshToken: String) {
        token = refreshToken
    }
    override fun clear() {
        token = null
    }
}

/**
 * Refresh token sealed with an AES-256-GCM key that never leaves the Android Keystore (P8, TR-SEC-11). Only the
 * ciphertext is in SharedPreferences, which is excluded from backups (data_extraction_rules.xml). If the key is
 * gone (app data cleared, device restored), the token can't be opened and the user simply logs in again.
 */
class KeystoreTokenStore(context: Context) : TokenStore {
    private val prefs = context.getSharedPreferences("session", Context.MODE_PRIVATE)

    override fun load(): String? {
        val sealed = prefs.getString(KEY_TOKEN, null) ?: return null
        return runCatching {
            val raw = Base64.decode(sealed, Base64.NO_WRAP)
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, raw, 0, IV_BYTES))
            String(cipher.doFinal(raw, IV_BYTES, raw.size - IV_BYTES), Charsets.UTF_8)
        }.getOrElse {
            clear()
            null
        }
    }

    override fun save(refreshToken: String) {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val sealed = cipher.iv + cipher.doFinal(refreshToken.toByteArray(Charsets.UTF_8))
        prefs.edit { putString(KEY_TOKEN, Base64.encodeToString(sealed, Base64.NO_WRAP)) }
    }

    override fun clear() {
        prefs.edit { remove(KEY_TOKEN) }
    }

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        (ks.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE)
        gen.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return gen.generateKey()
    }

    private companion object {
        const val KEYSTORE = "AndroidKeyStore"
        const val ALIAS = "sia.refresh-token"
        const val KEY_TOKEN = "refresh"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val IV_BYTES = 12
    }
}
