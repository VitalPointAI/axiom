"""
SQLAlchemy 2.0 declarative models for Axiom/NearTax.

All data tables carry user_id FK for multi-user isolation.
chain column on wallets/transactions enables multi-chain extensibility.

Phase 16: All in-scope user-sensitive columns now use EncryptedBytes TypeDecorator
(transparent AES-256-GCM per-column encryption). Cleartext routing columns
(id, user_id, wallet_id, chain, block_height, block_timestamp, created_at,
updated_at, primary keys, foreign keys) remain unchanged.
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
from db.crypto import EncryptedBytes


class User(Base):
    """Application users — authenticated via passkey, email magic link, or Google OAuth.

    Phase 7 adds: username, email, is_admin, codename columns (migration 006).
    near_account_id is now optional (nullable=True) to support email-only users.

    Phase 16 (migration 022):
    - email, near_account_id, username changed to BYTEA (EncryptedBytes)
    - Added mlkem_ek, mlkem_sealed_dk, wrapped_dek for ML-KEM-768 envelope
    - Added email_hmac, near_account_id_hmac for pre-session lookup (D-24)
    - Added worker_sealed_dek, worker_key_enabled for opt-in background jobs (D-17)
    """

    __tablename__ = "users"

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Phase 16: near_account_id encrypted; near_account_id_hmac for pre-session lookup
    near_account_id = mapped_column(EncryptedBytes, nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login_at = mapped_column(DateTime(timezone=True), nullable=True)

    # Phase 7 auth columns (added via migration 006) — now encrypted (migration 022)
    username = mapped_column(EncryptedBytes, nullable=True)
    email = mapped_column(EncryptedBytes, nullable=True)
    is_admin = mapped_column(Boolean, default=False, nullable=True)
    codename = mapped_column(String(64), unique=True, nullable=True)

    # Phase 16: ML-KEM-768 key material (D-11, D-12)
    mlkem_ek = mapped_column(LargeBinary, nullable=True)            # encapsulation (public) key
    mlkem_sealed_dk = mapped_column(LargeBinary, nullable=True)     # AES-sealed decapsulation key
    wrapped_dek = mapped_column(LargeBinary, nullable=True)         # KEM-wrapped DEK

    # Phase 16: HMAC surrogates for pre-session auth lookups (D-05, D-24)
    email_hmac = mapped_column(Text, unique=True, nullable=True, index=True)
    near_account_id_hmac = mapped_column(Text, unique=True, nullable=True, index=True)

    # Phase 16: Worker key for opt-in background processing (D-17)
    worker_sealed_dek = mapped_column(LargeBinary, nullable=True)
    worker_key_enabled = mapped_column(Boolean, nullable=False, default=False)

    wallets = relationship("Wallet", back_populates="user", cascade="all, delete-orphan")


class Wallet(Base):
    """Blockchain wallets/addresses tracked per user.

    Phase 16: account_id and label encrypted (D-06 — wallets.account_id is the
    single biggest linkability vector). is_owned encrypted.
    Uniqueness on (user_id, account_id, chain) was dropped in migration 022
    because account_id is now BYTEA — uniqueness is not guaranteed by the ORM
    constraint; callers must deduplicate in Python.
    """

    __tablename__ = "wallets"
    __table_args__ = (
        Index("ix_wallets_user_id", "user_id"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    account_id = mapped_column(EncryptedBytes, nullable=False)
    chain = mapped_column(String(20), nullable=False, default="near")
    label = mapped_column(EncryptedBytes, nullable=True)
    is_owned = mapped_column(EncryptedBytes, nullable=True)
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
    """Individual blockchain transactions for all supported chains.

    Phase 16: tx_hash, receipt_id, direction, counterparty, action_type,
    method_name, amount, fee, token_id, success, raw_data all encrypted (D-02).
    tx_dedup_hmac (BYTEA) replaces old cleartext uniqueness constraint (D-28).
    """

    __tablename__ = "transactions"
    __table_args__ = (
        # Phase 16: HMAC-based dedup constraint replaces old cleartext uq (D-28)
        UniqueConstraint("user_id", "tx_dedup_hmac", name="uq_tx_user_dedup_hmac"),
        Index("ix_transactions_user_id", "user_id"),
        Index("ix_transactions_wallet_id", "wallet_id"),
        Index("ix_transactions_chain", "chain"),
        Index("ix_transactions_block_timestamp", "block_timestamp"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    wallet_id = mapped_column(Integer, ForeignKey("wallets.id"), nullable=False)
    # Phase 16: encrypted columns
    tx_hash = mapped_column(EncryptedBytes, nullable=False)
    receipt_id = mapped_column(EncryptedBytes, nullable=True)
    chain = mapped_column(String(20), nullable=False, default="near")
    direction = mapped_column(EncryptedBytes, nullable=True)
    counterparty = mapped_column(EncryptedBytes, nullable=True)
    action_type = mapped_column(EncryptedBytes, nullable=True)
    method_name = mapped_column(EncryptedBytes, nullable=True)
    amount = mapped_column(EncryptedBytes, nullable=True)
    fee = mapped_column(EncryptedBytes, nullable=True)
    token_id = mapped_column(EncryptedBytes, nullable=True)
    block_height = mapped_column(BigInteger, nullable=True)
    block_timestamp = mapped_column(BigInteger, nullable=True)
    success = mapped_column(EncryptedBytes, nullable=True)
    raw_data = mapped_column(EncryptedBytes, nullable=True)
    # Phase 16: dedup HMAC (D-28) — cleartext for ON CONFLICT semantics
    tx_dedup_hmac = mapped_column(LargeBinary, nullable=False)
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
    """Individual staking deposit/withdraw/reward events per validator.

    Phase 16: validator_id, event_type, amount, amount_near, fmv_usd, fmv_cad,
    tx_hash encrypted. epoch_id, block_timestamp, wallet_id remain cleartext.
    """

    __tablename__ = "staking_events"
    __table_args__ = (
        # ck_staking_event_type dropped in migration 022 (can't validate BYTEA ciphertext)
        Index("ix_staking_events_user_id", "user_id"),
        Index("ix_staking_events_wallet_id", "wallet_id"),
        Index("ix_staking_events_block_timestamp", "block_timestamp"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    wallet_id = mapped_column(Integer, ForeignKey("wallets.id"), nullable=False)
    # Phase 16: encrypted columns
    validator_id = mapped_column(EncryptedBytes, nullable=False)
    event_type = mapped_column(EncryptedBytes, nullable=True)
    amount = mapped_column(EncryptedBytes, nullable=True)
    amount_near = mapped_column(EncryptedBytes, nullable=True)
    fmv_usd = mapped_column(EncryptedBytes, nullable=True)
    fmv_cad = mapped_column(EncryptedBytes, nullable=True)
    epoch_id = mapped_column(BigInteger, nullable=True)
    block_timestamp = mapped_column(BigInteger, nullable=True)
    tx_hash = mapped_column(EncryptedBytes, nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User")
    wallet = relationship("Wallet", back_populates="staking_events")


class EpochSnapshot(Base):
    """Per-epoch staked/unstaked balance snapshots for reward calculation.

    Phase 16: validator_id, staked_balance, unstaked_balance encrypted.
    epoch_id and wallet_id remain cleartext for indexing.
    uq_epoch_wallet_validator_epoch dropped in migration 022 (validator_id is now BYTEA).
    """

    __tablename__ = "epoch_snapshots"
    __table_args__ = (
        # uq_epoch_wallet_validator_epoch dropped in migration 022
        Index("ix_epoch_snapshots_user_id", "user_id"),
        Index("ix_epoch_snapshots_wallet_id", "wallet_id"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    wallet_id = mapped_column(Integer, ForeignKey("wallets.id"), nullable=False)
    # Phase 16: encrypted columns
    validator_id = mapped_column(EncryptedBytes, nullable=False)
    epoch_id = mapped_column(BigInteger, nullable=False)
    staked_balance = mapped_column(EncryptedBytes, nullable=False)
    unstaked_balance = mapped_column(EncryptedBytes, nullable=False)
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
    """NEAR lockup contract events — vesting, unlocking, transfers.

    Phase 16: lockup_account_id, event_type, amount, amount_near, fmv_usd, fmv_cad,
    tx_hash encrypted.
    """

    __tablename__ = "lockup_events"
    __table_args__ = (
        Index("ix_lockup_events_user_id", "user_id"),
        Index("ix_lockup_events_wallet_id", "wallet_id"),
        Index("ix_lockup_events_block_timestamp", "block_timestamp"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    wallet_id = mapped_column(Integer, ForeignKey("wallets.id"), nullable=False)
    # Phase 16: encrypted columns
    lockup_account_id = mapped_column(EncryptedBytes, nullable=False)
    event_type = mapped_column(EncryptedBytes, nullable=False)
    amount = mapped_column(EncryptedBytes, nullable=True)
    amount_near = mapped_column(EncryptedBytes, nullable=True)
    fmv_usd = mapped_column(EncryptedBytes, nullable=True)
    fmv_cad = mapped_column(EncryptedBytes, nullable=True)
    block_timestamp = mapped_column(BigInteger, nullable=True)
    tx_hash = mapped_column(EncryptedBytes, nullable=True)
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

    Phase 16: System rules (user_id IS NULL) keep cleartext pattern/category/name.
    User-scoped rules (user_id IS NOT NULL) use parallel *_enc BYTEA columns.
    The plain columns remain for backwards compatibility with system rules.
    """

    __tablename__ = "classification_rules"
    __table_args__ = (
        UniqueConstraint("name", name="uq_cr_name"),
        Index("ix_cr_chain", "chain"),
        Index("ix_cr_is_active", "is_active"),
        Index("ix_cr_priority", "priority"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    # user_id is nullable — NULL = system/global rule (not encrypted)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    name = mapped_column(String(128), nullable=False)
    chain = mapped_column(String(20), nullable=False)  # 'near', 'evm', 'exchange', 'all'
    # Cleartext columns for system rules (user_id IS NULL)
    pattern = mapped_column(JSONB, nullable=True)   # nullable because user rules use _enc
    category = mapped_column(String(50), nullable=True)  # nullable because user rules use _enc
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
    # Phase 16: parallel encrypted columns for user-scoped rules
    pattern_enc = mapped_column(EncryptedBytes, nullable=True)
    category_enc = mapped_column(EncryptedBytes, nullable=True)
    name_enc = mapped_column(EncryptedBytes, nullable=True)

    confirmed_by_user = relationship("User", foreign_keys=[confirmed_by])
    user = relationship("User", foreign_keys=[user_id])


class TransactionClassification(Base):
    """Per-transaction tax category assignments with multi-leg decomposition support.

    Multi-leg structure: parent row has leg_type='parent', child rows reference parent
    via parent_classification_id and have leg_type in ('sell_leg', 'buy_leg', 'fee_leg').
    leg_index orders the child legs within a parent group.

    CLASS-03: staking_event_id links staking reward income to the originating epoch event.
    CLASS-04: lockup_event_id links vest/unlock income to the lockup contract event.

    Phase 16: category, confidence, classification_source, fmv_usd, fmv_cad, notes
    encrypted. Indexes on category/classification_source dropped in migration 022
    (can't index ciphertext). Filter in Python after fetch.
    """

    __tablename__ = "transaction_classifications"
    __table_args__ = (
        Index("ix_tc_user_id", "user_id"),
        Index("ix_tc_transaction_id", "transaction_id"),
        Index("ix_tc_exchange_transaction_id", "exchange_transaction_id"),
        Index("ix_tc_parent_id", "parent_classification_id"),
        # ix_tc_category dropped in migration 022 (category is now BYTEA)
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
    # Phase 16: encrypted columns
    category = mapped_column(EncryptedBytes, nullable=False)
    confidence = mapped_column(EncryptedBytes, nullable=True)
    classification_source = mapped_column(EncryptedBytes, nullable=False)
    rule_id = mapped_column(Integer, ForeignKey("classification_rules.id"), nullable=True)
    staking_event_id = mapped_column(Integer, ForeignKey("staking_events.id"), nullable=True)
    lockup_event_id = mapped_column(Integer, ForeignKey("lockup_events.id"), nullable=True)
    fmv_usd = mapped_column(EncryptedBytes, nullable=True)
    fmv_cad = mapped_column(EncryptedBytes, nullable=True)
    needs_review = mapped_column(Boolean, nullable=False, default=True)
    specialist_confirmed = mapped_column(Boolean, nullable=False, default=False)
    confirmed_by = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_at = mapped_column(DateTime(timezone=True), nullable=True)
    notes = mapped_column(EncryptedBytes, nullable=True)
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

    Phase 16: User-scoped rules use parallel encrypted columns rule_type_enc
    and value_enc. Global rules (user_id IS NULL) keep cleartext columns.
    """

    __tablename__ = "spam_rules"
    __table_args__ = (
        Index("ix_sr_user_id", "user_id"),
        Index("ix_sr_rule_type", "rule_type"),
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=True)  # NULL = global
    # Cleartext columns for global rules (user_id IS NULL)
    rule_type = mapped_column(String(50), nullable=True)
    value = mapped_column(Text, nullable=True)
    created_by = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    is_active = mapped_column(Boolean, nullable=False, default=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Phase 16: parallel encrypted columns for user-scoped rules
    rule_type_enc = mapped_column(EncryptedBytes, nullable=True)
    value_enc = mapped_column(EncryptedBytes, nullable=True)

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

    Phase 16: old_value, new_value, notes, entity_type, action all encrypted.
    actor_type remains cleartext (non-sensitive routing field).
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_al_entity", "entity_id"),
        Index("ix_al_user_id", "user_id"),
        Index("ix_al_created_at", "created_at"),
        # ix_al_entity (entity_type, entity_id) and ix_al_action dropped in migration 022
        # (entity_type and action are now BYTEA — can't index ciphertext)
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    # Phase 16: encrypted columns
    entity_type = mapped_column(EncryptedBytes, nullable=False)
    entity_id = mapped_column(Integer, nullable=True)
    action = mapped_column(EncryptedBytes, nullable=False)
    old_value = mapped_column(EncryptedBytes, nullable=True)
    new_value = mapped_column(EncryptedBytes, nullable=False)
    actor_type = mapped_column(String(20), nullable=False)
    notes = mapped_column(EncryptedBytes, nullable=True)
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

    Phase 16: All financial + identifying columns encrypted. acb_dedup_hmac (BYTEA)
    replaces old cleartext uniqueness constraint (D-28).
    """

    __tablename__ = "acb_snapshots"
    __table_args__ = (
        # ck_acb_event_type dropped in migration 022 (event_type is now BYTEA)
        # uq_acb_user_token_classification dropped; replaced with HMAC dedup
        UniqueConstraint("user_id", "acb_dedup_hmac", name="uq_acb_user_dedup_hmac"),
        Index("ix_acb_user_id", "user_id"),
        Index("ix_acb_block_timestamp", "block_timestamp"),
        # ix_acb_token_symbol dropped in migration 022 (token_symbol is now BYTEA)
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    # Phase 16: encrypted columns
    token_symbol = mapped_column(EncryptedBytes, nullable=False)
    classification_id = mapped_column(
        Integer, ForeignKey("transaction_classifications.id"), nullable=False
    )
    block_timestamp = mapped_column(BigInteger, nullable=False)
    event_type = mapped_column(EncryptedBytes, nullable=False)
    # positive=acquire, negative=dispose (sign implied by event_type)
    units_delta = mapped_column(EncryptedBytes, nullable=False)
    units_after = mapped_column(EncryptedBytes, nullable=False)
    cost_cad_delta = mapped_column(EncryptedBytes, nullable=False)
    total_cost_cad = mapped_column(EncryptedBytes, nullable=False)
    acb_per_unit_cad = mapped_column(EncryptedBytes, nullable=False)
    proceeds_cad = mapped_column(EncryptedBytes, nullable=True)   # dispose only
    gain_loss_cad = mapped_column(EncryptedBytes, nullable=True)  # dispose only
    price_usd = mapped_column(EncryptedBytes, nullable=True)
    price_cad = mapped_column(EncryptedBytes, nullable=True)
    price_estimated = mapped_column(EncryptedBytes, nullable=False)
    needs_review = mapped_column(Boolean, nullable=False, default=False)
    # Phase 16: dedup HMAC (D-28) — cleartext for ON CONFLICT semantics
    acb_dedup_hmac = mapped_column(LargeBinary, nullable=False)
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

    Phase 16: token_symbol, units_disposed, proceeds_cad, acb_used_cad, fees_cad,
    gain_loss_cad, is_superficial_loss, denied_loss_cad encrypted.
    """

    __tablename__ = "capital_gains_ledger"
    __table_args__ = (
        UniqueConstraint("acb_snapshot_id", name="uq_cgl_acb_snapshot_id"),
        Index("ix_cgl_user_id", "user_id"),
        Index("ix_cgl_tax_year", "tax_year"),
        # ix_cgl_token_symbol dropped in migration 022 (token_symbol is now BYTEA)
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    acb_snapshot_id = mapped_column(
        Integer, ForeignKey("acb_snapshots.id"), nullable=False
    )
    # Phase 16: encrypted columns
    token_symbol = mapped_column(EncryptedBytes, nullable=False)
    disposal_date = mapped_column(Date, nullable=False)
    block_timestamp = mapped_column(BigInteger, nullable=False)
    units_disposed = mapped_column(EncryptedBytes, nullable=False)
    proceeds_cad = mapped_column(EncryptedBytes, nullable=False)
    acb_used_cad = mapped_column(EncryptedBytes, nullable=False)
    fees_cad = mapped_column(EncryptedBytes, nullable=False)
    gain_loss_cad = mapped_column(EncryptedBytes, nullable=False)
    is_superficial_loss = mapped_column(EncryptedBytes, nullable=False)
    denied_loss_cad = mapped_column(EncryptedBytes, nullable=True)
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

    Phase 16: token_symbol, units_received, fmv_usd, fmv_cad, acb_added_cad encrypted.
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
    # Phase 16: encrypted columns
    token_symbol = mapped_column(EncryptedBytes, nullable=False)
    income_date = mapped_column(Date, nullable=False)
    block_timestamp = mapped_column(BigInteger, nullable=False)
    units_received = mapped_column(EncryptedBytes, nullable=False)
    fmv_usd = mapped_column(EncryptedBytes, nullable=False)
    fmv_cad = mapped_column(EncryptedBytes, nullable=False)
    acb_added_cad = mapped_column(EncryptedBytes, nullable=False)
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

    Phase 16: expected_balance_acb, expected_balance_replay, actual_balance,
    manual_balance, difference, onchain_liquid, onchain_locked, onchain_staked,
    diagnosis_detail, notes, rpc_error, diagnosis_category, diagnosis_confidence
    all encrypted.
    uq_vr_wallet_token dropped in migration 022 (token_symbol is BYTEA).
    ck_vr_status dropped (status is BYTEA).
    """

    __tablename__ = "verification_results"
    __table_args__ = (
        # ck_vr_status and uq_vr_wallet_token dropped in migration 022
        Index("ix_vr_user_id", "user_id"),
        Index("ix_vr_wallet_id", "wallet_id"),
        Index("ix_vr_verified_at", "verified_at"),
        # ix_vr_status dropped in migration 022 (status is now BYTEA)
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    wallet_id = mapped_column(Integer, ForeignKey("wallets.id"), nullable=False)
    chain = mapped_column(String(20), nullable=False)
    # Phase 16: encrypted columns
    token_symbol = mapped_column(EncryptedBytes, nullable=False)

    # Balance components (all in human units, Decimal precision) — encrypted
    expected_balance_acb = mapped_column(EncryptedBytes, nullable=True)
    expected_balance_replay = mapped_column(EncryptedBytes, nullable=True)
    actual_balance = mapped_column(EncryptedBytes, nullable=True)
    manual_balance = mapped_column(EncryptedBytes, nullable=True)
    manual_balance_date = mapped_column(DateTime(timezone=True), nullable=True)
    difference = mapped_column(EncryptedBytes, nullable=True)
    tolerance = mapped_column(Numeric(24, 8), nullable=False, default=0.01)

    # NEAR decomposed components (NULL for non-NEAR) — encrypted
    onchain_liquid = mapped_column(EncryptedBytes, nullable=True)
    onchain_locked = mapped_column(EncryptedBytes, nullable=True)
    onchain_staked = mapped_column(EncryptedBytes, nullable=True)

    # Status — encrypted
    status = mapped_column(EncryptedBytes, nullable=False)

    # Diagnosis — encrypted
    diagnosis_category = mapped_column(EncryptedBytes, nullable=True)
    diagnosis_detail = mapped_column(EncryptedBytes, nullable=True)
    diagnosis_confidence = mapped_column(EncryptedBytes, nullable=True)

    # Resolution
    resolved_by = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at = mapped_column(DateTime(timezone=True), nullable=True)
    notes = mapped_column(EncryptedBytes, nullable=True)

    # Verification run metadata
    verified_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    rpc_error = mapped_column(EncryptedBytes, nullable=True)

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

    Phase 16: notes encrypted. status encrypted (ck_avs_status dropped in migration 022).
    """

    __tablename__ = "account_verification_status"
    __table_args__ = (
        # ck_avs_status dropped in migration 022 (status is now BYTEA)
        UniqueConstraint("wallet_id", name="uq_avs_wallet_id"),
        Index("ix_avs_user_id", "user_id"),
        # ix_avs_status dropped in migration 022 (status is now BYTEA)
    )

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    wallet_id = mapped_column(Integer, ForeignKey("wallets.id"), nullable=False)
    # Phase 16: encrypted columns
    status = mapped_column(EncryptedBytes, nullable=False)
    last_checked_at = mapped_column(DateTime(timezone=True), nullable=True)
    open_issues = mapped_column(Integer, nullable=False, default=0)
    notes = mapped_column(EncryptedBytes, nullable=True)
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

    Phase 16: rewrapped_client_dek stores the client DEK re-wrapped with the
    accountant's ML-KEM public key (D-25).
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
    # Phase 16: client DEK re-wrapped with accountant's ML-KEM ek (D-25)
    rewrapped_client_dek = mapped_column(LargeBinary, nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    accountant = relationship("User", foreign_keys=[accountant_user_id])
    client = relationship("User", foreign_keys=[client_user_id])


# ---------------------------------------------------------------------------
# Phase 16: Session DEK Cache (D-26)
# ---------------------------------------------------------------------------


class SessionDekCache(Base):
    """Encrypted DEK cache for IPC between auth-service and FastAPI (D-26).

    auth-service writes this row after login (AES-256-GCM wrapping of the
    plaintext DEK with SESSION_DEK_WRAP_KEY). FastAPI's get_session_dek()
    dependency reads and decrypts it per request. On logout, auth-service
    DELETEs the row — no FK to sessions table (auth-service owns lifecycle).
    """

    __tablename__ = "session_dek_cache"
    __table_args__ = (
        Index("ix_sdc_expires_at", "expires_at"),
    )

    session_id = mapped_column(Text, primary_key=True)
    encrypted_dek = mapped_column(LargeBinary, nullable=False)
    expires_at = mapped_column(DateTime(timezone=True), nullable=False)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
