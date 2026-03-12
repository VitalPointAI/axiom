"""Add updated_at column to file_imports and exchange_transactions tables.

Migration 002b adds the updated_at TIMESTAMPTZ column that is referenced in
file_handler.py (SET updated_at = NOW()) and dedup_handler.py
(SET updated_at = NOW()) but was missing from the 002 migration.

Nullable=True because existing rows will have NULL for updated_at until
they are next updated.

Revision ID: 002b
Revises: 002
Create Date: 2026-03-12 00:00:00 UTC
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "002b"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add updated_at to file_imports
    op.add_column(
        "file_imports",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )

    # Add updated_at to exchange_transactions
    op.add_column(
        "exchange_transactions",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("exchange_transactions", "updated_at")
    op.drop_column("file_imports", "updated_at")
