package bb.edu.cimh.sia

import android.app.Application
import android.content.Context
import android.os.SystemClock
import androidx.core.content.edit
import bb.edu.cimh.sia.data.AssignBody
import bb.edu.cimh.sia.data.CatalogApi
import bb.edu.cimh.sia.data.IdentityApi
import bb.edu.cimh.sia.data.InventoryApi
import bb.edu.cimh.sia.data.KeystoreTokenStore
import bb.edu.cimh.sia.data.OrdersApi
import bb.edu.cimh.sia.data.PickBody
import bb.edu.cimh.sia.data.PickForRequestBody
import bb.edu.cimh.sia.data.RelocateBody
import bb.edu.cimh.sia.data.SessionManager
import bb.edu.cimh.sia.data.SessionState
import bb.edu.cimh.sia.data.StowBody
import bb.edu.cimh.sia.data.UnassignBody
import bb.edu.cimh.sia.data.authedHttpClient
import bb.edu.cimh.sia.data.baseHttpClient
import bb.edu.cimh.sia.data.queue.ScanDatabase
import bb.edu.cimh.sia.data.queue.ScanOp
import bb.edu.cimh.sia.data.queue.ScanQueue
import bb.edu.cimh.sia.data.queue.ScanSender
import bb.edu.cimh.sia.data.queue.Sent
import bb.edu.cimh.sia.data.queue.SyncWorker
import bb.edu.cimh.sia.ui.lock.AppLock
import java.util.UUID

/** Manual dependency container: the app is small enough not to need a DI framework. */
class AppContainer(app: Application) {
    private val http = baseHttpClient()
    val session = SessionManager(IdentityApi(BuildConfig.IDENTITY_BASE, http), KeystoreTokenStore(app))
    /** For every call made as the signed-in user (adds the bearer token, refreshes on 401). */
    private val authed = authedHttpClient(http, session)
    val identity = IdentityApi(BuildConfig.IDENTITY_BASE, authed)
    val inventory = InventoryApi(BuildConfig.INVENTORY_BASE, authed)
    val catalog = CatalogApi(BuildConfig.CATALOG_BASE, authed)
    val orders = OrdersApi(BuildConfig.ORDERS_BASE, authed)
    val appLock = AppLock(clock = SystemClock::elapsedRealtime)

    private val prefs = app.getSharedPreferences("sync", Context.MODE_PRIVATE)

    val scans = ScanQueue(
        dao = ScanDatabase.open(app).scans(),
        sender = ScanSender { s ->
            when (s.op) {
                ScanOp.STOW -> Sent(unit = inventory.stow(StowBody(s.unit, s.shelf!!), s.key))
                ScanOp.PICK -> Sent(unit = inventory.pick(PickBody(s.unit, s.reason), s.key))
                ScanOp.RELOCATE -> Sent(unit = inventory.relocate(RelocateBody(s.unit, s.shelf!!), s.key))
                ScanOp.ORDER_PICK -> Sent(request = orders.pick(s.orderId!!, PickForRequestBody(s.lineId!!, s.unit), s.key))
                ScanOp.ASSIGN -> Sent(unit = inventory.assign(AssignBody(s.unit, s.assignee!!), s.key))
                ScanOp.UNASSIGN -> Sent(unit = inventory.unassign(UnassignBody(s.unit), s.key))
            }
        },
        accountId = { (session.state.value as? SessionState.SignedIn)?.account?.id },
        ensureSession = { session.ensureAccessToken() },
        newKey = { UUID.randomUUID().toString() },
        now = System::currentTimeMillis,
        schedule = { SyncWorker.schedule(app) },
        lastSync = prefs.getLong("lastSync", 0L).takeIf { it > 0 },
        onSynced = { t -> prefs.edit { putLong("lastSync", t) } },
    )
}

class SiaApplication : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}
