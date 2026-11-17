# SchoolCore merged APK engineering audit

## Scope

This audit is based on the uploaded `schoolcore (1).apk` (1,073,885 bytes), not an Android Studio source project. Its embedded web assets can be extracted and reviewed, but APK repackaging and Android package signing require the Android SDK build tools.

## Embedded asset inventory

| Asset | Finding |
|---|---|
| `assets/android-api.js` | Finance API is backed by the native AndroidStore bridge; local finance records include students, payments, expenses, users, settings and audit entries. |
| `assets/supabase-cloud.js` | Original APK had Supabase email auth and manual finance JSON snapshot backup/restore only. |
| `assets/supabase-config.js` | Project URL and publishable key were blank in the supplied APK. |
| `assets/student-report.html` | Academic workspace is persisted in browser localStorage under `aserfg_db_v1`; it contains students, subjects, marks, attendance, grading bands, accounts, history and settings. |
| `assets/app.js` | Finance UI can send a student roster into the academic iframe using `SCHOOLCORE_IMPORT_FINANCE_ROSTER`. |
| `assets/android-bridge.js` | Small native bridge wrapper used by the WebView app. |

## Confirmed integration gaps

1. Finance and academic records have independent local stores.
2. The original finance cloud client only uploaded/restored a JSON finance snapshot.
3. Academic `syncNow()` sets an offline-only status; it does not call Supabase.
4. The finance-to-academic roster message copies admission number, name, class and stream; it does not establish a shared server-side student UUID.
5. The normalized database and offline outbox exist, but a full adapter is still required to map finance and academic records into those tables.

## Recommended integration sequence

1. Complete multi-school onboarding and validate RLS isolation.
2. Add a durable local-to-cloud ID map keyed by school + local record type + local ID.
3. Use one parent WebView Supabase session owner; the academic iframe should request sync through a validated same-origin message bridge and must not create a second independent auth session.
4. Upsert shared student identity first by (school_id, admission_no), then use the returned student UUID for finance and academic child records.
5. Map fee accounts, payments, expenses, terms, subjects, assessments, marks and attendance into normalized tables.
6. Add an offline outbox, retry/backoff, conflict policy, sync status and reconciliation report.
7. Test with at least two schools and users per school before importing real records.

## Data safety rules

- Keep existing AndroidStore and localStorage records intact until cloud counts and reconciliation checks pass.
- Do not use whole-database snapshot restore as normal synchronization.
- Do not sync local app login password hashes or local account records into Supabase.
- Treat student, guardian and academic records as confidential; use least-privilege school membership and RLS.
- The publishable key is public client configuration, not authorization. Never put a Supabase service-role/secret key in the APK.
- The keystore password and private key must remain local and must not be committed to GitHub or pasted into chat.

## Android signing and packaging

A local `jarsigner -verify` check on the uploaded APK reports that the JAR signature verifies and identifies the signer as:

- Subject: `CN=SchoolCore, OU=Release, O=SchoolCore, L=Nairobi, ST=Nairobi, C=KE`
- Signature: RSA 2048 / SHA-256
- Certificate: self-signed; no timestamp; certificate validity reported through 2054-04-04.

This runtime currently has Java 21 and `jarsigner`, but does not have `apksigner`, `zipalign` or `apktool`. A final Android update must be rebuilt/repackaged, aligned, signed with the matching private key, and verified with Android `apksigner`. Do not treat a JAR-only signature verification as final Android package verification.

The APK's binary AndroidManifest.xml has not yet been decoded here, so package name, versionCode, minSdkVersion and targetSdkVersion must be extracted before producing an installable update. Preserve the application ID and increment versionCode. Never change the signing key.

## Current status

- APK extracted and embedded JS/HTML assets inspected.
- Base school schema migration `schoolcore_unified_schema_v2` was applied to Supabase project `unytieqnfzkmxhifovtn`; 12 school tables were created with RLS enabled.
- Additive migration `schoolcore_sync_identity_outbox_v1` was applied; it adds local/cloud ID mapping, an offline outbox and a role-checked student upsert RPC.
- Tenant RPC grant migration `schoolcore_restrict_tenant_rpc_grants` was applied and committed. Anonymous execution of `create_school` was tested and rejected with `Authentication required`.
- Two temporary Auth identities and two temporary schools were created inside a rolled-back SQL transaction to exercise RLS. Each user saw exactly one school and one student; cross-school student reads returned zero for both users. All test rows were rolled back.
- A replacement onboarding asset patch was prepared. It adds administrator self-registration, email-confirmation guidance, school creation, school selection and staff-role assignment. It keeps access tokens in memory and leaves the old personal finance snapshot explicitly separate from normalized sync.
- The Node mock test passed for registration-pending state, sign-in, school creation, creator admin role, staff-role validation and sign-out.
- Supabase hosted Auth confirmation settings still need dashboard verification. Hosted Supabase projects default to email confirmation enabled, but the connected project tools cannot toggle this setting. See `schoolcore-apk-patch/README.md`.
- No real signup email was sent because no test mailbox was supplied; email delivery and confirmation remain unverified.
- The APK binary is not modified and no replacement APK is claimed. The supplied APK does not include a separate Android Studio source project, and Android packaging tools are unavailable in this runtime.
- Normalized finance/academic record synchronization remains unfinished. The onboarding UI patch does not yet synchronize student, payment, expense, mark or attendance data.
