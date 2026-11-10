package bb.edu.cimh.sia.ui.scan

import android.content.Context
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.VibrationEffect
import android.os.VibratorManager
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import bb.edu.cimh.sia.data.queue.ScanOutcome

/** Vibration + sound per scan result (APD M-04), so staff can scan without looking at the screen. */
class ScanFeedback(context: Context) {
    private val vibrator = (context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager).defaultVibrator
    private val tones = runCatching { ToneGenerator(AudioManager.STREAM_NOTIFICATION, 80) }.getOrNull()

    fun play(outcome: ScanOutcome) {
        when (outcome) {
            is ScanOutcome.Done -> {
                vibrator.vibrate(VibrationEffect.createPredefined(VibrationEffect.EFFECT_CLICK))
                tones?.startTone(ToneGenerator.TONE_PROP_ACK, 150)
            }
            ScanOutcome.Queued -> {
                vibrator.vibrate(VibrationEffect.createPredefined(VibrationEffect.EFFECT_DOUBLE_CLICK))
                tones?.startTone(ToneGenerator.TONE_PROP_BEEP2, 200)
            }
            is ScanOutcome.Refused -> error()
        }
    }

    /** A refusal or an unknown code: long buzz, error tone. */
    fun error() {
        vibrator.vibrate(VibrationEffect.createWaveform(longArrayOf(0, 300, 120, 300), -1))
        tones?.startTone(ToneGenerator.TONE_SUP_ERROR, 400)
    }

    fun release() {
        tones?.release()
    }
}

@Composable
fun rememberScanFeedback(): ScanFeedback {
    val context = LocalContext.current
    val feedback = remember { ScanFeedback(context) }
    DisposableEffect(feedback) { onDispose { feedback.release() } }
    return feedback
}
