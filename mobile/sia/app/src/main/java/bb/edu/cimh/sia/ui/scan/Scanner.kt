package bb.edu.cimh.sia.ui.scan

import android.Manifest
import android.content.pm.PackageManager
import android.os.SystemClock
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.view.LifecycleCameraController
import androidx.camera.view.PreviewView
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.filled.QrCode2
import androidx.compose.material3.Card
import androidx.compose.material3.ElevatedSuggestionChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import bb.edu.cimh.sia.ui.theme.Mono
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.common.InputImage
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * One scan step, laid out like the legacy scan screens: the prompt chip ("Scan shelf"), the live camera, and a
 * card with the last code. Under it a text field: Bluetooth/USB scanners type the code and press Enter, and a
 * damaged label can be typed. [enabled] = false pauses scanning (while a result or a dialog is shown).
 */
@Composable
fun ScanInput(
    prompt: String,
    lastCode: String?,
    enabled: Boolean,
    onScan: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    var granted by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED)
    }
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted = it }
    var typed by rememberSaveable { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    val now = {
        val code = typed.trim()
        if (enabled && code.isNotEmpty()) {
            typed = ""
            onScan(code)
        }
    }
    // Enter can be handled before the last typed characters reach the field (found on the emulator with injected
    // keys; a Bluetooth scanner sends keys the same way), which cut codes short. Read the field a moment later.
    val submit: () -> kotlin.Unit = {
        scope.launch {
            delay(150)
            now()
        }
    }

    Column(modifier, verticalArrangement = Arrangement.spacedBy(12.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        ElevatedSuggestionChip(onClick = {}, label = { Text(prompt) })
        if (granted) {
            CameraScanner(
                enabled = enabled,
                onCode = onScan,
                modifier = Modifier.fillMaxWidth().height(240.dp).clip(MaterialTheme.shapes.large),
            )
        } else {
            OutlinedButton(onClick = { ask.launch(Manifest.permission.CAMERA) }) {
                Icon(Icons.Filled.PhotoCamera, contentDescription = null)
                Text("  Scan with the camera")
            }
        }
        Card(Modifier.fillMaxWidth()) {
            Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.QrCode2, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                Text(
                    lastCode ?: "Nothing scanned yet",
                    style = MaterialTheme.typography.bodyLarge,
                    fontFamily = Mono,
                    color = if (lastCode == null) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(start = 12.dp),
                )
            }
        }
        OutlinedTextField(
            value = typed,
            onValueChange = { v ->
                // Some scanners send the Enter as a newline character.
                if (v.endsWith("\n")) {
                    typed = v.trimEnd('\n')
                    submit()
                } else {
                    typed = v
                }
            },
            label = { Text("Type or use a Bluetooth scanner") },
            singleLine = true,
            enabled = enabled,
            // Codes are not words: no autocorrect or suggestions, which hold characters back while composing.
            keyboardOptions = KeyboardOptions(
                capitalization = KeyboardCapitalization.None,
                autoCorrectEnabled = false,
                keyboardType = KeyboardType.Ascii,
                imeAction = ImeAction.Done,
            ),
            keyboardActions = KeyboardActions(onDone = { submit() }),
            modifier = Modifier.fillMaxWidth().onPreviewKeyEvent {
                if (it.type == KeyEventType.KeyUp && (it.key == Key.Enter || it.key == Key.NumPadEnter)) {
                    submit()
                    true
                } else {
                    false
                }
            },
        )
    }
}

@androidx.annotation.OptIn(ExperimentalGetImage::class)
/** CameraX preview with ML Kit barcode detection on the device (QR labels and 1D product/tracking codes). */
@Composable
private fun CameraScanner(enabled: Boolean, onCode: (String) -> Unit, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current
    val active by rememberUpdatedState(enabled)
    val emit by rememberUpdatedState(onCode)
    val controller = remember { LifecycleCameraController(context) }
    DisposableEffect(lifecycle) {
        val detector = BarcodeScanning.getClient()
        var lastCode: String? = null
        var lastAt = 0L
        controller.setImageAnalysisAnalyzer(ContextCompat.getMainExecutor(context)) { proxy ->
            val media = proxy.image
            if (!active || media == null) {
                proxy.close()
                return@setImageAnalysisAnalyzer
            }
            detector.process(InputImage.fromMediaImage(media, proxy.imageInfo.rotationDegrees))
                .addOnSuccessListener { codes ->
                    val code = codes.firstNotNullOfOrNull { it.rawValue?.trim()?.takeIf(String::isNotEmpty) }
                    val t = SystemClock.elapsedRealtime()
                    // The same label stays in view for a while: one scan per code every 2 s.
                    if (code != null && active && (code != lastCode || t - lastAt > 2_000)) {
                        lastCode = code
                        lastAt = t
                        emit(code)
                    }
                }
                .addOnCompleteListener { proxy.close() }
        }
        controller.bindToLifecycle(lifecycle)
        onDispose {
            controller.unbind()
            detector.close()
        }
    }
    AndroidView(
        factory = { PreviewView(it).apply { this.controller = controller } },
        modifier = modifier,
    )
}

/**
 * Camera only, for a form field that can also be typed (M-08 tracking number): asks for the permission, then
 * reads one code and hands it over.
 */
@Composable
fun CameraField(onCode: (String) -> Unit, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    var granted by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED)
    }
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted = it }
    LaunchedEffect(Unit) { if (!granted) ask.launch(Manifest.permission.CAMERA) }
    if (granted) {
        CameraScanner(enabled = true, onCode = onCode, modifier = modifier.fillMaxWidth().height(240.dp).clip(MaterialTheme.shapes.large))
    } else {
        Text("Allow the camera to scan, or type the code.", style = MaterialTheme.typography.bodySmall)
    }
}
