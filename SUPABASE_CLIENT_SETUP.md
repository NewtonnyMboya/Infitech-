# InfiGen Supabase client configuration

The Android asset `supabase-config.js` contains the Supabase project URL and the publishable client key supplied for this project. A publishable key is intended to be embedded in a client app; it is not an authorization substitute. RLS, authenticated user sessions, server-side checks and least-privilege policies are mandatory.

Do not place service-role/secret keys, database passwords, payment provider secrets, M-PESA passkeys, Airtel secrets, PINs or OTPs in Android assets or source control.

The current bundled `index.html` is a local demo interface. It does not yet load the Supabase SDK or implement customer sign-in, account synchronization, transaction-history synchronization, or receipt storage. Adding this configuration file alone does not connect the app. The screenshot's customer access interface must be reconciled with this branch's older bundled HTML before wiring authentication and dashboard calls.

Backend SQL and Edge Function files are prepared under `supabase/` but still require review and deployment to the supplied Supabase project. Do not enable production payment processing.
