-- INFILINK application-owned session storage.
-- Apply with a migration role; the runtime role needs SELECT, INSERT, UPDATE.
CREATE TABLE IF NOT EXISTS infilink_sessions (
    token_digest BYTEA PRIMARY KEY CHECK (octet_length(token_digest) = 32),
    key_id TEXT NOT NULL CHECK (length(key_id) BETWEEN 1 AND 128),
    subject TEXT NOT NULL CHECK (length(subject) BETWEEN 1 AND 256),
    scopes JSONB NOT NULL CHECK (jsonb_typeof(scopes) = 'array'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS infilink_sessions_active_expiry_idx
    ON infilink_sessions (expires_at)
    WHERE revoked_at IS NULL;

-- Runtime cleanup can be scheduled independently; expired rows are never
-- accepted even if cleanup is delayed.
