package bb.edu.cimh.sia.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.KSerializer
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

/**
 * One v2 service (`<base>/api/<service>/v1/`). Errors become [ApiException] (problem+json, API README §4) or
 * [NetworkException]. Auth is whatever the [client] adds (the session's bearer interceptor for user calls).
 */
class ApiClient(baseUrl: String, service: String, val client: OkHttpClient) {
    val base: HttpUrl = "${baseUrl.trimEnd('/')}/api/$service/v1/".toHttpUrl()

    fun url(path: String, vararg query: Pair<String, String?>): HttpUrl {
        val b = base.resolve(path)!!.newBuilder()
        for ((k, v) in query) if (v != null) b.addQueryParameter(k, v)
        return b.build()
    }

    /** Path segments that come from scans (barcodes) must be encoded, never pasted into the path. */
    fun url(segments: List<String>, vararg query: Pair<String, String?>): HttpUrl {
        val b = base.newBuilder()
        segments.forEach { b.addPathSegment(it) }
        for ((k, v) in query) if (v != null) b.addQueryParameter(k, v)
        return b.build()
    }

    suspend fun <T> get(url: HttpUrl, out: KSerializer<T>): T =
        execute(Request.Builder().url(url).get().build()) { decode(it, out) }

    suspend fun <I, T> post(
        url: HttpUrl,
        body: I,
        input: KSerializer<I>,
        out: KSerializer<T>,
        headers: Map<String, String> = emptyMap(),
    ): T {
        val json = ApiJson.encodeToString(input, body).toRequestBody(JSON)
        val req = Request.Builder().url(url).post(json)
        headers.forEach { (k, v) -> req.header(k, v) }
        return execute(req.build()) { decode(it, out) }
    }

    suspend fun <T> execute(request: Request, read: (Response) -> T): T = withContext(Dispatchers.IO) {
        try {
            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) throw problemOf(response)
                read(response)
            }
        } catch (e: IOException) {
            throw NetworkException(e)
        }
    }

    private fun <T> decode(response: Response, s: KSerializer<T>): T = ApiJson.decodeFromString(s, response.body.string())

    private fun problemOf(response: Response): ApiException {
        val text = runCatching { response.body.string() }.getOrDefault("")
        val p = runCatching { ApiJson.decodeFromString(Problem.serializer(), text) }.getOrNull()
        return ApiException(response.code, p?.code, p?.detail ?: p?.title ?: "Request failed (${response.code})")
    }

    companion object {
        val JSON = "application/json".toMediaType()
        val EMPTY: RequestBody = ByteArray(0).toRequestBody(null)
    }
}
