# InfiGen live-banking readiness (implementation status)

This branch adds a secure starting point; it does NOT make the app a licensed bank or enable real-money transfers.

## Added in this change
- Android INTERNET permission for HTTPS backend calls. Cleartext HTTP is explicitly disabled.
- Supabase migration for profiles, KES accounts, transactions, provider attempts and audit events, with row-level security and own-record read policies.
- Atomic post_infigen_demo_transaction database function. It is restricted to the authenticated user's own demo account, bounds the amount, prevents negative balances, and records an audit event. It cannot post to a live account.
- Authenticated Edge Function banking-readiness, which reports only readiness flags and never returns provider secrets.
- Authenticated payment-initiate guard which fails closed. It intentionally does not initiate payments yet.

## Deploy the database migration
Review supabase/migrations/202611090001_infigen_banking_foundation.sql in the Supabase SQL editor, back up the project, then apply it to the intended project. Verify RLS and RPC grants with two separate test users before connecting the app. This repository change does not deploy the migration.

## Deploy Edge Functions
Deploy:
- supabase/functions/banking-readiness/index.ts
- supabase/functions/payment-initiate/index.ts

Keep provider credentials in Supabase Edge Function Secrets only. Never add consumer secrets, passkeys, Airtel client secrets, service-role keys, PINs, OTPs, or signing keys to Android assets, source control, screenshots, or client-side environment variables.

Expected secret names:
- DARAJA_CONSUMER_KEY, DARAJA_CONSUMER_SECRET, DARAJA_SHORTCODE, DARAJA_PASSKEY
- AIRTEL_CLIENT_ID, AIRTEL_CLIENT_SECRET
- MPESA_PRODUCTION_APPROVED, AIRTEL_PRODUCTION_APPROVED (must remain false until approval is documented)

Setting credentials alone does not make an integration functional. Provider-specific sandbox requests, callback authenticity, idempotency, transaction status reconciliation, reversals, rate limits, alerting and security tests remain required. Do not set production approval flags without the provider's written approval and the applicable legal authorization.

## Client integration still required
The current Android activity loads a bundled HTML asset. The screens must be wired to the authenticated Supabase session, call the readiness function, fetch only the current user's accounts and transactions, and call the demo RPC. Do not allow the browser UI to update balances directly. Do not present a payment as successful until verified by the server/provider.

## Build and release
The current GitHub Actions workflow builds a debug APK. Use it for testing only. A release APK requires a controlled signing key stored in GitHub Actions secrets or a secure release environment, plus dependency review, tests, backup/restore verification, and release signing. Do not commit a keystore or signing passwords.

## Provider onboarding
- M-PESA: https://developer.safaricom.co.ke/
- Airtel Africa: https://developers.airtel.africa/
- Supabase Edge Function secrets: https://supabase.com/docs/guides/functions/secrets
- Supabase data security/RLS: https://supabase.com/docs/guides/database/secure-data

No real-money transfer should be enabled until the relevant providers approve production use and the service has obtained all required authorizations.
