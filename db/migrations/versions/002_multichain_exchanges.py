"""Phase 2 database schema for multi-chain and exchange integrations.

Creates tables for exchange transaction storage, API connections,
supported exchanges catalog, and file import tracking:
  - exchange_transactions: all exchange CSV/API/AI-imported transactions
  - exchange_connections: stored API credentials per user per exchange
  - supported_exchanges: catalog of available integrations (seeded)
  - file_imports: uploaded file tracking for AI ingestion + idempotent re-import

Revision ID: 002
Revises: 001
Create Date: 2026-03-12 00:00:00 UTC
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # exchange_transactions
    # ------------------------------------------------------------------
    op.create_table(
        "exchange_transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("exchange", sa.String(50), nullable=False),
        sa.Column("tx_id", sa.String(256), nullable=True),
        sa.Column("tx_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tx_type", sa.String(50), nullable=True),
        sa.Column("asset", sa.String(50), nullable=False),
        sa.Column("quantity", sa.Numeric(30, 10), nullable=False),
        sa.Column("price_per_unit", sa.Numeric(24, 10), nullable=True),
        sa.Column("total_value", sa.Numeric(24, 10), nullable=True),
        sa.Column("fee", sa.Numeric(24, 10), nullable=True),
        sa.Column("fee_asset", sa.String(20), nullable=True),
        sa.Column("currency", sa.String(10), nullable=False, server_default="CAD"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("import_batch", sa.String(128), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="csv"),
        sa.Column("confidence_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_exchange_tx_user_id"),
        sa.PrimaryKeyConstraint("id", name="pk_exchange_transactions"),
        sa.UniqueConstraint("user_id", "exchange", "tx_id", name="uq_exchange_tx_user_exchange_txid"),
    )
    op.create_index("ix_exchange_transactions_user_id", "exchange_transactions", ["user_id"])
    op.create_index("ix_exchange_transactions_exchange", "exchange_transactions", ["exchange"])
    op.create_index("ix_exchange_transactions_tx_date", "exchange_transactions", ["tx_date"])

    # ------------------------------------------------------------------
    # exchange_connections
    # ------------------------------------------------------------------
    op.create_table(
        "exchange_connections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("exchange", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=True),
        sa.Column("api_key", sa.Text(), nullable=False),
        sa.Column("api_secret", sa.Text(), nullable=True),
        sa.Column("additional_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_exchange_conn_user_id"),
        sa.PrimaryKeyConstraint("id", name="pk_exchange_connections"),
        sa.UniqueConstraint("user_id", "exchange", name="uq_exchange_conn_user_exchange"),
    )

    # ------------------------------------------------------------------
    # supported_exchanges
    # ------------------------------------------------------------------
    op.create_table(
        "supported_exchanges",
        sa.Column("id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("logo_url", sa.String(512), nullable=True),
        sa.Column("has_api", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("has_csv", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("requires_api_key", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("requires_api_secret", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("additional_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("help_url", sa.String(512), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id", name="pk_supported_exchanges"),
    )

    # ------------------------------------------------------------------
    # file_imports
    # ------------------------------------------------------------------
    op.create_table(
        "file_imports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("file_hash", sa.String(128), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("exchange_detected", sa.String(50), nullable=True),
        sa.Column("rows_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_flagged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_file_imports_user_id"),
        sa.ForeignKeyConstraint(["job_id"], ["indexing_jobs.id"], name="fk_file_imports_job_id"),
        sa.PrimaryKeyConstraint("id", name="pk_file_imports"),
        sa.UniqueConstraint("user_id", "file_hash", name="uq_file_imports_user_hash"),
    )

    # ------------------------------------------------------------------
    # Seed supported_exchanges
    # ------------------------------------------------------------------
    supported_exchanges_table = sa.table(
        "supported_exchanges",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("has_api", sa.Boolean),
        sa.column("has_csv", sa.Boolean),
        sa.column("requires_api_key", sa.Boolean),
        sa.column("requires_api_secret", sa.Boolean),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        supported_exchanges_table,
        [
            {
                "id": "coinbase",
                "name": "Coinbase",
                "has_api": True,
                "has_csv": True,
                "requires_api_key": True,
                "requires_api_secret": True,
                "is_active": True,
                "sort_order": 1,
            },
            {
                "id": "crypto_com",
                "name": "Crypto.com",
                "has_api": True,
                "has_csv": True,
                "requires_api_key": True,
                "requires_api_secret": True,
                "is_active": True,
                "sort_order": 2,
            },
            {
                "id": "wealthsimple",
                "name": "Wealthsimple Crypto",
                "has_api": False,
                "has_csv": True,
                "requires_api_key": False,
                "requires_api_secret": False,
                "is_active": True,
                "sort_order": 3,
            },
            {
                "id": "uphold",
                "name": "Uphold",
                "has_api": False,
                "has_csv": True,
                "requires_api_key": False,
                "requires_api_secret": False,
                "is_active": True,
                "sort_order": 4,
            },
            {
                "id": "coinsquare",
                "name": "Coinsquare",
                "has_api": False,
                "has_csv": True,
                "requires_api_key": False,
                "requires_api_secret": False,
                "is_active": True,
                "sort_order": 5,
            },
            {
                "id": "bitbuy",
                "name": "Bitbuy",
                "has_api": False,
                "has_csv": True,
                "requires_api_key": False,
                "requires_api_secret": False,
                "is_active": True,
                "sort_order": 6,
            },
        ],
    )


def downgrade() -> None:
    # Drop in reverse dependency order (file_imports references indexing_jobs and users)
    op.drop_table("file_imports")
    op.drop_table("supported_exchanges")
    op.drop_table("exchange_connections")
    op.drop_table("exchange_transactions")
