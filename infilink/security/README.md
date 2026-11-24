# INFILINK Security (experimental)

This milestone adds standard-library reference primitives in `runtime/python/security.py`:

- **API keys:** high-entropy one-time token issuance, SHA-256 digest storage, constant-time digest comparison, expiry, revocation and bounded in-memory capacity. The plaintext token is returned only at issuance; callers must deliver it securely.
- **Principals and scopes:** successful verification returns a principal with explicit scopes.
- **RBAC:** explicit role-to-permission mapping; no implicit role inheritance.
- **Signed requests:** HMAC-SHA256 over method, path, timestamp, nonce and canonical bounded JSON body; timestamp-skew checks and a bounded replay cache.
- **Audit events:** bounded in-memory append-only event collection that rejects common credential-bearing field names.

## Example

```python
from security import APIKeyStore, Authorizer, RequestSigner

keys = APIKeyStore()
token, issued_principal = keys.issue("orders-service", {"orders.read"}, 3600)
principal = keys.verify(token)
if "orders.read" not in principal.scopes:
    raise PermissionError("scope denied")

rbac = Authorizer({"operator": {"orders.read", "orders.write"}})
rbac.require({"operator"}, "orders.write")

signer = RequestSigner(b"replace-with-a-secret-of-at-least-32-bytes")
headers = signer.sign("POST", "/v1/orders", {"order_id": "A-123"})
# On the receiving side, verify with a separately provisioned shared secret:
# receiver.verify("POST", "/v1/orders", {"order_id": "A-123"}, headers)
```

## Security boundaries and production requirements

- These are **building blocks**, not a complete identity provider, OAuth/OIDC implementation, authorization middleware or production key-management service.
- API keys and replay nonces are held in process memory. They are lost on restart and are not shared across workers/hosts. Use a durable, access-controlled database or managed secret/KMS service, with audited rotation and revocation, for production.
- The API key digest is SHA-256 because issued keys are generated with high entropy. Do not use this design for human passwords.
- HMAC provides integrity/authentication, not confidentiality. Use TLS 1.3 or QUIC for transport security; do not invent encryption.
- The replay cache is bounded and process-local. Multi-instance deployments need a shared atomic nonce store and rate limits.
- Use a separately provisioned signing secret per trust relationship and rotate it. Never place secrets in source control, URLs, logs or audit events.
- The in-memory audit sink is not durable or tamper-evident. Production audit events need protected append-only storage, access controls, retention policy and monitoring.
- The role map is supplied by trusted application configuration. The module does not authenticate human identities or establish roles.
- Do not expose the existing Bridge gateway publicly until authentication, authorization, TLS termination, rate limiting and operational monitoring are deployed and reviewed.

Run the full suite using the commands in `infilink/README.md`. IILP and these security primitives remain experimental and are not certified for sensitive or production workloads.
