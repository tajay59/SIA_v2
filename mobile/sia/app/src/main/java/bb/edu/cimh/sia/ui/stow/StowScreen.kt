package bb.edu.cimh.sia.ui.stow

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import bb.edu.cimh.sia.data.ApiException
import bb.edu.cimh.sia.data.InventoryApi
import bb.edu.cimh.sia.data.NetworkException
import bb.edu.cimh.sia.data.Shelf
import bb.edu.cimh.sia.data.queue.ScanQueue
import bb.edu.cimh.sia.ui.scan.ScanFeedback
import bb.edu.cimh.sia.ui.scan.ScanInput
import bb.edu.cimh.sia.ui.scan.ScanLine
import bb.edu.cimh.sia.ui.scan.ScanResults
import bb.edu.cimh.sia.ui.scan.rememberScanFeedback
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The shelf being stowed to. [checked] = false when it was scanned offline (the server checks it later). */
data class StowShelf(val barcode: String, val label: String, val checked: Boolean)

data class StowState(
    val shelf: StowShelf? = null,
    val busy: Boolean = false,
    val message: String? = null,
    val lastCode: String? = null,
    val lines: List<ScanLine> = emptyList(),
)

class StowViewModel(private val inventory: InventoryApi, private val queue: ScanQueue) : ViewModel() {
    private val _state = MutableStateFlow(StowState())
    val state = _state.asStateFlow()

    fun scanShelf(code: String, feedback: ScanFeedback) = launchBusy(code) {
        val shelf = try {
            val s: Shelf = inventory.shelf(code)
            StowShelf(s.barcode, s.label, checked = true)
        } catch (e: ApiException) {
            feedback.error()
            _state.update { it.copy(message = if (e.status == 404) "$code is not a shelf. Scan the shelf label." else e.message) }
            return@launchBusy
        } catch (e: NetworkException) {
            StowShelf(code, code, checked = false)
        }
        _state.update { it.copy(shelf = shelf, message = null, lines = emptyList()) }
    }

    fun scanUnit(code: String, feedback: ScanFeedback) = launchBusy(code) {
        val shelf = _state.value.shelf ?: return@launchBusy
        if (code == shelf.barcode) return@launchBusy // the shelf label scanned again
        val outcome = queue.stow(code, shelf.barcode)
        feedback.play(outcome)
        _state.update { it.copy(lines = (listOf(ScanLine(code, outcome, "Stowed")) + it.lines).take(50)) }
    }

    fun changeShelf() = _state.update { StowState() }

    private fun launchBusy(code: String, block: suspend () -> kotlin.Unit) {
        if (_state.value.busy) return
        _state.update { it.copy(busy = true, lastCode = code) }
        viewModelScope.launch {
            try {
                block()
            } finally {
                _state.update { it.copy(busy = false) }
            }
        }
    }
}

/** M-04 (APD §5; legacy order: scan the shelf, then scan units in a loop). */
@Composable
fun StowScreen(vm: StowViewModel, onDone: () -> kotlin.Unit, modifier: Modifier = Modifier) {
    val s by vm.state.collectAsStateWithLifecycle()
    val feedback = rememberScanFeedback()
    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        val shelf = s.shelf
        if (shelf == null) {
            Text("1. Scan the shelf", style = MaterialTheme.typography.titleMedium)
            ScanInput("Scan shelf", s.lastCode, enabled = !s.busy, onScan = { vm.scanShelf(it, feedback) })
            s.message?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        } else {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Text("Stowing to", style = MaterialTheme.typography.labelMedium)
                    Text(shelf.label, style = MaterialTheme.typography.titleMedium)
                    if (!shelf.checked) {
                        Text("Offline: the shelf is checked when the scans are sent.", style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            Text("2. Scan units", style = MaterialTheme.typography.titleMedium)
            // The latest result above the camera: visible without scrolling while scanning.
            ScanResults(s.lines.take(1))
            ScanInput("Scan unit", s.lastCode, enabled = !s.busy, onScan = { vm.scanUnit(it, feedback) })
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedButton(onClick = vm::changeShelf) { Text("Change shelf") }
                Button(onClick = { vm.changeShelf(); onDone() }) { Text("Done") }
            }
            ScanResults(s.lines.drop(1))
        }
    }
}
