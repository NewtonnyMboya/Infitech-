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

## Database model

Apply `supabase/migrations/202611170001_unified_schoolcore.sql` to project ref `unytieqnfzkmxhifovtn` with the Supabase CLI:

```sh
supabase link --project-ref unytieqnfzkmxhifovtn
supabase db push
```

The migration establishes school-scoped tables: `schools`, `profiles`, `school_members`, one shared `students` table, finance tables (`fee_accounts`, `fee_payments`, `expenses`), academic tables (`academic_terms`, `subjects`, `assessments`, `marks`, `attendance`), and `audit_events`. Foreign keys ensure finance and academic records refer to the same student UUID. Admission numbers and receipts are unique within a school.

## Secure setup

1. Link the Supabase CLI to project ref `unytieqnfzkmxhifovtn` and apply the migration above.
2. Configure Auth email confirmation and allowed redirect URLs for the actual app origins.
3. Configure the Android build with the project URL above and the supplied publishable key. Keep the key in local build configuration; never embed a service-role key in an APK, browser, or build artifact.
4. A signed-in user calls `create_school(name, code, county)`; the function creates the school and grants the caller its first admin membership.
5. Admins add existing Auth users with `add_school_member(school_id,email,role)`.
6. Test with two separate schools and users. Verify cross-school SELECT/INSERT/UPDATE/DELETE is blocked by RLS before importing real records.

RLS is enabled on all application tables. Finance roles and academic roles have separate write permissions; authenticated school members share read access to the student identity needed by both modules.

## Remaining Android integration (not completed by this schema commit)

The migration is the database foundation, not a rebuilt APK. The current finance-only snapshot client must be replaced by typed table sync; the academic iframe must be changed to use the same Supabase session and shared `students.id`. Migrate local integer IDs to UUID mappings, preserve local data until record counts/checksums reconcile, and queue offline mutations with idempotency keys to prevent duplicate receipts/marks. Add Realtime subscriptions filtered by `school_id` and explicit conflict handling. Do not use whole-snapshot restore for normal synchronization.

Do not load live student or financial records until the migration is applied, RLS isolation tests pass, and the Android client has been migrated. The supplied APK is already packaged/signed; changing embedded assets requires the original build/signing pipeline and a newly signed APK. The GitHub repository currently contains the marketplace/server project and migration/docs, but not the inspected APK's Android source/build project, so the APK client cannot be rebuilt from the repository as it stands.
