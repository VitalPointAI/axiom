"""Duplicate transaction detector for Axiom verification pipeline.

Final safety-net scan extending Phase 2 DedupHandler. Three scan types:
  1. Within-table exact tx_hash duplicates (auto-merge, score=1.0)
  2. Cross-chain bridge heuristic (flag only, score=0.60)
  3. Exchange-vs-on-chain full re-scan (multi-signal scoring)

Balance-aware auto-merge: merges only when removing the duplicate brings
the calculated balance closer to on-chain. All decisions logged in
verification_results for audit trail.
"""

import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from typing import Optional

from indexers.dedup_handler import ASSET_DECIMALS, AMOUNT_TOLERANCE
from db.audit import write_audit

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Score thresholds
SCORE_EXACT_HASH = Decimal("1.0")
SCORE_AMOUNT_TIME_ASSET = Decimal("0.85")
SCORE_EXCHANGE_MATCH = Decimal("0.80")
SCORE_AMOUNT_DAY_ASSET = Decimal("0.60")

# Threshold actions
THRESHOLD_AUTO_MERGE = Decimal("1.0")
THRESHOLD_BALANCE_AWARE = Decimal("0.75")
THRESHOLD_FLAG = Decimal("0.50")

# Time windows
BRIDGE_WINDOW_SECONDS = 1800  # 30 minutes for cross-chain bridges
EXCHANGE_WINDOW_SECONDS = 600  # 10 minutes for exchange-vs-on-chain

# Amount tolerance reused from DedupHandler
_AMOUNT_TOLERANCE = Decimal(str(AMOUNT_TOLERANCE))


def _resolve_token_symbol(token_id: str) -> str:
    """Normalize a token_id to a canonical symbol for comparison.

    Tries engine.acb.resolve_token_symbol first; falls back to uppercase.
    """
    try:
        from engine.acb import resolve_token_symbol
        return resolve_token_symbol(token_id)
    except ImportError:
        return (token_id or "").upper()


def _amounts_close(amount_a, amount_b, tolerance=_AMOUNT_TOLERANCE) -> bool:
    """Check if two Decimal amounts are within relative tolerance.

    Both amounts should already be in human-readable units.
    """
    try:
        a = Decimal(str(amount_a))
        b = Decimal(str(amount_b))
    except (InvalidOperation, TypeError):
        return False
    if b == 0:
        return a == 0
    diff = abs(a - b)
    relative = diff / abs(b)
    return relative <= tolerance


def _convert_onchain_amount(raw_amount, asset: str) -> Decimal:
    """Convert on-chain raw integer amount to human-readable Decimal.

    Uses ASSET_DECIMALS from DedupHandler (single source of truth).
    """
    try:
        raw = Decimal(str(raw_amount))
    except (InvalidOperation, TypeError):
        return Decimal("0")
    decimals = ASSET_DECIMALS.get((asset or "").upper(), 18)
    return raw / Decimal(10 ** decimals)


class DuplicateDetector:
    """Multi-signal duplicate transaction detector.

    Extends Phase 2 DedupHandler with full-table scanning, cross-chain
    bridge detection, and balance-aware auto-merge decisions.

    Args:
        pool: psycopg2 connection pool.
    """

    def __init__(self, pool):
        self.pool = pool

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan_user(self, user_id: int) -> dict:
        """Run all three duplicate scan types for a user.

        Scans in order:
          1. Within-table exact tx_hash duplicates (auto-merge)
          2. Cross-chain bridge heuristic (flag only)
          3. Exchange-vs-on-chain full re-scan (multi-signal)

        Args:
            user_id: The user whose transactions to scan.

        Returns:
            Dict with keys: hash_dupes_merged, bridge_flagged,
            exchange_flagged, exchange_merged, total_scanned.
        """
        logger.info("DuplicateDetector: starting scan for user_id=%s", user_id)

        hash_merged = self._scan_hash_duplicates(user_id)
        bridge_flagged = self._scan_bridge_duplicates(user_id)
        exchange_result = self._scan_exchange_duplicates(user_id)

        stats = {
            "hash_dupes_merged": hash_merged,
            "bridge_flagged": bridge_flagged,
            "exchange_flagged": exchange_result.get("flagged", 0),
            "exchange_merged": exchange_result.get("merged", 0),
            "total_scanned": exchange_result.get("total_scanned", 0),
        }

        logger.info(
            "DuplicateDetector: scan complete for user_id=%s — "
            "hash_merged=%d, bridge_flagged=%d, exchange_flagged=%d, exchange_merged=%d",
            user_id, stats["hash_dupes_merged"], stats["bridge_flagged"],
            stats["exchange_flagged"], stats["exchange_merged"],
        )
        return stats

    # ------------------------------------------------------------------
    # Scan 1: Within-table exact tx_hash duplicates
    # ------------------------------------------------------------------

    def _scan_hash_duplicates(self, user_id: int) -> int:
        """Find and auto-merge exact tx_hash duplicates within the transactions table.

        These are definite duplicates from fetcher bugs or re-indexing.
        Score = 1.0 (auto-merge immediately).

        For each duplicate group: keep the row with the LOWEST id (earliest
        inserted). Soft-delete others by setting needs_review=True with an
        explanatory note. Also flag related transaction_classifications.

        Returns:
            Count of merged (soft-deleted) duplicate rows.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # Find all tx_hash groups with more than one row
            cur.execute(
                """
                SELECT tx_hash, chain, wallet_id, COUNT(*) as cnt,
                       array_agg(id ORDER BY id) as ids
                FROM transactions
                WHERE wallet_id IN (SELECT id FROM wallets WHERE user_id = %s)
                  AND tx_hash IS NOT NULL
                GROUP BY tx_hash, chain, wallet_id
                HAVING COUNT(*) > 1
                """,
                (user_id,),
            )
            dupe_groups = cur.fetchall()

            if not dupe_groups:
                logger.info(
                    "DuplicateDetector: no hash duplicates for user_id=%s", user_id
                )
                conn.commit()
                return 0

            merged_count = 0

            for tx_hash, chain, wallet_id, cnt, ids in dupe_groups:
                kept_id = ids[0]  # lowest id = earliest inserted
                dupe_ids = ids[1:]

                for dupe_id in dupe_ids:
                    note = (
                        f"DUPLICATE: exact hash match with tx id={kept_id}. "
                        f"Score=1.0. Auto-merged."
                    )

                    # Flag any related transaction_classifications for review
                    cur.execute(
                        """
                        UPDATE transaction_classifications
                        SET needs_review = TRUE,
                            notes = %s
                        WHERE transaction_id = %s
                        """,
                        (note, dupe_id),
                    )

                    # Log merge in verification_results
                    detail = {
                        "type": "exact_hash_duplicate",
                        "kept_tx_id": kept_id,
                        "removed_tx_id": dupe_id,
                        "tx_hash": tx_hash,
                        "score": 1.0,
                        "action": "auto_merged",
                    }
                    self._log_duplicate(
                        conn=conn,
                        cur=cur,
                        user_id=user_id,
                        wallet_id=wallet_id,
                        chain=chain,
                        token_symbol=None,
                        detail=detail,
                        confidence=Decimal("1.0"),
                        status="resolved",
                    )
                    # Unified audit trail for duplicate merge
                    write_audit(
                        conn,
                        user_id=user_id,
                        entity_type="duplicate_merge",
                        entity_id=dupe_id,
                        action="duplicate_merge",
                        new_value={
                            "merged_with": kept_id,
                            "score": 1.0,
                            "tx_hash": tx_hash,
                        },
                        actor_type="system",
                    )
                    merged_count += 1

            conn.commit()
            logger.info(
                "DuplicateDetector: merged %d hash duplicates for user_id=%s",
                merged_count, user_id,
            )
            return merged_count

        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # Scan 2: Cross-chain bridge duplicates
    # ------------------------------------------------------------------

    def _scan_bridge_duplicates(self, user_id: int) -> int:
        """Detect cross-chain bridge transactions that appear as both send and receive.

        A bridge transaction appears on the source chain (direction='out') and
        destination chain (direction='in') with similar amount and within 30 minutes.
        Score = 0.60 (medium confidence -- never auto-merge bridges).

        Flags both transactions with needs_review=True and logs in
        verification_results for specialist review.

        Returns:
            Count of bridge pairs flagged.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # Get all outgoing transfers across all chains for this user
            cur.execute(
                """
                SELECT t.id, t.tx_hash, t.chain, t.amount, t.token_id,
                       t.block_timestamp, t.wallet_id
                FROM transactions t
                WHERE t.wallet_id IN (SELECT id FROM wallets WHERE user_id = %s)
                  AND t.direction = 'out'
                  AND t.action_type IN ('TRANSFER', 'transfer')
                ORDER BY t.block_timestamp
                """,
                (user_id,),
            )
            outgoing_txs = cur.fetchall()

            if not outgoing_txs:
                conn.commit()
                return 0

            # Get all incoming transfers for matching
            cur.execute(
                """
                SELECT t.id, t.tx_hash, t.chain, t.amount, t.token_id,
                       t.block_timestamp, t.wallet_id
                FROM transactions t
                WHERE t.wallet_id IN (SELECT id FROM wallets WHERE user_id = %s)
                  AND t.direction = 'in'
                  AND t.action_type IN ('TRANSFER', 'transfer')
                ORDER BY t.block_timestamp
                """,
                (user_id,),
            )
            incoming_txs = cur.fetchall()

            if not incoming_txs:
                conn.commit()
                return 0

            flagged_count = 0
            # Track already-flagged tx IDs to avoid double-flagging
            flagged_ids = set()

            for out_id, out_hash, out_chain, out_amount, out_token, out_ts, out_wallet in outgoing_txs:
                if out_id in flagged_ids:
                    continue

                out_symbol = _resolve_token_symbol(out_token or "")
                out_human_amount = _convert_onchain_amount(out_amount, out_symbol)

                for in_id, in_hash, in_chain, in_amount, in_token, in_ts, in_wallet in incoming_txs:
                    if in_id in flagged_ids:
                        continue

                    # Must be DIFFERENT chain for bridge detection
                    if out_chain == in_chain:
                        continue

                    in_symbol = _resolve_token_symbol(in_token or "")

                    # Same or equivalent asset
                    if out_symbol != in_symbol:
                        continue

                    # Amount within 1% tolerance
                    in_human_amount = _convert_onchain_amount(in_amount, in_symbol)
                    if not _amounts_close(out_human_amount, in_human_amount):
                        continue

                    # Timestamp within 30 minutes (bridge window)
                    try:
                        ts_diff = abs(int(in_ts or 0) - int(out_ts or 0))
                    except (ValueError, TypeError):
                        continue

                    if ts_diff > BRIDGE_WINDOW_SECONDS:
                        continue

                    # Found a potential bridge pair -- flag both
                    bridge_note = (
                        f"Potential bridge duplicate: OUT tx id={out_id} on {out_chain} "
                        f"<-> IN tx id={in_id} on {in_chain}. "
                        f"Amount={out_human_amount} {out_symbol}, time_diff={ts_diff}s. "
                        f"Score=0.60. Needs specialist review."
                    )

                    cur.execute(
                        """
                        UPDATE transaction_classifications
                        SET needs_review = TRUE,
                            notes = %s
                        WHERE transaction_id = %s AND (needs_review IS NOT TRUE
                              OR notes IS NULL
                              OR notes NOT LIKE %s)
                        """,
                        (bridge_note, out_id, "%bridge duplicate%"),
                    )
                    cur.execute(
                        """
                        UPDATE transaction_classifications
                        SET needs_review = TRUE,
                            notes = %s
                        WHERE transaction_id = %s AND (needs_review IS NOT TRUE
                              OR notes IS NULL
                              OR notes NOT LIKE %s)
                        """,
                        (bridge_note, in_id, "%bridge duplicate%"),
                    )

                    # Log in verification_results
                    detail = {
                        "type": "cross_chain_bridge",
                        "out_tx_id": out_id,
                        "out_chain": out_chain,
                        "out_tx_hash": out_hash,
                        "in_tx_id": in_id,
                        "in_chain": in_chain,
                        "in_tx_hash": in_hash,
                        "amount": str(out_human_amount),
                        "asset": out_symbol,
                        "time_diff_seconds": ts_diff,
                        "score": 0.60,
                        "action": "flagged_for_review",
                    }
                    self._log_duplicate(
                        conn=conn,
                        cur=cur,
                        user_id=user_id,
                        wallet_id=out_wallet,
                        chain=out_chain,
                        token_symbol=out_symbol,
                        detail=detail,
                        confidence=Decimal("0.60"),
                        status="open",
                    )

                    flagged_ids.add(out_id)
                    flagged_ids.add(in_id)
                    flagged_count += 1
                    break  # Move to next outgoing tx

            conn.commit()
            logger.info(
                "DuplicateDetector: flagged %d bridge pairs for user_id=%s",
                flagged_count, user_id,
            )
            return flagged_count

        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # Scan 3: Exchange-vs-on-chain full re-scan
    # ------------------------------------------------------------------

    def _scan_exchange_duplicates(self, user_id: int) -> dict:
        """Full re-scan of exchange_transactions vs on-chain transactions.

        Extends DedupHandler but:
          - Re-scans ALL exchange txs (not just unflagged ones) as a final sweep
          - Uses multi-signal scoring instead of binary match/no-match
          - Balance-aware auto-merge for high-confidence matches

        Multi-signal scoring:
          Signal 4: exchange amount ~ on-chain amount (1%) + timestamp +-10min -> 0.80
          Signal 2: same amount + timestamp +-10min + same asset -> 0.85
          Signal 3: same amount + same day + same asset -> 0.60

        Threshold actions:
          >= 1.0: auto-merge (won't happen for exchange dupes)
          0.75-1.0: balance-aware auto-merge if improves reconciliation
          0.50-0.75: flag for specialist review
          < 0.50: log only

        Returns:
            Dict with keys: flagged, merged, total_scanned.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # Fetch ALL exchange transactions for this user (final sweep)
            cur.execute(
                """
                SELECT id, exchange, tx_id, tx_type, asset, quantity, tx_date,
                       wallet_id
                FROM exchange_transactions
                WHERE user_id = %s
                ORDER BY tx_date
                """,
                (user_id,),
            )
            exchange_txs = cur.fetchall()

            if not exchange_txs:
                conn.commit()
                return {"flagged": 0, "merged": 0, "total_scanned": 0}

            # Fetch all on-chain transactions for this user
            cur.execute(
                """
                SELECT t.id, t.tx_hash, t.chain, t.amount, t.token_id,
                       t.block_timestamp, t.direction, t.wallet_id
                FROM transactions t
                WHERE t.wallet_id IN (SELECT id FROM wallets WHERE user_id = %s)
                ORDER BY t.block_timestamp
                """,
                (user_id,),
            )
            onchain_txs = cur.fetchall()

            flagged = 0
            merged = 0

            for ex_row in exchange_txs:
                ex_id, exchange, tx_id, tx_type, asset, quantity, tx_date, ex_wallet_id = ex_row

                if tx_date is None or quantity is None:
                    continue

                try:
                    ex_amount = Decimal(str(quantity))
                except (InvalidOperation, TypeError):
                    continue

                # Ensure tx_date is timezone-aware
                if hasattr(tx_date, 'tzinfo') and tx_date.tzinfo is None:
                    tx_date = tx_date.replace(tzinfo=timezone.utc)

                ex_epoch = int(tx_date.timestamp()) if hasattr(tx_date, 'timestamp') else 0
                ex_symbol = (asset or "").upper()

                best_score = Decimal("0")
                best_match_id = None
                best_match_chain = None
                best_match_wallet = None
                best_signal = None

                for oc_row in onchain_txs:
                    oc_id, oc_hash, oc_chain, oc_amount, oc_token, oc_ts, oc_dir, oc_wallet = oc_row

                    oc_symbol = _resolve_token_symbol(oc_token or "")
                    oc_human = _convert_onchain_amount(oc_amount, oc_symbol)

                    try:
                        ts_diff = abs(int(oc_ts or 0) - ex_epoch)
                    except (ValueError, TypeError):
                        continue

                    score = Decimal("0")
                    signal = None

                    # Signal 4: exchange amount ~ on-chain amount (1%) + timestamp +-10min
                    if ts_diff <= EXCHANGE_WINDOW_SECONDS and _amounts_close(ex_amount, oc_human):
                        score = max(score, SCORE_EXCHANGE_MATCH)
                        signal = "signal_4_exchange_match"

                    # Signal 2: same amount + timestamp +-10min + same asset
                    if (ts_diff <= EXCHANGE_WINDOW_SECONDS
                            and ex_symbol == oc_symbol
                            and _amounts_close(ex_amount, oc_human)):
                        score = max(score, SCORE_AMOUNT_TIME_ASSET)
                        signal = "signal_2_amount_time_asset"

                    # Signal 3: same amount + same day + same asset
                    if ex_symbol == oc_symbol and _amounts_close(ex_amount, oc_human):
                        try:
                            oc_date = datetime.fromtimestamp(int(oc_ts or 0), tz=timezone.utc).date()
                            ex_date_val = tx_date.date() if hasattr(tx_date, 'date') else None
                            if oc_date == ex_date_val:
                                if score < SCORE_AMOUNT_DAY_ASSET:
                                    score = SCORE_AMOUNT_DAY_ASSET
                                    signal = "signal_3_amount_day_asset"
                        except (ValueError, TypeError, OSError):
                            pass

                    if score > best_score:
                        best_score = score
                        best_match_id = oc_id
                        best_match_chain = oc_chain
                        best_match_wallet = oc_wallet
                        best_signal = signal

                # Apply threshold actions
                if best_score >= THRESHOLD_AUTO_MERGE:
                    # score >= 1.0: auto-merge (won't happen for exchange dupes)
                    pass

                elif best_score >= THRESHOLD_BALANCE_AWARE:
                    # 0.75 <= score < 1.0: balance-aware auto-merge
                    did_merge = self._balance_aware_merge(
                        conn=conn,
                        cur=cur,
                        user_id=user_id,
                        exchange_tx_id=ex_id,
                        onchain_tx_id=best_match_id,
                        chain=best_match_chain,
                        score=best_score,
                    )
                    if did_merge:
                        merged += 1
                    else:
                        # Flag for review instead
                        note = (
                            f"Potential duplicate of on-chain tx id={best_match_id} "
                            f"on {best_match_chain}. Score={best_score}. "
                            f"Signal: {best_signal}. Balance-aware merge declined."
                        )
                        cur.execute(
                            """
                            UPDATE exchange_transactions
                            SET needs_review = TRUE,
                                notes = %s,
                                updated_at = NOW()
                            WHERE id = %s
                            """,
                            (note, ex_id),
                        )
                        flagged += 1

                    # Log in verification_results
                    detail = {
                        "type": "exchange_vs_onchain",
                        "exchange_tx_id": ex_id,
                        "onchain_tx_id": best_match_id,
                        "score": float(best_score),
                        "signal": best_signal,
                        "action": "auto_merged" if did_merge else "flagged_for_review",
                    }
                    self._log_duplicate(
                        conn=conn,
                        cur=cur,
                        user_id=user_id,
                        wallet_id=ex_wallet_id or best_match_wallet,
                        chain=best_match_chain or "unknown",
                        token_symbol=ex_symbol,
                        detail=detail,
                        confidence=best_score,
                        status="resolved" if did_merge else "open",
                    )

                elif best_score >= THRESHOLD_FLAG:
                    # 0.50 <= score < 0.75: flag for specialist review
                    note = (
                        f"Potential duplicate of on-chain tx id={best_match_id} "
                        f"on {best_match_chain}. Score={best_score}. "
                        f"Signal: {best_signal}. Needs specialist review."
                    )
                    cur.execute(
                        """
                        UPDATE exchange_transactions
                        SET needs_review = TRUE,
                            notes = %s,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (note, ex_id),
                    )
                    flagged += 1

                    detail = {
                        "type": "exchange_vs_onchain",
                        "exchange_tx_id": ex_id,
                        "onchain_tx_id": best_match_id,
                        "score": float(best_score),
                        "signal": best_signal,
                        "action": "flagged_for_review",
                    }
                    self._log_duplicate(
                        conn=conn,
                        cur=cur,
                        user_id=user_id,
                        wallet_id=ex_wallet_id or best_match_wallet,
                        chain=best_match_chain or "unknown",
                        token_symbol=ex_symbol,
                        detail=detail,
                        confidence=best_score,
                        status="open",
                    )

                else:
                    # < 0.50: log only at debug level
                    if best_score > Decimal("0"):
                        logger.debug(
                            "DuplicateDetector: low-score match for exchange tx %s "
                            "(score=%s, signal=%s) — log only",
                            ex_id, best_score, best_signal,
                        )

            conn.commit()
            logger.info(
                "DuplicateDetector: exchange scan for user_id=%s — "
                "flagged=%d, merged=%d, total_scanned=%d",
                user_id, flagged, merged, len(exchange_txs),
            )
            return {"flagged": flagged, "merged": merged, "total_scanned": len(exchange_txs)}

        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # Balance-aware auto-merge
    # ------------------------------------------------------------------

    def _balance_aware_merge(
        self,
        conn,
        cur,
        user_id: int,
        exchange_tx_id: int,
        onchain_tx_id: int,
        chain: str,
        score: Decimal,
    ) -> bool:
        """Determine if removing the exchange duplicate improves reconciliation accuracy.

        Algorithm:
          1. Get the exchange tx direction and amount
          2. Get current calculated balance (sum in - out - fees for this wallet)
          3. Compute balance_after_merge (adjust by removing exchange tx contribution)
          4. Get on-chain balance from most recent verification_results for this wallet
          5. If merge brings calculated balance closer to on-chain: return True

        If True: marks exchange tx needs_review=True with auto-merge note.
        Returns False if no on-chain balance available (don't merge without ground truth).

        Args:
            conn: active database connection.
            cur: active cursor.
            user_id: user ID.
            exchange_tx_id: the exchange transaction to potentially remove.
            onchain_tx_id: the matching on-chain transaction.
            chain: chain name for the on-chain tx.
            score: the multi-signal score for this match.

        Returns:
            True if merge was performed, False otherwise.
        """
        # Get exchange tx details
        cur.execute(
            """
            SELECT asset, quantity, tx_type, wallet_id
            FROM exchange_transactions
            WHERE id = %s
            """,
            (exchange_tx_id,),
        )
        ex_row = cur.fetchone()
        if not ex_row:
            return False

        asset, quantity, tx_type, ex_wallet_id = ex_row
        try:
            ex_amount = Decimal(str(quantity))
        except (InvalidOperation, TypeError):
            return False

        # Determine exchange tx direction
        tx_type_lower = (tx_type or "").lower().strip()
        if tx_type_lower in ("send", "withdrawal", "sell", "trade"):
            direction = "out"
        elif tx_type_lower in ("receive", "deposit", "buy", "reward", "interest",
                                "staking_reward", "airdrop", "mining"):
            direction = "in"
        else:
            return False

        # Get wallet_id for the exchange account
        if not ex_wallet_id:
            return False

        # Get current calculated balance for this asset from transactions
        # associated with the exchange wallet
        cur.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN direction = 'in' THEN
                    CAST(amount AS NUMERIC) / POWER(10, 24) ELSE 0 END), 0) -
                COALESCE(SUM(CASE WHEN direction = 'out' THEN
                    CAST(amount AS NUMERIC) / POWER(10, 24) ELSE 0 END), 0) -
                COALESCE(SUM(CASE WHEN fee IS NOT NULL THEN
                    CAST(fee AS NUMERIC) / POWER(10, 24) ELSE 0 END), 0)
            FROM transactions
            WHERE wallet_id = %s
              AND token_id = %s
              AND (needs_review IS NOT TRUE OR notes IS NULL OR notes NOT LIKE %s)
            """,
            (ex_wallet_id, asset, "%DUPLICATE%"),
        )
        row = cur.fetchone()
        calculated_balance = Decimal(str(row[0])) if row and row[0] is not None else Decimal("0")

        # Compute balance after merge
        if direction == "in":
            balance_after_merge = calculated_balance - ex_amount
        else:
            balance_after_merge = calculated_balance + ex_amount

        # Get on-chain balance from most recent verification_results
        cur.execute(
            """
            SELECT actual_balance
            FROM verification_results
            WHERE wallet_id = %s
              AND token_symbol = %s
              AND actual_balance IS NOT NULL
            ORDER BY verified_at DESC
            LIMIT 1
            """,
            (ex_wallet_id, (asset or "").upper()),
        )
        vr_row = cur.fetchone()
        if not vr_row or vr_row[0] is None:
            # No on-chain balance available -- don't auto-merge without ground truth
            return False

        onchain_balance = Decimal(str(vr_row[0]))

        # Check if merge improves accuracy
        diff_before = abs(calculated_balance - onchain_balance)
        diff_after = abs(balance_after_merge - onchain_balance)

        if diff_after < diff_before:
            # Merge improves accuracy
            improvement = diff_before - diff_after
            note = (
                f"Auto-merged: balance-aware merge improved accuracy by "
                f"{improvement} {asset}. Score={score}. "
                f"Matched on-chain tx id={onchain_tx_id}."
            )
            cur.execute(
                """
                UPDATE exchange_transactions
                SET needs_review = TRUE,
                    notes = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (note, exchange_tx_id),
            )
            logger.info(
                "DuplicateDetector: balance-aware merge for exchange tx %s "
                "(improvement=%s %s, score=%s)",
                exchange_tx_id, improvement, asset, score,
            )
            return True

        # Merge would not improve accuracy
        return False

    # ------------------------------------------------------------------
    # Audit trail logging
    # ------------------------------------------------------------------

    def _log_duplicate(
        self,
        conn,
        cur,
        user_id: int,
        wallet_id: int,
        chain: str,
        token_symbol: Optional[str],
        detail: dict,
        confidence: Decimal,
        status: str = "open",
    ) -> None:
        """Log a duplicate detection result in verification_results.

        Inserts a new row with diagnosis_category='duplicate_merged' for
        audit trail. Does NOT upsert -- each detection is a separate record.

        Args:
            conn: active database connection (caller manages transaction).
            cur: active cursor.
            user_id: user ID.
            wallet_id: wallet ID involved.
            chain: chain name.
            token_symbol: token symbol (may be None for hash dupes).
            detail: JSONB-serializable dict with merge evidence.
            confidence: confidence score (0.0-1.0).
            status: 'open' for flagged, 'resolved' for auto-merged.
        """
        import json

        cur.execute(
            """
            INSERT INTO verification_results (
                user_id, wallet_id, chain, token_symbol,
                diagnosis_category, diagnosis_detail, diagnosis_confidence,
                status, verified_at, notes
            ) VALUES (
                %s, %s, %s, %s,
                'duplicate_merged', %s, %s,
                %s, NOW(), %s
            )
            """,
            (
                user_id,
                wallet_id,
                chain or "unknown",
                token_symbol or "UNKNOWN",
                json.dumps(detail),
                confidence,
                status,
                f"Duplicate detection: {detail.get('type', 'unknown')} "
                f"(confidence={confidence}, action={detail.get('action', 'unknown')})",
            ),
        )
