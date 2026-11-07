package bb.edu.cimh.sia.data

import kotlinx.coroutines.runBlocking
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class SessionManagerTest {
    private val server = MockWebServer()
    private lateinit var store: InMemoryTokenStore
    private lateinit var session: SessionManager
    private lateinit var userApi: IdentityApi

    @Before
    fun setUp() {
        server.start()
        val base = server.url("/").toString()
        val http = baseHttpClient()
        store = InMemoryTokenStore()
        session = SessionManager(IdentityApi(base, http), store)
        userApi = IdentityApi(base, authedHttpClient(http, session))
    }

    @After
    fun tearDown() = server.close()

    private fun account(role: String = "staff", mfa: Boolean = false) =
        """{"id":"USR1","firstname":"Sam","lastname":"Staff","email":"s@cimh.edu.bb","role":"$role",
           "status":"ACTIVE","isCimh":true,"mfaEnabled":$mfa,"version":3,"newField":"ignored"}"""

    private fun tokens(access: String, refresh: String, role: String = "staff", mfa: Boolean = false) =
        json(200, """{"account":${account(role, mfa)},"accessToken":"$access","refreshToken":"$refresh","expiresIn":900}""")

    private fun problem(status: Int, code: String, detail: String = "nope") =
        MockResponse.Builder().code(status).addHeader("Content-Type", "application/problem+json")
            .body("""{"status":$status,"code":"$code","title":"t","detail":"$detail"}""").build()

    private fun json(status: Int, body: String) =
        MockResponse.Builder().code(status).addHeader("Content-Type", "application/json").body(body).build()

    private fun noContent() = MockResponse.Builder().code(204).build()

    @Test
    fun `staff login keeps the session and stores only the refresh token`() = runBlocking {
        server.enqueue(tokens("A1", "R1"))
        val r = session.login(" s@cimh.edu.bb ", "pw", null)
        assertTrue(r is LoginResult.Success)
        assertEquals("R1", store.load())
        assertEquals("A1", session.accessToken)
        assertTrue(session.state.value is SessionState.SignedIn)
        val sent = server.takeRequest()
        assertEquals("/api/identity/v1/auth/login", sent.url.encodedPath)
    }

    @Test
    fun `admin with MFA is asked for the code`() = runBlocking {
        server.enqueue(problem(403, "MFA_REQUIRED"))
        assertEquals(LoginResult.CodeNeeded, session.login("a@cimh.edu.bb", "pw", null))
        server.enqueue(problem(401, "MFA_INVALID"))
        assertEquals(LoginResult.CodeInvalid, session.login("a@cimh.edu.bb", "pw", "000000"))
        server.enqueue(tokens("A1", "R1", role = "admin", mfa = true))
        assertTrue(session.login("a@cimh.edu.bb", "pw", "123456") is LoginResult.Success)
    }

    @Test
    fun `customers are refused and their session is closed at once`() = runBlocking {
        server.enqueue(tokens("A1", "R1", role = "user"))
        server.enqueue(noContent())
        assertEquals(LoginResult.StaffOnly, session.login("c@met.bb", "pw", null))
        server.takeRequest()
        val logout = server.takeRequest()
        assertEquals("/api/identity/v1/auth/logout", logout.url.encodedPath)
        assertEquals("Bearer A1", logout.headers["Authorization"])
        assertNull(store.load())
        assertEquals(SessionState.Unknown, session.state.value)
    }

    @Test
    fun `admin without MFA must set it up on the web first`() = runBlocking {
        server.enqueue(tokens("A1", "R1", role = "admin", mfa = false))
        server.enqueue(noContent())
        assertEquals(LoginResult.MfaSetupRequired, session.login("a@cimh.edu.bb", "pw", null))
        assertNull(store.load())
    }

    @Test
    fun `wrong password and offline give readable messages`() = runBlocking {
        server.enqueue(problem(401, "INVALID_CREDENTIALS"))
        assertEquals(LoginResult.Failed("Email or password is incorrect."), session.login("s@cimh.edu.bb", "x", null))
        server.close()
        assertEquals(LoginResult.Failed(SessionManager.OFFLINE), session.login("s@cimh.edu.bb", "x", null))
    }

    @Test
    fun `expired access token is refreshed once and the call retried`() = runBlocking {
        server.enqueue(tokens("A1", "R1"))
        session.login("s@cimh.edu.bb", "pw", null)
        server.takeRequest()

        server.enqueue(problem(401, "TOKEN_EXPIRED"))
        server.enqueue(tokens("A2", "R2"))
        server.enqueue(json(200, account()))
        val me = userApi.me()
        assertEquals("USR1", me.id)

        assertEquals("Bearer A1", server.takeRequest().headers["Authorization"])
        val refresh = server.takeRequest()
        assertEquals("/api/identity/v1/auth/refresh", refresh.url.encodedPath)
        assertEquals("Bearer A2", server.takeRequest().headers["Authorization"])
        assertEquals("R2", store.load()) // rotated
    }

    @Test
    fun `refused refresh ends the session and forgets the token`() = runBlocking {
        server.enqueue(tokens("A1", "R1"))
        session.login("s@cimh.edu.bb", "pw", null)

        server.enqueue(problem(401, "TOKEN_EXPIRED"))
        server.enqueue(problem(401, "TOKEN_REUSE"))
        val failed = runCatching { userApi.me() }.exceptionOrNull()
        assertTrue(failed is ApiException && failed.status == 401)
        assertEquals(SessionState.Ended(SessionManager.ENDED), session.state.value)
        assertNull(store.load())
        assertNull(session.accessToken)
    }

    @Test
    fun `app start resumes a stored session`() = runBlocking {
        store.save("R0")
        server.enqueue(tokens("A1", "R1"))
        session.restore()
        assertTrue(session.state.value is SessionState.SignedIn)
        assertEquals("R1", store.load())
    }

    @Test
    fun `app start without a token shows login`() = runBlocking {
        session.restore()
        assertEquals(SessionState.SignedOut, session.state.value)
    }

    @Test
    fun `logout forgets everything even when the server is unreachable`() = runBlocking {
        server.enqueue(tokens("A1", "R1"))
        session.login("s@cimh.edu.bb", "pw", null)
        server.close()
        session.logout()
        assertEquals(SessionState.SignedOut, session.state.value)
        assertNull(store.load())
    }
}
