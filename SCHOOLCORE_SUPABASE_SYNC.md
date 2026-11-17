# SchoolCore: unified Supabase stage

## Configured project target

The project URL supplied for this integration is:

- Project URL: `https://unytieqnfzkmxhifovtn.supabase.co`
- Project ref: `unytieqnfzkmxhifovtn`
- Client credential: publishable key supplied by the project owner; keep it in the local Android build configuration and do not commit it to Git.

The publishable key is designed for client-side use with correctly enforced Row Level Security. Never use or embed a `service_role` or secret key in the APK, browser, or source repository. Since the publishable key was shared in chat, consider rotating it if this conversation is not an appropriate place to share project configuration.

## APK inspection findings

The supplied `schoolcore (1).apk` contains two disconnected persistence paths:

- Finance endpoints in `assets/android-api.js` persist via the native AndroidStore bridge.
- `assets/supabase-cloud.js` signs in to Supabase but only uploads/restores a JSON `finance_snapshots` row.
- Academic data in `assets/student-report.html` is stored in browser localStorage. Its `syncNow()` explicitly sets offline-only status and does not contact Supabase.
- `assets/supabase-config.js` has blank URL and publishable key values.

Consequently, the APK is not currently syncing academic records, and the finance/academic registers are not a shared database. The URL and publishable key are now known, but credentials alone do not apply the schema or change the packaged APK.

## Merged APK audit and signing

See [`SCHOOLCORE_APK_AUDIT.md`](SCHOOLCORE_APK_AUDIT.md) for the extracted asset inventory, integration gaps, recommended sync sequence, and Android signing/toolchain findings. The supplied APK signature verifies with the SchoolCore release signer; a final Android package rebuild and `apksigner` verification are still pending.

## Database model

Apply `supabase/migrations/202611170001_unified_schoolcore.sql` to project ref `unytieqnfzkmxhifovtn` with the Supabase CLI:

```sh
supabase link --project-ref unytieqnfzkmxhifovtn
supabase db push
```

The migration establishes school-scoped tables: `schools`, `profiles`, `school_members`, one shared `students` table, finance tables (`fee_accounts`, `fee_payments`, `expenses`), academic tables (`academic_terms`, `subjects`, `assessments`, `marks`, `attendance`), and `audit_events`. Foreign keys ensure finance and academic records refer to the same student UUID. Admission numbers and receipts are unique within a school.

## Multi-school onboarding with administrator self-registration

SchoolCore is a multi-tenant application. There is no hard-coded school name, school code, tenant, administrator email, or shared school password. Each school administrator can register directly in the app and create a school tenant without an invitation.

1. On first launch, show **Create an account** and **Sign in**. Do not preselect or silently create a school.
2. For self-registration, collect the administrator's name, email, and password through Supabase Auth `signUp`. Never store passwords in application tables, local finance/academic stores, logs, or the Git repository. Show email-confirmation guidance when the Supabase project requires confirmation.
3. After successful registration and a valid authenticated session, show **Create a school**. Collect the school's name and optional school code/county, then call `create_school(name, code, county)`. The database function requires `auth.uid()`, creates the school tenant, and assigns the signed-in caller its first admin membership.
4. If the user already has an account, they sign in and can create a new school or select a school they already belong to. Do not create a tenant automatically on sign-up.
5. The administrator can add staff by their email and assign a least-privilege role using `add_school_member(school_id,email,role)`. The staff member must first register and verify/sign in to their own Auth account; the admin then adds that existing account. Never share one administrator login among staff.
6. On later launches, users sign in and select only from schools where they have membership. A user with no membership must not be able to read or write that school's records.
7. Test at least two separate school tenants and separate users. Verify cross-school SELECT/INSERT/UPDATE/DELETE is blocked by RLS before importing real records.

The existing Supabase publishable key is application configuration, not a school credential. It can be present in a client build with RLS correctly enforced; never use or embed a `service_role` or secret key in the APK, browser, or source repository. Each school's records are scoped by its own school UUID. The same student UUID is shared by finance and academic modules **within that school**, not across different schools.

Registration and tenant creation are distinct steps: creating an Auth account does not create a school. Enable email confirmation and suitable Auth abuse protections/rate limits for public self-registration. Do not expose a client-side path that lets a newly registered user add themselves to an existing school or grant themselves an elevated role. The `create_school` function is authenticated and grants admin only for the new tenant created by that caller.

RLS is enabled on the school tables. Finance and academic writes are restricted by membership role. The Android client still needs the sign-up/sign-in screens, email-confirmation handling, school creation form, school selector, staff-management UI, and actual table synchronization; these are not yet present in the supplied APK.

## Remaining Android integration (not completed by this schema commit)

The migration is the database foundation, not a rebuilt APK. The current finance-only snapshot client must be replaced by typed table sync; the academic iframe must be changed to use the same Supabase session and shared `students.id`. Migrate local integer IDs to UUID mappings, preserve local data until record counts/checksums reconcile, and queue offline mutations with idempotency keys to prevent duplicate receipts/marks. Add Realtime subscriptions filtered by `school_id` and explicit conflict handling. Do not use whole-snapshot restore for normal synchronization.

Do not load live student or financial records until the migration is applied, RLS isolation tests pass, and the Android client has been migrated. The supplied APK is already packaged/signed; changing embedded assets requires the original build/signing pipeline and a newly signed APK. The GitHub repository currently contains the marketplace/server project and migration/docs, but not the inspected APK's Android source/build project, so the APK client cannot be rebuilt from the repository as it stands.
