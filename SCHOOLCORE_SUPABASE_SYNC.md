# SchoolCore: unified Supabase integration

## Target project

- Supabase project URL: `https://unytieqnfzkmxhifovtn.supabase.co`
- Project ref: `unytieqnfzkmxhifovtn`
- Use the project's publishable key in the Android client only. It is public client configuration, not authorization. Never embed a secret/service-role key in an APK or browser client.

## Database state already applied

The target project already contains the additive SchoolCore database foundation. It was applied through the connected Supabase project tools because the original repository migration conflicted with an existing marketplace `public.profiles` table.

Applied migrations:

1. `schoolcore_unified_schema_v2` — creates 12 school-scoped tables:
   - `schools`
   - `school_member_roles`
   - `school_students`
   - `school_fee_accounts`
   - `school_fee_payments`
   - `school_expenses`
   - `school_academic_terms`
   - `school_subjects`
   - `school_assessments`
   - `school_marks`
   - `school_attendance`
   - `school_audit_events`
2. `schoolcore_sync_identity_outbox_v1` — adds `school_sync_id_map`, `school_sync_outbox`, and the role-checked `school_upsert_student` RPC.
3. `schoolcore_restrict_tenant_rpc_grants` — restricts tenant creation, membership and helper RPC execution to signed-in users.
4. `schoolcore_require_confirmed_staff_email` — requires the target staff Auth account to have a confirmed email before a school admin can add it to a tenant.

All 14 SchoolCore tables have RLS enabled. Existing marketplace tables were preserved. Do not blindly run `supabase db push` against the original `202611170001_unified_schoolcore.sql` file: it is the initial draft and conflicts with the existing marketplace schema. Use the applied database state as the reference and reconcile migration history before any CLI deployment.

## Multi-school onboarding

There is no fixed school name, school code, tenant, administrator email or shared school password. Each school creates its own account and tenant.

1. The administrator opens **School account / registration** on the app's login screen.
2. They enter their name, email and password. Supabase Auth creates the account.
3. With email confirmation enabled, the administrator opens the confirmation email, confirms the address, returns to SchoolCore and signs in.
4. The administrator enters the school's name and optional school code/county.
5. The app calls `create_school(p_name,p_code,p_county)`. The database requires `auth.uid()`, creates the tenant and grants the creator the first `admin` membership.
6. The administrator adds staff using `add_school_member(p_school,p_email,p_role)`. The database rejects an Auth account whose email is not yet confirmed.
7. Users can select only schools where they already have membership. Creating an Auth account alone does not create or join a school.

Allowed staff roles are `bursar`, `accountant`, `teacher`, `exams_officer` and `viewer`; `admin` is reserved for school administration. The database checks the caller's admin membership before adding staff. Users cannot self-join an existing tenant through the app.

## Email confirmation and SMTP

The client signup flow deliberately does not create a school before email verification and successful sign-in. The replacement asset patch displays confirmation instructions and then lets the user sign in.

A project owner must verify these hosted Auth settings in Supabase Dashboard:

1. **Authentication → Providers → Email**: Email provider enabled; **Confirm email** ON.
2. **Authentication → URL Configuration**: a valid Site URL configured for the confirmation redirect.
3. **Authentication → SMTP Settings**: configure a trusted custom SMTP provider before production and test delivery.
4. Auth security settings: enable leaked-password protection and use appropriate rate limits/CAPTCHA protections for public self-registration.

Hosted Supabase projects default to email confirmation enabled, but this integration's connected project tools cannot change the hosted Auth provider toggle. Therefore the setting has not been independently verified or changed here. The current Android WebView flow uses the configured Site URL and asks the user to return to the app after confirmation; it does not yet implement a native Android deep-link callback.

## Android onboarding patch

The supplied merged APK already loads `assets/supabase-cloud.js` and `assets/supabase-config.js`. A replacement asset patch is delivered separately in the associated ChatGPT work session. It adds:

- administrator self-registration and sign-in;
- email-confirmation messaging;
- school creation and school selection;
- staff email and role assignment;
- the original personal finance snapshot controls, kept separate from normalized synchronization.

The client keeps access tokens in JavaScript memory only; users must sign in again after the app/WebView restarts. The patch does not store tokens in localStorage or sessionStorage. Staff must register and confirm their email first, then be added by an administrator.

The onboarding mock test passes. A two-identity/two-school RLS test was run in a temporary SQL transaction and rolled back: each identity saw one school and one student, and cross-school student reads returned zero. Anonymous `create_school` calls failed with `Authentication required`, and anonymous school reads returned zero. The database also rejected adding an unconfirmed staff account and accepted a confirmed account. No real signup email was sent, so delivery and actual email confirmation still require a real test mailbox.

## Important remaining work

- The APK itself has not been modified, rebuilt, aligned, signed or verified. The repository does not contain the Android Studio source/build project, and the current environment lacks `apksigner`, `zipalign` and `apktool`.
- The onboarding patch does not yet synchronize normalized finance or academic records. Finance data still uses AndroidStore, academic data still uses localStorage, and the legacy `finance_snapshots` feature remains a personal backup rather than multi-school synchronization.
- Implement the parent WebView's shared session owner and a typed adapter for finance and academic tables. Map both modules to the same `school_students.id` using `(school_id, admission_no)`; preserve local IDs in `school_sync_id_map` and queue offline writes in `school_sync_outbox`.
- Add retry/backoff, idempotency, conflict resolution, reconciliation reports, and school-scoped Realtime only after the data adapter is complete.
- Run authenticated tests with real test accounts for all roles before importing production student, fee, attendance or examination data.

See [SCHOOLCORE_APK_AUDIT.md](SCHOOLCORE_APK_AUDIT.md) and [schoolcore-apk-patch/README.md](schoolcore-apk-patch/README.md) for the audit and patch notes.
