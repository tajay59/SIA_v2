package bb.edu.cimh.sia.ui.pick

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import bb.edu.cimh.sia.data.ApiException
import bb.edu.cimh.sia.data.IdentityApi
import bb.edu.cimh.sia.data.NetworkException
import bb.edu.cimh.sia.data.Person
import bb.edu.cimh.sia.data.queue.ScanOutcome
import bb.edu.cimh.sia.data.queue.ScanQueue
import bb.edu.cimh.sia.ui.scan.ScanFeedback
import bb.edu.cimh.sia.ui.scan.ScanInput
import bb.edu.cimh.sia.ui.scan.ScanLine
import bb.edu.cimh.sia.ui.scan.ScanResults
import bb.edu.cimh.sia.ui.scan.rememberScanFeedback
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The Pick tab's three jobs, as on SIA web `/pick`: take units off with a reason, issue to a person, take returns. */
enum class PickMode(val label: String) { PICK("Pick"), ISSUE("Issue"), RETURN("Return") }

data class PickState(
    val mode: PickMode = PickMode.PICK,
    val reason: String? = null,
    val person: Person? = null,
    val people: List<Person> = emptyList(),
    val searching: Boolean = false,
    val searchMessage: String? = null,
    val busy: Boolean = false,
    val lastCode: String? = null,
    val lines: List<ScanLine> = emptyList(),
)

class PickViewModel(private val queue: ScanQueue, private val identity: IdentityApi) : ViewModel() {
    private val _state = MutableStateFlow(PickState())
    val state = _state.asStateFlow()

    fun setMode(mode: PickMode) = _state.update { it.copy(mode = mode, lines = emptyList(), lastCode = null) }

    fun setReason(reason: String) = _state.update { it.copy(reason = reason.trim().take(MAX_REASON)) }

    fun changeReason() = _state.update { it.copy(reason = null) }

    /** Online only: people come from identity-svc (staff read access). */
    fun search(q: String) {
        if (q.trim().length < 2) return _state.update { it.copy(people = emptyList(), searchMessage = null) }
        _state.update { it.copy(searching = true, searchMessage = null) }
        viewModelScope.launch {
            try {
                val people = identity.findPeople(q.trim())
                _state.update { it.copy(people = people, searchMessage = if (people.isEmpty()) "Nobody found." else null) }
            } catch (e: NetworkException) {
                _state.update { it.copy(searchMessage = "No connection. Choosing a person needs the network.") }
            } catch (e: ApiException) {
                _state.update { it.copy(searchMessage = e.message) }
            } finally {
                _state.update { it.copy(searching = false) }
            }
        }
    }

    fun choose(person: Person?) = _state.update { it.copy(person = person, people = emptyList(), lines = emptyList()) }

    fun scan(code: String, feedback: ScanFeedback) {
        val s = _state.value
        if (s.busy) return
        val run: suspend () -> Pair<ScanOutcome, String> = when (s.mode) {
            PickMode.PICK -> { val r = s.reason ?: return; { queue.pick(code, r) to "Picked" } }
            PickMode.ISSUE -> { val p = s.person ?: return; { queue.assign(code, p.id) to "With ${p.name}" } }
            PickMode.RETURN -> { { queue.unassign(code) to "Returned; stow it on a shelf" } }
        }
        _state.update { it.copy(busy = true, lastCode = code) }
        viewModelScope.launch {
            try {
                val (outcome, done) = run()
                feedback.play(outcome)
                _state.update { it.copy(lines = (listOf(ScanLine(code, outcome, done)) + it.lines).take(50)) }
            } finally {
                _state.update { it.copy(busy = false) }
            }
        }
    }

    companion object {
        const val MAX_REASON = 300
    }
}

/** M-05 (APD §5; legacy and SIA web: the reason once, then scan units) plus Issue/Return (who has what). */
@Composable
fun PickScreen(vm: PickViewModel, modifier: Modifier = Modifier) {
    val s by vm.state.collectAsStateWithLifecycle()
    val feedback = rememberScanFeedback()
    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            PickMode.entries.forEachIndexed { i, m ->
                SegmentedButton(
                    selected = s.mode == m, onClick = { vm.setMode(m) },
                    shape = SegmentedButtonDefaults.itemShape(i, PickMode.entries.size),
                ) { Text(m.label) }
            }
        }
        when (s.mode) {
            PickMode.PICK -> PickWithReason(s, vm, feedback)
            PickMode.ISSUE -> Issue(s, vm, feedback)
            PickMode.RETURN -> {
                Text("Scan units coming back. Then stow them on a shelf.", style = MaterialTheme.typography.bodyMedium)
                Scanning("Scan the returned unit", s, vm, feedback)
            }
        }
    }
}

@Composable
private fun Scanning(prompt: String, s: PickState, vm: PickViewModel, feedback: ScanFeedback) {
    // The latest result above the camera: visible without scrolling while scanning.
    ScanResults(s.lines.take(1))
    ScanInput(prompt, s.lastCode, enabled = !s.busy, onScan = { vm.scan(it, feedback) })
    ScanResults(s.lines.drop(1))
}

@Composable
private fun PickWithReason(s: PickState, vm: PickViewModel, feedback: ScanFeedback) {
    val reason = s.reason
    if (reason == null) {
        var text by rememberSaveable { mutableStateOf("") }
        Text("Pick with a reason", style = MaterialTheme.typography.titleMedium)
        OutlinedTextField(
            value = text,
            onValueChange = { text = it.take(PickViewModel.MAX_REASON) },
            label = { Text("Reason") },
            supportingText = { Text("${text.length} / ${PickViewModel.MAX_REASON}") },
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = { if (text.isNotBlank()) vm.setReason(text) }),
            modifier = Modifier.fillMaxWidth(),
        )
        Button(onClick = { vm.setReason(text) }, enabled = text.isNotBlank()) { Text("Start scanning") }
    } else {
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp)) {
                Text("Reason", style = MaterialTheme.typography.labelMedium)
                Text(reason, style = MaterialTheme.typography.bodyLarge)
            }
        }
        OutlinedButton(onClick = vm::changeReason) { Text("Change reason") }
        Scanning("Scan unit", s, vm, feedback)
    }
}

@Composable
private fun Issue(s: PickState, vm: PickViewModel, feedback: ScanFeedback) {
    val person = s.person
    if (person == null) {
        var q by rememberSaveable { mutableStateOf("") }
        // Search as the name is typed, after a short pause.
        LaunchedEffect(q) {
            delay(300)
            vm.search(q)
        }
        Text("Issue to", style = MaterialTheme.typography.titleMedium)
        OutlinedTextField(
            value = q, onValueChange = { q = it.take(100) }, label = { Text("Name or email") },
            singleLine = true, modifier = Modifier.fillMaxWidth(),
        )
        s.searchMessage?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        s.people.forEach { p ->
            ListItem(
                headlineContent = { Text(p.name) },
                supportingContent = { Text(listOfNotNull(p.email, p.organisationName).joinToString(" · ")) },
                modifier = Modifier.clickable { vm.choose(p) },
            )
            HorizontalDivider()
        }
    } else {
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp)) {
                Text("Issuing to", style = MaterialTheme.typography.labelMedium)
                Text(person.name, style = MaterialTheme.typography.titleMedium)
                Text(person.email, style = MaterialTheme.typography.bodySmall)
            }
        }
        OutlinedButton(onClick = { vm.choose(null) }) { Text("Other person") }
        Scanning("Scan unit", s, vm, feedback)
    }
}
