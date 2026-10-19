# InfiGen Software & Digital Products Marketplace

This package is a marketplace starter with server-side order totals, an M-Pesa Daraja STK Push flow, order status access tokens, payment callback handling with a Daraja STK query attempt, and private download delivery. It is **not approved or tested for live payments**. It must be deployed with persistent private storage and tested with the merchant's own Daraja sandbox credentials before any real customers use it.

## What changed
- Removed fabricated sample products, sale prices, star ratings, review counts and discount claims. The public catalog starts empty until the owner adds verified product information.
- Product listing data is loaded from `/api/products`.
- `/api/checkout` accepts product IDs and quantities only; the server looks up the current catalog prices and computes the order total.
- Order records and private digital files are stored outside the public static web root in `DATA_DIR`.
- Download endpoints only release files for orders marked paid and use expiring per-entitlement tokens. License-required items receive generated license strings after payment verification.
- Checkout stays unavailable without Daraja credentials and an HTTPS callback URL. Live payments additionally require `ALLOW_LIVE_PAYMENTS=true`.

## Deployment and product sourcing

- Railway-specific deployment, persistent volume, environment-variable, and sandbox test instructions: see `RAILWAY_DEPLOYMENT.md`.
- Product sourcing, vendor authorization, open-source compliance, and listing evidence requirements: see `PRODUCT_SOURCING.md`.
- After starting the server, run `npm run test:smoke` (or set `SMOKE_TEST_URL` to the deployed URL) for a basic health/catalog smoke test. This is not an end-to-end payment test.
- The admin API requires evidence fields before publishing an active listing; these fields are review gates, not an automated legal verification.

## Requirements and local setup
- Node.js 20 or newer.
- `npm install`
- Copy `.env.example` to `.env` for local testing and use a local environment-variable loader of your choice, or export variables in your shell. Do not commit `.env`.
- `npm start`
- Open `http://localhost:3000`; health endpoint: `GET /api/health`.

## Product catalog and private delivery files
Catalog records are stored at `DATA_DIR/products.json`. The application creates this file empty on first start. Do not expect sample listings or fabricated prices/ratings; the catalog remains empty until you publish verified products. Add verified products with the authenticated endpoint:

`POST /api/admin/products` with header `x-admin-token: YOUR_ADMIN_API_TOKEN` and JSON body such as:

```json
{
  "id": "my-genuine-app",
  "name": "Verified product name",
  "category": "Software",
  "description": "Accurate description, supported features and license scope.",
  "priceKes": 1500,
  "rightsBasis": "owned",
  "sourceUrl": "https://your-own-product-page.example",
  "proofReference": "internal-ownership-record-001",
  "image": "https://example.com/owned-or-authorized-product-image.jpg",
  "licenseRequired": true,
  "fileName": "my-genuine-app.zip",
  "version": "1.0.0",
  "compatibility": "List verified OS/runtime requirements",
  "active": true
}
```

Use only products you own or are authorized to resell, accurate prices in whole KES, and real license/compatibility terms. For an active product, include `rightsBasis` (`owned`, `authorized_reseller`, or `open_source_compliant`), an official HTTPS `sourceUrl`, and an internal `proofReference`; open-source products also require `licenseUrl`. See `PRODUCT_SOURCING.md`. The `fileName` is optional for hosted products or license-only sales. For downloadable products, place the actual file in `DATA_DIR/files/` using that exact basename. Never put product archives, private license pools, credentials or customer data in the public project folder. Admin product API currently edits product metadata; file upload is intentionally not exposed publicly.

## Order and delivery workflow
1. Customer selects catalog products and enters email and Kenyan phone number.
2. Server validates product IDs/quantities and calculates price from its catalog.
3. Server creates a pending order and asks Daraja to send an STK Push.
4. Customer approves payment on their phone.
5. Daraja calls the HTTPS callback. The app attempts a Daraja STK query before marking the order paid; if verification is unavailable, the order remains pending verification.
6. Only paid orders receive expiring download tokens and generated license strings. The order access token is shown once at checkout; customers must save the private order-status link.

## Daraja sandbox setup
1. Create/configure an application in the official Safaricom Daraja portal and obtain your own sandbox Consumer Key, Consumer Secret, shortcode and Lipa Na M-Pesa passkey.
2. Deploy behind a public HTTPS domain and set `MPESA_CALLBACK_URL=https://YOUR-DOMAIN/api/mpesa/callback` exactly.
3. Configure `MPESA_ENVIRONMENT=sandbox`, the credentials, shortcode and correct transaction type in the deployment's secret manager.
4. Set a long random `ADMIN_API_TOKEN`. Mount a persistent private volume at `DATA_DIR=/data` (or your platform's supported path).
5. Confirm `GET /api/health` reports sandbox and checkout enabled. Add a clearly identified test product with a low sandbox price and test the full prompt/callback/status/download flow.
6. Test success, cancellation, wrong PIN, timeout, duplicate callback, unknown checkout ID, delayed callback, invalid order token and unavailable file. Verify an accepted STK request alone never grants access.

## Production blockers — do not skip
- No Daraja credentials, merchant shortcode, deployment domain or real product inventory were provided; no live provider test was possible from this workspace.
- Use a transactional database (e.g. managed PostgreSQL) instead of the current JSON-file store before handling concurrent production orders. JSON writes are not safe for multi-instance or high-concurrency deployments.
- Add shared rate limiting, CSRF/origin protections for any browser-authenticated admin surface, alerting, structured audit logs, backup/restore drills, and monitoring.
- Review callback verification against current Daraja documentation and reconcile payments with transaction status/receipt data before fulfilment. Add a scheduled reconciliation process for pending callbacks.
- Configure email delivery for receipts and recovery; current customer flow exposes a private order link once at checkout and polls status in the browser.
- Review refund, privacy, consumer protection, tax, software licensing, malware scanning, and seller authorization policies.
- Do not set `ALLOW_LIVE_PAYMENTS=true` until these controls have been reviewed and real low-value production validation is approved by the merchant.
