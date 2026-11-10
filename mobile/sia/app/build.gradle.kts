import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.ksp)
}

android {
    namespace = "bb.edu.cimh.sia"
    compileSdk = 37

    defaultConfig {
        // New id: the legacy app (com.google.stockinventoryapp) stays installed until cut-over (IR6).
        applicationId = "bb.edu.cimh.sia"
        minSdk = 31 // Android 12 (TRD; owner 2026-11-10: the Galaxy Note 10+ test phone tops out at Android 12)
        targetSdk = 37
        // CI sets SIA_VERSION_CODE (run number) so every internal build installs over the previous one.
        versionCode = System.getenv("SIA_VERSION_CODE")?.toIntOrNull() ?: 1
        versionName = "0.8.0"
        // Staging-lite; production gets its own value when CIMH IT has the DNS name (INFRASTRUCTURE §10).
        // Behind nginx every service shares the host (`/api/<service>/v1`).
        for (service in listOf("IDENTITY", "CATALOG", "INVENTORY", "ORDERS")) {
            buildConfigField("String", "${service}_BASE", "\"https://sia.hashiz.store\"")
        }
    }

    // Release signing (upload key): from `keystore.properties` next to settings.gradle.kts (git-ignored) or from
    // SIA_KEYSTORE_* environment variables (CI secrets). Without either, assembleRelease stays unsigned.
    val keyProps = Properties().apply {
        rootProject.file("keystore.properties").takeIf { it.exists() }?.inputStream()?.use { load(it) }
    }
    fun key(name: String, env: String): String? = keyProps.getProperty(name) ?: System.getenv(env)
    val storePath = key("storeFile", "SIA_KEYSTORE_FILE")
    signingConfigs {
        if (storePath != null) {
            create("release") {
                storeFile = rootProject.file(storePath)
                storePassword = key("storePassword", "SIA_KEYSTORE_PASSWORD")
                keyAlias = key("keyAlias", "SIA_KEY_ALIAS")
                keyPassword = key("keyPassword", "SIA_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        debug {
            // The emulator reaches the dev stack on the host, one port per service (CLAUDE.md); cleartext only in debug.
            mapOf("IDENTITY" to 18001, "CATALOG" to 18002, "INVENTORY" to 18004, "ORDERS" to 18005).forEach { (service, port) ->
                buildConfigField("String", "${service}_BASE", "\"http://10.0.2.2:$port\"")
            }
            applicationIdSuffix = ".debug"
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfigs.findByName("release")?.let { signingConfig = it }
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    lint {
        // Versions are chosen on purpose (at least two weeks old), so update hints are noise; the rest gates CI.
        disable += setOf("GradleDependency", "AndroidGradlePluginVersion", "NewerVersionAvailable")
        warningsAsErrors = true
        abortOnError = true
    }
    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

kotlin {
    jvmToolchain(17)
}

ksp {
    // Exported schemas are committed: they are what a later version's migration tests start from.
    arg("room.schemaLocation", "$projectDir/schemas")
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.biometric)
    implementation(libs.androidx.fragment.ktx)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.okhttp)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.compose.material.icons)
    implementation(libs.navigation.compose)
    implementation(libs.room.runtime)
    implementation(libs.room.ktx)
    ksp(libs.room.compiler)
    implementation(libs.work.runtime.ktx)
    implementation(libs.camera.camera2)
    implementation(libs.camera.lifecycle)
    implementation(libs.camera.view)
    implementation(libs.mlkit.barcode)
    debugImplementation(libs.compose.ui.tooling)

    testImplementation(libs.junit)
    testImplementation(libs.okhttp.mockwebserver)
    testImplementation(libs.kotlinx.coroutines.test)
}
