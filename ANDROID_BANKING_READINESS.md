# InfiGen Android banking readiness

## What this branch adds
- A standalone Android application project under `android/`.
- A local, offline-capable preview screen with InfiGen branding and launcher icon.
- A GitHub Actions workflow that builds a debug APK and publishes it as a workflow artifact.
- Explicit labels for all banking functions that are not yet connected to real services.

## Current status — not a live banking application
The existing root project is a digital-products marketplace with an M-Pesa checkout flow for marketplace orders. That checkout is not a bank account ledger and must not be reused as proof of deposits to customer accounts.

The Android preview intentionally does not collect National ID numbers, claim to validate identity, create spendable balances, or initiate deposits, withdrawals or transfers. The KSh 500 threshold is a requested product rule, not an authorization to accept deposits or a representation of regulatory approval.

## Required integrations before real-money launch
1. **Identity / KYC:** contract an authorized identity-verification provider. Verify consent, source, exact match rules, audit trails, data retention, appeal/review and access controls. Never infer names from an ID number locally.
2. **Banking authorization:** confirm the operating model and applicable Kenyan regulatory approvals/partner arrangements before offering deposit-taking, stored value, remittance or account services. Obtain Kenyan legal/compliance review.
3. **Payments:** integrate approved M-PESA Daraja services for the correct merchant/business use case, an Airtel Money partner API, and bank transfer rails through contracted banks/aggregators. A customer payment checkout does not itself create an account-to-account banking rail.
4. **Ledger:** implement a server-side double-entry ledger with immutable journal entries, idempotency keys, reconciliation, reversals, limits, fees, holds and audit logs. Never trust a client-supplied balance.
5. **Accounts:** issue unique account identifiers only from the backend with collision-safe constraints. Distinguish an internal wallet/account reference from a regulated bank account number.
6. **Activation:** activate only after a provider-confirmed, reconciled qualifying deposit. Enforce KSh 500 as the requested minimum while applying provider and legal transaction limits; do not promise an unlimited real-world maximum.
7. **Security / privacy:** authentication, MFA, secure recovery, encryption in transit/at rest, secrets management, device/session controls, rate limiting, fraud monitoring, data minimization, backups and incident response.
8. **Production data:** migrate the current JSON-file order store to a transactional database before concurrent financial operations. Add automated reconciliation and independent security testing.

## Build
The workflow `.github/workflows/android-build.yml` builds a debug APK on pushes to `infigen-android-foundation` or by manual dispatch. The APK is a preview shell, not a signed production banking release.

## Provider secrets
Never commit credentials, production API keys, private keys, customer ID data or callback secrets. Use the deployment platform's secret manager and provider sandbox first.
