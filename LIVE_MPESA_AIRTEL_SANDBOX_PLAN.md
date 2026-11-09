# InfiGen M-PESA and Airtel Money secure integration plan

## Current state
Production approval is not yet obtained and neither provider's credentials are configured. Live money movement remains disabled. The existing payment-initiate Edge Function rejects production requests (403) and refuses sandbox checkout (503) until a tested provider adapter and callback handling are deployed.

## M-PESA (Safaricom Daraja)
- Complete Safaricom business onboarding and register through the official Daraja developer portal.
- Obtain sandbox credentials and approved test shortcode/passkey.
- Confirm the required product: customer collection (such as STK Push) and/or disbursement are separate capabilities.
- Configure secrets only in Supabase Edge Function secrets: DARAJA_CONSUMER_KEY, DARAJA_CONSUMER_SECRET, DARAJA_SHORTCODE, DARAJA_PASSKEY.
- Complete sandbox certification, callback verification and reconciliation, then obtain written production approval.

## Airtel Money
- Complete Airtel Africa merchant/developer onboarding for Kenya.
- Confirm collection versus disbursement product, settlement arrangement, sandbox access and callback requirements.
- Configure credentials only as Supabase Edge Function secrets: AIRTEL_CLIENT_ID, AIRTEL_CLIENT_SECRET, plus product-specific callback/signing material.
- Complete provider sandbox tests and obtain written production approval.

## Required implementation before enabling sandbox checkout
1. Provider API adapters execute only server-side in Supabase Edge Functions, never in Android assets.
2. Authenticate each customer and validate amount, KES currency, phone number, provider, transaction type and account ownership server-side.
3. Create a pending intent before provider request; never credit an account from a client-side success message or redirect.
4. Use provider OAuth/tokens, TLS, bounded timeouts, safe retries and unique idempotency keys.
5. Verify callbacks using the provider's documented authentication/signature mechanism; reject invalid callbacks.
6. Enforce unique provider event/reference IDs and idempotent callback processing.
7. Confirm final status through provider status-query/reconciliation where available.
8. Post ledger entries atomically only after verified provider success; support failed, expired, reversed and disputed states.
9. Redact credentials, authorization headers, full phone numbers and sensitive payloads from logs; apply rate limits and fraud controls.

## Sandbox test matrix
For each provider/product: success, invalid phone, invalid amount, user cancellation, provider rejection, timeout, duplicate initiation, duplicate callback, invalid callback authentication, out-of-order callback, status-query reconciliation, reversal/refund and retry after server restart.

## Production activation gates
Written provider production approval; production credentials in Supabase secrets; authenticated callbacks; end-to-end certification and reconciliation sign-off; review of applicable Kenyan legal, regulatory, AML/KYC, consumer-protection and data-protection obligations; monitoring, incident response and dispute/refund operations. Production remains disabled until every gate is independently met for each provider.

Never put service-role keys, provider secrets, passkeys, PINs, OTPs or signing keys in source control, Android assets, logs or chat.
