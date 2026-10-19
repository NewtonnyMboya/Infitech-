# InfiGen product sourcing plan

The live storefront intentionally starts empty. Do not invent prices, ratings, reviews, license keys, or reseller rights. A product page on a vendor's website does **not** automatically grant permission to resell that product.

## Best first inventory: products you own

Start with a small set of digital products that you or your team created and can support:

- Website templates, landing-page themes, UI kits and icon packs.
- Original plugins, scripts, integrations and developer utilities.
- Business templates, spreadsheet tools, automation workflows and setup guides.
- Your own software, with versioned installers, checksums, compatibility notes, refund terms and a clear license.

For every listing, record the author/rights holder, version, tested platform, actual price in KES, delivery file, support contact, refund policy, and license scope. Do not publish until the download has been malware-scanned and tested.

## Official partner routes to investigate for third-party software

These are legitimate starting points for requesting authorization, not a guarantee that an application will be approved or that a product may be sold in Kenya.

- **JetBrains reseller program:** https://www.jetbrains.com/company/resellers/become-a-reseller/ — official page describes Authorized and Premium reseller paths and an application process.
- **Microsoft Cloud Solution Provider (CSP):** https://learn.microsoft.com/en-us/partner-center/enroll/csp-supported-partner-relationships — review eligibility, regional limits and partner/distributor requirements before selling subscriptions.
- **Adobe Solution Partner Program:** https://partners.adobe.com/solution-partners/registration.html — official partner registration and review process; confirm whether your intended products and territory permit resale.

Ask each vendor/distributor for written authorization covering Kenya, allowed channels, advertised prices, license provisioning, renewals, taxes, support obligations, refunds and trademark use. Store the authorization agreement/reference privately and renew it when required.

## Open-source products

Only sell a product or bundle when its license and your distribution method permit it. Preserve required copyright and license notices, include source code or offer it when the license requires, disclose modifications, and do not imply official endorsement. Confirm the specific license for the exact version. Where permission is unclear, offer installation/support services rather than selling the software itself.

## Price and review policy

- Prices: use a dated vendor/distributor quote or your own documented price; state currency, tax treatment, subscription period, renewal and refund conditions.
- Ratings/reviews: do not publish until they come from real, consented customers and can be audited. Never seed fake reviews.
- Product descriptions: use vendor-provided marketing assets only where the terms allow it; otherwise create original text and imagery.
- Keys: generate or provision only valid licenses from an authorized source. The starter's random license strings are placeholders for internal fulfillment mechanics, **not** valid third-party software keys. Do not use that feature to represent vendor activation keys as real.

## Evidence needed before activating a listing

The admin endpoint now requires active listings to provide:
- `rightsBasis`: `owned`, `authorized_reseller`, or `open_source_compliant`;
- `sourceUrl`: HTTPS URL to the official product/source page;
- `proofReference`: internal reference to your ownership evidence, signed reseller agreement, or license review;
- `licenseUrl`: official HTTPS license URL for `open_source_compliant` listings.

`proofReference` is an internal audit reference; it is not independently verified by the application. Keep contracts private and ensure an authorized person reviews the evidence before activating a product.
