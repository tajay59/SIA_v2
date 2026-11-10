package bb.edu.cimh.sia.ui.scan

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.CloudQueue
import androidx.compose.material.icons.filled.ErrorOutline
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import bb.edu.cimh.sia.ui.theme.Mono
import bb.edu.cimh.sia.data.queue.ScanOutcome

/** One line of a scan session: what was scanned and what the server (or the queue) said. */
data class ScanLine(val code: String, val outcome: ScanOutcome, val doneText: String)

/** Newest first. The chip says Done / Queued / Refused, so a queued scan is never mistaken for a done one. */
@Composable
fun ScanResults(lines: List<ScanLine>, modifier: Modifier = Modifier) {
    Column(modifier.semantics { liveRegion = LiveRegionMode.Polite }, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        lines.forEach { line -> ScanRow(line) }
    }
}

@Composable
private fun ScanRow(line: ScanLine) {
    val (label, detail, icon, color) = when (val o = line.outcome) {
        is ScanOutcome.Done -> Quad("Done", o.unit?.productName?.let { "${line.doneText} · $it" } ?: line.doneText, Icons.Filled.CheckCircle, MaterialTheme.colorScheme.primary)
        ScanOutcome.Queued -> Quad("Queued", "No connection: sent when the network is back", Icons.Filled.CloudQueue, MaterialTheme.colorScheme.secondary)
        is ScanOutcome.Refused -> Quad("Refused", o.message, Icons.Filled.ErrorOutline, MaterialTheme.colorScheme.error)
    }
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        AssistChip(
            onClick = {},
            label = { Text(label) },
            leadingIcon = { Icon(icon, contentDescription = null, tint = color) },
            colors = AssistChipDefaults.assistChipColors(labelColor = color),
        )
        Column(Modifier.padding(start = 12.dp).weight(1f)) {
            Text(line.code, fontFamily = Mono, style = MaterialTheme.typography.bodyMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(detail, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

private data class Quad<A, B, C, D>(val a: A, val b: B, val c: C, val d: D)
