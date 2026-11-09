# Safaricom M-PESA go-live checklist for InfiGen

Status: BLOCKED — production authorization and implementation tests are not yet verified. This checklist does not enable live payments.

## Choose the exact product

- **Collection (customer pays InfiGen):** use the applicable M-PESA Express/STK Push product and an approved live PayBill/Till configuration. STK Push requires the appropriate shortcode and passkey.
- **Payout (InfiGen sends money to a customer):** use the M-PESA Business-to-Customer (B2C) product. Safaricom's current Daraja documentation says production B2C requires an appropriate B2C/one-account shortcode, production app/product access, and an authorized API initiator. A collection passkey does not grant B2C access.
- Collection and payout are independent capabilities. Do not enable one because the other was approved.

## Provider onboarding

1. Sign in to the official Daraja portal: https://developer.safaricom.co.ke/
2. Create or select the app and verify the exact product(s) needed in the current portal documentation.
3. Complete sandbox tests for each product.
4. Apply for production access / Go Live with the appropriate live business shortcode and required business administrator/operator details.
5. Confirm Safaricom has enabled the exact production product and issued production credentials/endpoints. For B2C, confirm the required disbursement account and API operator roles with Safaricom.
6. Store production secrets only in Supabase Edge Function secrets. Never put them in the APK, source files, database rows, issue comments, or chat.

Official references:
- Daraja portal: https://developer.safaricom.co.ke/
- B2C documentation and production requirements: https://developer.safaricom.co.ke/apis/BusinessToCustomer
- Transaction Status API for secondary reconciliation: https://developer.safaricom.co.ke/apis/TransactionStatus

## Required engineering gates before live money movement

- Implement a server-only adapter for each approved product; no provider API calls from the Android app.
- Validate authenticated user, account ownership, KES amount, Kenyan phone number, limits and idempotency.
- Verify callbacks according to current provider documentation, bind events to an existing intent, reject duplicates/replays, and redact sensitive payloads.
- Treat provider acknowledgements as pending; only independently verified success may trigger an atomic, exactly-once ledger posting.
- Add status reconciliation for missing/ambiguous callbacks. Unknown outcomes must remain pending/unknown.
- Test success, rejection, cancellation, duplicate initiation, duplicate callback, invalid callback, timeout, retry, late callback, reconciliation and reversal/compensation.
- Complete security, legal/compliance, monitoring and incident-response reviews.
- Obtain written production authorization for the exact product and confirm settlement/account ownership.
- Have an independent reviewer verify the release gates.

## Current application safeguard

The Supabase `payment-initiate` endpoint must continue returning `live_payments_disabled` for production until the above gates are completed and reviewed. Readiness flags and secret presence are informational; neither alone may turn live money movement on.

Never test a newly enabled production flow using funds or phone numbers without explicit authorization and a controlled test plan.
