"""Phase 16: session_client_dek_cache for accountant viewing (D-25)

This table stores per-accountant-session wrapped copies of each granted
client's DEK.  At accountant login time the auth-service or the
POST /api/accountant/sessions/materialize endpoint inserts one row per
active grant (keyed by session_id + client_user_id).

When the accountant sets viewing_as_user_id = client_id, the
get_effective_user_with_dek dependency reads this table to retrieve the
client's DEK for the lifetime of that request.

Rows expire with the accountant's session and must be deleted on logout
(plan 16-07 integration test verifies this — T-16-37).

Revision ID: 023
Revises: 022
"""

from alembic import op
import sqlalchemy as sa

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "session_client_dek_cache",
        sa.Column("session_id", sa.Text, nullable=False),
        sa.Column("client_user_id", sa.BigInteger, nullable=False),
        # Wrapped client DEK: nonce (12) || AES-GCM(SESSION_DEK_WRAP_KEY, client_dek)
        # Same wire format as session_dek_cache.encrypted_dek
        sa.Column("encrypted_client_dek", sa.LargeBinary, nullable=False),
        # Expiry matches the accountant's session TTL; rows are cleaned up on logout
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("session_id", "client_user_id"),
    )
    # Index for TTL sweeps and logout cleanup
    op.create_index(
        "ix_session_client_dek_cache_expires",
        "session_client_dek_cache",
        ["expires_at"],
    )
    # Index for lookup by session_id only (used by logout DELETE)
    op.create_index(
        "ix_session_client_dek_cache_session",
        "session_client_dek_cache",
        ["session_id"],
    )


def downgrade():
    op.drop_index("ix_session_client_dek_cache_session", table_name="session_client_dek_cache")
    op.drop_index("ix_session_client_dek_cache_expires", table_name="session_client_dek_cache")
    op.drop_table("session_client_dek_cache")
