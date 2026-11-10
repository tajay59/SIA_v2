package bb.edu.cimh.sia.data.queue

import bb.edu.cimh.sia.data.ApiException
import bb.edu.cimh.sia.data.NetworkException
import bb.edu.cimh.sia.data.OrderRequest
import bb.edu.cimh.sia.data.StockUnit
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** What happened to one scan right after it was made. */
sealed interface ScanOutcome {
    /** [unit] for inventory scans, [request] (updated lines) for a pick against a request. */
    data class Done(val unit: StockUnit? = null, val request: OrderRequest? = null) : ScanOutcome
    /** The server said no (409 UNIT_ALREADY_STOWED, 404 ...). Kept in M-11 until retried or discarded. */
    data class Refused(val code: String?, val message: String) : ScanOutcome
    /** No answer (offline, server down): sent later by [SyncWorker]. */
    data object Queued : ScanOutcome
}

enum class DrainResult { EMPTY, RETRY_LATER, NO_SESSION }

/** What the server returned for a scan. */
data class Sent(val unit: StockUnit? = null, val request: OrderRequest? = null)

/** Sends one scan (inventory or order-svc in the app, a fake in tests). */
fun interface ScanSender {
    suspend fun send(scan: QueuedScan): Sent
}

/**
 * The offline queue's rules (APD §5). Every scan goes through it, online or not, so there is one code path:
 * the row is written first, then the queue is sent oldest first. Order matters: a stow and a later pick of the
 * same unit must reach the server in that order, so a scan never overtakes a queued one.
 *
 * - success: the row is deleted.
 * - no answer, 408, 429, 5xx: the row stays PENDING with the same key, and sending stops (retried later).
 * - 401 (session over even after a refresh): sending stops; the rows wait for the next login of this account.
 * - any other 4xx: the row becomes FAILED with the server's message. The server replays that refusal for the key,
 *   so only a retry from M-11 (new key) sends it again.
 */
class ScanQueue(
    private val dao: ScanDao,
    private val sender: ScanSender,
    /** The signed-in account, or null. */
    private val accountId: () -> String?,
    /** Makes sure an access token exists (the worker may run in a fresh process). False = no session. */
    private val ensureSession: suspend () -> Boolean,
    private val newKey: () -> String,
    private val now: () -> Long,
    /** Asks WorkManager to send the queue when the network is back. */
    private val schedule: () -> kotlin.Unit,
    lastSync: Long? = null,
    private val onSynced: (Long) -> kotlin.Unit = {},
) {
    private val mutex = Mutex()
    private val _lastSync = MutableStateFlow(lastSync)
    val lastSync: StateFlow<Long?> = _lastSync.asStateFlow()

    suspend fun stow(unit: String, shelf: String) = submit(ScanOp.STOW, unit, shelf = shelf)

    suspend fun pick(unit: String, reason: String) = submit(ScanOp.PICK, unit, reason = reason)

    /** M-07: a unit for one line of a request (order-svc checks product, line and reservation). */
    suspend fun pickForRequest(unit: String, requestId: String, lineId: String) =
        submit(ScanOp.ORDER_PICK, unit, orderId = requestId, lineId = lineId)

    suspend fun relocate(unit: String, toShelf: String) = submit(ScanOp.RELOCATE, unit, shelf = toShelf)

    /** Issue a unit to a person (it leaves its shelf; returned with [unassign], then stowed). */
    suspend fun assign(unit: String, accountId: String) = submit(ScanOp.ASSIGN, unit, assignee = accountId)

    suspend fun unassign(unit: String) = submit(ScanOp.UNASSIGN, unit)

    private suspend fun submit(
        op: ScanOp,
        unit: String,
        shelf: String? = null,
        reason: String? = null,
        orderId: String? = null,
        lineId: String? = null,
        assignee: String? = null,
    ): ScanOutcome {
        val account = accountId() ?: return ScanOutcome.Refused(null, "Not signed in.")
        val scan = QueuedScan(
            key = newKey(), op = op, unit = unit.trim(), shelf = shelf?.trim(), reason = reason, orderId = orderId, lineId = lineId, assignee = assignee,
            accountId = account, createdAt = now(),
        )
        val id = dao.insert(scan)
        val results = HashMap<Long, ScanOutcome>()
        val drained = drain(results)
        return results[id] ?: run {
            if (drained != DrainResult.EMPTY) schedule()
            ScanOutcome.Queued
        }
    }

    /** Sends every PENDING scan of the signed-in account, oldest first (the worker and [submit] both call it). */
    suspend fun drain(): DrainResult = drain(null)

    private suspend fun drain(results: MutableMap<Long, ScanOutcome>?): DrainResult = mutex.withLock { drainLocked(results) }

    private suspend fun drainLocked(results: MutableMap<Long, ScanOutcome>?): DrainResult {
        // Session first: in a process the worker started, nobody is signed in until the stored session is restored.
        if (!ensureSession()) return DrainResult.NO_SESSION
        val account = accountId() ?: return DrainResult.NO_SESSION
        while (true) {
            val scan = dao.nextPending(account) ?: return DrainResult.EMPTY
            dao.countAttempt(scan.id)
            try {
                val sent = sender.send(scan)
                dao.delete(scan.id)
                val t = now()
                _lastSync.value = t
                onSynced(t)
                results?.put(scan.id, ScanOutcome.Done(sent.unit, sent.request))
            } catch (e: NetworkException) {
                return DrainResult.RETRY_LATER
            } catch (e: ApiException) {
                when {
                    e.status == 401 -> return DrainResult.NO_SESSION
                    e.status == 408 || e.status == 429 || e.status >= 500 -> return DrainResult.RETRY_LATER
                    else -> {
                        val message = e.message ?: "Refused (${e.status})"
                        dao.fail(scan.id, e.code, message)
                        results?.put(scan.id, ScanOutcome.Refused(e.code, message))
                    }
                }
            }
        }
    }

    /** M-11: send a refused scan again with a new key. */
    suspend fun retry(id: Long) {
        dao.retry(id, newKey())
        if (drain() != DrainResult.EMPTY) schedule()
    }

    suspend fun discard(id: Long) = dao.delete(id)

    /** The signed-in account's scans only: another account's are never sent and cannot be acted on. */
    fun observe(accountId: String) = dao.observeAll(accountId)

    /** Log out: the queue belongs to the account that scanned (the UI confirms first when scans are pending). */
    suspend fun clear() = dao.clear()
}
