pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
// The build needs a JDK 17 toolchain (jvmToolchain(17)); Android Studio now bundles a newer JDK, so Gradle
// downloads Temurin 17 when a machine has none.
plugins {
    id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "sia-mobile"
include(":app")
