pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        // For Connect-Kotlin
        maven { url = uri("https://maven.buf.build/buf-plugin") }
    }
}

rootProject.name = "R2T4"
include(":app")
