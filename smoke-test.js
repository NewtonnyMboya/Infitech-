'use strict';
const assert = require('node:assert/strict');
const base = process.env.SMOKE_TEST_URL || 'http://127.0.0.1:3000';
(async () => {
  const healthResponse = await fetch(`${base}/api/health`);
  assert.equal(healthResponse.status, 200, 'health endpoint should return HTTP 200');
  const health = await healthResponse.json();
  assert.equal(health.ok, true, 'health should report ok');
  assert.equal(health.environment, process.env.EXPECTED_MPESA_ENVIRONMENT || 'sandbox', 'environment must match expected setting');
  const productsResponse = await fetch(`${base}/api/products`);
  assert.equal(productsResponse.status, 200, 'catalog endpoint should return HTTP 200');
  const products = await productsResponse.json();
  assert.ok(Array.isArray(products), 'catalog should be an array');
  for (const product of products) {
    assert.ok(Number.isSafeInteger(product.priceKes) && product.priceKes > 0, `invalid price for ${product.id}`);
    assert.ok(product.name && product.description, `missing listing details for ${product.id}`);
  }
  console.log(JSON.stringify({ ok: true, environment: health.environment, checkoutEnabled: health.checkoutEnabled, productCount: products.length }, null, 2));
})().catch(error => { console.error(`Smoke test failed: ${error.message}`); process.exitCode = 1; });
