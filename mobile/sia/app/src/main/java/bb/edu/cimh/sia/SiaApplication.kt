package bb.edu.cimh.sia

import android.app.Application
import android.os.SystemClock
import bb.edu.cimh.sia.data.IdentityApi
import bb.edu.cimh.sia.data.KeystoreTokenStore
import bb.edu.cimh.sia.data.SessionManager
import bb.edu.cimh.sia.data.authedHttpClient
import bb.edu.cimh.sia.data.baseHttpClient
import bb.edu.cimh.sia.ui.lock.AppLock

/** Manual dependency container: the app is small enough not to need a DI framework. */
class AppContainer(app: Application) {
    private val http = baseHttpClient()
    val session = SessionManager(IdentityApi(BuildConfig.API_BASE, http), KeystoreTokenStore(app))
    /** For every call made as the signed-in user (adds the bearer token, refreshes on 401). */
    val identity = IdentityApi(BuildConfig.API_BASE, authedHttpClient(http, session))
    val appLock = AppLock(clock = SystemClock::elapsedRealtime)
}

class SiaApplication : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}
