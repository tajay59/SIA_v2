package bb.edu.cimh.sia.ui.login

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import bb.edu.cimh.sia.data.LoginResult
import bb.edu.cimh.sia.data.SessionManager
import kotlinx.coroutines.launch

enum class LoginNotice { None, StaffOnly, MfaSetup }

class LoginViewModel(private val session: SessionManager) : ViewModel() {
    var email by mutableStateOf("")
    var password by mutableStateOf("")
    var code by mutableStateOf("")
    var askCode by mutableStateOf(false)
        private set
    var busy by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set
    var notice by mutableStateOf(LoginNotice.None)
        private set

    val canSubmit: Boolean
        get() = !busy && email.isNotBlank() && password.isNotEmpty() && (!askCode || code.length == 6)

    fun submit() {
        if (!canSubmit) return
        busy = true
        error = null
        viewModelScope.launch {
            when (val r = session.login(email, password, if (askCode) code else null)) {
                is LoginResult.Success -> password = ""
                LoginResult.CodeNeeded -> askCode = true
                LoginResult.CodeInvalid -> {
                    code = ""
                    error = "That code is not valid. Enter the current code from your authenticator app."
                }
                LoginResult.StaffOnly -> notice = LoginNotice.StaffOnly
                LoginResult.MfaSetupRequired -> notice = LoginNotice.MfaSetup
                is LoginResult.Failed -> error = r.message
            }
            busy = false
        }
    }

    fun back() {
        notice = LoginNotice.None
        askCode = false
        code = ""
        password = ""
        error = null
    }
}
