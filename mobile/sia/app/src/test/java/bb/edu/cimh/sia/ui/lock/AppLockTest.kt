package bb.edu.cimh.sia.ui.lock

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AppLockTest {
    private var now = 0L
    private val lock = AppLock(timeoutMs = 300_000, clock = { now })

    @Test
    fun `locks after five minutes without a touch`() {
        now = 299_999
        lock.check(armed = true)
        assertFalse(lock.locked.value)
        now = 300_000
        lock.check(armed = true)
        assertTrue(lock.locked.value)
    }

    @Test
    fun `a touch starts the period again`() {
        now = 200_000
        lock.touch()
        now = 400_000
        lock.check(armed = true)
        assertFalse(lock.locked.value)
    }

    @Test
    fun `never locks when nobody is signed in`() {
        now = 10_000_000
        lock.check(armed = false)
        assertFalse(lock.locked.value)
    }

    @Test
    fun `touches while locked do not unlock, the credential does`() {
        now = 300_000
        lock.check(armed = true)
        lock.touch()
        lock.check(armed = true)
        assertTrue(lock.locked.value)
        lock.unlocked()
        assertFalse(lock.locked.value)
        now = 500_000
        lock.check(armed = true)
        assertFalse(lock.locked.value)
    }
}
