package bb.edu.cimh.sia.data

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/**
 * The parts of docs/api/identity.openapi.yaml the app uses (LoginResponse, Account, Problem). Unknown fields are
 * ignored, so the server can add fields without breaking older app versions.
 */
@Serializable
data class LoginRequest(
    val email: String,
    val password: String,
    val totp: String? = null,
    val client: String = "mobile",
)

@Serializable
data class RefreshRequest(val refreshToken: String)

@Serializable
data class Account(
    val id: String,
    val firstname: String,
    val lastname: String,
    val email: String,
    val role: String,
    val status: String,
    val isCimh: Boolean = false,
    val mfaEnabled: Boolean = false,
    val version: Int = 1,
    val organisationName: String? = null,
) {
    val isStaff: Boolean get() = role == "staff" || role == "admin"
    val displayName: String get() = "$firstname $lastname".trim()
}

@Serializable
data class LoginResponse(
    val account: Account,
    val accessToken: String? = null,
    val refreshToken: String? = null,
    val expiresIn: Int = 900,
)

/** RFC 9457 problem body (API README §4). */
@Serializable
data class Problem(
    val status: Int = 0,
    val code: String? = null,
    val title: String? = null,
    val detail: String? = null,
)

val ApiJson = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    encodeDefaults = true
}
