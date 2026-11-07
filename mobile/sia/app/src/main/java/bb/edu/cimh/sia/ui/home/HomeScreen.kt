package bb.edu.cimh.sia.ui.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import bb.edu.cimh.sia.data.Account

/** M-02 home (APD §5). Shortcuts, offline badge and the bottom navigation arrive with the scanning flows (P8). */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(account: Account, onLogout: () -> Unit) {
    Scaffold(topBar = { TopAppBar(title = { Text("SIA Mobile") }) }) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("Good to see you, ${account.firstname}", style = MaterialTheme.typography.headlineSmall)
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(account.email, style = MaterialTheme.typography.bodyMedium)
                    Text(if (account.role == "admin") "Administrator" else "Staff", style = MaterialTheme.typography.bodySmall)
                }
            }
            Text(
                "Lookup, stow, pick and shipping come to this app as the inventory and order services go live.",
                style = MaterialTheme.typography.bodyMedium,
            )
            OutlinedButton(onClick = onLogout, modifier = Modifier.fillMaxWidth()) { Text("Log out") }
        }
    }
}
