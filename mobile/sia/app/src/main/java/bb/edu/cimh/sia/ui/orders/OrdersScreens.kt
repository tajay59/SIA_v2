package bb.edu.cimh.sia.ui.orders

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import bb.edu.cimh.sia.ui.theme.Mono
import bb.edu.cimh.sia.data.ApiException
import bb.edu.cimh.sia.data.NetworkException
import bb.edu.cimh.sia.data.OrderRequest
import bb.edu.cimh.sia.data.OrdersApi
import bb.edu.cimh.sia.data.RequestSummary
import bb.edu.cimh.sia.data.ShipmentInput
import bb.edu.cimh.sia.data.queue.ScanOutcome
import bb.edu.cimh.sia.data.queue.ScanQueue
import bb.edu.cimh.sia.ui.scan.CameraField
import bb.edu.cimh.sia.ui.scan.ScanFeedback
import bb.edu.cimh.sia.ui.scan.ScanInput
import bb.edu.cimh.sia.ui.scan.ScanLine
import bb.edu.cimh.sia.ui.scan.ScanResults
import bb.edu.cimh.sia.ui.scan.rememberScanFeedback
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.time.LocalDate

// ---------------------------------------------------------------- M-06 list

data class OrdersState(
    val items: List<RequestSummary> = emptyList(),
    val next: String? = null,
    val loading: Boolean = false,
    val message: String? = null,
)

class OrdersViewModel(private val orders: OrdersApi) : ViewModel() {
    private val _state = MutableStateFlow(OrdersState())
    val state = _state.asStateFlow()

    fun refresh() = load(cursor = null)

    fun more() = _state.value.next?.let { load(it) }

    private fun load(cursor: String?) {
        if (_state.value.loading) return
        _state.update { it.copy(loading = true, message = null) }
        viewModelScope.launch {
            try {
                val page = orders.toPick(cursor)
                _state.update { s -> s.copy(items = (if (cursor == null) emptyList() else s.items) + page.items, next = page.nextCursor) }
            } catch (e: NetworkException) {
                _state.update { it.copy(message = "No connection. The list needs the network; queued picks are still sent later.") }
            } catch (e: ApiException) {
                _state.update { it.copy(message = e.message) }
            } finally {
                _state.update { it.copy(loading = false) }
            }
        }
    }
}

private fun statusText(status: String) = status.lowercase().replace('_', ' ').replaceFirstChar { it.uppercase() }

/** M-06 (APD §5): requests with units to pick or to ship (paid PURCHASING, Pro Bono APPROVED/PICKING). */
@Composable
fun OrdersScreen(vm: OrdersViewModel, onOpen: (String) -> Unit, modifier: Modifier = Modifier) {
    val s by vm.state.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { vm.refresh() }
    Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (s.loading) LinearProgressIndicator(Modifier.fillMaxWidth())
        s.message?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        if (!s.loading && s.items.isEmpty() && s.message == null) {
            Text("Nothing to pick or ship.", style = MaterialTheme.typography.bodyLarge)
        }
        s.items.forEach { r ->
            ListItem(
                overlineContent = { Text("${if (r.type == "PROBONO") "Pro Bono" else "Paid"} · ${statusText(r.status)}") },
                headlineContent = { Text(r.id, fontFamily = Mono) },
                supportingContent = {
                    Text(
                        listOfNotNull(r.customerName, r.organisationName, "${r.lineCount} line${if (r.lineCount == 1) "" else "s"}",
                            r.waitingDays?.let { "waiting $it d" }).joinToString(" · "),
                    )
                },
                modifier = Modifier.clickable { onOpen(r.id) },
            )
            HorizontalDivider()
        }
        if (s.next != null) TextButton(onClick = { vm.more() }) { Text("Load more") }
        TextButton(onClick = vm::refresh) { Text("Refresh") }
    }
}

// ---------------------------------------------------------------- M-07 pick

data class PickOrderState(
    val request: OrderRequest? = null,
    /** Picks queued offline per line: counted as picked so the next unit goes to the right line. */
    val queued: Map<String, Int> = emptyMap(),
    val busy: Boolean = false,
    val lastCode: String? = null,
    val lines: List<ScanLine> = emptyList(),
    val message: String? = null,
) {
    fun progress(lineId: String): Int =
        (request?.lines?.firstOrNull { it.lineId == lineId }?.picked?.size ?: 0) + (queued[lineId] ?: 0)
}

class PickOrderViewModel(private val orders: OrdersApi, private val queue: ScanQueue) : ViewModel() {
    private val _state = MutableStateFlow(PickOrderState())
    val state = _state.asStateFlow()

    fun open(id: String) {
        if (_state.value.request?.id == id) return
        _state.value = PickOrderState(busy = true)
        viewModelScope.launch {
            try {
                val r = orders.request(id)
                _state.update {
                    it.copy(request = r, message = if ("pick" in r.allowedActions || "ship" in r.allowedActions) null else "Request ${r.id} has nothing to pick now (${statusText(r.status).lowercase()}).")
                }
            } catch (e: NetworkException) {
                _state.update { it.copy(message = "No connection. Open the request again when the network is back.") }
            } catch (e: ApiException) {
                _state.update { it.copy(message = if (e.status == 404) "No request with this id." else e.message) }
            } finally {
                _state.update { it.copy(busy = false) }
            }
        }
    }

    /** As on SIA web: the line is the first unfinished one for the unit's product (`<productId>_<code>`). */
    fun scan(code: String, feedback: ScanFeedback) {
        val s = _state.value
        val r = s.request ?: return
        if (s.busy) return
        val line = r.pickableLines.firstOrNull { l ->
            (if ('_' in code) code.startsWith("${l.productId}_") else true) && s.progress(l.lineId) < l.qty
        }
        if (line == null) {
            feedback.error()
            _state.update {
                it.copy(lastCode = code, lines = listOf(ScanLine(code, ScanOutcome.Refused(null, "No line of this request still needs this product"), "")) + it.lines)
            }
            return
        }
        _state.update { it.copy(busy = true, lastCode = code) }
        viewModelScope.launch {
            try {
                val outcome = queue.pickForRequest(code, r.id, line.lineId)
                feedback.play(outcome)
                _state.update { st ->
                    val updated = (outcome as? ScanOutcome.Done)?.request
                    val queued = if (outcome == ScanOutcome.Queued) st.queued + (line.lineId to ((st.queued[line.lineId] ?: 0) + 1)) else st.queued
                    val next = st.copy(request = updated ?: st.request, queued = queued)
                    val text = "${line.product.name} · ${next.progress(line.lineId)} of ${line.qty}"
                    next.copy(lines = (listOf(ScanLine(code, outcome, text)) + st.lines).take(50))
                }
            } finally {
                _state.update { it.copy(busy = false) }
            }
        }
    }
}

/** M-07 (APD §5): CIMH-stock and Pro Bono lines with progress; scan units; a wrong unit shows a refused chip. */
@Composable
fun PickOrderScreen(vm: PickOrderViewModel, requestId: String, onShip: () -> Unit, modifier: Modifier = Modifier) {
    val s by vm.state.collectAsStateWithLifecycle()
    val feedback = rememberScanFeedback()
    LaunchedEffect(requestId) { vm.open(requestId) }
    Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (s.busy && s.request == null) LinearProgressIndicator(Modifier.fillMaxWidth())
        s.message?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        val r = s.request ?: return@Column
        Text(r.id, style = MaterialTheme.typography.titleMedium, fontFamily = Mono)
        Text(listOfNotNull(if (r.type == "PROBONO") "Pro Bono" else "Paid", statusText(r.status), r.customerName, r.organisationName).joinToString(" · "))
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                r.pickableLines.forEach { l ->
                    val done = s.progress(l.lineId)
                    Text(l.product.name, style = MaterialTheme.typography.bodyLarge)
                    Text(
                        "$done of ${l.qty} picked" + ((s.queued[l.lineId] ?: 0).takeIf { it > 0 }?.let { " ($it queued)" } ?: "") +
                            if (l.reservation?.status == "FAILED") " · not enough stock: requote" else "",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    LinearProgressIndicator(progress = { if (l.qty == 0) 1f else done.toFloat() / l.qty }, modifier = Modifier.fillMaxWidth())
                }
                if (r.pickableLines.isEmpty()) Text("Nothing to pick: supplier items ship direct.")
            }
        }
        val complete = r.pickableLines.all { s.progress(it.lineId) >= it.qty }
        if (complete) {
            // The server checks that every unit is picked (409 PICKING_INCOMPLETE); queued picks must reach it first.
            Button(onClick = onShip, enabled = s.queued.isEmpty()) {
                Text("Ship")
            }
            if (s.queued.isNotEmpty()) Text("Every unit is scanned. Ship once the queued picks are sent (Sync queue).", style = MaterialTheme.typography.bodySmall)
        } else {
            ScanResults(s.lines.take(1))
            ScanInput("Scan unit", s.lastCode, enabled = !s.busy, onScan = { vm.scan(it, feedback) })
        }
        ScanResults(if (complete) s.lines else s.lines.drop(1))
    }
}

// ---------------------------------------------------------------- M-08 ship

private val CARRIERS = listOf("FEDEX" to "FedEx", "DHL" to "DHL", "HAND" to "Hand delivery")

/** M-08 (APD §5): carrier, tracking (typed or scanned from the label), note, date. Needs the network. */
@Composable
fun ShipScreen(orders: OrdersApi, requestId: String, onShipped: () -> Unit, modifier: Modifier = Modifier) {
    var request by remember { mutableStateOf<OrderRequest?>(null) }
    var carrier by rememberSaveable { mutableStateOf("FEDEX") }
    var tracking by rememberSaveable { mutableStateOf("") }
    var note by rememberSaveable { mutableStateOf("") }
    var date by rememberSaveable { mutableStateOf(LocalDate.now().toString()) }
    var notify by rememberSaveable { mutableStateOf(true) }
    var busy by rememberSaveable { mutableStateOf(false) }
    var message by rememberSaveable { mutableStateOf<String?>(null) }
    var reload by rememberSaveable { mutableStateOf(0) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(requestId, reload) {
        try {
            request = orders.request(requestId)
        } catch (e: NetworkException) {
            message = "No connection. Shipping needs the network."
        } catch (e: ApiException) {
            message = e.message
        }
    }
    val dateOk = runCatching { LocalDate.parse(date) }.isSuccess
    val trackingOk = carrier == "HAND" || tracking.isNotBlank()

    Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(requestId, style = MaterialTheme.typography.titleMedium, fontFamily = Mono)
        request?.shipTo?.let { to -> Text(listOfNotNull("Ship to", to.name, to.city, to.country).joinToString(" · ")) }
        Text("Carrier", style = MaterialTheme.typography.labelLarge)
        Column(Modifier.selectableGroup()) {
            CARRIERS.forEach { (value, label) ->
                Row(
                    Modifier.fillMaxWidth().selectable(selected = carrier == value, onClick = { carrier = value }, role = Role.RadioButton).padding(vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    RadioButton(selected = carrier == value, onClick = null)
                    Text(label, modifier = Modifier.padding(start = 12.dp))
                }
            }
        }
        if (carrier != "HAND") {
            var camera by rememberSaveable { mutableStateOf(false) }
            OutlinedTextField(
                value = tracking, onValueChange = { tracking = it.take(100) }, label = { Text("Tracking number") },
                singleLine = true, modifier = Modifier.fillMaxWidth(),
                trailingIcon = {
                    IconButton(onClick = { camera = !camera }) {
                        Icon(Icons.Filled.QrCodeScanner, contentDescription = if (camera) "Close the camera" else "Scan the label's tracking barcode")
                    }
                },
            )
            if (camera) CameraField(onCode = { tracking = it.take(100); camera = false })
        }
        OutlinedTextField(
            value = note, onValueChange = { note = it.take(300) },
            label = { Text(if (carrier == "HAND") "Note (who delivered)" else "Note") }, modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = date, onValueChange = { date = it.take(10) }, label = { Text("Ship date (YYYY-MM-DD)") },
            isError = !dateOk, singleLine = true, modifier = Modifier.fillMaxWidth(),
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            Switch(checked = notify, onCheckedChange = { notify = it })
            Text("Email the customer", modifier = Modifier.padding(start = 12.dp))
        }
        message?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Button(
            enabled = !busy && request != null && dateOk && trackingOk,
            onClick = {
                val r = request ?: return@Button
                busy = true
                message = null
                scope.launch {
                    try {
                        orders.ship(
                            r,
                            ShipmentInput(carrier, tracking.trim().ifBlank { null }.takeIf { carrier != "HAND" }, note.trim().ifBlank { null }, date, notify),
                        )
                        onShipped()
                    } catch (e: NetworkException) {
                        message = "No connection. Try again when the network is back."
                    } catch (e: ApiException) {
                        message = e.message
                        if (e.status == 409 || e.status == 412) reload++ // someone changed the request: load the current version
                    } finally {
                        busy = false
                    }
                }
            },
        ) { Text("Ship") }
    }
}
