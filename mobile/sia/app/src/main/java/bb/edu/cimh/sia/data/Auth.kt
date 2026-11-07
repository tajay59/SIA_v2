package bb.edu.cimh.sia.data

import kotlinx.coroutines.runBlocking
import okhttp3.Authenticator
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.Route
import java.util.concurrent.TimeUnit

/** Adds `Authorization: Bearer <access>` to every call that doesn't set its own. */
class BearerInterceptor(private val session: SessionManager) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val req = chain.request()
        val token = session.accessToken
        if (token == null || req.header("Authorization") != null) return chain.proceed(req)
        return chain.proceed(req.newBuilder().header("Authorization", "Bearer $token").build())
    }
}

/**
 * On 401 (expired access token) refresh once and retry the call with the new token. A second 401 for the same
 * call, or a refused refresh, gives up (the session state then shows the login screen).
 */
class RefreshAuthenticator(private val session: SessionManager) : Authenticator {
    override fun authenticate(route: Route?, response: Response): Request? {
        if (response.priorResponse != null) return null
        val sent = response.request.header("Authorization")?.removePrefix("Bearer ") ?: return null
        val fresh = runBlocking { session.refresh(stale = sent) } ?: return null
        return response.request.newBuilder().header("Authorization", "Bearer $fresh").build()
    }
}

fun baseHttpClient(): OkHttpClient = OkHttpClient.Builder()
    .connectTimeout(10, TimeUnit.SECONDS)
    .readTimeout(20, TimeUnit.SECONDS)
    .build()

fun authedHttpClient(base: OkHttpClient, session: SessionManager): OkHttpClient = base.newBuilder()
    .addInterceptor(BearerInterceptor(session))
    .authenticator(RefreshAuthenticator(session))
    .build()
