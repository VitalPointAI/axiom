"""Gap detection re-index with loop protection.

Queues targeted re-index jobs when balance mismatches are detected by
the BalanceReconciler. Caps retries at MAX_REINDEX_PER_DAY per wallet
to prevent infinite re-index loops. After the cap, sets
manual_review_required on the verification result.
"""

import json
import logging

logger = logging.getLogger(__name__)

MAX_REINDEX_PER_DAY = 3


def get_reindex_count_today(pool, user_id, wallet_id):
    """Count re-index jobs created today for a wallet.

    Args:
        pool: psycopg2 connection pool.
        user_id: User ID.
        wallet_id: Wallet ID.

    Returns:
        int count of re-index jobs today.
    """
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*) FROM indexing_jobs
            WHERE user_id = %s AND wallet_id = %s
              AND job_type LIKE '%%reindex%%'
              AND created_at >= CURRENT_DATE
            """,
            (user_id, wallet_id),
        )
        count = cur.fetchone()[0]
        cur.close()
        conn.commit()
        return count
    except Exception:
        conn.rollback()
        return 0
    finally:
        pool.putconn(conn)


def queue_reindex_if_needed(pool, user_id, wallet_id, chain, mismatch_info):
    """Queue a targeted re-index job if retry cap not reached.

    Args:
        pool: psycopg2 connection pool.
        user_id: User ID.
        wallet_id: Wallet ID.
        chain: Chain name (e.g. 'near', 'ethereum').
        mismatch_info: Dict with mismatch details (difference, expected, actual).

    Returns:
        True if re-index job queued, False if capped.
    """
    count = get_reindex_count_today(pool, user_id, wallet_id)

    if count >= MAX_REINDEX_PER_DAY:
        logger.warning(
            "Re-index cap reached for wallet_id=%s (%d/%d today). "
            "Setting manual_review_required.",
            wallet_id, count, MAX_REINDEX_PER_DAY,
        )
        _set_manual_review(pool, wallet_id)
        return False

    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO indexing_jobs
                (user_id, wallet_id, chain, job_type, status, priority, cursor)
            VALUES (%s, %s, %s, %s, 'queued', 5, %s)
            """,
            (
                user_id,
                wallet_id,
                chain,
                f"{chain}_reindex",
                json.dumps(mismatch_info) if mismatch_info else None,
            ),
        )
        conn.commit()
        cur.close()
        logger.info(
            "Queued re-index job for wallet_id=%s chain=%s (attempt %d/%d today)",
            wallet_id, chain, count + 1, MAX_REINDEX_PER_DAY,
        )
        return True
    except Exception:
        conn.rollback()
        logger.error(
            "Failed to queue re-index for wallet_id=%s", wallet_id, exc_info=True,
        )
        return False
    finally:
        pool.putconn(conn)


def _set_manual_review(pool, wallet_id):
    """Set manual_review_required on verification result for this wallet.

    Args:
        pool: psycopg2 connection pool.
        wallet_id: Wallet ID.
    """
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE verification_results
            SET manual_review_required = true, updated_at = NOW()
            WHERE wallet_id = %s AND status = 'open'
            """,
            (wallet_id,),
        )
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        logger.error(
            "Failed to set manual_review for wallet_id=%s", wallet_id, exc_info=True,
        )
    finally:
        pool.putconn(conn)
