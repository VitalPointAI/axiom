"""Phase 7 auth schema.

Formalizes auth tables that the Next.js app creates ad-hoc. Uses IF NOT EXISTS
patterns so migration is safe even when some tables already exist.

Changes:
  - ALTER users table: add username, email, is_admin, codename columns (IF NOT EXISTS)
  - passkeys: WebAuthn credential storage per user
  - sessions: HTTP session tokens with expiry
  - challenges: WebAuthn/OAuth one-time challenge storage
  - magic_link_tokens: email magic link auth tokens
  - accountant_access: accountant-to-client permission grants

All ALTER TABLE and CREATE TABLE statements are idempotent via IF NOT EXISTS.

Revision ID: 006
Revises: 005
Create Date: 2026-03-13 00:00:00 UTC
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Extend users table with auth-related columns (all nullable, IF NOT EXISTS)
    # ------------------------------------------------------------------
    op.execute("""
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS username VARCHAR(128) UNIQUE,
            ADD COLUMN IF NOT EXISTS email VARCHAR(256) UNIQUE,
            ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS codename VARCHAR(64) UNIQUE
    """)

    # ------------------------------------------------------------------
    # passkeys — WebAuthn credential storage
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS passkeys (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            credential_id TEXT UNIQUE NOT NULL,
            public_key  BYTEA NOT NULL,
            counter     BIGINT NOT NULL DEFAULT 0,
            device_type TEXT,
            backed_up   BOOLEAN NOT NULL DEFAULT FALSE,
            last_used_at TIMESTAMPTZ,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_passkeys_user_id ON passkeys(user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_passkeys_credential_id ON passkeys(credential_id)
    """)

    # ------------------------------------------------------------------
    # sessions — HTTP session token storage
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          TEXT PRIMARY KEY,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at  TIMESTAMPTZ NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_sessions_user_id ON sessions(user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_sessions_expires_at ON sessions(expires_at)
    """)

    # ------------------------------------------------------------------
    # challenges — WebAuthn/OAuth one-time challenge tokens
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS challenges (
            id             TEXT PRIMARY KEY,
            challenge      BYTEA NOT NULL,
            challenge_type TEXT NOT NULL
                CHECK (challenge_type IN ('registration','authentication','oauth_state','magic_link')),
            user_id        INTEGER REFERENCES users(id) ON DELETE CASCADE,
            expires_at     TIMESTAMPTZ NOT NULL,
            metadata       JSONB,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_challenges_expires_at ON challenges(expires_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_challenges_user_id ON challenges(user_id)
    """)

    # ------------------------------------------------------------------
    # magic_link_tokens — email magic link auth tokens
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS magic_link_tokens (
            id          TEXT PRIMARY KEY,
            email       TEXT NOT NULL,
            user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
            expires_at  TIMESTAMPTZ NOT NULL,
            used_at     TIMESTAMPTZ,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_magic_link_tokens_email ON magic_link_tokens(email)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_magic_link_tokens_expires_at ON magic_link_tokens(expires_at)
    """)

    # ------------------------------------------------------------------
    # accountant_access — accountant-to-client permission grants
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS accountant_access (
            id                  SERIAL PRIMARY KEY,
            accountant_user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            client_user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            permission_level    TEXT NOT NULL
                CHECK (permission_level IN ('read','readwrite')),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (accountant_user_id, client_user_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_accountant_access_accountant ON accountant_access(accountant_user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_accountant_access_client ON accountant_access(client_user_id)
    """)


def downgrade() -> None:
    # Drop in reverse dependency order
    op.execute("DROP TABLE IF EXISTS accountant_access")
    op.execute("DROP TABLE IF EXISTS magic_link_tokens")
    op.execute("DROP TABLE IF EXISTS challenges")
    op.execute("DROP TABLE IF EXISTS sessions")
    op.execute("DROP TABLE IF EXISTS passkeys")
    # Revert users columns (non-idempotent for downgrade; best-effort)
    op.execute("""
        ALTER TABLE users
            DROP COLUMN IF EXISTS codename,
            DROP COLUMN IF EXISTS is_admin,
            DROP COLUMN IF EXISTS email,
            DROP COLUMN IF EXISTS username
    """)
