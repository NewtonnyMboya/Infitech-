# Railway deployment checklist (sandbox only)

This project is a Node.js/Express starter. These steps prepare a Railway deployment; they do not create a Railway project, buy a domain, or connect credentials on your behalf.

## 1. Deploy the repository

1. Create a private Git repository and upload the contents of this package (the `package.json` and `server.js` should be at the service root, or configure Railway's root directory to `infigen_marketplace`).
2. In Railway, create a project and deploy from that repository.
3. Confirm the service uses Node.js 20+ and the start command `npm start`. The included `railway.json` configures `/api/health` as its health check.
4. Generate a Railway domain in the service's Networking settings. Use the exact generated HTTPS domain for the callback.

## 2. Attach persistent storage

Add a Railway Volume mounted at `/data`. Set `DATA_DIR=/data`. Keep only one running replica while this starter uses JSON files; concurrent writes and multi-replica operation are not safe. Before production, migrate orders, products, payments, and entitlements to managed PostgreSQL with transactions and unique constraints.

## 3. Add Railway service variables

Set these in the service's Variables page. Never commit them to Git or paste secrets into support chats.

- `NODE_ENV=production`
- `DATA_DIR=/data`
- `MPESA_ENVIRONMENT=sandbox`
- `MPESA_CONSUMER_KEY` = Consumer Key for your own Daraja sandbox app
- `MPESA_CONSUMER_SECRET` = Consumer Secret for that app
- `MPESA_SHORTCODE` = the Daraja sandbox Lipa Na M-Pesa Online shortcode shown in the official test credentials (commonly `174379` for STK Push)
- `MPESA_PASSKEY` = the sandbox Lipa Na M-Pesa Online passkey from the official test credentials
- `MPESA_TRANSACTION_TYPE=CustomerPayBillOnline` (only if this matches your sandbox product/configuration)
- `MPESA_CALLBACK_URL=https://YOUR-RAILWAY-DOMAIN/api/mpesa/callback`
- `ADMIN_API_TOKEN` = a unique, high-entropy random token, at least 32 random bytes
- `ALLOW_LIVE_PAYMENTS=false`

Do not copy production credentials into sandbox variables. Keep `ALLOW_LIVE_PAYMENTS=false` and `MPESA_ENVIRONMENT=sandbox` throughout testing.

## 4. Verify service health

Open `https://YOUR-RAILWAY-DOMAIN/api/health`. Expect `ok: true`, `environment: "sandbox"`, and `checkoutEnabled: true` only after all required M-Pesa variables and a valid HTTPS callback are configured. If checkout remains disabled, inspect the service logs and verify variable names and values (do not log the secrets themselves).

## 5. Test in the Daraja sandbox

1. Create a Daraja account and a sandbox app at https://developer.safaricom.co.ke/ and enable the required M-Pesa Express/STK Push API product.
2. Use only Safaricom's sandbox test credentials and supported test-number flow. A real customer payment must never be used for this test.
3. Add a low-value test listing that you own/control. For publishing through `/api/admin/products`, set `active: true` only with `rightsBasis`, `sourceUrl`, and `proofReference`; open-source items also need `licenseUrl`.
4. Complete successful, cancelled, timeout, wrong-PIN, duplicate-callback, delayed-callback, and unknown-checkout tests. Confirm an order is not marked paid and no download/license appears until verification succeeds.
5. Test expired download links, invalid order access tokens, missing product files, service restart, and volume persistence.
6. Reconcile the order's amount, phone number, receipt and provider status before enabling fulfillment. The callback handler now requires callback amount/phone/receipt consistency plus a successful Daraja query; test that behavior with actual sandbox responses.

## 6. Before real payments

This package is not production-certified. Migrate the JSON store to PostgreSQL, implement scheduled reconciliation for `payment_verification_pending`, add transactional/idempotent payment fulfillment, secure/admin-authenticate catalog operations, rate limits and alerting, backups and restore tests, and review licensing, refund, tax, privacy, customer support and malware-scanning requirements. Only switch to production after Safaricom merchant onboarding, production credentials and live callback configuration are approved and tested.
