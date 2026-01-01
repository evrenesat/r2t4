plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "com.r2t4.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.r2t4.app"
        minSdk = 26  // Android 8.0
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0-mvp1"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    // Include proto generated sources
    sourceSets {
        getByName("main") {
            java.srcDirs("src/main/java", "build/generated/source/proto/main/java")
        }
    }
}

dependencies {
    // Core Android
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.service)
    implementation(libs.androidx.activity.compose)
    implementation(libs.guava)

    // Compose
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    implementation(libs.androidx.material.icons)
    implementation(libs.androidx.navigation.compose)
    debugImplementation(libs.androidx.ui.tooling)

    // DataStore for settings
    implementation(libs.androidx.datastore.preferences)

    // CameraX
    implementation(libs.androidx.camera.core)
    implementation(libs.androidx.camera.camera2)
    implementation(libs.androidx.camera.lifecycle)

    // Connect-Kotlin (gRPC)
    implementation(libs.connect.kotlin)
    implementation(libs.connect.kotlin.okhttp)
    implementation(libs.connect.kotlin.google.java)
    implementation(libs.okhttp)

    // Porcupine Wake Word
    implementation(libs.porcupine.android)

    // Coroutines
    implementation(libs.kotlinx.coroutines.core)
    implementation(libs.kotlinx.coroutines.android)
}
