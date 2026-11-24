-- Shared, single-use OIDC login transactions for all INFILINK workers.
-- The browser state is never stored directly; only its SHA-256 digest is kept.
CREATE TABLE IF NOT EXISTS infilink_oidc_transactions (
    state_digest BYTEA PRIMARY KEY CHECK (octet_length(state_digest) = 32),
    nonce TEXT NOT NULL CHECK (length(nonce) BETWEEN 32 AND 256),
    code_verifier TEXT NOT NULL CHECK (length(code_verifier) BETWEEN 43 AND 128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS infilink_oidc_transactions_expiry_idx
    ON infilink_oidc_transactions (expires_at);

-- Expired rows are rejected at consume time even if cleanup is delayed.
