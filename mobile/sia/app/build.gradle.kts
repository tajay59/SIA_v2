plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

android {
    namespace = "bb.edu.cimh.sia"
    compileSdk = 37

    defaultConfig {
        // New id: the legacy app (com.google.stockinventoryapp) stays installed until cut-over (IR6).
        applicationId = "bb.edu.cimh.sia"
        minSdk = 31 // Android 12 (TRD; owner 2026-11-10: the Galaxy Note 10+ test phone tops out at Android 12)
        targetSdk = 37
        versionCode = 1
        versionName = "0.1.0"
        // Staging-lite; production gets its own value when CIMH IT has the DNS name (INFRASTRUCTURE §10).
        buildConfigField("String", "API_BASE", "\"https://sia.hashiz.store\"")
    }

    buildTypes {
        debug {
            // The emulator reaches the dev stack on the host (identity on 18001); cleartext only in debug.
            buildConfigField("String", "API_BASE", "\"http://10.0.2.2:18001\"")
            applicationIdSuffix = ".debug"
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
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
    debugImplementation(libs.compose.ui.tooling)

    testImplementation(libs.junit)
    testImplementation(libs.okhttp.mockwebserver)
    testImplementation(libs.kotlinx.coroutines.test)
}
