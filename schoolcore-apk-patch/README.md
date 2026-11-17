# SchoolCore APK onboarding patch

The supplied merged APK already loads `assets/supabase-cloud.js` and `assets/supabase-config.js`. The companion asset patch replaces those two files to add administrator self-registration, email-confirmation guidance, school creation, school selection, staff assignment, and the existing personal finance snapshot controls.

The patch ZIP is delivered in the associated ChatGPT work session. It includes the two replacement assets, a mock onboarding test, and the full replacement instructions. The connected patch includes the configured project URL and the project's publishable client key in `assets/supabase-config.js`; that key is public client configuration, not a service-role secret.

## Flow

1. Administrator enters name, email, and password.
2. Supabase email confirmation is completed; the user returns to the app and signs in.
3. The authenticated user enters the school's name and optional code/county.
4. The `create_school` RPC creates the tenant and grants the creator the first admin membership.
5. The administrator adds staff by the email they registered with and chooses a least-privilege role.
6. A user can select only schools where they have membership.

Staff must self-register first. No default school, school name, shared school password, or service-role key is embedded. Access tokens are memory-only.

## Auth dashboard checklist

In Supabase Dashboard → Authentication → Providers → Email, ensure the Email provider is enabled and **Confirm email** is ON. Set a valid Site URL under Authentication → URL Configuration. For production, configure custom SMTP and enable leaked-password protection. Hosted Supabase projects default to email confirmation enabled, but the setting must be verified by a project owner. The available Supabase project tools cannot change this hosted Auth toggle.

## Validation boundaries

- Mock test: registration-pending state, sign-in, tenant creation, creator admin role, staff-role validation and sign-out.
- Database test: two temporary Auth identities and two temporary schools were used inside a rolled-back transaction. Each identity saw one school and one student; cross-school student reads returned zero.
- Anonymous create-school RPC was rejected with “Authentication required”; anonymous school reads returned zero.
- A real signup email delivery test still needs a real test mailbox.
- The APK has not been rebuilt/re-signed. The original APK assets must be replaced, then the APK aligned, signed with the matching release key, and verified with Android `apksigner`.
- Normalized finance/academic synchronization is still a separate unfinished stage.
