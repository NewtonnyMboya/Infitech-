# InfiGen M-PESA sandbox payment flows

This branch adds an authenticated **sandbox-only** M-PESA request flow for:
- Collection: STK Push (customer approves on their phone)
- Payout: B2C request (sandbox disbursement)

It does not enable production, and it does not credit/debit an InfiGen balance. Provider callbacks are treated as untrusted notifications and stored for reconciliation only. Do not use real customer data.

## Deploy prerequisites
1. Apply `supabase/migrations/20261110000000_infigen_mpesa_sandbox_journal.sql`.
2. Deploy `mpesa-payment-initiate` with JWT verification enabled.
3. Deploy `mpesa-payment-callback` with JWT verification disabled because Safaricom calls it server-to-server. It must remain publicly reachable over HTTPS.
4. Set only sandbox credentials for testing:
   - `DARAJA_SANDBOX_CONSUMER_KEY`
   - `DARAJA_SANDBOX_CONSUMER_SECRET`
   - `DARAJA_SANDBOX_SHORTCODE`
   - `DARAJA_SANDBOX_PASSKEY`
   - `DARAJA_SANDBOX_B2C_SHORTCODE`
   - `DARAJA_SANDBOX_B2C_INITIATOR_NAME`
   - `DARAJA_SANDBOX_B2C_SECURITY_CREDENTIAL`
   Supabase provides `SUPABASE_URL`, `SUPABASE_ANON_KEY`/publishable key and `SUPABASE_SERVICE_ROLE_KEY` to Edge Functions.
5. Configure Safaricom sandbox test numbers and verify callbacks in logs.

## Request body
POST `/functions/v1/mpesa-payment-initiate` with authenticated Supabase bearer token and JSON:
`{"flow":"collection","phone":"0712345678","amount":10,"idempotencyKey":"a-unique-random-key-at-least-16"}`
or `flow:"payout"`. Amount is KES, whole shillings. Use the same idempotency key to retry safely; the endpoint does not resend a previously journaled request.

## Before any production release
The implementation must be reviewed and completed with provider-approved production access, verified callback authenticity/reconciliation, transaction-status queries, atomic ledger posting, payout authorization/limits, audit and fraud controls, and end-to-end sandbox tests. Never enable live money movement by setting an environment variable alone.
