package bb.edu.cimh.sia.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

// Design Brief §3 / §14.2: the same hex values as the Vuetify theme (contrast-checked there).
private val Light = lightColorScheme(
    primary = Color(0xFF006FA8),
    onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFE6F4FB),
    onPrimaryContainer = Color(0xFF0F1A24),
    secondary = Color(0xFF53606C),
    background = Color(0xFFF5F7FA),
    onBackground = Color(0xFF0F1A24),
    surface = Color(0xFFFFFFFF),
    onSurface = Color(0xFF0F1A24),
    surfaceVariant = Color(0xFFF0F3F7),
    outline = Color(0xFFC7D0DA),
    error = Color(0xFFB42318),
)

private val Dark = darkColorScheme(
    primary = Color(0xFF5CC2FF),
    onPrimary = Color(0xFF0D1117),
    primaryContainer = Color(0xFF0B2A3D),
    onPrimaryContainer = Color(0xFFE6EDF3),
    secondary = Color(0xFF9AA7B4),
    background = Color(0xFF0D1117),
    onBackground = Color(0xFFE6EDF3),
    surface = Color(0xFF161B22),
    onSurface = Color(0xFFE6EDF3),
    surfaceVariant = Color(0xFF1C232C),
    outline = Color(0xFF3A4552),
    error = Color(0xFFF97066),
)

/** Custom roles Material 3 has no slot for. */
object SiaColors {
    val success = Color(0xFF1A7F37)
    val warning = Color(0xFFB54708)
    val probono = Color(0xFFF5C400) // badge only, ink text
}

private val SiaShapes = Shapes(
    extraSmall = RoundedCornerShape(4.dp),
    small = RoundedCornerShape(4.dp),
    medium = RoundedCornerShape(8.dp),
    large = RoundedCornerShape(12.dp),
)

@Composable
fun SiaTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (dark) Dark else Light, shapes = SiaShapes, content = content)
}
