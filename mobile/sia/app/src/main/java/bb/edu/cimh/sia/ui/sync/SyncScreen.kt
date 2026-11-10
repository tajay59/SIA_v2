package bb.edu.cimh.sia.ui.sync

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import bb.edu.cimh.sia.ui.theme.Mono
import bb.edu.cimh.sia.data.queue.QueuedScan
import bb.edu.cimh.sia.data.queue.ScanOp
import bb.edu.cimh.sia.data.queue.ScanQueue
import bb.edu.cimh.sia.data.queue.ScanStatus
import kotlinx.coroutines.launch
import java.text.DateFormat
import java.util.Date

/** M-11 (APD §5): scans not yet accepted by the server. Retry (new key) or discard a refused one. */
@Composable
fun SyncScreen(queue: ScanQueue, accountId: String, modifier: Modifier = Modifier) {
    val scans by queue.observe(accountId).collectAsStateWithLifecycle(emptyList())
    val lastSync by queue.lastSync.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    Column(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(
            "Last sync: ${lastSync?.let { DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(Date(it)) } ?: "never"}",
            style = MaterialTheme.typography.bodyMedium,
        )
        val pending = scans.count { it.status == ScanStatus.PENDING }
        if (pending > 0) {
            Button(onClick = { scope.launch { queue.drain() } }) { Text("Send $pending now") }
        }
        if (scans.isEmpty()) Text("Every scan has been sent.", style = MaterialTheme.typography.bodyLarge)
        LazyColumn {
            items(scans, key = { it.id }) { scan ->
                ScanItem(
                    scan,
                    onRetry = { scope.launch { queue.retry(scan.id) } },
                    onDiscard = { scope.launch { queue.discard(scan.id) } },
                )
                HorizontalDivider()
            }
        }
    }
}

@Composable
private fun ScanItem(scan: QueuedScan, onRetry: () -> Unit, onDiscard: () -> Unit) {
    val what = when (scan.op) {
        ScanOp.STOW -> "Stow to ${scan.shelf}"
        ScanOp.PICK -> "Pick: ${scan.reason}"
        ScanOp.ORDER_PICK -> "Pick for request ${scan.orderId}"
        ScanOp.ASSIGN -> "Issue to a person"
        ScanOp.UNASSIGN -> "Return"
        ScanOp.RELOCATE -> "Move to ${scan.shelf}"
    }
    ListItem(
        overlineContent = {
            Text(
                if (scan.status == ScanStatus.FAILED) "Refused" else "Queued",
                color = if (scan.status == ScanStatus.FAILED) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.secondary,
            )
        },
        headlineContent = { Text(scan.unit, fontFamily = Mono) },
        supportingContent = {
            Column {
                Text(what)
                scan.errorMessage?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                if (scan.status == ScanStatus.FAILED) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = onRetry) { Text("Retry") }
                        TextButton(onClick = onDiscard) { Text("Discard") }
                    }
                }
            }
        },
    )
}
