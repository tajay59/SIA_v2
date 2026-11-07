package bb.edu.cimh.sia.data

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

sealed interface SessionState {
    /** Start-up: a stored refresh token is being tried. */
    data object Unknown : SessionState
    data object SignedOut : SessionState
    data class SignedIn(val account: Account) : SessionState
    /** The server ended the session (refresh refused, account suspended, token reuse). */
    data class Ended(val message: String) : SessionState
}

sealed interface LoginResult {
    data class Success(val account: Account) : LoginResult
    /** Admin with MFA: ask for the 6-digit code and send the same request again with it. */
    data object CodeNeeded : LoginResult
    data object CodeInvalid : LoginResult
    /** Customers can't use SIA (APD §2 "staff only"). */
    data object StaffOnly : LoginResult
    /** Admin without MFA: everything but /me would be 403 MFA_REQUIRED (TR-AUTH-9). Set it up on SIA web. */
    data object MfaSetupRequired : LoginResult
    data class Failed(val message: String) : LoginResult
}

/**
 * M-01 session (APD §5, TAD security): access token in memory (15 min), refresh token in [TokenStore] (7 days,
 * rotated on every use; a reused one ends every session of the user server-side). Refreshes are single-flight:
 * concurrent 401s wait for one refresh and then all use the new token.
 */
class SessionManager(private val api: IdentityApi, private val store: TokenStore) {
    private val _state = MutableStateFlow<SessionState>(SessionState.Unknown)
    val state: StateFlow<SessionState> = _state.asStateFlow()

    @Volatile
    var accessToken: String? = null
        private set

    private val mutex = Mutex()

    /** App start: resume the stored session, or show the login screen. */
    suspend fun restore() {
        if (store.load() == null) {
            _state.value = SessionState.SignedOut
            return
        }
        when (refreshLocked(stale = null)) {
            is RefreshOutcome.Ok -> Unit
            is RefreshOutcome.Ended -> Unit
            // Offline at start-up: keep the token, try again on the next request or app start.
            RefreshOutcome.Offline -> _state.value = SessionState.Ended(OFFLINE)
        }
    }

    suspend fun login(email: String, password: String, totp: String?): LoginResult {
        val response = try {
            api.login(LoginRequest(email.trim(), password, totp?.takeIf { it.isNotBlank() }))
        } catch (e: ApiException) {
            return loginError(e)
        } catch (e: NetworkException) {
            return LoginResult.Failed(OFFLINE)
        }
        val access = response.accessToken
        val refresh = response.refreshToken
        if (access == null || refresh == null) return LoginResult.Failed("The server did not return a session.")
        val account = response.account
        when {
            !account.isStaff -> {
                runCatching { api.logout(access) }
                return LoginResult.StaffOnly
            }
            account.role == "admin" && !account.mfaEnabled -> {
                runCatching { api.logout(access) }
                return LoginResult.MfaSetupRequired
            }
        }
        accessToken = access
        store.save(refresh)
        _state.value = SessionState.SignedIn(account)
        return LoginResult.Success(account)
    }

    /**
     * Called by the authenticator after a 401 with [stale]. Returns the token to retry with, or null when the
     * session is over (the state then says why) or the network is down.
     */
    suspend fun refresh(stale: String?): String? =
        when (val r = refreshLocked(stale)) {
            is RefreshOutcome.Ok -> r.token
            else -> null
        }

    suspend fun logout() {
        val access = accessToken
        end(SessionState.SignedOut)
        if (access != null) runCatching { api.logout(access) }
    }

    private sealed interface RefreshOutcome {
        data class Ok(val token: String) : RefreshOutcome
        data object Ended : RefreshOutcome
        data object Offline : RefreshOutcome
    }

    private suspend fun refreshLocked(stale: String?): RefreshOutcome = mutex.withLock {
        val current = accessToken
        if (current != null && current != stale) return RefreshOutcome.Ok(current) // someone else refreshed
        val refresh = store.load() ?: run {
            end(SessionState.Ended(ENDED))
            return RefreshOutcome.Ended
        }
        try {
            val r = api.refresh(refresh)
            val access = r.accessToken
            val next = r.refreshToken
            if (access == null || next == null || !r.account.isStaff) {
                end(SessionState.Ended(ENDED))
                return RefreshOutcome.Ended
            }
            store.save(next)
            accessToken = access
            _state.value = SessionState.SignedIn(r.account)
            RefreshOutcome.Ok(access)
        } catch (e: ApiException) {
            end(SessionState.Ended(if (e.code == "ACCOUNT_SUSPENDED") e.message ?: ENDED else ENDED))
            RefreshOutcome.Ended
        } catch (e: NetworkException) {
            RefreshOutcome.Offline
        }
    }

    private fun end(next: SessionState) {
        accessToken = null
        store.clear()
        _state.value = next
    }

    private fun loginError(e: ApiException): LoginResult = when (e.code) {
        "MFA_REQUIRED" -> LoginResult.CodeNeeded
        "MFA_INVALID" -> LoginResult.CodeInvalid
        "INVALID_CREDENTIALS" -> LoginResult.Failed("Email or password is incorrect.")
        "ACCOUNT_PENDING_VERIFICATION" -> LoginResult.Failed("Verify your email address first (see the code we sent).")
        "ACCOUNT_PENDING_APPROVAL" -> LoginResult.Failed("Your account is waiting for approval by an administrator.")
        "ACCOUNT_REJECTED" -> LoginResult.Failed("This account was not approved.")
        "ACCOUNT_SUSPENDED" -> LoginResult.Failed("This account is suspended. Contact an administrator.")
        "ACCOUNT_LOCKED" -> LoginResult.Failed(e.message ?: "Too many failed attempts. Try again later.")
        else -> if (e.status == 429) {
            LoginResult.Failed("Too many attempts. Please wait a moment.")
        } else {
            LoginResult.Failed(e.message ?: "Login failed.")
        }
    }

    companion object {
        const val ENDED = "Your session has ended. Please log in again."
        const val OFFLINE = "No connection to the server. Check the network and try again."
    }
}
