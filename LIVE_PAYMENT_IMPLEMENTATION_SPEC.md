# InfiGen live payment implementation specification

Status: PRE-AUTHORIZATION — collection and payout flows requested; live money movement MUST remain disabled.

## Required provider products
- M-PESA collection: Daraja customer-initiated payment/STK Push, subject to the active Daraja documentation and merchant product.
- M-PESA payout: Business-to-Customer (B2C), subject to the appropriate disbursement shortcode/account and production entitlement.
- Airtel Money collection: Kenya-market collection product enabled for the merchant application.
- Airtel Money payout: Kenya-market disbursement product enabled for the merchant application.
Treat each provider/product pair as a separate capability. Credentials or approval for one do not imply approval for another.

## Service boundary
The Android app may submit an authenticated intent only. It must never call provider APIs directly, hold provider secrets, decide final transaction status, or credit the ledger from a client redirect. Provider requests, callback validation, status queries, reconciliation and ledger posting belong in Supabase Edge Functions and database transactions.

## Canonical transaction lifecycle
1. Authenticate the Supabase user and verify ownership of the destination/source account.
2. Validate a whole-KES amount within configured limits, KES currency, normalized Kenyan phone number, provider, flow, and per-user/merchant limits.
3. Insert a pending payment intent with a server-generated UUID idempotency key and immutable amount/currency/user/provider/flow fields.
4. Call the provider from the server with a bounded timeout and a safe correlation ID. Never treat an HTTP acknowledgement as final payment success.
5. Receive the provider callback at a public HTTPS endpoint. Validate documented callback authentication/signature, bind it to a known intent, enforce event uniqueness/replay protection, and persist the raw event only after redaction/retention rules are applied.
6. If callback delivery is absent or ambiguous, query provider status using the documented reconciliation API where available. A timeout must remain pending/unknown, not become success or failure by guess.
7. In one database transaction, transition a known pending intent and insert balanced, immutable ledger entries exactly once only after independently verified success. Reject amount, currency, account, or reference mismatches.
8. Support failed, cancelled, expired, reversed, refunded and disputed states; payout flows need separate reversal/compensation handling. Never silently edit historical ledger entries.
9. Emit redacted audit events and metrics for initiation, callback verification, reconciliation, ledger posting, administrative changes and failures.

## Required controls
- Idempotency for both client initiation and provider callback/event processing.
- Unique constraints for provider + provider reference/event ID and a unique ledger posting per intent.
- Server-side rate limits, amount limits, beneficiary allowlists/step-up confirmation for payouts, and velocity/fraud checks.
- Strict separation of sandbox and production credentials, endpoints, callback URLs and data.
- Secrets only in Supabase Edge Function secrets. Never expose them in Android assets, client bundles, database rows, logs or chat.
- Restrictive CORS where practical; bearer authentication on customer endpoints; callbacks use the provider's documented verification mechanism, not customer bearer auth.
- Redact access tokens, secrets, PINs, OTPs, full phone numbers and sensitive provider payloads from logs.
- Monitoring and an operator process for stuck transactions, provider outages, complaints, refunds and reconciliation breaks.

## Acceptance gates — independently for all four provider/product pairs
- Provider sandbox credentials and exact current API contract confirmed.
- Adapter unit tests and mocked contract tests pass.
- Sandbox end-to-end tests pass: success, rejection, invalid phone, cancellation, duplicate initiation, duplicate callback, invalid callback, out-of-order events, timeout, retry, late callback, reconciliation, and reversal/refund or documented manual handling.
- Database concurrency test proves one intent cannot post twice.
- Security review confirms callback verification, RLS, ownership checks, secret isolation, limits and redacted logs.
- Merchant has written production enablement for the exact product, production credentials and approved settlement account.
- Legal/compliance review and operational runbooks completed.
- A separate, explicit production feature flag is enabled only after all gates pass. Missing, false, malformed or unavailable configuration must fail closed.

## Current blocking facts
Production authorization is pending. No provider credentials or sandbox test evidence has been supplied/verified in this repository. Therefore no real collection or payout may be initiated, and a provider response, redirect, or client-side screen must never be represented as a completed payment. The existing payment-initiate function must continue returning live_payments_disabled for production and must not advertise sandbox checkout as functional until the adapter and callbacks are implemented and tested.


## M-PESA STK sandbox implementation status (2026-11-09)

The branch now contains:
- `supabase/migrations/202611090003_mpesa_stk_intents.sql`: payment intent and redacted provider-event tables, owner-only intent reads, uniqueness/idempotency constraints.
- `supabase/functions/mpesa-stk-sandbox-initiate/index.ts`: sandbox-only STK initiation, authenticated caller, account ownership check, Kenyan phone/amount validation, server-side credentials, idempotency key, bounded provider requests, and conservative unknown status for ambiguous failures.
- `supabase/functions/mpesa-stk-callback/index.ts`: callback intake with body hash and redacted metadata. It only records callback arrival and does not credit balances or mark success.
- `supabase/functions/banking-readiness/index.ts`: independent collection and payout readiness reports.

Important limitations:
- These files are committed to GitHub; they have NOT been deployed to Supabase by this change.
- No credentials have been tested, no sandbox request has been made, and no end-to-end callback has been verified.
- The existing Android app's payment initiation flow has not yet been confirmed wired to the new sandbox function.
- A separate STK status/reconciliation function is still required. Only that server-side verifier may finalize an intent after matching provider-confirmed checkout ID, result, amount, merchant/shortcode, and receipt. Ledger posting must be atomic and idempotent.
- The callback endpoint is public and treats every incoming callback as untrusted. Never trust its ResultCode, phone, amount or receipt by itself.
- Production stays disabled. Do not add production endpoint selection or production secrets to the sandbox function.
