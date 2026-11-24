-- Browser binding for Keycloak authorization callbacks.
-- Both values are SHA-256 digests; raw state and browser cookie are not stored.
CREATE TABLE IF NOT EXISTS infilink_oidc_browser_bindings (
    state_digest BYTEA PRIMARY KEY CHECK (octet_length(state_digest) = 32),
    browser_digest BYTEA NOT NULL CHECK (octet_length(browser_digest) = 32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS infilink_oidc_browser_bindings_expiry_idx
    ON infilink_oidc_browser_bindings (expires_at);
