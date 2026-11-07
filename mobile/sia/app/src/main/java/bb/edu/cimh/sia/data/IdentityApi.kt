package bb.edu.cimh.sia.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.KSerializer
import kotlinx.serialization.serializer
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException

/** The server answered with an error (problem+json). */
class ApiException(val status: Int, val code: String?, message: String) : Exception(message)

/** No answer: offline, DNS, TLS (including a pin mismatch) or timeout. */
class NetworkException(cause: IOException) : Exception(cause.message, cause)

private val JSON = "application/json".toMediaType()

/**
 * identity-svc over HTTPS (`/api/identity/v1`). Mobile clients send `client: "mobile"` and get the tokens in the
 * body instead of cookies (identity.openapi.yaml LoginResponse); every other call uses `Authorization: Bearer`.
 */
class IdentityApi(baseUrl: String, private val client: OkHttpClient) {
    private val base: HttpUrl = "${baseUrl.trimEnd('/')}/api/identity/v1/".toHttpUrl()

    suspend fun login(body: LoginRequest): LoginResponse = post("auth/login", body)

    suspend fun refresh(refreshToken: String): LoginResponse = post("auth/refresh", RefreshRequest(refreshToken))

    suspend fun logout(accessToken: String) {
        execute(request("auth/logout").header("Authorization", "Bearer $accessToken").post(EMPTY).build()) { }
    }

    /** Uses whatever auth the client adds (the session's bearer interceptor). */
    suspend fun me(): Account = execute(request("me").get().build()) { decode(it, serializer<Account>()) }

    private suspend inline fun <reified In, reified Out> post(path: String, body: In): Out {
        val json = ApiJson.encodeToString(serializer<In>(), body).toRequestBody(JSON)
        return execute(request(path).post(json).build()) { decode(it, serializer<Out>()) }
    }

    private fun request(path: String): Request.Builder = Request.Builder().url(base.resolve(path)!!)

    private fun <T> decode(response: Response, s: KSerializer<T>): T = ApiJson.decodeFromString(s, response.body.string())

    private suspend fun <T> execute(request: Request, read: (Response) -> T): T = withContext(Dispatchers.IO) {
        try {
            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) throw problemOf(response)
                read(response)
            }
        } catch (e: IOException) {
            throw NetworkException(e)
        }
    }

    private fun problemOf(response: Response): ApiException {
        val text = runCatching { response.body.string() }.getOrDefault("")
        val p = runCatching { ApiJson.decodeFromString(Problem.serializer(), text) }.getOrNull()
        return ApiException(response.code, p?.code, p?.detail ?: p?.title ?: "Request failed (${response.code})")
    }

    private companion object {
        val EMPTY: RequestBody = ByteArray(0).toRequestBody(null)
    }
}
