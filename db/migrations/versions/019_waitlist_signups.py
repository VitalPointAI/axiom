"""Create waitlist_signups table for email capture.

Stores email addresses from the marketing site waitlist form.
Unique constraint on email prevents duplicates; source column
tracks where the signup originated.

Revision ID: 019
Revises: 018
"""

from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"


def upgrade():
    op.create_table(
        "waitlist_signups",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("source", sa.String(50), server_default="website"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_waitlist_signups_email",
        "waitlist_signups",
        ["email"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_waitlist_signups_email", table_name="waitlist_signups")
    op.drop_table("waitlist_signups")
