plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
android {
    namespace = "org.ankicompanion.app"
    compileSdk = 35
    defaultConfig {
        applicationId = "org.ankicompanion.app"
        minSdk = 26
        targetSdk = 35
        versionCode = providers.environmentVariable("APP_VERSION_CODE").orElse("1").get().toInt()
        versionName = providers.environmentVariable("APP_VERSION_NAME").orElse("0.1.0").get()
    }
    signingConfigs {
        create("release") {
            val path = System.getenv("ANDROID_KEYSTORE")
            if (path != null) {
                storeFile = file(path)
                storePassword = System.getenv("ANDROID_STORE_PASSWORD")
                keyAlias = System.getenv("ANDROID_KEY_ALIAS") ?: "companion"
                keyPassword = System.getenv("ANDROID_KEY_PASSWORD")
            }
        }
    }
    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { buildConfig = true }
    testOptions { unitTests.isReturnDefaultValues = true }
}
dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("com.caverock:androidsvg-aar:1.4")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
