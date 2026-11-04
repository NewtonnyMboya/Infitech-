# Infinity Money Transfer Android app

Standalone Android Studio starter project. Initial KSh 1,000,000 is demo-only and not real or withdrawable funds.

## Build
Open this folder in Android Studio with JDK 17 and Android SDK 35. Build with `gradle assembleDebug`. APK output: `app/build/outputs/apk/debug/app-debug.apk`.

## Skrill
The app opens the official Skrill website and offers a demo transfer flow. Live payment creation is intentionally disabled. Live use requires an approved Skrill merchant account, provider-approved API access, HTTPS backend, server-side secrets, verified payment status/callbacks, idempotency, a database ledger, and legal/compliance review. Never place merchant secrets in the APK.
