plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
// Use the owner's Firebase Android *client* configuration in every build,
// including emulator integration tests. No service-account secrets live here.
val firebaseClient = rootProject.file("../deployment/firebase/android-client.json")
val googleServices = file("google-services.json")
if (!googleServices.exists() && firebaseClient.isFile) {
    firebaseClient.copyTo(googleServices)
}
if (googleServices.exists()) {
    apply(plugin = "com.google.gms.google-services")
}

android {
    namespace = "org.ankicompanion.app"
    compileSdk = 35
    defaultConfig {
        applicationId = "org.ankicompanion.app"
        minSdk = 26
        targetSdk = 35
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
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
    // Mihon uses OkHttp for reliable APK transfer; leave installation to Android.
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.caverock:androidsvg-aar:1.4")
    implementation(platform("com.google.firebase:firebase-bom:35.0.2"))
    implementation("com.google.firebase:firebase-messaging")
    implementation("androidx.work:work-runtime:2.10.1")
    androidTestImplementation("androidx.test.uiautomator:uiautomator:2.3.0")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test:rules:1.6.1")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}