-- User accounts for multi-user support
-- Phase 16: Post-quantum encryption at rest
--
-- This file reflects the schema AFTER migration 022_pqe_schema runs.
-- Key changes from pre-PQE schema:
--   - email, near_account_id, username are now BYTEA (AES-256-GCM ciphertext via EncryptedBytes)
--   - email_hmac TEXT UNIQUE replaces the old email UNIQUE index (D-05)
--   - near_account_id_hmac TEXT UNIQUE replaces old near_account_id UNIQUE (D-24)
--   - mlkem_ek, mlkem_sealed_dk, wrapped_dek: ML-KEM-768 envelope columns (D-11, D-12)
--   - worker_sealed_dek, worker_key_enabled: opt-in background worker key (D-17)

CREATE TABLE IF NOT EXISTS users (
    id                      INTEGER PRIMARY KEY,
    -- Plaintext metadata (not user-linkable on its own)
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at           TIMESTAMPTZ,
    is_admin                BOOLEAN DEFAULT FALSE,
    codename                VARCHAR(64) UNIQUE,

    -- PQE: encrypted PII columns (EncryptedBytes ciphertext, AES-256-GCM)
    -- NULL until the user logs in post-migration and the session DEK is set
    email                   BYTEA,
    near_account_id         BYTEA,
    username                BYTEA,

    -- HMAC surrogates for pre-session lookup (D-05, D-24)
    -- Populated at migration time from existing plaintext values.
    -- New users: populated at registration time before plaintext is ever written.
    email_hmac              TEXT UNIQUE,
    near_account_id_hmac    TEXT UNIQUE,

    -- ML-KEM-768 key envelope (D-11, D-12)
    -- Provisioned by auth-service → FastAPI /internal/crypto/keygen IPC call
    -- at first registration. All three NULLABLE until provisioned.
    mlkem_ek                BYTEA,          -- 1184 bytes: ML-KEM-768 encapsulation key
    mlkem_sealed_dk         BYTEA,          -- 2428 bytes: AES-GCM(sealing_key, dk)
    wrapped_dek             BYTEA,          -- 1148 bytes: ML-KEM-768 ct || AES-GCM(shared_secret, dek)

    -- Opt-in background worker key (D-17)
    -- NULL and FALSE by default. Set via Settings UI worker-key toggle.
    worker_sealed_dek       BYTEA,          -- re-wrapped DEK for background worker process
    worker_key_enabled      BOOLEAN NOT NULL DEFAULT FALSE
);

-- Lookup indexes
CREATE INDEX IF NOT EXISTS idx_users_email_hmac ON users (email_hmac);
CREATE INDEX IF NOT EXISTS idx_users_near_account_id_hmac ON users (near_account_id_hmac);

-- Note: session_dek_cache table (D-26) is defined in migration 022 alongside
-- this users schema change. See db/models/_all_models.py SessionDekCache model.

-- accountant_access extension (D-25): rewrapped_client_dek BYTEA column
-- ALTER TABLE accountant_access ADD COLUMN IF NOT EXISTS rewrapped_client_dek BYTEA;
-- (Applied by migration 022; listed here for reference)
