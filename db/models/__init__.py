"""
SQLAlchemy 2.0 declarative models for Axiom/NearTax.

Sub-modules: base, _all_models.
All model classes are re-exported from this __init__.py for backward compatibility.
"""

from db.models.base import Base
from db.models._all_models import (
    User,
    Wallet,
    Transaction,
    IndexingJob,
    StakingEvent,
    EpochSnapshot,
    PriceCache,
    LockupEvent,
    ClassificationRule,
    TransactionClassification,
    SpamRule,
    ClassificationAuditLog,
    ACBSnapshot,
    CapitalGainsLedger,
    IncomeLedger,
    PriceCacheMinute,
    VerificationResult,
    AccountVerificationStatus,
    Passkey,
    Session,
    Challenge,
    MagicLinkToken,
    AccountantAccess,
)

__all__ = [
    "Base",
    "User",
    "Wallet",
    "Transaction",
    "IndexingJob",
    "StakingEvent",
    "EpochSnapshot",
    "PriceCache",
    "LockupEvent",
    "ClassificationRule",
    "TransactionClassification",
    "SpamRule",
    "ClassificationAuditLog",
    "ACBSnapshot",
    "CapitalGainsLedger",
    "IncomeLedger",
    "PriceCacheMinute",
    "VerificationResult",
    "AccountVerificationStatus",
    "Passkey",
    "Session",
    "Challenge",
    "MagicLinkToken",
    "AccountantAccess",
]
