"""
SQLAlchemy 2.0 declarative models for Axiom/NearTax.

All data tables carry user_id FK for multi-user isolation.
chain column on wallets/transactions enables multi-chain extensibility.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import mapped_column, relationship

from db.models.base import Base


class User(Base):
    """Application users — authenticated via passkey, email magic link, or Google OAuth.

    Phase 7 adds: username, email, is_admin, codename columns (migration 006).
    near_account_id is now optional (nullable=True) to support email-only users.
    """

    __tablename__ = "users"

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    near_account_id = mapped_column(String(128), unique=True, nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login_at = mapped_column(DateTime(timezone=True), nullable=True)

    # Phase 7 auth columns (added via migration 006)
    username = mapped_column(String(128), unique=True, nullable=True)
    email = mapped_column(String(256), unique=True, nullable=True)
    is_admin = mapped_column(Boolean, default=False, nullable=True)
    codename = mapped_column(String(64), unique=True, nullable=True)

    wallets = relationship("Wallet", back_populates="user", cascade="all, delete-orphan")


class Wallet(Base):
    """Blockchain wallets/addresses tracked per user."""

    __tablename__ = "wallets"
    __table_args__ = (
        UniqueConstraint("user_id", "account_id", "chain", name="uq_wallet_user_account_chain"),
        Index("ix_wallets_user_id", "user_id"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    account_id = mapped_column(String(128), nullable=False)
    chain = mapped_column(String(20), nullable=False, default="near")
    label = mapped_column(String(256), nullable=True)
    is_owned = mapped_column(Boolean, default=True, nullable=False)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", back_populates="wallets")
    transactions = relationship("Transaction", back_populates="wallet", cascade="all, delete-orphan")
    indexing_jobs = relationship("IndexingJob", back_populates="wallet", cascade="all, delete-orphan")
    staking_events = relationship("StakingEvent", back_populates="wallet", cascade="all, delete-orphan")
    epoch_snapshots = relationship("EpochSnapshot", back_populates="wallet", cascade="all, delete-orphan")
    lockup_events = relationship("LockupEvent", back_populates="wallet", cascade="all, delete-orphan")


class Transaction(Base):
    """Individual blockchain transactions for all supported chains."""

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint(
            "chain", "tx_hash", "receipt_id", "wallet_id",
            name="uq_tx_chain_hash_receipt_wallet",
        ),
        CheckConstraint("direction IN ('in', 'out')", name="ck_tx_direction"),
        Index("ix_transactions_user_id", "user_id"),
        Index("ix_transactions_wallet_id", "wallet_id"),
        Index("ix_transactions_chain", "chain"),
        Index("ix_transactions_block_timestamp", "block_timestamp"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    wallet_id = mapped_column(Integer, ForeignKey("wallets.id"), nullable=False)
    tx_hash = mapped_column(String(128), nullable=False)
    receipt_id = mapped_column(String(128), nullable=True)
    chain = mapped_column(String(20), nullable=False, default="near")
    direction = mapped_column(String(3), nullable=True)
    counterparty = mapped_column(String(128), nullable=True)
    action_type = mapped_column(String(64), nullable=True)
    method_name = mapped_column(String(128), nullable=True)
    amount = mapped_column(Numeric(40, 0), nullable=True)   # yoctoNEAR or wei
    fee = mapped_column(Numeric(40, 0), nullable=True)
    token_id = mapped_column(String(128), nullable=True)    # FT contract address
    block_height = mapped_column(BigInteger, nullable=True)
    block_timestamp = mapped_column(BigInteger, nullable=True)
    success = mapped_column(Boolean, nullable=True)
    raw_data = mapped_column(JSONB, nullable=True)          # JSONB, NOT TEXT
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User")
    wallet = relationship("Wallet", back_populates="transactions")


class IndexingJob(Base):
    """Database-backed job queue for resumable indexing operations."""

    __tablename__ = "indexing_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','completed','failed','retrying')",
            name="ck_job_status",
        ),
        Index("ix_indexing_jobs_user_id", "user_id"),
        Index("ix_indexing_jobs_status", "status"),
        Index("ix_indexing_jobs_wallet_id", "wallet_id"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    wallet_id = mapped_column(Integer, ForeignKey("wallets.id"), nullable=False)
    job_type = mapped_column(String(32), nullable=False)    # e.g. "full_sync", "incremental_sync"
    chain = mapped_column(String(20), nullable=False, default="near")
    status = mapped_column(String(20), nullable=False, default="queued")
    priority = mapped_column(Integer, default=0, nullable=False)  # higher = more urgent
    cursor = mapped_column(String(256), nullable=True)      # resume point for pagination
    progress_fetched = mapped_column(Integer, default=0, nullable=False)
    progress_total = mapped_column(Integer, nullable=True)
    attempts = mapped_column(Integer, default=0, nullable=False)
    max_attempts = mapped_column(Integer, default=100, nullable=False)  # self-healing
    last_error = mapped_column(Text, nullable=True)
    started_at = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at = mapped_column(DateTime(timezone=True), nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User")
    wallet = relationship("Wallet", back_populates="indexing_jobs")


class StakingEvent(Base):
    """Individual staking deposit/withdraw/reward events per validator."""

    __tablename__ = "staking_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('deposit','withdraw','reward')",
            name="ck_staking_event_type",
        ),
        Index("ix_staking_events_user_id", "user_id"),
        Index("ix_staking_events_wallet_id", "wallet_id"),
        Index("ix_staking_events_block_timestamp", "block_timestamp"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    wallet_id = mapped_column(Integer, ForeignKey("wallets.id"), nullable=False)
    validator_id = mapped_column(String(128), nullable=False)
    event_type = mapped_column(String(20), nullable=True)
    amount = mapped_column(Numeric(40, 0), nullable=True)   # yoctoNEAR
    amount_near = mapped_column(Numeric(24, 8), nullable=True)  # human-readable NEAR
    fmv_usd = mapped_column(Numeric(18, 8), nullable=True)
    fmv_cad = mapped_column(Numeric(18, 8), nullable=True)
    epoch_id = mapped_column(BigInteger, nullable=True)
    block_timestamp = mapped_column(BigInteger, nullable=True)
    tx_hash = mapped_column(String(128), nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User")
    wallet = relationship("Wallet", back_populates="staking_events")


class EpochSnapshot(Base):
    """Per-epoch staked/unstaked balance snapshots for reward calculation."""

    __tablename__ = "epoch_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "wallet_id", "validator_id", "epoch_id",
            name="uq_epoch_wallet_validator_epoch",
        ),
        Index("ix_epoch_snapshots_user_id", "user_id"),
        Index("ix_epoch_snapshots_wallet_id", "wallet_id"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    wallet_id = mapped_column(Integer, ForeignKey("wallets.id"), nullable=False)
    validator_id = mapped_column(String(128), nullable=False)
    epoch_id = mapped_column(BigInteger, nullable=False)
    staked_balance = mapped_column(Numeric(40, 0), nullable=False)  # yoctoNEAR
    unstaked_balance = mapped_column(Numeric(40, 0), nullable=False, default=0)
    epoch_timestamp = mapped_column(BigInteger, nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User")
    wallet = relationship("Wallet", back_populates="epoch_snapshots")


class PriceCache(Base):
    """Historical token prices — chain-agnostic, multi-source."""

    __tablename__ = "price_cache"
    __table_args__ = (
        UniqueConstraint("coin_id", "date", "currency", name="uq_price_coin_date_currency"),
        Index("ix_price_cache_coin_date", "coin_id", "date"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    coin_id = mapped_column(String(64), nullable=False)     # e.g. "near", "ethereum"
    date = mapped_column(Date, nullable=False)
    currency = mapped_column(String(10), nullable=False)    # e.g. "usd", "cad"
    price = mapped_column(Numeric(24, 10), nullable=False)
    source = mapped_column(String(32), nullable=True)       # e.g. "coingecko"
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LockupEvent(Base):
    """NEAR lockup contract events — vesting, unlocking, transfers."""

    __tablename__ = "lockup_events"
    __table_args__ = (
        Index("ix_lockup_events_user_id", "user_id"),
        Index("ix_lockup_events_wallet_id", "wallet_id"),
        Index("ix_lockup_events_block_timestamp", "block_timestamp"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    wallet_id = mapped_column(Integer, ForeignKey("wallets.id"), nullable=False)
    lockup_account_id = mapped_column(String(128), nullable=False)
    event_type = mapped_column(String(32), nullable=False)  # "create","vest","unlock","transfer","withdraw"
    amount = mapped_column(Numeric(40, 0), nullable=True)
    amount_near = mapped_column(Numeric(24, 8), nullable=True)
    fmv_usd = mapped_column(Numeric(18, 8), nullable=True)
    fmv_cad = mapped_column(Numeric(18, 8), nullable=True)
    block_timestamp = mapped_column(BigInteger, nullable=True)
    tx_hash = mapped_column(String(128), nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User")
    wallet = relationship("Wallet", back_populates="lockup_events")


class ClassificationRule(Base):
    """Rule-based classifier definitions using JSONB pattern matching.

    Rules are applied in priority order (higher = first). Each rule maps a
    chain-specific JSONB pattern to a TaxCategory with a confidence score.
    The uq_cr_name unique constraint enables idempotent ON CONFLICT (name) DO UPDATE
    upserts by the rule seeder.
    """

    __tablename__ = "classification_rules"
    __table_args__ = (
        UniqueConstraint("name", name="uq_cr_name"),
        Index("ix_cr_chain", "chain"),
        Index("ix_cr_is_active", "is_active"),
        Index("ix_cr_priority", "priority"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    name = mapped_column(String(128), nullable=False)
    chain = mapped_column(String(20), nullable=False)  # 'near', 'evm', 'exchange', 'all'
    pattern = mapped_column(JSONB, nullable=False)  # e.g. {"method_name": "deposit_and_stake"}
    category = mapped_column(String(50), nullable=False)  # TaxCategory enum value
    confidence = mapped_column(Numeric(4, 3), nullable=False)  # 0.000 to 1.000
    priority = mapped_column(Integer, nullable=False, default=0)  # higher = runs first
    specialist_confirmed = mapped_column(Boolean, nullable=False, default=False)
    confirmed_by = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_at = mapped_column(DateTime(timezone=True), nullable=True)
    sample_tx_count = mapped_column(Integer, nullable=True)
    is_active = mapped_column(Boolean, nullable=False, default=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    confirmed_by_user = relationship("User", foreign_keys=[confirmed_by])


class TransactionClassification(Base):
    """Per-transaction tax category assignments with multi-leg decomposition support.

    Multi-leg structure: parent row has leg_type='parent', child rows reference parent
    via parent_classification_id and have leg_type in ('sell_leg', 'buy_leg', 'fee_leg').
    leg_index orders the child legs within a parent group.

    CLASS-03: staking_event_id links staking reward income to the originating epoch event.
    CLASS-04: lockup_event_id links vest/unlock income to the lockup contract event.
    """

    __tablename__ = "transaction_classifications"
    __table_args__ = (
        Index("ix_tc_user_id", "user_id"),
        Index("ix_tc_transaction_id", "transaction_id"),
        Index("ix_tc_exchange_transaction_id", "exchange_transaction_id"),
        Index("ix_tc_parent_id", "parent_classification_id"),
        Index("ix_tc_category", "category"),
        Index("ix_tc_needs_review", "needs_review"),
        # Partial unique indexes defined in migration via op.execute() — not redeclared here
        # to avoid SQLAlchemy attempting to create them again during metadata operations.
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    transaction_id = mapped_column(Integer, ForeignKey("transactions.id"), nullable=True)
    exchange_transaction_id = mapped_column(
        Integer, ForeignKey("exchange_transactions.id"), nullable=True
    )
    parent_classification_id = mapped_column(
        Integer, ForeignKey("transaction_classifications.id"), nullable=True
    )
    leg_type = mapped_column(String(20), nullable=False, default="parent")
    # Values: 'parent', 'sell_leg', 'buy_leg', 'fee_leg'
    leg_index = mapped_column(Integer, nullable=False, default=0)
    category = mapped_column(String(50), nullable=False)  # TaxCategory enum value
    confidence = mapped_column(Numeric(4, 3), nullable=True)  # NULL = rule-based (certain)
    classification_source = mapped_column(String(20), nullable=False)
    # Values: 'rule', 'ai', 'manual', 'specialist'
    rule_id = mapped_column(Integer, ForeignKey("classification_rules.id"), nullable=True)
    staking_event_id = mapped_column(Integer, ForeignKey("staking_events.id"), nullable=True)
    lockup_event_id = mapped_column(Integer, ForeignKey("lockup_events.id"), nullable=True)
    fmv_usd = mapped_column(Numeric(18, 8), nullable=True)
    fmv_cad = mapped_column(Numeric(18, 8), nullable=True)
    needs_review = mapped_column(Boolean, nullable=False, default=True)
    specialist_confirmed = mapped_column(Boolean, nullable=False, default=False)
    confirmed_by = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_at = mapped_column(DateTime(timezone=True), nullable=True)
    notes = mapped_column(Text, nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User", foreign_keys=[user_id])
    transaction = relationship("Transaction", foreign_keys=[transaction_id])
    rule = relationship("ClassificationRule", foreign_keys=[rule_id])
    staking_event = relationship("StakingEvent", foreign_keys=[staking_event_id])
    lockup_event = relationship("LockupEvent", foreign_keys=[lockup_event_id])
    confirmed_by_user = relationship("User", foreign_keys=[confirmed_by])
    parent = relationship(
        "TransactionClassification",
        foreign_keys=[parent_classification_id],
        remote_side="TransactionClassification.id",
        back_populates="child_legs",
    )
    child_legs = relationship(
        "TransactionClassification",
        foreign_keys=[parent_classification_id],
        back_populates="parent",
    )


class SpamRule(Base):
    """User-scoped and global spam detection rules.

    user_id=NULL means a global/system rule applied to all users.
    rule_type determines how 'value' is interpreted:
      - 'contract_address': exact match on counterparty/token_id
      - 'dust_threshold': numeric threshold — amounts below this are spam
      - 'token_symbol': token symbol prefix/exact match
      - 'pattern': regex or glob pattern on tx fields
    """

    __tablename__ = "spam_rules"
    __table_args__ = (
        Index("ix_sr_user_id", "user_id"),
        Index("ix_sr_rule_type", "rule_type"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=True)  # NULL = global
    rule_type = mapped_column(String(50), nullable=False)
    # Values: 'contract_address', 'dust_threshold', 'token_symbol', 'pattern'
    value = mapped_column(Text, nullable=False)
    created_by = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    is_active = mapped_column(Boolean, nullable=False, default=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", foreign_keys=[user_id])
    creator = relationship("User", foreign_keys=[created_by])


class AuditLog(Base):
    """Unified audit trail for all data mutations.

    Append-only. Never updated. Tracks classification changes, ACB corrections,
    duplicate merges, verification resolutions, report generation, invariant violations.

    entity_type values: 'transaction_classification', 'acb_snapshot',
        'verification_result', 'report_package', 'duplicate_merge', 'manual_balance'
    action values: 'initial_classify', 'reclassify', 'acb_correction',
        'duplicate_merge', 'balance_override', 'report_generated',
        'invariant_violation', 'verification_resolved'
    actor_type values: 'system', 'user', 'specialist', 'ai'
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_al_entity", "entity_type", "entity_id"),
        Index("ix_al_user_id", "user_id"),
        Index("ix_al_created_at", "created_at"),
        Index("ix_al_action", "action"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    entity_type = mapped_column(String(50), nullable=False)
    entity_id = mapped_column(Integer, nullable=True)
    action = mapped_column(String(50), nullable=False)
    old_value = mapped_column(JSONB(astext_type=Text()), nullable=True)
    new_value = mapped_column(JSONB(astext_type=Text()), nullable=False)
    actor_type = mapped_column(String(20), nullable=False)
    notes = mapped_column(Text, nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", foreign_keys=[user_id])


class ACBSnapshot(Base):
    """Per-transaction ACB (Adjusted Cost Base) state snapshots.

    Represents the state of a user's ACB pool for a given token after each
    acquisition or disposal event. Ordered by block_timestamp for replay.

    event_type:
      'acquire' — tokens received (buy, swap, staking reward treated as income+acquire)
      'dispose' — tokens sent (sell, swap, gift, conversion)

    units_delta is always positive; sign is implied by event_type.
    proceeds_cad and gain_loss_cad are populated only for 'dispose' events.
    """

    __tablename__ = "acb_snapshots"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('acquire', 'dispose')",
            name="ck_acb_event_type",
        ),
        UniqueConstraint(
            "user_id",
            "token_symbol",
            "classification_id",
            name="uq_acb_user_token_classification",
        ),
        Index("ix_acb_user_id", "user_id"),
        Index("ix_acb_token_symbol", "token_symbol"),
        Index("ix_acb_block_timestamp", "block_timestamp"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    token_symbol = mapped_column(String(32), nullable=False)
    classification_id = mapped_column(
        Integer, ForeignKey("transaction_classifications.id"), nullable=False
    )
    block_timestamp = mapped_column(BigInteger, nullable=False)
    event_type = mapped_column(String(20), nullable=False)
    # positive=acquire, negative=dispose (sign implied by event_type)
    units_delta = mapped_column(Numeric(24, 8), nullable=False)
    units_after = mapped_column(Numeric(24, 8), nullable=False)
    cost_cad_delta = mapped_column(Numeric(24, 8), nullable=False)
    total_cost_cad = mapped_column(Numeric(24, 8), nullable=False)
    acb_per_unit_cad = mapped_column(Numeric(24, 8), nullable=False)
    proceeds_cad = mapped_column(Numeric(24, 8), nullable=True)   # dispose only
    gain_loss_cad = mapped_column(Numeric(24, 8), nullable=True)  # dispose only
    price_usd = mapped_column(Numeric(18, 8), nullable=True)
    price_cad = mapped_column(Numeric(18, 8), nullable=True)
    price_estimated = mapped_column(Boolean, nullable=False, default=False)
    needs_review = mapped_column(Boolean, nullable=False, default=False)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", foreign_keys=[user_id])
    classification = relationship(
        "TransactionClassification", foreign_keys=[classification_id]
    )
    capital_gains_entry = relationship(
        "CapitalGainsLedger",
        back_populates="acb_snapshot",
        uselist=False,
    )


class CapitalGainsLedger(Base):
    """One row per disposal event recording the capital gain or loss.

    Links to the originating ACBSnapshot via acb_snapshot_id (unique — one
    disposal snapshot produces at most one capital gains record).

    is_superficial_loss and denied_loss_cad are populated by SuperficialLossDetector
    in Phase 4 Plan 02.

    tax_year is the calendar year of disposal_date.
    """

    __tablename__ = "capital_gains_ledger"
    __table_args__ = (
        UniqueConstraint("acb_snapshot_id", name="uq_cgl_acb_snapshot_id"),
        Index("ix_cgl_user_id", "user_id"),
        Index("ix_cgl_tax_year", "tax_year"),
        Index("ix_cgl_token_symbol", "token_symbol"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    acb_snapshot_id = mapped_column(
        Integer, ForeignKey("acb_snapshots.id"), nullable=False
    )
    token_symbol = mapped_column(String(32), nullable=False)
    disposal_date = mapped_column(Date, nullable=False)
    block_timestamp = mapped_column(BigInteger, nullable=False)
    units_disposed = mapped_column(Numeric(24, 8), nullable=False)
    proceeds_cad = mapped_column(Numeric(24, 8), nullable=False)
    acb_used_cad = mapped_column(Numeric(24, 8), nullable=False)
    fees_cad = mapped_column(Numeric(24, 8), nullable=False, default=0)
    gain_loss_cad = mapped_column(Numeric(24, 8), nullable=False)
    is_superficial_loss = mapped_column(Boolean, nullable=False, default=False)
    denied_loss_cad = mapped_column(Numeric(24, 8), nullable=True)
    needs_review = mapped_column(Boolean, nullable=False, default=False)
    tax_year = mapped_column(SmallInteger, nullable=False)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", foreign_keys=[user_id])
    acb_snapshot = relationship(
        "ACBSnapshot",
        back_populates="capital_gains_entry",
        foreign_keys=[acb_snapshot_id],
    )


class IncomeLedger(Base):
    """One row per income event (staking reward, lockup vest, airdrop, other).

    acb_added_cad equals fmv_cad — the FMV at receipt becomes the cost basis
    for the newly acquired units (added to the ACBSnapshot for that token).

    source_type values: 'staking', 'vesting', 'airdrop', 'other'
    """

    __tablename__ = "income_ledger"
    __table_args__ = (
        Index("ix_il_user_id", "user_id"),
        Index("ix_il_tax_year", "tax_year"),
        Index("ix_il_source_type", "source_type"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    source_type = mapped_column(String(20), nullable=False)
    staking_event_id = mapped_column(
        Integer, ForeignKey("staking_events.id"), nullable=True
    )
    lockup_event_id = mapped_column(
        Integer, ForeignKey("lockup_events.id"), nullable=True
    )
    classification_id = mapped_column(
        Integer, ForeignKey("transaction_classifications.id"), nullable=True
    )
    token_symbol = mapped_column(String(32), nullable=False)
    income_date = mapped_column(Date, nullable=False)
    block_timestamp = mapped_column(BigInteger, nullable=False)
    units_received = mapped_column(Numeric(24, 8), nullable=False)
    fmv_usd = mapped_column(Numeric(18, 8), nullable=False)
    fmv_cad = mapped_column(Numeric(18, 8), nullable=False)
    acb_added_cad = mapped_column(Numeric(24, 8), nullable=False)  # = fmv_cad
    tax_year = mapped_column(SmallInteger, nullable=False)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", foreign_keys=[user_id])
    staking_event = relationship("StakingEvent", foreign_keys=[staking_event_id])
    lockup_event = relationship("LockupEvent", foreign_keys=[lockup_event_id])
    classification = relationship(
        "TransactionClassification", foreign_keys=[classification_id]
    )


class PriceCacheMinute(Base):
    """Minute-level (or sub-hourly) price cache separate from daily price_cache.

    unix_ts is rounded to the nearest minute for cache key consistency:
      ts_minute = (unix_ts // 60) * 60

    is_estimated=True when the closest available CoinGecko timestamp was more
    than 15 minutes (900 seconds) from the requested unix_ts.

    source: 'coingecko', 'coingecko_estimated', or None
    """

    __tablename__ = "price_cache_minute"
    __table_args__ = (
        UniqueConstraint("coin_id", "unix_ts", "currency", name="uq_pcm_coin_ts_currency"),
        Index("ix_pcm_coin_ts", "coin_id", "unix_ts"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    coin_id = mapped_column(String(64), nullable=False)
    unix_ts = mapped_column(BigInteger, nullable=False)  # seconds, rounded to minute
    currency = mapped_column(String(10), nullable=False)
    price = mapped_column(Numeric(24, 10), nullable=False)
    source = mapped_column(String(32), nullable=True)
    is_estimated = mapped_column(Boolean, nullable=False, default=False)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VerificationResult(Base):
    """Per-wallet verification run results with auto-diagnosis.

    One row per (wallet_id, token_symbol) — upserted each verification run.
    Stores both ACB-based and raw-replay expected balances for dual cross-check.
    NEAR wallets include decomposed on-chain balance (liquid + locked + staked).
    Exchange wallets support manual balance entry for reconciliation.

    status values: 'open', 'resolved', 'accepted', 'unverified'
    diagnosis_category values: 'missing_staking_rewards', 'uncounted_fees',
        'unindexed_period', 'classification_error', 'duplicate_merged',
        'within_tolerance', 'unknown'
    """

    __tablename__ = "verification_results"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'resolved', 'accepted', 'unverified')",
            name="ck_vr_status",
        ),
        UniqueConstraint("wallet_id", "token_symbol", name="uq_vr_wallet_token"),
        Index("ix_vr_user_id", "user_id"),
        Index("ix_vr_wallet_id", "wallet_id"),
        Index("ix_vr_status", "status"),
        Index("ix_vr_verified_at", "verified_at"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    wallet_id = mapped_column(Integer, ForeignKey("wallets.id"), nullable=False)
    chain = mapped_column(String(20), nullable=False)
    token_symbol = mapped_column(String(32), nullable=False, default="NEAR")

    # Balance components (all in human units, Decimal precision)
    expected_balance_acb = mapped_column(Numeric(24, 8), nullable=True)
    expected_balance_replay = mapped_column(Numeric(24, 8), nullable=True)
    actual_balance = mapped_column(Numeric(24, 8), nullable=True)
    manual_balance = mapped_column(Numeric(24, 8), nullable=True)
    manual_balance_date = mapped_column(DateTime(timezone=True), nullable=True)
    difference = mapped_column(Numeric(24, 8), nullable=True)
    tolerance = mapped_column(Numeric(24, 8), nullable=False, default=0.01)

    # NEAR decomposed components (NULL for non-NEAR)
    onchain_liquid = mapped_column(Numeric(24, 8), nullable=True)
    onchain_locked = mapped_column(Numeric(24, 8), nullable=True)
    onchain_staked = mapped_column(Numeric(24, 8), nullable=True)

    # Status
    status = mapped_column(String(20), nullable=False, default="open")

    # Diagnosis
    diagnosis_category = mapped_column(String(50), nullable=True)
    diagnosis_detail = mapped_column(JSONB, nullable=True)
    diagnosis_confidence = mapped_column(Numeric(4, 3), nullable=True)

    # Resolution
    resolved_by = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at = mapped_column(DateTime(timezone=True), nullable=True)
    notes = mapped_column(Text, nullable=True)

    # Verification run metadata
    verified_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    rpc_error = mapped_column(Text, nullable=True)

    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", foreign_keys=[user_id])
    wallet = relationship("Wallet", foreign_keys=[wallet_id])
    resolved_by_user = relationship("User", foreign_keys=[resolved_by])


class AccountVerificationStatus(Base):
    """Per-wallet verification status rollup for Phase 7 UI dashboard.

    One row per wallet_id (UNIQUE constraint). Updated after each verification run.
    status is the worst-case of all verification_results for that wallet:
      - 'verified': no open issues, at least one result exists
      - 'flagged': open issues exist
      - 'unverified': no verification results yet

    open_issues: count of verification_results with status='open' for this wallet.
    """

    __tablename__ = "account_verification_status"
    __table_args__ = (
        CheckConstraint(
            "status IN ('verified', 'flagged', 'unverified')",
            name="ck_avs_status",
        ),
        UniqueConstraint("wallet_id", name="uq_avs_wallet_id"),
        Index("ix_avs_user_id", "user_id"),
        Index("ix_avs_status", "status"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    wallet_id = mapped_column(Integer, ForeignKey("wallets.id"), nullable=False)
    status = mapped_column(String(20), nullable=False, default="unverified")
    last_checked_at = mapped_column(DateTime(timezone=True), nullable=True)
    open_issues = mapped_column(Integer, nullable=False, default=0)
    notes = mapped_column(Text, nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", foreign_keys=[user_id])
    wallet = relationship("Wallet", foreign_keys=[wallet_id])


# ---------------------------------------------------------------------------
# Phase 7 Auth Models (migration 006)
# ---------------------------------------------------------------------------


class Passkey(Base):
    """WebAuthn passkey credentials stored per user.

    credential_id is the base64url-encoded credential ID from the authenticator.
    counter is incremented on each use for replay attack prevention.
    """

    __tablename__ = "passkeys"
    __table_args__ = (
        Index("ix_passkeys_user_id", "user_id"),
        Index("ix_passkeys_credential_id", "credential_id"),
    )

    id = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    credential_id = mapped_column(Text, unique=True, nullable=False)
    public_key = mapped_column(LargeBinary, nullable=False)
    counter = mapped_column(BigInteger, nullable=False, default=0)
    device_type = mapped_column(Text, nullable=True)
    backed_up = mapped_column(Boolean, nullable=False, default=False)
    last_used_at = mapped_column(DateTime(timezone=True), nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", foreign_keys=[user_id])


class Session(Base):
    """HTTP session tokens — HTTP-only cookie value with expiry.

    id is a token_hex(32) random string stored as the cookie value.
    Sessions are single-use per browser tab and expire after 7 days.
    """

    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_expires_at", "expires_at"),
    )

    id = mapped_column(Text, primary_key=True)
    user_id = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at = mapped_column(DateTime(timezone=True), nullable=False)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", foreign_keys=[user_id])


class Challenge(Base):
    """One-time WebAuthn/OAuth challenge tokens.

    challenge_type indicates the flow:
      - 'registration': WebAuthn passkey registration
      - 'authentication': WebAuthn passkey login
      - 'oauth_state': Google OAuth CSRF state parameter
      - 'magic_link': email magic link generation challenge

    user_id is nullable — challenges are created before user identity is confirmed
    (e.g., during registration or login before credential verification).
    """

    __tablename__ = "challenges"
    __table_args__ = (
        CheckConstraint(
            "challenge_type IN ('registration','authentication','oauth_state','magic_link')",
            name="ck_challenge_type",
        ),
        Index("ix_challenges_expires_at", "expires_at"),
        Index("ix_challenges_user_id", "user_id"),
    )

    id = mapped_column(Text, primary_key=True)
    challenge = mapped_column(LargeBinary, nullable=False)
    challenge_type = mapped_column(Text, nullable=False)
    user_id = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    expires_at = mapped_column(DateTime(timezone=True), nullable=False)
    challenge_metadata = mapped_column("metadata", JSONB, nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", foreign_keys=[user_id])


class MagicLinkToken(Base):
    """Email magic link one-time tokens.

    Tokens expire and can only be used once (used_at is set on first use).
    user_id is nullable to support both new user signup and existing user login flows.
    """

    __tablename__ = "magic_link_tokens"
    __table_args__ = (
        Index("ix_magic_link_tokens_email", "email"),
        Index("ix_magic_link_tokens_expires_at", "expires_at"),
    )

    id = mapped_column(Text, primary_key=True)
    email = mapped_column(Text, nullable=False)
    user_id = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    expires_at = mapped_column(DateTime(timezone=True), nullable=False)
    used_at = mapped_column(DateTime(timezone=True), nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", foreign_keys=[user_id])


class AccountantAccess(Base):
    """Accountant-to-client access grants with permission levels.

    permission_level:
      - 'read': accountant can view client data but not modify
      - 'readwrite': accountant can view and make changes (e.g., mark items reviewed)

    UNIQUE(accountant_user_id, client_user_id) prevents duplicate grants.
    """

    __tablename__ = "accountant_access"
    __table_args__ = (
        CheckConstraint(
            "permission_level IN ('read','readwrite')",
            name="ck_aa_permission_level",
        ),
        UniqueConstraint("accountant_user_id", "client_user_id", name="uq_aa_accountant_client"),
        Index("ix_accountant_access_accountant", "accountant_user_id"),
        Index("ix_accountant_access_client", "client_user_id"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    accountant_user_id = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_user_id = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    permission_level = mapped_column(Text, nullable=False)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    accountant = relationship("User", foreign_keys=[accountant_user_id])
    client = relationship("User", foreign_keys=[client_user_id])
