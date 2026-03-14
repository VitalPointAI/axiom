"""
LedgerReport — full transaction ledger joining all transaction sources.

Produces a unified CSV audit trail of every NEAR, EVM, and exchange transaction
with their tax classifications. Ordered chronologically.

Exports:
    LedgerReport
"""

import logging
from pathlib import Path
from typing import Optional

from reports.engine import ReportEngine, fiscal_year_range, fmt_cad

logger = logging.getLogger(__name__)

# CSV headers for the unified ledger
LEDGER_HEADERS = [
    'Date',
    'Chain',
    'Account/Exchange',
    'TX Hash/ID',
    'Type',
    'Category',
    'Direction',
    'Counterparty',
    'Amount',
    'Token',
    'Fee',
    'FMV USD',
    'FMV CAD',
    'Classification Source',
    'Confidence',
    'Needs Review',
    'Notes',
]


class LedgerReport(ReportEngine):
    """Full transaction ledger joining NEAR, EVM, and exchange transactions.

    Inherits gate check, pool wiring, and CSV writing from ReportEngine.
    """

    def generate(
        self,
        user_id: int,
        tax_year: int,
        output_dir: str,
        year_end_month: int = 12,
        excluded_wallet_ids: Optional[list] = None,
    ) -> dict:
        """Generate unified transaction ledger CSV.

        Queries:
          1. NEAR/EVM transactions (transactions table) LEFT JOIN transaction_classifications
             where leg_type = 'parent', LEFT JOIN wallets for account_id.
          2. Exchange transactions (transaction_classifications with exchange_transaction_id)
             JOIN exchange_transactions.
          Both sets UNION ALL into one chronologically ordered result.

        Args:
            user_id: User to generate report for.
            tax_year: Tax year (used for fiscal year range).
            output_dir: Directory to write CSV into.
            year_end_month: Fiscal year end month (1-12, default 12).
            excluded_wallet_ids: List of wallet IDs to exclude from on-chain side.

        Returns:
            dict with keys: total_count, count_by_chain, count_by_category.
        """
        self._check_gate(user_id, tax_year)

        start_date, end_date = fiscal_year_range(tax_year, year_end_month)

        # Convert dates to epoch nanoseconds for NEAR block_timestamp comparison
        # and use plain date for exchange tx_date comparison
        int(start_date.strftime('%s')) * 1_000_000_000 \
            if hasattr(start_date, 'strftime') else 0
        int(end_date.strftime('%s')) * 1_000_000_000 \
            if hasattr(end_date, 'strftime') else 0

        # Compute epoch seconds from dates for timestamp comparison
        from datetime import datetime
        start_dt = datetime(start_date.year, start_date.month, start_date.day)
        end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)
        start_epoch_sec = int(start_dt.timestamp())
        end_epoch_sec = int(end_dt.timestamp())
        # NEAR block_timestamp is nanoseconds
        start_epoch_nano = start_epoch_sec * 1_000_000_000
        end_epoch_nano = end_epoch_sec * 1_000_000_000

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # Build wallet exclusion clause for on-chain side
            wallet_exclusion = ''
            wallet_params: list = []
            if excluded_wallet_ids:
                placeholders = ','.join(['%s'] * len(excluded_wallet_ids))
                wallet_exclusion = f'AND t.wallet_id NOT IN ({placeholders})'
                wallet_params = list(excluded_wallet_ids)

            # On-chain transactions (NEAR + EVM) side
            onchain_sql = f"""
                SELECT
                    TO_CHAR(TO_TIMESTAMP(t.block_timestamp / 1000000000.0), 'YYYY-MM-DD HH24:MI:SS')
                        AS date_str,
                    t.chain,
                    COALESCE(w.account_id, '') AS account_or_exchange,
                    COALESCE(t.tx_hash, '') AS tx_ref,
                    COALESCE(t.action_type, '') AS action_type,
                    COALESCE(tc.category, '') AS category,
                    COALESCE(t.direction, '') AS direction,
                    COALESCE(t.counterparty, '') AS counterparty,
                    t.amount AS amount_raw,
                    COALESCE(t.token_id, '') AS token_id,
                    t.fee AS fee_raw,
                    tc.fmv_usd,
                    tc.fmv_cad,
                    COALESCE(tc.classification_source, '') AS classification_source,
                    tc.confidence,
                    COALESCE(tc.needs_review, false) AS needs_review,
                    tc.notes,
                    t.block_timestamp AS sort_ts
                FROM transactions t
                LEFT JOIN transaction_classifications tc
                    ON tc.transaction_id = t.id AND tc.leg_type = 'parent'
                LEFT JOIN wallets w ON t.wallet_id = w.id
                WHERE t.user_id = %s
                  AND t.block_timestamp BETWEEN %s AND %s
                  {wallet_exclusion}
            """
            onchain_params = [user_id, start_epoch_nano, end_epoch_nano] + wallet_params

            # Exchange transactions side
            exchange_sql = """
                SELECT
                    COALESCE(
                        TO_CHAR(et.tx_date, 'YYYY-MM-DD HH24:MI:SS'),
                        TO_CHAR(et.tx_date, 'YYYY-MM-DD')
                    ) AS date_str,
                    'exchange' AS chain,
                    et.exchange AS account_or_exchange,
                    COALESCE(et.tx_id, '') AS tx_ref,
                    COALESCE(et.tx_type, '') AS action_type,
                    COALESCE(tc2.category, '') AS category,
                    '' AS direction,
                    NULL AS counterparty,
                    NULL AS amount_raw,
                    COALESCE(et.asset, '') AS token_id,
                    et.fee AS fee_raw,
                    tc2.fmv_usd,
                    tc2.fmv_cad,
                    COALESCE(tc2.classification_source, '') AS classification_source,
                    tc2.confidence,
                    COALESCE(tc2.needs_review, false) AS needs_review,
                    tc2.notes,
                    EXTRACT(EPOCH FROM et.tx_date)::BIGINT * 1000000000 AS sort_ts
                FROM transaction_classifications tc2
                JOIN exchange_transactions et ON tc2.exchange_transaction_id = et.id
                WHERE tc2.user_id = %s
                  AND tc2.leg_type = 'parent'
                  AND tc2.exchange_transaction_id IS NOT NULL
                  AND et.tx_date BETWEEN %s AND %s
            """
            exchange_params = [user_id, start_date, end_date]

            full_sql = f"""
                SELECT date_str, chain, account_or_exchange, tx_ref,
                       action_type, category, direction, counterparty,
                       amount_raw, token_id, fee_raw, fmv_usd, fmv_cad,
                       classification_source, confidence, needs_review, notes
                FROM (
                    {onchain_sql}
                    UNION ALL
                    {exchange_sql}
                ) combined
                ORDER BY sort_ts ASC NULLS LAST
            """
            all_params = onchain_params + exchange_params

            # Close the regular cursor; open a named cursor for server-side streaming
            cur.close()
            named_cur = conn.cursor(name="ledger_stream")
            named_cur.itersize = 1000
            named_cur.execute(full_sql, all_params)
            rows = list(named_cur)
            named_cur.close()
        finally:
            self.pool.putconn(conn)

        # Build CSV rows
        csv_rows = []
        count_by_chain: dict = {}
        count_by_category: dict = {}

        for row in rows:
            (
                date_str, chain, account_or_exchange, tx_ref,
                action_type, category, direction, counterparty,
                amount_raw, token_id, fee_raw, fmv_usd, fmv_cad,
                classification_source, confidence, needs_review, notes,
            ) = row

            chain_str = str(chain) if chain else ''
            category_str = str(category) if category else ''

            count_by_chain[chain_str] = count_by_chain.get(chain_str, 0) + 1
            count_by_category[category_str] = count_by_category.get(category_str, 0) + 1

            csv_rows.append((
                str(date_str) if date_str else '',
                chain_str,
                str(account_or_exchange) if account_or_exchange else '',
                str(tx_ref) if tx_ref else '',
                str(action_type) if action_type else '',
                category_str,
                str(direction) if direction else '',
                str(counterparty) if counterparty else '',
                str(amount_raw) if amount_raw is not None else '',
                str(token_id) if token_id else '',
                str(fee_raw) if fee_raw is not None else '',
                fmt_cad(fmv_usd),
                fmt_cad(fmv_cad),
                str(classification_source) if classification_source else '',
                str(confidence) if confidence is not None else '',
                'Yes' if needs_review else 'No',
                str(notes) if notes else '',
            ))

        output_path = str(Path(output_dir) / f'transaction_ledger_{tax_year}.csv')
        self.write_csv(output_path, LEDGER_HEADERS, csv_rows)

        logger.info(
            "LedgerReport: user_id=%s tax_year=%s total_count=%d written to %s",
            user_id, tax_year, len(csv_rows), output_path,
        )

        return {
            'total_count': len(csv_rows),
            'count_by_chain': count_by_chain,
            'count_by_category': count_by_category,
        }
