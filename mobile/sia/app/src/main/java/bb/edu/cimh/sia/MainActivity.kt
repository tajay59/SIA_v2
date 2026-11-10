package bb.edu.cimh.sia

import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import bb.edu.cimh.sia.data.SessionState
import bb.edu.cimh.sia.data.queue.SyncWorker
import bb.edu.cimh.sia.ui.nav.SiaApp
import bb.edu.cimh.sia.ui.lock.LockScreen
import bb.edu.cimh.sia.ui.lock.canLock
import bb.edu.cimh.sia.ui.login.LoginScreen
import bb.edu.cimh.sia.ui.login.LoginViewModel
import bb.edu.cimh.sia.ui.theme.SiaTheme
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** FragmentActivity because BiometricPrompt (app lock) needs one. */
class MainActivity : FragmentActivity() {
    private val container get() = (application as SiaApplication).container

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { SiaTheme { App() } }
    }

    override fun onUserInteraction() {
        super.onUserInteraction()
        container.appLock.touch()
    }

    override fun onResume() {
        super.onResume()
        container.appLock.check(armed = container.session.state.value is SessionState.SignedIn)
    }

    @Composable
    private fun App() {
        val session = container.session
        val lock = container.appLock
        val state by session.state.collectAsStateWithLifecycle()
        val locked by lock.locked.collectAsStateWithLifecycle()
        val scope = rememberCoroutineScope()
        var noScreenLock by rememberSaveable { mutableStateOf(false) }

        LaunchedEffect(Unit) { if (session.state.value == SessionState.Unknown) session.restore() }

        when (val s = state) {
            SessionState.Unknown -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            SessionState.SignedOut, is SessionState.Ended -> {
                val vm: LoginViewModel = viewModel { LoginViewModel(session) }
                val message = when {
                    noScreenLock -> "Set a screen lock (PIN, pattern or password) on this device to use SIA Mobile."
                    s is SessionState.Ended -> s.message
                    else -> null
                }
                LoginScreen(vm, message)
            }
            is SessionState.SignedIn -> {
                LaunchedEffect(s.account.id) {
                    // TR-SEC-11: the app lock needs a device credential; without one, nobody stays signed in.
                    if (!canLock(this@MainActivity)) {
                        noScreenLock = true
                        session.logout()
                        return@LaunchedEffect
                    }
                    noScreenLock = false
                    lock.reset()
                    // Scans queued in an earlier session of this account go out now (or when the network is back).
                    SyncWorker.schedule(this@MainActivity)
                    while (true) {
                        delay(15_000)
                        lock.check(armed = true)
                    }
                }
                val logout: () -> Unit = {
                    scope.launch {
                        session.logout()
                        lock.reset()
                    }
                }
                if (locked) {
                    LockScreen(this@MainActivity, onUnlocked = lock::unlocked, onLogout = logout)
                } else {
                    SiaApp(container, s.account, onLogout = logout)
                }
            }
        }
    }
}
