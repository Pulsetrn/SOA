CREATE TABLE refresh_sessions (
    jti UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_refresh_sessions_token_hash CHECK (token_hash ~ '^[0-9a-f]{64}$')
);

CREATE INDEX ix_refresh_sessions_user_id ON refresh_sessions(user_id);
