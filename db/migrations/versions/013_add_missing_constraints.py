"""Add missing unique constraint uq_tc_tx_leg on transaction_classifications.

This constraint is required by the classifier's ON CONFLICT upsert logic.
It was referenced in code but never created by a migration.
"""


def upgrade(cur):
    # Add unique constraint for classifier upsert
    # Only applies to rows with a non-null transaction_id
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_tc_tx_leg'
            ) THEN
                ALTER TABLE transaction_classifications
                ADD CONSTRAINT uq_tc_tx_leg
                UNIQUE (user_id, transaction_id, leg_type);
            END IF;
        END $$
    """)


def downgrade(cur):
    cur.execute("""
        ALTER TABLE transaction_classifications
        DROP CONSTRAINT IF EXISTS uq_tc_tx_leg
    """)
