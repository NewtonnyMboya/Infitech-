# SchoolCore merged APK engineering audit

## Scope

This audit is based on the uploaded `schoolcore (1).apk` (1,073,885 bytes), not an Android Studio source project. Its embedded web assets can be extracted and reviewed, but APK repackaging and Android package signing require the Android SDK build tools.

## Embedded asset inventory

| Asset | Finding |
|---|---|
| `assets/android-api.js` | Finance API is backed by the native `AndroidStore` bridge; local finance records include students, payments, expenses, users, settings and audit entries. |
| `assets/supabase-cloud.js` | Supabase email auth and manual finance JSON snapshot backup/restore only. It uses `finance_snapshots`, which is not part of the proposed normalized schema migration. |
| `assets/supabase-config.js` | Project URL and publishable key are blank in the supplied APK. |
| `assets/student-report.html` | Academic workspace is persisted in browser `localStorage` under `aserfg_db_v1`; it contains students, subjects, marks, attendance, grading bands, accounts, history and settings. |
| `assets/app.js` | Finance UI can send a student roster into the academic iframe using `SCHOOLCORE_IMPORT_FINANCE_ROSTER`. |
| `assets/android-bridge.js` | Small native bridge wrapper used by the WebView app. |

## Confirmed integration gaps

1. Finance and academic records have independent local stores.
2. The finance cloud client only uploads/restores the finance JSON snapshot.
3. Academic `syncNow()` sets an offline-only status; it does not call Supabase.
4. The finance-to-academic roster message copies admission number, name, class and stream; it does not establish a shared server-side student UUID.
5. The proposed normalized database migration has a shared `students` table, but an adapter is still required to map local integer/string IDs to stable server UUIDs and to map the academic workspace's exam/term/grade model to `academic_terms`, `assessments`, `subjects`, `marks` and `attendance`.

## Recommended integration sequence

1. Apply and validate the normalized schema migration in the target Supabase project.
2. Create the school and first admin membership; invite additional Supabase Auth users and assign least-privilege roles.
3. Add a durable local-to-cloud ID map keyed by school + local record type + local ID. Use deterministic idempotency keys for payments and marks; never deduplicate financial receipts by amount/date alone.
4. Build one parent WebView Supabase session owner. The academic iframe should request sync through a validated same-origin message bridge; it should not create a second independent auth session or store access tokens in localStorage.
5. Upsert the shared student identity first by `(school_id, admission_no)`, then use the returned student UUID for finance and academic child records.
6. Map finance fee totals to `fee_accounts`, payments to `fee_payments`, expenses to `expenses`; map academic terms, exams, subjects, marks and attendance to their normalized tables. Preserve original local IDs in the sync map.
7. Add an offline outbox, retry/backoff, conflict policy, sync status and reconciliation report. Do not silently overwrite newer server data.
8. Test with two schools and at least two users per school. Verify RLS isolation, role boundaries, duplicate retry safety, offline/online transitions and restore from backup before any real data migration.
9. Only after tests pass, enable background/foreground sync and consider Supabase Realtime subscriptions scoped to the selected school.

## Data safety rules

- Keep existing AndroidStore and localStorage records intact until cloud counts and reconciliation checks pass.
- Do not use whole-database snapshot restore as normal synchronization.
- Do not sync local app login password hashes or local account records into Supabase.
- Treat student, guardian and academic records as confidential; use least-privilege school membership and RLS.
- The publishable key is client configuration, not authorization. RLS is the security boundary. Never put a service-role/secret key in the APK or repository.
- The previously supplied publishable key is intentionally omitted from this repository documentation and from source control.

## Android signing and packaging

A local `jarsigner -verify` check on the uploaded APK reports that the JAR signature verifies and identifies the signer as:

- Subject: `CN=SchoolCore, OU=Release, O=SchoolCore, L=Nairobi, ST=Nairobi, C=KE`
- Signature: RSA 2048 / SHA-256
- Certificate: self-signed; no timestamp; certificate validity reported through 2054-04-04.

A self-signed certificate is expected for many Android app signing keys. The missing public trust chain warning from `jarsigner` does not by itself mean the APK signature is corrupt. The original keystore and alias have been supplied by the owner and the earlier certificate comparison matched the APK signer.

This runtime currently has Java 21 and `jarsigner`, but does not have `apksigner`, `zipalign` or `apktool`. A final Android update must be rebuilt/repackaged, aligned, signed with the matching private key, and verified with Android `apksigner` (including the supported v1/v2/v3 schemes). Do not treat a JAR-only signature verification as final Android package verification.

The APK's binary AndroidManifest.xml has not yet been decoded here, so package name, versionCode, minSdkVersion and targetSdkVersion must be extracted before producing an installable update. Preserve the application ID and increment versionCode. Never change the signing key. The keystore password and private key must remain local and must not be committed to GitHub or pasted into chat.

## Current status

- APK extracted and embedded JS/HTML assets inspected.
- Finance/academic sync gap confirmed.
- Existing normalized Supabase schema and RLS foundation is in the repository branch `feat/unified-schoolcore-supabase`.
- APK binary is not modified and no replacement APK is claimed.
- Supabase migration has not been applied; RLS tests and real data migration have not run.
- Android packaging toolchain and manifest decoding remain prerequisites to producing a final installable APK.
