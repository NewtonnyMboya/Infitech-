# Supabase setup for InfiGen

This migration foundation moves marketplace persistence from local JSON files to managed PostgreSQL. It is designed for the existing Express backend and keeps the Daraja integration server-side.

## 1. Create the project

1. Create a Supabase project in the region closest to your customers and application host.
2. Open **SQL Editor** and run `supabase/schema.sql`.
3. In **Project Settings → API**, copy the Project URL and the `service_role` key. Store both only in Render's secret environment settings. Never put the service-role key in browser JavaScript, GitHub, screenshots, or chat.
4. Create a private Storage bucket named `infigen-products` (the SQL also creates it).

## 2. Required server environment variables

- `SUPABASE_URL`: project URL
- `SUPABASE_SERVICE_ROLE_KEY`: service-role secret
- Keep `MPESA_ENVIRONMENT=sandbox` and `ALLOW_LIVE_PAYMENTS=false`.

## 3. Data model

- `products`: catalog, price and sourcing evidence.
- `orders`: payment state, provider references and hashed order-access token.
- `order_items`: immutable purchase-time product names and prices.
- `entitlements`: per-purchase download-token hashes and generated license keys.
- `infigen-products`: private digital product files.

RLS is enabled and direct access from `anon` and `authenticated` is revoked. The trusted Express backend must use the service-role key. Never expose that key to the storefront.

## 4. Migration status and safe rollout

The SQL schema is the database foundation, not proof that the live application has been switched over. The existing Express routes still use the JSON store until the backend adapter and data migration are implemented and verified. Do not point production traffic at this schema yet.

Before cutover:
1. Implement and test the Supabase repository adapter for catalog, orders, order items and entitlements.
2. Add an idempotent import of existing `products.json` and `orders.json`; preserve order IDs, status, provider request IDs, token hashes and receipts. Never import raw customer access tokens (the app stores only hashes).
3. Move private files into the private Storage bucket and verify signed downloads after paid-order authorization.
4. Add transactional fulfillment and callback idempotency; reconcile pending payments with Daraja.
5. Run migration tests against a separate Supabase staging project, then freeze writes and take a final backup before cutover.

The current JSON files should be retained as a rollback snapshot until post-cutover reconciliation is complete. No live payment mode is enabled by this change.
