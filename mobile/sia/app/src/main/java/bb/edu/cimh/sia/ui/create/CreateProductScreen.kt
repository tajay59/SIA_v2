package bb.edu.cimh.sia.ui.create

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AddPhotoAlternate
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuAnchorType
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import bb.edu.cimh.sia.data.ApiException
import bb.edu.cimh.sia.data.CatalogApi
import bb.edu.cimh.sia.data.NetworkException
import bb.edu.cimh.sia.data.Photo
import bb.edu.cimh.sia.data.ProductInput
import bb.edu.cimh.sia.data.Reference
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.util.UUID

/** The form, as text the user typed; [toInput] turns it into a strict ProductInput or says what is wrong. */
data class ProductForm(
    val name: String = "",
    val make: String = "",
    val modelname: String = "",
    val modelnumber: String = "",
    val sn: String = "",
    val sn1: String = "",
    val type: String = "",
    val department: String = "",
    val project: String = "",
    val sellable: Boolean = false,
    val probono: Boolean = false,
    val description: String = "",
    val details: String = "",
    val unitquantity: String = "",
    val cost: String = "",
    val threshold: String = "0",
    val weight: String = "",
    val length: String = "",
    val width: String = "",
    val height: String = "",
) {
    /** Field → message; empty when the form can be sent. */
    fun errors(): Map<String, String> = buildMap {
        if (name.isBlank()) put("name", "Enter a name")
        if (type.isBlank()) put("type", "Choose a type")
        if (department.isBlank()) put("department", "Choose a department")
        if (cost.isNotBlank() && !COST.matches(cost.trim())) put("cost", "A amount like 150 or 150.00")
        if (threshold.toIntOrNull()?.let { it < 0 } != false) put("threshold", "0 or more")
        if (unitquantity.isNotBlank() && (unitquantity.toIntOrNull() ?: 0) < 1) put("unitquantity", "1 or more")
        if (weight.isNotBlank() && (weight.toDoubleOrNull() ?: -1.0) < 0) put("weight", "A number, 0 or more")
    }

    fun toInput(): ProductInput {
        fun opt(s: String) = s.trim().ifBlank { null }
        val dims = listOf(length, width, height).map { it.trim() }
        return ProductInput(
            name = name.trim(), type = type, department = department,
            // Pro Bono items are always sellable (PRD).
            sellable = sellable || probono, probono = probono, threshold = threshold.trim().toInt(),
            make = opt(make), modelname = opt(modelname), modelnumber = opt(modelnumber), sn = opt(sn), sn1 = opt(sn1),
            description = opt(description), details = opt(details), project = opt(project),
            cost = opt(cost)?.let { money(it) }, unitquantity = opt(unitquantity)?.toInt(), weight = opt(weight)?.toDouble(),
            // Legacy kept L × W × H as one text field.
            dimension = if (dims.all { it.isBlank() }) null else dims.joinToString(" x ") { it.ifBlank { "?" } },
        )
    }

    companion object {
        private val COST = Regex("""^\d{1,12}(\.\d{1,2})?$""")
        fun money(s: String): String = s.trim().let { if ('.' in it) it.padEnd(it.indexOf('.') + 3, '0') else "$it.00" }
    }
}

data class CreateProductState(
    val reference: Reference? = null,
    val form: ProductForm = ProductForm(),
    val photos: List<Uri> = emptyList(),
    val showErrors: Boolean = false,
    val busy: Boolean = false,
    val message: String? = null,
)

class CreateProductViewModel(private val catalog: CatalogApi) : ViewModel() {
    private val _state = MutableStateFlow(CreateProductState())
    val state = _state.asStateFlow()

    init {
        viewModelScope.launch {
            try {
                _state.update { it.copy(reference = catalog.reference()) }
            } catch (e: Exception) {
                _state.update { it.copy(message = "Could not load types and departments. Check the connection.") }
            }
        }
    }

    fun edit(change: (ProductForm) -> ProductForm) = _state.update { it.copy(form = change(it.form)) }

    fun addPhotos(uris: List<Uri>) = _state.update { it.copy(photos = (it.photos + uris).distinct().take(10)) }

    fun removePhoto(uri: Uri) = _state.update { it.copy(photos = it.photos - uri) }

    /** Creates the product, then uploads the photos (processed in the background by media-worker). */
    fun save(context: Context, onSaved: (String) -> Unit) {
        val s = _state.value
        if (s.busy) return
        if (s.form.errors().isNotEmpty()) {
            _state.update { it.copy(showErrors = true, message = "Check the marked fields.") }
            return
        }
        _state.update { it.copy(busy = true, message = null) }
        viewModelScope.launch {
            try {
                val product = catalog.create(s.form.toInput())
                if (s.photos.isNotEmpty()) {
                    val photos = withContext(Dispatchers.IO) { s.photos.mapNotNull { readPhoto(context, it) } }
                    try {
                        catalog.uploadImages(product.id, photos)
                    } catch (e: Exception) {
                        // The product exists; photos can be added again on SIA web. Say so instead of failing the save.
                        _state.update { it.copy(message = "Product saved, but the photos were not uploaded: ${e.message}") }
                    }
                }
                withContext(Dispatchers.IO) { File(context.cacheDir, "photos").listFiles()?.forEach { it.delete() } }
                _state.value = CreateProductState(reference = s.reference)
                onSaved(product.id)
            } catch (e: NetworkException) {
                _state.update { it.copy(message = "No connection. Creating a product needs the network.") }
            } catch (e: ApiException) {
                _state.update { it.copy(message = e.message) }
            } finally {
                _state.update { it.copy(busy = false) }
            }
        }
    }

    private fun readPhoto(context: Context, uri: Uri): Photo? {
        val mime = context.contentResolver.getType(uri) ?: "image/jpeg"
        val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: return null
        return Photo("${UUID.randomUUID()}.${mime.substringAfter('/')}", mime, bytes)
    }
}

/** M-09 (APD §5; legacy order: photos, then the product fields, then Submit). Online only. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CreateProductScreen(vm: CreateProductViewModel, onSaved: (String) -> Unit, modifier: Modifier = Modifier) {
    val s by vm.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val f = s.form
    val errors = if (s.showErrors) f.errors() else emptyMap()
    var pending by rememberSaveable { mutableStateOf<Uri?>(null) }
    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        pending?.let { if (ok) vm.addPhotos(listOf(it)) }
        pending = null
    }
    val gallery = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(10)) { vm.addPhotos(it) }

    Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (s.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        Text("Photos", style = MaterialTheme.typography.titleSmall)
        if (s.photos.isEmpty()) Text("No photos added yet.", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            s.photos.forEach { uri -> Thumbnail(uri, onRemove = { vm.removePhoto(uri) }) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = {
                val dir = File(context.cacheDir, "photos").apply { mkdirs() }
                val uri = FileProvider.getUriForFile(context, "${context.packageName}.photos", File(dir, "${UUID.randomUUID()}.jpg"))
                pending = uri
                camera.launch(uri)
            }) {
                Icon(Icons.Filled.PhotoCamera, contentDescription = null)
                Text("  Take photo")
            }
            OutlinedButton(onClick = { gallery.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) }) {
                Icon(Icons.Filled.AddPhotoAlternate, contentDescription = null)
                Text("  Gallery")
            }
        }

        Field("Name", f.name, error = errors["name"]) { v -> vm.edit { it.copy(name = v.take(200)) } }
        Field("Make", f.make) { v -> vm.edit { it.copy(make = v.take(100)) } }
        Field("Model name", f.modelname) { v -> vm.edit { it.copy(modelname = v.take(100)) } }
        Field("Model number", f.modelnumber) { v -> vm.edit { it.copy(modelnumber = v.take(100)) } }
        Field("Reference (serial)", f.sn) { v -> vm.edit { it.copy(sn = v.take(100)) } }
        Field("Reference 2", f.sn1) { v -> vm.edit { it.copy(sn1 = v.take(100)) } }

        val ref = s.reference
        Choice("Type", ref?.types?.map { it.key to it.label }.orEmpty(), f.type, errors["type"]) { v -> vm.edit { it.copy(type = v) } }
        Choice("Department", ref?.departments?.map { it to it }.orEmpty(), f.department, errors["department"]) { v -> vm.edit { it.copy(department = v) } }
        Choice("Project (optional)", listOf("" to "None") + ref?.projects?.filter { it.active }?.map { it.code to it.name }.orEmpty(), f.project, null) { v ->
            vm.edit { it.copy(project = v) }
        }
        Toggle("Customers can request it (sellable)", f.sellable || f.probono, enabled = !f.probono) { v -> vm.edit { it.copy(sellable = v) } }
        Toggle("Pro Bono (free)", f.probono) { v -> vm.edit { it.copy(probono = v) } }

        Field("Description", f.description, singleLine = false) { v -> vm.edit { it.copy(description = v.take(5000)) } }
        Field("Details", f.details, singleLine = false) { v -> vm.edit { it.copy(details = v.take(5000)) } }
        Field("Unit quantity", f.unitquantity, error = errors["unitquantity"], keyboard = KeyboardType.Number) { v -> vm.edit { it.copy(unitquantity = v.filter(Char::isDigit).take(6)) } }
        Field("Cost (BBD)", f.cost, error = errors["cost"], keyboard = KeyboardType.Decimal) { v -> vm.edit { it.copy(cost = v.take(15)) } }
        Field("Low-stock threshold", f.threshold, error = errors["threshold"], keyboard = KeyboardType.Number) { v -> vm.edit { it.copy(threshold = v.filter(Char::isDigit).take(6)) } }
        Field("Weight (kg)", f.weight, error = errors["weight"], keyboard = KeyboardType.Decimal) { v -> vm.edit { it.copy(weight = v.take(10)) } }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Field("Length", f.length, modifier = Modifier.weight(1f)) { v -> vm.edit { it.copy(length = v.take(10)) } }
            Field("Width", f.width, modifier = Modifier.weight(1f)) { v -> vm.edit { it.copy(width = v.take(10)) } }
            Field("Height", f.height, modifier = Modifier.weight(1f)) { v -> vm.edit { it.copy(height = v.take(10)) } }
        }
        s.message?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Button(onClick = { vm.save(context, onSaved) }, enabled = !s.busy && s.reference != null) { Text("Submit") }
    }
}

@Composable
private fun Field(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
    error: String? = null,
    keyboard: KeyboardType = KeyboardType.Text,
    singleLine: Boolean = true,
    onChange: (String) -> Unit,
) {
    OutlinedTextField(
        value = value, onValueChange = onChange, label = { Text(label) }, singleLine = singleLine,
        isError = error != null, supportingText = error?.let { { Text(it) } },
        keyboardOptions = KeyboardOptions(keyboardType = keyboard), modifier = modifier.fillMaxWidth(),
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun Choice(label: String, options: List<Pair<String, String>>, value: String, error: String?, onPick: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = open, onExpandedChange = { open = it }) {
        OutlinedTextField(
            value = options.firstOrNull { it.first == value }?.second ?: "", onValueChange = {}, readOnly = true,
            label = { Text(label) }, isError = error != null, supportingText = error?.let { { Text(it) } },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = open) },
            modifier = Modifier.fillMaxWidth().menuAnchor(ExposedDropdownMenuAnchorType.PrimaryNotEditable),
        )
        ExposedDropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            options.forEach { (key, text) ->
                DropdownMenuItem(text = { Text(text) }, onClick = { onPick(key); open = false })
            }
        }
    }
}

@Composable
private fun Toggle(label: String, checked: Boolean, enabled: Boolean = true, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(label, modifier = Modifier.weight(1f))
        Switch(checked = checked, onCheckedChange = onChange, enabled = enabled)
    }
}

@Composable
private fun Thumbnail(uri: Uri, onRemove: () -> Unit) {
    val context = LocalContext.current
    val bitmap by produceState<Bitmap?>(null, uri) {
        value = withContext(Dispatchers.IO) {
            runCatching {
                val opts = BitmapFactory.Options().apply { inSampleSize = 8 }
                context.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, opts) }
            }.getOrNull()
        }
    }
    Box(Modifier.size(88.dp)) {
        bitmap?.let { Image(it.asImageBitmap(), contentDescription = "Photo", contentScale = ContentScale.Crop, modifier = Modifier.size(88.dp)) }
        IconButton(onClick = onRemove, modifier = Modifier.align(Alignment.TopEnd)) {
            Icon(Icons.Filled.Close, contentDescription = "Remove photo", tint = MaterialTheme.colorScheme.onPrimary)
        }
    }
}

