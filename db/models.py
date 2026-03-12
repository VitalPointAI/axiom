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
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    """Application users — authenticated via NEAR wallet."""

    __tablename__ = "users"

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    near_account_id = mapped_column(String(128), unique=True, nullable=False)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login_at = mapped_column(DateTime(timezone=True), nullable=True)

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
