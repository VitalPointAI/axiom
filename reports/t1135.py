"""
T1135Checker — Foreign Property Check for CRA T1135 form.

Determines whether a user must file T1135 (Foreign Income Verification Statement)
by computing the peak cost basis (MAX total_cost_cad from acb_snapshots) per token
within the fiscal year, categorising each token as:
  - foreign: held on a non-Canadian exchange (Coinbase, Crypto.com, Uphold, etc.)
  - domestic: held on a Canadian exchange (Wealthsimple)
  - ambiguous: self-custodied (NEAR/EVM wallets) — CRA position unclear

CRA threshold: if total peak foreign property cost > $100,000 CAD, T1135 required.

Exports:
    T1135Checker
"""

import logging
from decimal import Decimal
from pathlib import Path
from typing import Optional

from reports.engine import ReportEngine, fiscal_year_range, fmt_cad

logger = logging.getLogger(__name__)

# Exchanges considered Canadian domestic for T1135 purposes
CANADIAN_EXCHANGES = frozenset(['wealthsimple'])

# Exchanges considered foreign (US-headquartered or ambiguous jurisdiction)
# Note: Coinsquare is technically Canadian but has US parent — flagged for specialist review
FOREIGN_EXCHANGES = frozenset(['coinbase', 'crypto_com', 'uphold', 'coinsquare'])

T1135_THRESHOLD = Decimal('100000')

T1135_HEADERS = [
    'Token',
    'Peak Cost (CAD)',
    'Holding Source',
    'Foreign Property',
    'Notes',
]


class T1135Checker(ReportEngine):
    """T1135 Foreign Property Checker using peak ACB cost basis.

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
        """Generate T1135 foreign property check CSV.

        Queries MAX(total_cost_cad) per token from acb_snapshots within the
        fiscal year, then determines holding source from the mock data (in
        production, would join exchange_transactions/wallets to determine source).

        The test interface passes rows as (token_symbol, peak_cost_cad, holding_source)
        tuples — the holding_source comes from the caller's query joining wallets and
        exchange_transactions, or 'self_custody' for NEAR/EVM wallets.

        Args:
            user_id: User to generate report for.
            tax_year: Tax year for peak cost calculation.
            output_dir: Directory to write CSV into.
            year_end_month: Fiscal year end month (1-12, default 12).
            excluded_wallet_ids: Wallet IDs to exclude (currently unused for ACB query).

        Returns:
            dict with keys: total_foreign_cost, threshold, required (bool),
                tokens (list of dicts), self_custody_tokens (list of token symbols).
        """
        self._check_gate(user_id, tax_year)

        start_date, end_date = fiscal_year_range(tax_year, year_end_month)

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # Query peak total_cost_cad per token within fiscal year
            # Also determine holding source by checking exchange_transactions
            # (The holding_source column is resolved via a subquery in production;
            # tests inject it directly as a third column from the mock.)
            cur.execute(
                """
                SELECT
                    acb.token_symbol,
                    MAX(acb.total_cost_cad) AS peak_cost_cad,
                    COALESCE(
                        (
                            SELECT et.exchange
                            FROM transaction_classifications tc
                            JOIN exchange_transactions et ON tc.exchange_transaction_id = et.id
                            WHERE tc.user_id = acb.user_id
                              AND et.asset = acb.token_symbol
                            ORDER BY et.tx_date DESC
                            LIMIT 1
                        ),
                        'self_custody'
                    ) AS holding_source
                FROM acb_snapshots acb
                WHERE acb.user_id = %s
                  AND TO_TIMESTAMP(acb.block_timestamp) >= %s
                  AND TO_TIMESTAMP(acb.block_timestamp) <= %s
                GROUP BY acb.token_symbol, acb.user_id
                """,
                (user_id, start_date, end_date),
            )
            rows = cur.fetchall()
            cur.close()
        finally:
            self.pool.putconn(conn)

        # Categorise each token
        total_foreign_cost = Decimal('0')
        self_custody_tokens = []
        tokens = []
        csv_rows = []

        for row in rows:
            token_symbol, peak_cost_cad, holding_source = row

            peak = Decimal(str(peak_cost_cad)) if peak_cost_cad is not None else Decimal('0')
            source_str = str(holding_source).lower() if holding_source else 'self_custody'

            is_foreign = source_str in FOREIGN_EXCHANGES
            is_domestic = source_str in CANADIAN_EXCHANGES
            is_ambiguous = not is_foreign and not is_domestic  # self_custody or unknown

            if is_ambiguous:
                self_custody_tokens.append(token_symbol)
                foreign_flag = 'Ambiguous'
                notes = 'CRA position unclear — specialist review required'
            elif is_foreign:
                foreign_flag = 'Yes'
                total_foreign_cost += peak
                notes = f'Held on {holding_source} (foreign exchange)'
            else:
                foreign_flag = 'No'
                notes = f'Held on {holding_source} (Canadian exchange)'

            tokens.append({
                'token_symbol': token_symbol,
                'peak_cost_cad': peak,
                'holding_source': source_str,
                'is_foreign': is_foreign,
                'is_ambiguous': is_ambiguous,
            })

            csv_rows.append((
                token_symbol,
                fmt_cad(peak),
                source_str,
                foreign_flag,
                notes,
            ))

        # Footer row with totals
        required = total_foreign_cost > T1135_THRESHOLD
        csv_rows.append((
            'TOTAL',
            fmt_cad(total_foreign_cost),
            '',
            'Required' if required else 'Not Required',
            f'Foreign property threshold: {fmt_cad(T1135_THRESHOLD)} CAD — '
            f'{"MUST FILE T1135" if required else "T1135 not required"}',
        ))

        output_path = str(Path(output_dir) / f't1135_check_{tax_year}.csv')
        self.write_csv(output_path, T1135_HEADERS, csv_rows)

        logger.info(
            "T1135Checker: user_id=%s tax_year=%s total_foreign=%s required=%s",
            user_id, tax_year, total_foreign_cost, required,
        )

        return {
            'total_foreign_cost': total_foreign_cost,
            'threshold': T1135_THRESHOLD,
            'required': required,
            'tokens': tokens,
            'self_custody_tokens': self_custody_tokens,
        }
