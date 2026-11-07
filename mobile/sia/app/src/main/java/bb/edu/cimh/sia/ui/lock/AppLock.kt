package bb.edu.cimh.sia.ui.lock

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * TR-SEC-11 app lock: after [timeoutMs] without a touch (in the app or away from it) the app locks, and the user
 * unlocks with the device credential or a strong biometric. Time comes from a monotonic clock, so changing the
 * device time does not unlock it.
 */
class AppLock(private val timeoutMs: Long = 5 * 60_000L, private val clock: () -> Long) {
    private val _locked = MutableStateFlow(false)
    val locked: StateFlow<Boolean> = _locked.asStateFlow()
    private var lastActive = clock()

    fun touch() {
        if (!_locked.value) lastActive = clock()
    }

    /** Call on resume and periodically while visible. Locks only when [armed] (someone is signed in). */
    fun check(armed: Boolean) {
        if (armed && !_locked.value && clock() - lastActive >= timeoutMs) _locked.value = true
    }

    fun unlocked() {
        lastActive = clock()
        _locked.value = false
    }

    /** Sign-in or sign-out starts a fresh period. */
    fun reset() = unlocked()
}
