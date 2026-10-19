# InfiGen M-Pesa Daraja setup and test checklist

## Current status
- Daraja STK Push initiation is implemented for sandbox/production endpoints, using server-side credentials.
- Order IDs, server-side catalog totals, pending states and order access tokens are implemented.
- The callback attempts an STK Push query before marking a successful payment as paid. If query verification is not available, fulfilment remains pending.
- Paid orders receive expiring download tokens and generated license strings for items marked `licenseRequired`.
- No merchant credentials were supplied. The package has not been deployed or tested against the user's Daraja account, and must not be considered production-ready.

## Configuration
Set these in Railway or the hosting provider's secret-variable settings:
- `MPESA_ENVIRONMENT=sandbox`
- `MPESA_CONSUMER_KEY`
- `MPESA_CONSUMER_SECRET`
- `MPESA_SHORTCODE`
- `MPESA_PASSKEY`
- `MPESA_TRANSACTION_TYPE=CustomerPayBillOnline` only if this matches the shortcode's supported transaction type
- `MPESA_CALLBACK_URL=https://YOUR-DOMAIN/api/mpesa/callback`
- `DATA_DIR=/data` with a persistent private volume mounted there
- `ADMIN_API_TOKEN` as a long random secret
- `ALLOW_LIVE_PAYMENTS=false`

Use the official Safaricom Daraja portal to obtain credentials and confirm the correct shortcode, passkey and transaction type. Never paste production secrets into source code, commit them, or send them in chat.

## Sandbox test plan
1. Deploy to a publicly reachable HTTPS domain and verify `/api/health`.
2. Register the exact callback URL in your Daraja configuration if required by your app setup.
3. Add a legitimate test product using `POST /api/admin/products`; place its file under `DATA_DIR/files/` if it is downloadable.
4. Make a sandbox checkout using a supported test phone number and complete the simulated prompt.
5. Verify callback receipt, provider query result, order status, amount, receipt fields and only then download/license availability.
6. Exercise cancelled/failed payment, duplicate callback, delayed callback, unknown checkout ID, provider outage, expired token and missing file cases.
7. Confirm that manipulating browser prices, product IDs, quantities or order IDs cannot produce free access or access to another order.

## Before enabling live payments
Use a persistent transactional database, implement rate limiting and scheduled reconciliation, review callback verification against current Daraja documentation, configure monitoring/backups/email delivery, and complete security and legal reviews. Only set `ALLOW_LIVE_PAYMENTS=true` after a merchant-approved production readiness review. An STK Push accepted response is not proof that the customer paid.
