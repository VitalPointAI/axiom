"""Add auth_user_mapping table for near-phantom-auth integration.

Maps UUID-based auth users (from near-phantom-auth's anon_users/oauth_users)
to Axiom's integer-based users table. The near-phantom-auth tables themselves
are created by the auth service's initialize() call.

Revision ID: 009
"""

from alembic import op


revision = "009"
down_revision = "008"


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS auth_user_mapping (
            auth_user_id TEXT PRIMARY KEY,
            axiom_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            user_type TEXT NOT NULL DEFAULT 'anonymous',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_auth_user_mapping_axiom
            ON auth_user_mapping(axiom_user_id);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS auth_user_mapping;")
