plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}
android {
    namespace = "com.infinity.moneytransfer"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.infinity.moneytransfer"
        minSdk = 23
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"
    }
}
