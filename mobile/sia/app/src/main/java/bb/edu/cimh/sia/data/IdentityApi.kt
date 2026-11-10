package bb.edu.cimh.sia.data

import kotlinx.serialization.Serializable
import kotlinx.serialization.serializer
import okhttp3.OkHttpClient
import okhttp3.Request

/**
 * identity-svc over HTTPS (`/api/identity/v1`). Mobile clients send `client: "mobile"` and get the tokens in the
 * body instead of cookies (identity.openapi.yaml LoginResponse); every other call uses `Authorization: Bearer`.
 */
class IdentityApi(baseUrl: String, client: OkHttpClient) {
    private val api = ApiClient(baseUrl, "identity", client)

    suspend fun login(body: LoginRequest): LoginResponse =
        api.post(api.url("auth/login"), body, serializer(), serializer())

    suspend fun refresh(refreshToken: String): LoginResponse =
        api.post(api.url("auth/refresh"), RefreshRequest(refreshToken), serializer(), serializer())

    suspend fun logout(accessToken: String) {
        val req = Request.Builder().url(api.url("auth/logout"))
            .header("Authorization", "Bearer $accessToken").post(ApiClient.EMPTY).build()
        api.execute(req) { }
    }

    /** Uses whatever auth the client adds (the session's bearer interceptor). */
    suspend fun me(): Account = api.get(api.url("me"), serializer())

    /** Issue to a person: active accounts by name or email prefix (staff read access, as the SIA web PersonPicker). */
    suspend fun findPeople(q: String): List<Person> =
        api.get(api.url("admin/accounts", "q" to q, "status" to "ACTIVE", "limit" to "20"), serializer<PersonPage>()).items
}

@Serializable
data class Person(
    val id: String,
    val firstname: String,
    val lastname: String,
    val email: String,
    val organisationName: String? = null,
) {
    val name: String get() = "$firstname $lastname".trim()
}

@Serializable
data class PersonPage(val items: List<Person> = emptyList())
