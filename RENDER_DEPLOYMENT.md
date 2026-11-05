# Render deployment (sandbox only)

This blueprint deploys InfiGen as a single Render web service with a persistent disk. It deliberately keeps M-Pesa in sandbox mode and live payments disabled.

## Deploy

1. Push the `cloud-readiness-ci` branch to GitHub (or merge its reviewed changes into your deployment branch).
2. In Render, choose **New + → Blueprint** and connect `NewtonnyMboya/Infitech-`.
3. Select branch `cloud-readiness-ci` and let Render read `render.yaml`.
4. Confirm the service uses the Starter plan and has the persistent disk mounted at `/data`. The JSON-file store requires one running instance; do not increase replicas.
5. Deploy. Render will generate `ADMIN_API_TOKEN`; keep it private.

## Add Daraja sandbox secrets

In the Render service's Environment settings, add these values from your Safaricom Daraja sandbox application:

- `MPESA_CONSUMER_KEY`
- `MPESA_CONSUMER_SECRET`
- `MPESA_SHORTCODE`
- `MPESA_PASSKEY`
- `MPESA_CALLBACK_URL`

Set `MPESA_CALLBACK_URL` to the exact HTTPS URL:
`https://YOUR-RENDER-SERVICE.onrender.com/api/mpesa/callback`

Confirm `MPESA_ENVIRONMENT=sandbox` and `ALLOW_LIVE_PAYMENTS=false`. Do not add production credentials or change either setting for this staging deployment.

## Verify staging

1. Open `https://YOUR-RENDER-SERVICE.onrender.com/api/health`. Expect HTTP 200, `environment: "sandbox"`, and `checkoutEnabled: true` after all five Daraja variables and the HTTPS callback URL are configured.
2. Add only a test product through the authenticated admin product endpoint. Use a product you own or have documented permission to distribute.
3. Test the sandbox checkout end-to-end, including successful prompt approval, cancellation, timeout, duplicate and delayed callbacks, wrong PIN, invalid order token, expired download token, and missing private file.
4. Restart/redeploy the service and confirm catalogue and order data persist on the mounted disk.
5. Confirm that no order is fulfilled merely because an STK prompt was accepted; only a verified payment may grant downloads.

## Important current limitations — not production approved

- The application currently persists products and orders in JSON files. The persistent disk is a staging bridge, not a substitute for a transactional database. Before public production traffic, migrate orders, payments, products, and entitlements to managed PostgreSQL with transactions, unique constraints, and idempotent fulfillment.
- The current callback flow attempts an STK query, but there is no scheduled reconciliation worker for orders stuck in `payment_verification_pending`. Add provider-backed reconciliation and alerting before production.
- Add shared rate limiting, admin origin/CSRF protections appropriate to the final admin authentication model, structured audit logs, monitoring, backup/restore drills, and a documented incident/refund process.
- Verify current Safaricom Daraja callback and query semantics against the official documentation and your merchant account. Test using your own sandbox app.
- This repository configuration does not create a Render account, domain, Daraja credentials, merchant approval, or production approval.

## Live payments remain disabled

Do not set `ALLOW_LIVE_PAYMENTS=true` or switch `MPESA_ENVIRONMENT` to `production` until the database migration, security review, payment reconciliation, provider approval, and a controlled production validation have all passed and been explicitly approved by the merchant.
