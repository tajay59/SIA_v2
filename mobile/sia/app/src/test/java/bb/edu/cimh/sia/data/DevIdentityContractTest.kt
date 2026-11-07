package bb.edu.cimh.sia.data

import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test

/**
 * The same session code against a real identity-svc (the dev stack), so the DTOs and the token flow are checked
 * against the server, not only against the mock. Runs only when SIA_DEV_IDENTITY is set, e.g.
 *   SIA_DEV_IDENTITY=http://localhost:18001 SIA_DEV_STAFF=s@cimh.edu.bb SIA_DEV_CUSTOMER=c@cimh.edu.bb \
 *   SIA_DEV_PASSWORD=... ./gradlew testDebugUnitTest --tests '*DevIdentityContractTest'
 * (accounts made like tests/e2e-web/support.ts does).
 */
class DevIdentityContractTest {
    private val base = System.getenv("SIA_DEV_IDENTITY")

    private fun env(name: String): String = System.getenv(name) ?: error("$name is not set")

    @Test
    fun `login, refresh rotation, staff-only and logout against the dev identity`() = runBlocking {
        assumeTrue("SIA_DEV_IDENTITY not set", base != null)
        val http = baseHttpClient()
        val store = InMemoryTokenStore()
        val session = SessionManager(IdentityApi(base!!, http), store)
        val user = IdentityApi(base, authedHttpClient(http, session))

        val r = session.login(env("SIA_DEV_STAFF"), env("SIA_DEV_PASSWORD"), null)
        assertTrue("login: $r", r is LoginResult.Success)
        assertEquals(env("SIA_DEV_STAFF"), user.me().email)

        // Force a refresh as if the access token had expired: the refresh token must rotate.
        val firstRefresh = store.load()
        val fresh = session.refresh(stale = session.accessToken)
        assertTrue(fresh != null)
        assertNotEquals(firstRefresh, store.load())
        assertEquals("staff", user.me().role)

        // The old refresh token is now spent: using it again is reuse and ends the session server-side.
        val reuse = runCatching { IdentityApi(base, http).refresh(firstRefresh!!) }.exceptionOrNull()
        assertTrue("reuse: $reuse", reuse is ApiException && reuse.status == 401)

        assertEquals(LoginResult.StaffOnly, session.login(env("SIA_DEV_CUSTOMER"), env("SIA_DEV_PASSWORD"), null))
        assertEquals(
            LoginResult.Failed("Email or password is incorrect."),
            session.login(env("SIA_DEV_STAFF"), "not the password at all", null),
        )
    }
}
