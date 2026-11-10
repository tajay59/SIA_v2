package bb.edu.cimh.sia.ui.lookup

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import bb.edu.cimh.sia.ui.theme.Mono
import bb.edu.cimh.sia.data.ApiException
import bb.edu.cimh.sia.data.CatalogApi
import bb.edu.cimh.sia.data.InventoryApi
import bb.edu.cimh.sia.data.NetworkException
import bb.edu.cimh.sia.data.ProductStock
import bb.edu.cimh.sia.data.ProductSummary
import bb.edu.cimh.sia.data.Shelf
import bb.edu.cimh.sia.data.StockUnit
import bb.edu.cimh.sia.data.queue.ScanOutcome
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

/** What M-03 shows; each view can go back to the one it came from. */
sealed interface LookupView {
    data object Scan : LookupView
    data class ShelfUnits(val shelf: Shelf, val units: List<StockUnit>, val next: String?) : LookupView
    data class Results(val query: String, val items: List<ProductSummary>, val next: String?) : LookupView
    data class Product(val product: ProductSummary, val stock: ProductStock?) : LookupView
    data class UnitSheet(val unit: StockUnit, val relocating: Boolean = false, val result: ScanLine? = null) : LookupView
}

data class LookupState(
    val stack: List<LookupView> = listOf(LookupView.Scan),
    val busy: Boolean = false,
    val lastCode: String? = null,
    val message: String? = null,
) {
    val view: LookupView get() = stack.last()
}

class LookupViewModel(
    private val inventory: InventoryApi,
    private val catalog: CatalogApi,
    private val queue: ScanQueue,
) : ViewModel() {
    private val _state = MutableStateFlow(LookupState())
    val state = _state.asStateFlow()

    /** A unit label, a shelf label, or words to search the catalogue with. */
    fun lookup(code: String, feedback: ScanFeedback) = load(code) {
        val unit = notFoundAsNull { inventory.unit(code) }
        if (unit != null) return@load LookupView.UnitSheet(unit)
        val shelf = notFoundAsNull { inventory.shelf(code) }
        if (shelf != null) {
            val page = inventory.shelfUnits(shelf.barcode)
            return@load LookupView.ShelfUnits(shelf, page.items, page.nextCursor)
        }
        if (code.length < 2) return@load null
        val page = catalog.search(code)
        if (page.items.isEmpty()) {
            feedback.error()
            _state.update { it.copy(message = "Nothing found for \"$code\".") }
            return@load null
        }
        LookupView.Results(code, page.items, page.nextCursor)
    }

    fun openProduct(product: ProductSummary) = load(null) {
        LookupView.Product(product, notFoundAsNull { inventory.stock(product.id) })
    }

    /** After M-09: the new product (stock is empty until labels are stowed). */
    fun openProductId(id: String) = load(null) {
        val product = catalog.product(id)
        LookupView.Product(product, notFoundAsNull { inventory.stock(product.id) })
    }

    fun openProductOf(unit: StockUnit) = load(null) {
        val product = catalog.product(unit.product)
        LookupView.Product(product, notFoundAsNull { inventory.stock(product.id) })
    }

    fun openUnit(barcode: String) = load(null) { LookupView.UnitSheet(inventory.unit(barcode)) }

    fun moreShelfUnits() {
        val v = _state.value.view as? LookupView.ShelfUnits ?: return
        val cursor = v.next ?: return
        replace(null) { inventory.shelfUnits(v.shelf.barcode, cursor).let { v.copy(units = v.units + it.items, next = it.nextCursor) } }
    }

    fun moreResults() {
        val v = _state.value.view as? LookupView.Results ?: return
        val cursor = v.next ?: return
        replace(null) { catalog.search(v.query, cursor).let { v.copy(items = v.items + it.items, next = it.nextCursor) } }
    }

    fun startRelocate() = _state.update { s ->
        val v = s.view as? LookupView.UnitSheet ?: return@update s
        s.copy(stack = s.stack.dropLast(1) + v.copy(relocating = true, result = null))
    }

    /** Relocate goes through the offline queue like every scan. */
    fun relocateTo(shelf: String, feedback: ScanFeedback) {
        val v = _state.value.view as? LookupView.UnitSheet ?: return
        if (shelf == v.unit.barcode) return
        replace(shelf) {
            val outcome = queue.relocate(v.unit.barcode, shelf)
            feedback.play(outcome)
            val unit = (outcome as? ScanOutcome.Done)?.unit ?: v.unit
            LookupView.UnitSheet(unit, relocating = false, result = ScanLine(shelf, outcome, "Moved"))
        }
    }

    fun back(): Boolean {
        val s = _state.value
        if (s.stack.size <= 1) return false
        _state.update { it.copy(stack = it.stack.dropLast(1), message = null) }
        return true
    }

    /** Pushes the view [block] returns (null = stay). */
    private fun load(code: String?, block: suspend () -> LookupView?) = show(code, replace = false, block)

    /** Replaces the current view with the one [block] returns. */
    private fun replace(code: String?, block: suspend () -> LookupView) = show(code, replace = true, block)

    private fun show(code: String?, replace: Boolean, block: suspend () -> LookupView?) {
        if (_state.value.busy) return
        _state.update { it.copy(busy = true, message = null, lastCode = code ?: it.lastCode) }
        viewModelScope.launch {
            try {
                val next = block() ?: return@launch
                _state.update { it.copy(stack = (if (replace) it.stack.dropLast(1) else it.stack) + next) }
            } catch (e: NetworkException) {
                _state.update { it.copy(message = "No connection. Lookup needs the network.") }
            } catch (e: ApiException) {
                _state.update { it.copy(message = e.message) }
            } finally {
                _state.update { it.copy(busy = false) }
            }
        }
    }

    private suspend fun <T> notFoundAsNull(block: suspend () -> T): T? = try {
        block()
    } catch (e: ApiException) {
        if (e.status == 404) null else throw e
    }
}

/** M-03 (APD §5): scan a shelf or a unit, or type to search; product with its places; unit sheet with relocate. */
@Composable
fun LookupScreen(vm: LookupViewModel, modifier: Modifier = Modifier, openProduct: String? = null) {
    val s by vm.state.collectAsStateWithLifecycle()
    val feedback = rememberScanFeedback()
    LaunchedEffect(openProduct) { openProduct?.let(vm::openProductId) }
    BackHandler(enabled = s.stack.size > 1) { vm.back() }
    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (s.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        s.message?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        when (val v = s.view) {
            LookupView.Scan ->
                ScanInput("Scan shelf or unit", s.lastCode, enabled = !s.busy, onScan = { vm.lookup(it, feedback) })
            is LookupView.ShelfUnits -> {
                Text(v.shelf.label, style = MaterialTheme.typography.titleMedium)
                Text("${v.units.size}${if (v.next != null) "+" else ""} units", style = MaterialTheme.typography.bodySmall)
                v.units.forEach { u ->
                    ListItem(
                        headlineContent = { Text(u.productName ?: u.product) },
                        supportingContent = { Text(u.barcode, fontFamily = Mono) },
                        modifier = Modifier.clickable { vm.openUnit(u.barcode) },
                    )
                    HorizontalDivider()
                }
                if (v.next != null) TextButton(onClick = vm::moreShelfUnits) { Text("Load more") }
            }
            is LookupView.Results -> {
                Text("Results for \"${v.query}\"", style = MaterialTheme.typography.titleMedium)
                v.items.forEach { p ->
                    ListItem(
                        headlineContent = { Text(p.name) },
                        supportingContent = { Text(p.subtitle) },
                        modifier = Modifier.clickable { vm.openProduct(p) },
                    )
                    HorizontalDivider()
                }
                if (v.next != null) TextButton(onClick = vm::moreResults) { Text("Load more") }
            }
            is LookupView.Product -> ProductView(v)
            is LookupView.UnitSheet -> UnitView(v, busy = s.busy, lastCode = s.lastCode, vm = vm, feedback = feedback)
        }
    }
}

@Composable
private fun ProductView(v: LookupView.Product) {
    Text(v.product.name, style = MaterialTheme.typography.titleLarge)
    Text(v.product.subtitle, style = MaterialTheme.typography.bodyMedium)
    val stock = v.stock
    if (stock == null) {
        Text("No stock record yet.", style = MaterialTheme.typography.bodyMedium)
        return
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("Available ${stock.available} · Reserved ${stock.reserved} · Issued ${stock.assigned}")
            if (stock.threshold > 0) Text("Low-stock level ${stock.threshold}", style = MaterialTheme.typography.bodySmall)
        }
    }
    Text("Locations", style = MaterialTheme.typography.titleMedium)
    if (stock.byLocation.isEmpty()) Text("Not on any shelf.")
    stock.byLocation.forEach { place ->
        ListItem(headlineContent = { Text(place.label) }, trailingContent = { Text("${place.count}") })
        HorizontalDivider()
    }
}

@Composable
private fun UnitView(v: LookupView.UnitSheet, busy: Boolean, lastCode: String?, vm: LookupViewModel, feedback: ScanFeedback) {
    val u = v.unit
    Text(u.productName ?: u.product, style = MaterialTheme.typography.titleLarge)
    Text(u.barcode, fontFamily = Mono)
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            u.serial?.let { Text("Serial $it") }
            Text(
                when {
                    u.assignedTo != null -> "Issued to a person (return it on SIA web before stowing)"
                    u.picked -> "Picked${u.pickedReason?.let { r -> ": $r" } ?: ""}"
                    u.place != null -> u.place!!
                    else -> "Not stowed yet"
                },
            )
            if (u.reservedFor != null) Text("Reserved for request ${u.reservedFor}", style = MaterialTheme.typography.bodySmall)
        }
    }
    v.result?.let { ScanResults(listOf(it)) }
    if (v.relocating) {
        ScanInput("Scan the new shelf", lastCode, enabled = !busy, onScan = { vm.relocateTo(it, feedback) })
    } else {
        if (u.stowed && !u.picked && u.assignedTo == null) {
            OutlinedButton(onClick = vm::startRelocate) { Text("Relocate") }
        }
        TextButton(onClick = { vm.openProductOf(u) }) { Text("Open product") }
    }
}
