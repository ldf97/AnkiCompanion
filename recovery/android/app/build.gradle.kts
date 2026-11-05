plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
android {
  namespace = "org.ankicompanion.recovery"
  compileSdk = 35
  defaultConfig {
    applicationId = "org.ankicompanion.recovery"
    minSdk = 26
    targetSdk = 35
    versionCode = 1
    versionName = "1.0.0"
  }
  signingConfigs {
    create("independentRecovery") {
      storeFile = file(System.getenv("RECOVERY_KEYSTORE") ?: "recovery-signing.p12")
      storePassword = "LabOnlyPong2026"
      keyAlias = "ponglab"
      keyPassword = "LabOnlyPong2026"
    }
  }
  buildTypes { getByName("release") {
    isMinifyEnabled = false
    signingConfig = signingConfigs.getByName("independentRecovery")
  }}
  compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
  kotlinOptions { jvmTarget = "17" }
}
dependencies {
  implementation("androidx.core:core-ktx:1.15.0")
  implementation("com.squareup.okhttp3:okhttp:4.12.0")
}
