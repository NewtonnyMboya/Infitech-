# M-PESA STK sandbox deployment checklist

This branch contains a sandbox-only STK initiation function and a callback intake function. It is not a production payment integration. No Supabase deployment or provider call has been performed by the GitHub edits.

## 1. Apply the database migration

Apply `supabase/migrations/202611090003_mpesa_stk_intents.sql` to the linked Supabase project using the SQL Editor or Supabase CLI after reviewing it. Do not apply it to a different project by mistake.

## 2. Configure only sandbox secrets

Set these in Supabase Dashboard → Edge Functions → Secrets. Use the sandbox values from your Daraja developer application:
- `DARAJA_CONSUMER_KEY`
- `DARAJA_CONSUMER_SECRET`
- `DARAJA_SHORTCODE`
- `DARAJA_PASSKEY`
- `MPESA_STK_CALLBACK_URL` (public HTTPS URL of the deployed callback function)

Never put these values in Android assets, app settings, GitHub source, issues, logs or chat. Do not configure production credentials for the sandbox function. The Supabase service-role key must remain server-only.

## 3. Deploy functions

From a trusted development environment with the Supabase CLI installed and the correct project linked:

```sh
supabase link --project-ref ftcinepxmdyrpwjjtviu
supabase db push
supabase functions deploy mpesa-stk-sandbox-initiate
supabase functions deploy mpesa-stk-callback --no-verify-jwt
supabase functions deploy banking-readiness
```

The callback is a public provider webhook and cannot require a Supabase user JWT. It must remain untrusted: it records redacted callback metadata only and must not credit balances. Keep authentication enabled for the initiation and readiness functions.

If you already applied the migration manually, check the schema version before running `supabase db push`.

## 4. Test sandbox behavior

1. Sign in to InfiGen and use the **M-PESA STK Push · Sandbox test only** section in the APK once that UI update is merged/built. Until then, call the function with an authenticated Supabase session and an `Idempotency-Key` header.
2. Use only a test application/shortcode and test scenario supported by your Daraja sandbox.
3. Confirm the intent is created with `environment='sandbox'` and that an accepted request remains pending.
4. Confirm callback events are recorded as unverified and do not alter any account balance.
5. Verify duplicate idempotency keys do not send another STK prompt.
6. Do not treat callback ResultCode, a checkout acknowledgement, a client redirect, or a printed receipt as proof of payment.

## 5. Still required before any real money

- A separate STK status/reconciliation function must query Daraja and independently match checkout ID, shortcode, amount and result.
- An audited, atomic, idempotent ledger-posting operation must be added and tested only after independent provider verification.
- Sandbox success, rejection, cancellation, duplicate, timeout, retry, late callback and reconciliation tests must pass.
- Safaricom must approve the exact production STK product and issue production credentials.
- Production adapter and configuration must be a separately reviewed release. Do not repurpose this sandbox-only endpoint for production.

Current state: production money movement remains disabled.
