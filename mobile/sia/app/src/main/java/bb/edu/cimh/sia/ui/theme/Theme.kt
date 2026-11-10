package bb.edu.cimh.sia.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import bb.edu.cimh.sia.R

// Design Brief §3 / §14.2: the same hex values as the Vuetify theme (contrast-checked there). Every Material 3
// role a component reads is set: unset roles fall back to the baseline purple palette (cards came out lilac).
private val Light = lightColorScheme(
    primary = Color(0xFF006FA8),
    onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFE6F4FB),
    onPrimaryContainer = Color(0xFF0F1A24),
    secondary = Color(0xFF53606C),
    onSecondary = Color(0xFFFFFFFF),
    secondaryContainer = Color(0xFFE8EDF2),
    onSecondaryContainer = Color(0xFF0F1A24),
    tertiary = Color(0xFF53606C),
    onTertiary = Color(0xFFFFFFFF),
    tertiaryContainer = Color(0xFFE8EDF2),
    onTertiaryContainer = Color(0xFF0F1A24),
    background = Color(0xFFF5F7FA),
    onBackground = Color(0xFF0F1A24),
    surface = Color(0xFFFFFFFF),
    onSurface = Color(0xFF0F1A24),
    surfaceVariant = Color(0xFFF0F3F7),
    onSurfaceVariant = Color(0xFF53606C),
    surfaceTint = Color(0xFF006FA8),
    surfaceBright = Color(0xFFFFFFFF),
    surfaceDim = Color(0xFFE8EDF2),
    surfaceContainerLowest = Color(0xFFFFFFFF),
    surfaceContainerLow = Color(0xFFFFFFFF),
    surfaceContainer = Color(0xFFFFFFFF),
    surfaceContainerHigh = Color(0xFFF0F3F7),
    surfaceContainerHighest = Color(0xFFF0F3F7),
    inverseSurface = Color(0xFF0F1A24),
    inverseOnSurface = Color(0xFFF5F7FA),
    inversePrimary = Color(0xFF5CC2FF),
    outline = Color(0xFFC7D0DA),
    outlineVariant = Color(0xFFE1E7EE),
    error = Color(0xFFB42318),
    onError = Color(0xFFFFFFFF),
    errorContainer = Color(0xFFFDECEA),
    onErrorContainer = Color(0xFF7A1A12),
)

private val Dark = darkColorScheme(
    primary = Color(0xFF5CC2FF),
    onPrimary = Color(0xFF0D1117),
    primaryContainer = Color(0xFF0B2A3D),
    onPrimaryContainer = Color(0xFFE6EDF3),
    secondary = Color(0xFF9AA7B4),
    onSecondary = Color(0xFF0D1117),
    secondaryContainer = Color(0xFF232C36),
    onSecondaryContainer = Color(0xFFE6EDF3),
    tertiary = Color(0xFF9AA7B4),
    onTertiary = Color(0xFF0D1117),
    tertiaryContainer = Color(0xFF232C36),
    onTertiaryContainer = Color(0xFFE6EDF3),
    background = Color(0xFF0D1117),
    onBackground = Color(0xFFE6EDF3),
    surface = Color(0xFF161B22),
    onSurface = Color(0xFFE6EDF3),
    surfaceVariant = Color(0xFF1C232C),
    onSurfaceVariant = Color(0xFF9AA7B4),
    surfaceTint = Color(0xFF5CC2FF),
    surfaceBright = Color(0xFF232C36),
    surfaceDim = Color(0xFF0D1117),
    surfaceContainerLowest = Color(0xFF0D1117),
    surfaceContainerLow = Color(0xFF161B22),
    surfaceContainer = Color(0xFF161B22),
    surfaceContainerHigh = Color(0xFF1C232C),
    surfaceContainerHighest = Color(0xFF1C232C),
    inverseSurface = Color(0xFFE6EDF3),
    inverseOnSurface = Color(0xFF0D1117),
    inversePrimary = Color(0xFF006FA8),
    outline = Color(0xFF3A4552),
    outlineVariant = Color(0xFF2A333E),
    error = Color(0xFFF97066),
    onError = Color(0xFF0D1117),
    errorContainer = Color(0xFF3B1714),
    onErrorContainer = Color(0xFFFDECEA),
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

// Design Brief §4: Inter for all text, JetBrains Mono for ids, barcodes and codes. Bundled variable fonts (OFL,
// licences in assets/licenses) so the app looks the same on every phone and works offline.
@OptIn(ExperimentalTextApi::class)
private fun inter(weight: Int) =
    Font(R.font.inter, FontWeight(weight), variationSettings = FontVariation.Settings(FontVariation.weight(weight)))

@OptIn(ExperimentalTextApi::class)
private fun mono(weight: Int) =
    Font(R.font.jetbrains_mono, FontWeight(weight), variationSettings = FontVariation.Settings(FontVariation.weight(weight)))

val Inter = FontFamily(inter(400), inter(500), inter(600), inter(700))

/** Use for every barcode, id and serial instead of FontFamily.Monospace. */
val Mono = FontFamily(mono(400), mono(500))

private val SiaTypography = Typography().run {
    fun TextStyle.inter() = copy(fontFamily = Inter)
    Typography(
        displayLarge = displayLarge.inter(), displayMedium = displayMedium.inter(), displaySmall = displaySmall.inter(),
        headlineLarge = headlineLarge.inter(), headlineMedium = headlineMedium.inter(),
        headlineSmall = headlineSmall.inter().copy(fontWeight = FontWeight.SemiBold),
        titleLarge = titleLarge.inter().copy(fontWeight = FontWeight.SemiBold),
        titleMedium = titleMedium.inter().copy(fontWeight = FontWeight.SemiBold),
        titleSmall = titleSmall.inter(),
        // Brief §14.2: body 14/22.
        bodyLarge = bodyLarge.inter(),
        bodyMedium = bodyMedium.inter().copy(fontSize = 14.sp, lineHeight = 22.sp),
        bodySmall = bodySmall.inter(),
        labelLarge = labelLarge.inter(), labelMedium = labelMedium.inter(), labelSmall = labelSmall.inter(),
    )
}

@Composable
fun SiaTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (dark) Dark else Light, shapes = SiaShapes, typography = SiaTypography, content = content)
}
