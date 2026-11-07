package bb.edu.cimh.sia.ui.lock

import androidx.biometric.BiometricManager
import androidx.biometric.BiometricManager.Authenticators.BIOMETRIC_STRONG
import androidx.biometric.BiometricManager.Authenticators.DEVICE_CREDENTIAL
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity

const val UNLOCK_WITH = BIOMETRIC_STRONG or DEVICE_CREDENTIAL

/** True when the device has a screen lock (PIN, pattern, password or strong biometric) the app can ask for. */
fun canLock(activity: FragmentActivity): Boolean =
    BiometricManager.from(activity).canAuthenticate(UNLOCK_WITH) == BiometricManager.BIOMETRIC_SUCCESS

fun promptUnlock(activity: FragmentActivity, onUnlocked: () -> Unit) {
    val prompt = BiometricPrompt(
        activity,
        ContextCompat.getMainExecutor(activity),
        object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) = onUnlocked()
        },
    )
    prompt.authenticate(
        BiometricPrompt.PromptInfo.Builder()
            .setTitle("Unlock SIA Mobile")
            .setSubtitle("Use your screen lock")
            .setAllowedAuthenticators(UNLOCK_WITH)
            .build(),
    )
}

@Composable
fun LockScreen(activity: FragmentActivity, onUnlocked: () -> Unit, onLogout: () -> Unit) {
    LaunchedEffect(Unit) { promptUnlock(activity, onUnlocked) }
    Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(
            Modifier.fillMaxSize().safeDrawingPadding().padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text("SIA Mobile is locked", style = MaterialTheme.typography.titleLarge)
            Text("It locks after 5 minutes without use.", style = MaterialTheme.typography.bodyMedium)
            Button(onClick = { promptUnlock(activity, onUnlocked) }, modifier = Modifier.fillMaxWidth()) { Text("Unlock") }
            TextButton(onClick = onLogout) { Text("Log out") }
        }
    }
}
