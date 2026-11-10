package bb.edu.cimh.sia.ui.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CloudQueue
import androidx.compose.material.icons.filled.ErrorOutline
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import bb.edu.cimh.sia.data.Account
import bb.edu.cimh.sia.ui.nav.Tab
import java.text.DateFormat
import java.util.Date

/** M-02 (APD §5): shortcuts, offline queue badge, last sync. */
@Composable
fun HomeScreen(
    account: Account,
    pending: Int,
    failed: Int,
    lastSync: Long?,
    onOpen: (Tab) -> Unit,
    onSync: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Good to see you, ${account.firstname}", style = MaterialTheme.typography.headlineSmall)
        if (pending > 0 || failed > 0) {
            Card(
                onClick = onSync,
                colors = CardDefaults.cardColors(
                    containerColor = if (failed > 0) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.secondaryContainer,
                ),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(if (failed > 0) Icons.Filled.ErrorOutline else Icons.Filled.CloudQueue, contentDescription = null)
                    Text(
                        listOfNotNull(
                            pending.takeIf { it > 0 }?.let { "$it scan${if (it == 1) "" else "s"} waiting to be sent" },
                            failed.takeIf { it > 0 }?.let { "$it refused" },
                        ).joinToString(" · "),
                        modifier = Modifier.padding(start = 12.dp),
                    )
                }
            }
        }
        Text(
            "Last sync: ${lastSync?.let { DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(Date(it)) } ?: "never"}",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        listOf(Tab.Lookup, Tab.Stow, Tab.Pick, Tab.Orders).forEach { tab ->
            Card(onClick = { onOpen(tab) }, modifier = Modifier.fillMaxWidth()) {
                Row(Modifier.padding(20.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(tab.icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                    Column(Modifier.padding(start = 16.dp)) {
                        Text(tab.label, style = MaterialTheme.typography.titleMedium)
                        Text(tab.hint, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
    }
}
