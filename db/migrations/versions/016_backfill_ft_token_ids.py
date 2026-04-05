"""Backfill token_id for existing NEAR FT transfer transactions.

Parses raw_data to find ft_transfer/ft_transfer_call transactions
and sets token_id to the receiver_account_id (token contract).

Revision ID: 016
Revises: 015
"""

from alembic import op

revision = "016"
down_revision = "015"


def upgrade():
    # Update NEAR FT transactions where token_id is NULL but method_name
    # indicates an FT transfer. The token contract is receiver_account_id
    # stored in raw_data.
    op.execute("""
        UPDATE transactions
        SET token_id = raw_data->>'receiver_account_id'
        WHERE chain = 'near'
          AND token_id IS NULL
          AND method_name IN ('ft_transfer', 'ft_transfer_call')
          AND raw_data->>'receiver_account_id' IS NOT NULL
    """)


def downgrade():
    # Cannot reliably undo — would need to know which rows were backfilled
    pass
