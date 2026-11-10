package bb.edu.cimh.sia.data.queue

import bb.edu.cimh.sia.data.ApiException
import bb.edu.cimh.sia.data.NetworkException
import bb.edu.cimh.sia.data.OrderRequest
import bb.edu.cimh.sia.data.StockUnit
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

private class FakeDao : ScanDao {
    val rows = linkedMapOf<Long, QueuedScan>()
    private var nextId = 1L
    private val flow = MutableStateFlow<List<QueuedScan>>(emptyList())
    private fun emit() { flow.value = rows.values.toList() }
    override suspend fun insert(scan: QueuedScan): Long = nextId++.also { rows[it] = scan.copy(id = it); emit() }
    override suspend fun get(id: Long) = rows[id]
    override suspend fun nextPending(accountId: String) =
        rows.values.firstOrNull { it.status == ScanStatus.PENDING && it.accountId == accountId }
    override suspend fun countAttempt(id: Long) { rows[id] = rows[id]!!.let { it.copy(attempts = it.attempts + 1) } }
    override suspend fun fail(id: Long, code: String?, message: String) {
        rows[id] = rows[id]!!.copy(status = ScanStatus.FAILED, errorCode = code, errorMessage = message); emit()
    }
    override suspend fun retry(id: Long, key: String) {
        rows[id] = rows[id]!!.copy(status = ScanStatus.PENDING, key = key, errorCode = null, errorMessage = null); emit()
    }
    override suspend fun delete(id: Long) { rows.remove(id); emit() }
    override suspend fun clear() { rows.clear(); emit() }
    override fun observeAll(accountId: String): Flow<List<QueuedScan>> = flow
}

class ScanQueueTest {
    private val dao = FakeDao()
    private val sent = mutableListOf<QueuedScan>()
    private var answer: (QueuedScan) -> StockUnit = { StockUnit(it.unit, "MET1") }
    private var keys = 0
    private var scheduled = 0
    private var account: String? = "a1"
    private var sessionOk = true

    private val queue = ScanQueue(
        dao = dao,
        sender = ScanSender { s -> sent += s; Sent(unit = answer(s)) },
        accountId = { account },
        ensureSession = { sessionOk },
        newKey = { "k${++keys}" },
        now = { 1000L },
        schedule = { scheduled++ },
    )

    @Test fun onlineScanIsDoneAndDeleted() = runTest {
        val r = queue.stow("U1", "S1")
        assertTrue(r is ScanOutcome.Done)
        assertTrue(dao.rows.isEmpty())
        assertEquals(1000L, queue.lastSync.value)
        assertEquals("k1", sent.single().key)
    }

    @Test fun offlineScanIsQueuedKeepsKeyAndSchedules() = runTest {
        answer = { throw NetworkException(IOException("down")) }
        assertEquals(ScanOutcome.Queued, queue.stow("U1", "S1"))
        assertEquals(1, scheduled)
        answer = { StockUnit(it.unit, "MET1") }
        assertEquals(DrainResult.EMPTY, queue.drain())
        assertEquals(listOf("k1", "k1"), sent.map { it.key }) // same key on retry: no double stow
    }

    @Test fun refusalIsFailedAndNotRetriedAutomatically() = runTest {
        answer = { throw ApiException(409, "UNIT_ALREADY_STOWED", "Already on shelf 3") }
        val r = queue.stow("U1", "S1") as ScanOutcome.Refused
        assertEquals("UNIT_ALREADY_STOWED", r.code)
        assertEquals(ScanStatus.FAILED, dao.rows.values.single().status)
        assertEquals(DrainResult.EMPTY, queue.drain())
        assertEquals(1, sent.size)
    }

    @Test fun serverErrorKeepsScanPending() = runTest {
        answer = { throw ApiException(503, null, "down") }
        assertEquals(ScanOutcome.Queued, queue.pick("U1", "Damaged"))
        assertEquals(ScanStatus.PENDING, dao.rows.values.single().status)
    }

    @Test fun newScanNeverOvertakesQueuedOne() = runTest {
        answer = { throw NetworkException(IOException("down")) }
        queue.stow("U1", "S1")
        answer = { StockUnit(it.unit, "MET1") }
        queue.pick("U1", "Loan")
        assertEquals(listOf("U1:STOW", "U1:STOW", "U1:PICK"), sent.map { "${it.unit}:${it.op}" })
        assertTrue(dao.rows.isEmpty())
    }

    @Test fun retryFromSyncScreenUsesNewKey() = runTest {
        answer = { throw ApiException(404, "NOT_FOUND", "No such shelf") }
        queue.stow("U1", "S9")
        answer = { StockUnit(it.unit, "MET1") }
        queue.retry(dao.rows.keys.single())
        assertEquals(listOf("k1", "k2"), sent.map { it.key })
        assertTrue(dao.rows.isEmpty())
    }

    @Test fun noSessionLeavesQueueAlone() = runTest {
        answer = { throw NetworkException(IOException("down")) }
        queue.stow("U1", "S1")
        sessionOk = false
        assertEquals(DrainResult.NO_SESSION, queue.drain())
        assertEquals(1, dao.rows.size)
    }

    @Test fun requestPickCarriesLineAndReturnsTheRequest() = runTest {
        val q = ScanQueue(
            dao = dao,
            sender = ScanSender { s -> sent += s; Sent(request = OrderRequest(id = s.orderId!!, type = "PROBONO", status = "PICKING", version = 3)) },
            accountId = { "a1" }, ensureSession = { true }, newKey = { "k" }, now = { 1L }, schedule = {},
        )
        val r = q.pickForRequest("U1", "ORD1", "L1") as ScanOutcome.Done
        assertEquals("PICKING", r.request?.status)
        assertEquals(ScanOp.ORDER_PICK, sent.single().op)
        assertEquals("L1", sent.single().lineId)
    }

    @Test fun issueCarriesThePersonAndReturnDoesNot() = runTest {
        queue.assign("U1", "USR9")
        queue.unassign("U1")
        assertEquals(listOf(ScanOp.ASSIGN to "USR9", ScanOp.UNASSIGN to null), sent.map { it.op to it.assignee })
    }

    @Test fun otherAccountsScansAreNotSent() = runTest {
        answer = { throw NetworkException(IOException("down")) }
        queue.stow("U1", "S1")
        account = "a2"
        answer = { StockUnit(it.unit, "MET1") }
        assertEquals(DrainResult.EMPTY, queue.drain())
        assertEquals(1, dao.rows.size)
    }
}
