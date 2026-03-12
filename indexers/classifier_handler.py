"""ClassifierHandler — job handler for transaction classification.

Registered in IndexerService as 'classify_transactions' job type.
Classifies all unclassified transactions for the job's user_id.
Seeds classification_rules on first run if rules table is empty.
"""

import logging
from engine.classifier import TransactionClassifier
from engine.rule_seeder import seed_classification_rules

logger = logging.getLogger(__name__)


class ClassifierHandler:
    """Job handler for the 'classify_transactions' job type.

    Wires the full classification pipeline into the IndexerService job queue.
    On first invocation (or when classification_rules is empty), seeds the
    default rule set before classifying.

    Args:
        pool: psycopg2 connection pool (ThreadedConnectionPool or similar).
        price_service: Optional PriceService for FMV lookups on income events.
    """

    def __init__(self, pool, price_service=None):
        self.pool = pool
        self.price_service = price_service
        self.classifier = TransactionClassifier(pool, price_service)
        self._rules_seeded = False

    def _ensure_rules_seeded(self) -> None:
        """Seed classification_rules on first run if table is empty.

        Uses a per-instance flag (_rules_seeded) so the COUNT query runs
        at most once per handler lifetime. Safe to call before every job.
        """
        if self._rules_seeded:
            return
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM classification_rules")
            count = cur.fetchone()[0]
            if count == 0:
                logger.info("No classification rules found; seeding defaults...")
                inserted = seed_classification_rules(self.pool)
                logger.info("Seeded %d classification rules", inserted)
            else:
                logger.debug("classification_rules already populated (%d rules)", count)
            self._rules_seeded = True
        finally:
            self.pool.putconn(conn)

    def run_classify(self, job: dict) -> None:
        """Classify all unclassified transactions for job['user_id'].

        Called by IndexerService when job_type == 'classify_transactions'.

        Full pipeline executed by TransactionClassifier:
          1. Load active rules (cached per TransactionClassifier instance)
          2. For each NEAR/EVM/Exchange tx:
             a. Spam check (SpamDetector)
             b. Internal transfer check (WalletGraph)
             c. Deterministic rule match (priority DESC, first wins)
             d. AI fallback (Claude API) if no match or confidence < 0.70
             e. Staking/lockup event linkage (CLASS-03, CLASS-04)
             f. DEX swap decomposition into parent + child legs (CLASS-05)
          3. Upsert transaction_classifications (preserves specialist_confirmed)
          4. Write classification_audit_log entries

        Args:
            job: Job dict from indexing_jobs row. Must contain 'user_id'.
        """
        user_id = job["user_id"]
        logger.info("Starting classification for user %d", user_id)

        self._ensure_rules_seeded()

        stats = self.classifier.classify_user_transactions(user_id)
        logger.info(
            "Classification complete for user %d: "
            "%d classified, %d confirmed (preserved), %d flagged for review",
            user_id,
            stats["classified"],
            stats["skipped_confirmed"],
            stats["needs_review"],
        )
