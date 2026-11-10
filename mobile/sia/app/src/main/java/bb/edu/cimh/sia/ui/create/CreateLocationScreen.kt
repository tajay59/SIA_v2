package bb.edu.cimh.sia.ui.create

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import bb.edu.cimh.sia.ui.theme.Mono
import bb.edu.cimh.sia.data.ApiException
import bb.edu.cimh.sia.data.InventoryApi
import bb.edu.cimh.sia.data.Location
import bb.edu.cimh.sia.data.LocationInput
import bb.edu.cimh.sia.data.NetworkException
import bb.edu.cimh.sia.data.Shelf
import bb.edu.cimh.sia.data.Site
import bb.edu.cimh.sia.data.SiteInput
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class CreateLocationState(
    val sites: List<Site> = emptyList(),
    val site: Site? = null,
    val locations: List<Location> = emptyList(),
    val location: Location? = null,
    /** Shelves added in this session, newest batch first (codes to label). */
    val added: List<Shelf> = emptyList(),
    val busy: Boolean = false,
    val message: String? = null,
)

class CreateLocationViewModel(private val inventory: InventoryApi) : ViewModel() {
    private val _state = MutableStateFlow(CreateLocationState())
    val state = _state.asStateFlow()

    init {
        run { _state.update { it.copy(sites = inventory.sites()) } }
    }

    fun pickSite(site: Site) {
        _state.update { it.copy(site = site, location = null, locations = emptyList(), added = emptyList()) }
        run { _state.update { it.copy(locations = inventory.locations(site.barcode)) } }
    }

    fun newSite(name: String, country: String) = run {
        val site = inventory.createSite(SiteInput(name.trim(), country.trim().uppercase()))
        _state.update { it.copy(sites = it.sites + site, site = site, locations = emptyList(), location = null, added = emptyList()) }
    }

    fun pickLocation(location: Location) = _state.update { it.copy(location = location, added = emptyList()) }

    fun newLocation(name: String, description: String) = run {
        val site = _state.value.site ?: return@run
        val loc = inventory.createLocation(site.barcode, LocationInput(name.trim(), description.trim().ifBlank { null }))
        _state.update { it.copy(locations = it.locations + loc, location = loc, added = emptyList()) }
    }

    fun addShelves(count: Int) = run {
        val loc = _state.value.location ?: return@run
        val shelves = inventory.addShelves(loc.barcode, count)
        _state.update { it.copy(added = shelves + it.added) }
    }

    fun back() = _state.update {
        when {
            it.location != null -> it.copy(location = null, added = emptyList())
            it.site != null -> it.copy(site = null, locations = emptyList())
            else -> it
        }
    }

    private fun run(block: suspend () -> kotlin.Unit) {
        if (_state.value.busy) return
        _state.update { it.copy(busy = true, message = null) }
        viewModelScope.launch {
            try {
                block()
            } catch (e: NetworkException) {
                _state.update { it.copy(message = "No connection. Places are created on the server, so this needs the network.") }
            } catch (e: ApiException) {
                _state.update { it.copy(message = e.message) }
            } finally {
                _state.update { it.copy(busy = false) }
            }
        }
    }
}

/** M-10 (APD §5; legacy order): site → location → shelves. Shelf codes are made by the server; label them on SIA web. */
@Composable
fun CreateLocationScreen(vm: CreateLocationViewModel, modifier: Modifier = Modifier) {
    val s by vm.state.collectAsStateWithLifecycle()
    Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (s.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        s.message?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        val site = s.site
        val location = s.location
        when {
            site == null -> {
                Text("1. Site", style = MaterialTheme.typography.titleMedium)
                s.sites.filter { it.active }.forEach { st ->
                    ListItem(
                        headlineContent = { Text(st.name) }, supportingContent = { Text(st.country) },
                        modifier = Modifier.fillMaxWidth().clickable { vm.pickSite(st) },
                    )
                    HorizontalDivider()
                }
                NewSite(enabled = !s.busy, onCreate = vm::newSite)
            }
            location == null -> {
                Text("${site.name} · 2. Location", style = MaterialTheme.typography.titleMedium)
                s.locations.filter { it.active }.forEach { l ->
                    ListItem(
                        headlineContent = { Text(l.name) },
                        supportingContent = { Text("${l.shelfCount ?: 0} shelves") },
                        modifier = Modifier.fillMaxWidth().clickable { vm.pickLocation(l) },
                    )
                    HorizontalDivider()
                }
                NewLocation(enabled = !s.busy, onCreate = vm::newLocation)
                OutlinedButton(onClick = vm::back) { Text("Other site") }
            }
            else -> {
                Text("${site.name} · ${location.name} · 3. Shelves", style = MaterialTheme.typography.titleMedium)
                var count by rememberSaveable { mutableStateOf("1") }
                val n = count.toIntOrNull()
                OutlinedTextField(
                    value = count, onValueChange = { count = it.filter(Char::isDigit).take(3) }, label = { Text("Shelves to add (1–200)") },
                    isError = n == null || n !in 1..200, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.fillMaxWidth(),
                )
                Button(onClick = { vm.addShelves(n!!) }, enabled = !s.busy && n != null && n in 1..200) { Text("Add shelves") }
                if (s.added.isNotEmpty()) {
                    Card(Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text("Added (print the labels on SIA web: Inventory › Location)", style = MaterialTheme.typography.labelLarge)
                            s.added.sortedBy { it.number }.forEach { sh ->
                                Text("Shelf ${sh.number}  ${sh.barcode}", fontFamily = Mono, style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }
                OutlinedButton(onClick = vm::back) { Text("Other location") }
            }
        }
    }
}

@Composable
private fun NewSite(enabled: Boolean, onCreate: (String, String) -> kotlin.Unit) {
    var name by rememberSaveable { mutableStateOf("") }
    var country by rememberSaveable { mutableStateOf("BB") }
    Text("New site", style = MaterialTheme.typography.labelLarge)
    OutlinedTextField(value = name, onValueChange = { name = it.take(100) }, label = { Text("Name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(
        value = country, onValueChange = { country = it.filter(Char::isLetter).take(2).uppercase() },
        label = { Text("Country (2 letters, e.g. BB)") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
    )
    Button(onClick = { onCreate(name, country) }, enabled = enabled && name.isNotBlank() && country.length == 2) { Text("Create site") }
}

@Composable
private fun NewLocation(enabled: Boolean, onCreate: (String, String) -> kotlin.Unit) {
    var name by rememberSaveable { mutableStateOf("") }
    var description by rememberSaveable { mutableStateOf("") }
    Text("New location", style = MaterialTheme.typography.labelLarge)
    OutlinedTextField(value = name, onValueChange = { name = it.take(100) }, label = { Text("Name (e.g. Rack A)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(value = description, onValueChange = { description = it.take(300) }, label = { Text("Description (optional)") }, modifier = Modifier.fillMaxWidth())
    Button(onClick = { onCreate(name, description) }, enabled = enabled && name.isNotBlank()) { Text("Create location") }
}
