package bb.edu.cimh.sia.ui.login

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp

/** M-01 login (APD §5): email + password; admins with MFA get a code step; customers see "staff only". */
@Composable
fun LoginScreen(vm: LoginViewModel, endedMessage: String?) {
    Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(
            Modifier
                .fillMaxSize()
                .safeDrawingPadding()
                .imePadding()
                .verticalScroll(rememberScrollState())
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Column(Modifier.widthIn(max = 420.dp).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Text("SIA Mobile", style = MaterialTheme.typography.headlineMedium)
                when (vm.notice) {
                    LoginNotice.StaffOnly -> Notice(
                        title = "This app is for CIMH staff",
                        body = "Customers request items in the CIMH Stores web shop.",
                        onBack = vm::back,
                    )
                    LoginNotice.MfaSetup -> Notice(
                        title = "Turn on two-step verification first",
                        body = "Administrators must set up an authenticator app in SIA on the web before using the mobile app.",
                        onBack = vm::back,
                    )
                    LoginNotice.None -> Form(vm, endedMessage)
                }
            }
        }
    }
}

@Composable
private fun Form(vm: LoginViewModel, endedMessage: String?) {
    var showPassword by rememberSaveable { mutableStateOf(false) }
    val codeFocus = remember { FocusRequester() }
    Text("Log in with your CIMH staff account.", style = MaterialTheme.typography.bodyMedium)
    val message = vm.error ?: endedMessage
    if (message != null) {
        Text(
            message,
            color = MaterialTheme.colorScheme.error,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.semantics { contentDescription = "Error: $message" },
        )
    }
    OutlinedTextField(
        value = vm.email,
        onValueChange = { vm.email = it },
        label = { Text("Email") },
        singleLine = true,
        enabled = !vm.askCode,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next),
        modifier = Modifier.fillMaxWidth(),
    )
    OutlinedTextField(
        value = vm.password,
        onValueChange = { vm.password = it },
        label = { Text("Password") },
        singleLine = true,
        enabled = !vm.askCode,
        visualTransformation = if (showPassword) VisualTransformation.None else PasswordVisualTransformation(),
        trailingIcon = {
            TextButton(onClick = { showPassword = !showPassword }) { Text(if (showPassword) "Hide" else "Show") }
        },
        keyboardOptions = KeyboardOptions(
            keyboardType = KeyboardType.Password,
            imeAction = if (vm.askCode) ImeAction.Next else ImeAction.Done,
        ),
        keyboardActions = KeyboardActions(onDone = { vm.submit() }),
        modifier = Modifier.fillMaxWidth(),
    )
    if (vm.askCode) {
        LaunchedEffect(Unit) { codeFocus.requestFocus() }
        OutlinedTextField(
            value = vm.code,
            onValueChange = { v -> vm.code = v.filter(Char::isDigit).take(6) },
            label = { Text("6-digit code") },
            supportingText = { Text("From your authenticator app") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword, imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = { vm.submit() }),
            modifier = Modifier.fillMaxWidth().focusRequester(codeFocus),
        )
    }
    Button(onClick = vm::submit, enabled = vm.canSubmit, modifier = Modifier.fillMaxWidth().height(48.dp)) {
        if (vm.busy) {
            CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
        } else {
            Text(if (vm.askCode) "Verify" else "Log in")
        }
    }
    if (vm.askCode) {
        TextButton(onClick = vm::back, modifier = Modifier.fillMaxWidth()) { Text("Use another account") }
    }
}

@Composable
private fun Notice(title: String, body: String, onBack: () -> Unit) {
    Text(title, style = MaterialTheme.typography.titleLarge)
    Text(body, style = MaterialTheme.typography.bodyMedium)
    OutlinedButton(onClick = onBack, modifier = Modifier.fillMaxWidth()) { Text("Back to login") }
}
