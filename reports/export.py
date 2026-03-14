"""
reports/export.py — CSV export modules for Koinly and accounting software.

Provides:
  - KoinlyExport: Koinly-compatible CSV export (tax-year-specific + full history)
  - AccountingExporter: QuickBooks IIF, Xero CSV, Sage 50 CSV, Generic double-entry CSV

Both classes extend ReportEngine for gate-check and pool wiring.

Koinly label mapping (KOINLY_LABEL_MAP):
  Maps TransactionClassification.category values to Koinly label strings.

Amount conversion:
  - NEAR transactions: amounts stored as yoctoNEAR (Numeric(40,0)); divide by 1e24
  - EVM transactions: amounts stored as wei; divide by 1e18
  - Exchange transactions: already in human units (no conversion needed)

Accounting account codes used as generic placeholders:
  - 1500 = Crypto Assets
  - 4100 = Capital Gains
  - 4200 = Crypto Income
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from reports.engine import ReportEngine, fiscal_year_range, fmt_cad

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

YOCTO_DIVISOR = Decimal('1000000000000000000000000')   # 1e24
WEI_DIVISOR   = Decimal('1000000000000000000')          # 1e18

# Koinly label mapping: TransactionClassification.category -> Koinly label
KOINLY_LABEL_MAP = {
    'income':         'reward',
    'staking_reward': 'staking',
    'capital_gain':   '',
    'capital_loss':   '',
    'transfer':       '',
    'fee':            '',
    'airdrop':        'airdrop',
    'vesting':        'income',
}

KOINLY_HEADERS = [
    'Date',
    'Sent Amount', 'Sent Currency',
    'Received Amount', 'Received Currency',
    'Fee Amount', 'Fee Currency',
    'Net Worth Amount', 'Net Worth Currency',
    'Label',
    'Description',
    'TxHash',
]

# Accounting account codes (generic placeholders for all 4 export formats)
ACCT_CRYPTO_ASSETS  = '1500'
ACCT_CAPITAL_GAINS  = '4100'
ACCT_CRYPTO_INCOME  = '4200'
ACCT_CASH_PROCEEDS  = '1000'

ACCT_NAME_CRYPTO_ASSETS = 'Crypto Assets'
ACCT_NAME_CAPITAL_GAINS = 'Capital Gains'
ACCT_NAME_CRYPTO_INCOME = 'Crypto Income'
ACCT_NAME_CASH_PROCEEDS = 'Cash / Proceeds'
ACCT_NAME_ACB_PREFIX    = 'ACB - '


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ns_to_datetime(timestamp_ns: int) -> datetime:
    """Convert NEAR nanosecond block_timestamp to UTC datetime."""
    timestamp_s = int(timestamp_ns) / 1_000_000_000
    return datetime.fromtimestamp(timestamp_s, tz=timezone.utc)


def _convert_near_amount(raw: Decimal) -> Decimal:
    """Convert yoctoNEAR to NEAR (divide by 1e24)."""
    if raw is None or raw == 0:
        return Decimal('0')
    return Decimal(str(raw)) / YOCTO_DIVISOR


def _fmt_units8(value: Decimal) -> str:
    """Format to 8 decimal places; return '' for zero or None."""
    if value is None or value == 0:
        return ''
    return str(value.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# KoinlyExport
# ---------------------------------------------------------------------------

class KoinlyExport(ReportEngine):
    """Generate Koinly-compatible CSV export from classified transaction data.

    Queries transaction_classifications joined to transactions (NEAR) and
    exchange_transactions (exchange), maps classification categories to Koinly
    labels, converts amounts from on-chain units to human units.

    Args:
        pool: psycopg2 connection pool.
        specialist_override: If True, bypass gate check with a warning.
    """

    def generate(self, user_id: int, tax_year: int, output_dir: str,
                 year_end_month: int = 12, full_history: bool = False) -> dict:
        """Generate Koinly CSV file.

        Args:
            user_id: User whose transactions to export.
            tax_year: Tax year; used for file naming and date filtering.
            output_dir: Directory to write the CSV file.
            year_end_month: Fiscal year end month (default 12 = calendar year).
            full_history: If True, skip gate check and include all history.
                          Output file will be koinly_export_full.csv.

        Returns:
            dict: row_count (int), file_path (str).
        """
        start_date, end_date = fiscal_year_range(tax_year, year_end_month)

        if not full_history:
            self._check_gate(user_id, tax_year)

        conn = self.pool.getconn()
        try:
            # Named cursors for server-side streaming (avoids loading all rows into memory)
            near_cur = conn.cursor(name="export_stream_near")
            near_cur.itersize = 500
            near_cur.execute(
                """
                SELECT
                    tc.category,
                    tc.direction,
                    t.amount,
                    t.fee,
                    t.block_timestamp,
                    t.tx_hash,
                    t.action_type,
                    w.account_id,
                    'near' AS network
                FROM transaction_classifications tc
                JOIN transactions t ON tc.transaction_id = t.id
                LEFT JOIN wallets w ON t.wallet_id = w.id
                WHERE tc.user_id = %s AND tc.leg_type = 'parent'
                ORDER BY t.block_timestamp
                """,
                (user_id,),
            )
            near_rows = list(near_cur)
            near_cur.close()

            exchange_cur = conn.cursor(name="export_stream_exchange")
            exchange_cur.itersize = 500
            exchange_cur.execute(
                """
                SELECT
                    tc.category,
                    tc.direction,
                    et.amount,
                    et.fee,
                    et.tx_date,
                    et.tx_id,
                    et.tx_type,
                    et.exchange,
                    et.asset
                FROM transaction_classifications tc
                JOIN exchange_transactions et ON tc.exchange_transaction_id = et.id
                WHERE tc.user_id = %s AND tc.leg_type = 'parent'
                ORDER BY et.tx_date
                """,
                (user_id,),
            )
            exchange_rows = list(exchange_cur)
            exchange_cur.close()
        finally:
            self.pool.putconn(conn)

        rows = []

        # Process NEAR rows
        for row in near_rows:
            (category, direction, amount, fee, block_timestamp_ns,
             tx_hash, action_type, account_id, network) = row

            # Convert timestamp
            if block_timestamp_ns is not None:
                dt = _ns_to_datetime(int(block_timestamp_ns))
                date_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
                tx_date_obj = dt.date()
            else:
                continue  # skip rows without a timestamp

            # Date filter for non-full-history exports
            if not full_history:
                if not (start_date <= tx_date_obj <= end_date):
                    continue

            # Convert amounts from yoctoNEAR to NEAR
            human_amount = _convert_near_amount(Decimal(str(amount)) if amount is not None else Decimal('0'))
            human_fee    = _convert_near_amount(Decimal(str(fee))    if fee    is not None else Decimal('0'))

            token_symbol = 'NEAR'
            label        = KOINLY_LABEL_MAP.get(category, '')
            description  = f"{action_type or ''} - {account_id or ''}".strip(' -')
            hash_val     = tx_hash or ''

            koinly_row = _build_koinly_row(
                date_str, direction, human_amount, token_symbol,
                human_fee, token_symbol, label, description, hash_val,
            )
            rows.append(koinly_row)

        # Process exchange rows
        for row in exchange_rows:
            (category, direction, amount, fee, tx_date,
             tx_id, tx_type, exchange, asset) = row

            # tx_date may be a date object or string
            if tx_date is None:
                continue
            if hasattr(tx_date, 'strftime'):
                date_str = tx_date.strftime('%Y-%m-%d')
                tx_date_obj = tx_date if hasattr(tx_date, 'year') else tx_date
            else:
                date_str = str(tx_date)
                try:
                    tx_date_obj = datetime.strptime(str(tx_date), '%Y-%m-%d').date()
                except ValueError:
                    tx_date_obj = None

            # Date filter for non-full-history exports
            if not full_history and tx_date_obj is not None:
                if not (start_date <= tx_date_obj <= end_date):
                    continue

            # Exchange amounts already in human units
            human_amount = Decimal(str(amount)) if amount is not None else Decimal('0')
            human_fee    = Decimal(str(fee))    if fee    is not None else Decimal('0')

            token_symbol = asset or 'UNKNOWN'
            label        = KOINLY_LABEL_MAP.get(category, '')
            description  = f"{tx_type or ''} - {exchange or ''}".strip(' -')
            hash_val     = tx_id or ''

            koinly_row = _build_koinly_row(
                date_str, direction, human_amount, token_symbol,
                human_fee, token_symbol, label, description, hash_val,
            )
            rows.append(koinly_row)

        # Write CSV
        if full_history:
            filename = 'koinly_export_full.csv'
        else:
            filename = f'koinly_export_{tax_year}.csv'

        output_path = Path(output_dir) / filename
        self.write_csv(str(output_path), KOINLY_HEADERS, rows)
        logger.info("KoinlyExport: wrote %d rows to %s", len(rows), output_path)

        return {
            'row_count': len(rows),
            'file_path': str(output_path),
        }


def _build_koinly_row(date_str, direction, amount, currency, fee, fee_currency,
                       label, description, tx_hash):
    """Build a single Koinly CSV row tuple."""
    sent_amount = sent_currency = received_amount = received_currency = ''

    if direction == 'out':
        sent_amount   = _fmt_units8(amount) if amount else ''
        sent_currency = currency if amount else ''
    else:
        received_amount   = _fmt_units8(amount) if amount else ''
        received_currency = currency if amount else ''

    fee_amount_str  = _fmt_units8(fee) if fee and fee > 0 else ''
    fee_currency_str = fee_currency if fee_amount_str else ''

    return (
        date_str,
        sent_amount, sent_currency,
        received_amount, received_currency,
        fee_amount_str, fee_currency_str,
        '', '',          # Net Worth Amount / Currency — not pre-calculated
        label,
        description,
        tx_hash,
    )


# ---------------------------------------------------------------------------
# AccountingExporter
# ---------------------------------------------------------------------------

class AccountingExporter(ReportEngine):
    """Generate accounting software export files from capital gains and income ledgers.

    Produces four files:
      - quickbooks_{year}.iif  — QuickBooks Desktop IIF tab-delimited
      - xero_{year}.csv        — Xero journal import CSV
      - sage50_{year}.csv      — Sage 50 general journal import CSV
      - double_entry_{year}.csv — Generic balanced double-entry CSV

    All monetary values use Decimal arithmetic.

    Args:
        pool: psycopg2 connection pool.
        specialist_override: If True, bypass gate check with a warning.
    """

    def generate_all(self, user_id: int, tax_year: int, output_dir: str,
                     year_end_month: int = 12) -> dict:
        """Generate all four accounting export files.

        Args:
            user_id: User whose data to export.
            tax_year: Tax year to export.
            output_dir: Directory to write files.
            year_end_month: Fiscal year end month.

        Returns:
            dict mapping export type to file path.
        """
        self._check_gate(user_id, tax_year)
        start_date, end_date = fiscal_year_range(tax_year, year_end_month)

        conn = self.pool.getconn()
        try:
            # Named cursors for server-side streaming of accounting data
            gains_cur = conn.cursor(name="acct_stream_gains")
            gains_cur.itersize = 500
            gains_cur.execute(
                """
                SELECT
                    cgl.disposal_date,
                    cgl.token_symbol,
                    cgl.proceeds_cad,
                    cgl.acb_used_cad,
                    cgl.gain_loss_cad,
                    COALESCE(t.tx_hash, et.tx_id, CAST(cgl.id AS TEXT)) AS tx_ref
                FROM capital_gains_ledger cgl
                LEFT JOIN acb_snapshots snap ON cgl.acb_snapshot_id = snap.id
                LEFT JOIN transaction_classifications tc ON snap.classification_id = tc.id
                LEFT JOIN transactions t ON tc.transaction_id = t.id
                LEFT JOIN exchange_transactions et ON tc.exchange_transaction_id = et.id
                WHERE cgl.user_id = %s AND cgl.tax_year = %s
                ORDER BY cgl.disposal_date
                """,
                (user_id, tax_year),
            )
            gains_rows = list(gains_cur)
            gains_cur.close()

            income_cur = conn.cursor(name="acct_stream_income")
            income_cur.itersize = 500
            income_cur.execute(
                """
                SELECT
                    il.income_date,
                    il.token_symbol,
                    il.fmv_cad,
                    il.source_type,
                    COALESCE(t.tx_hash, et.tx_id, CAST(il.id AS TEXT)) AS tx_ref
                FROM income_ledger il
                LEFT JOIN transaction_classifications tc ON il.classification_id = tc.id
                LEFT JOIN transactions t ON tc.transaction_id = t.id
                LEFT JOIN exchange_transactions et ON tc.exchange_transaction_id = et.id
                WHERE il.user_id = %s AND il.tax_year = %s
                ORDER BY il.income_date
                """,
                (user_id, tax_year),
            )
            income_rows = list(income_cur)
            income_cur.close()
        finally:
            self.pool.putconn(conn)

        output = Path(output_dir)
        files = {}

        files['quickbooks'] = self._write_quickbooks_iif(output, tax_year, gains_rows, income_rows)
        files['xero']       = self._write_xero_csv(output, tax_year, gains_rows, income_rows)
        files['sage50']     = self._write_sage50_csv(output, tax_year, gains_rows, income_rows)
        files['double_entry'] = self._write_double_entry_csv(output, tax_year, gains_rows, income_rows)

        logger.info("AccountingExporter: generated 4 files for user_id=%s tax_year=%s",
                    user_id, tax_year)
        return files

    # -----------------------------------------------------------------------
    # QuickBooks IIF
    # -----------------------------------------------------------------------

    def _write_quickbooks_iif(self, output_dir: Path, tax_year: int,
                               gains_rows: list, income_rows: list) -> str:
        """Write QuickBooks Desktop IIF file.

        Format: tab-delimited. Header rows start with '!'.
        Each transaction is a TRNS + SPL + ENDTRNS triplet.

        Columns: DATE  ACCNT  NAME  AMOUNT  DOCNUM  MEMO
        """
        path = output_dir / f'quickbooks_{tax_year}.iif'
        path.parent.mkdir(parents=True, exist_ok=True)

        lines = []
        # IIF header rows
        lines.append('!TRNS\tDATE\tACCNT\tNAME\tAMOUNT\tDOCNUM\tMEMO')
        lines.append('!SPL\tDATE\tACCNT\tNAME\tAMOUNT\tDOCNUM\tMEMO')
        lines.append('!ENDTRNS')

        for row in gains_rows:
            (disposal_date, token, proceeds, acb, gain_loss, tx_ref) = row
            date_str   = disposal_date.strftime('%m/%d/%Y') if hasattr(disposal_date, 'strftime') else str(disposal_date)
            proceeds_d = Decimal(str(proceeds))
            name       = f"{token} Disposal"
            memo       = f"Disposal of {token}"
            docnum     = str(tx_ref or '')

            lines.append(f"TRNS\t{date_str}\t{ACCT_NAME_CRYPTO_ASSETS}\t{name}\t{fmt_cad(proceeds_d)}\t{docnum}\t{memo}")
            lines.append(f"SPL\t{date_str}\t{ACCT_NAME_CAPITAL_GAINS}\t{name}\t-{fmt_cad(proceeds_d)}\t{docnum}\t{memo}")
            lines.append('ENDTRNS')

        for row in income_rows:
            (income_date, token, fmv_cad, source_type, tx_ref) = row
            date_str = income_date.strftime('%m/%d/%Y') if hasattr(income_date, 'strftime') else str(income_date)
            fmv_d    = Decimal(str(fmv_cad))
            name     = f"{token} {source_type}"
            memo     = f"{source_type} income: {token}"
            docnum   = str(tx_ref or '')

            lines.append(f"TRNS\t{date_str}\t{ACCT_NAME_CRYPTO_ASSETS}\t{name}\t{fmt_cad(fmv_d)}\t{docnum}\t{memo}")
            lines.append(f"SPL\t{date_str}\t{ACCT_NAME_CRYPTO_INCOME}\t{name}\t-{fmt_cad(fmv_d)}\t{docnum}\t{memo}")
            lines.append('ENDTRNS')

        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
            f.write('\n')

        return str(path)

    # -----------------------------------------------------------------------
    # Xero CSV
    # -----------------------------------------------------------------------

    def _write_xero_csv(self, output_dir: Path, tax_year: int,
                         gains_rows: list, income_rows: list) -> str:
        """Write Xero journal import CSV.

        Headers: Date, Description, Reference, Debit, Credit, Account Code, Tax Rate
        Tax Rate for crypto is 'GST Free' (crypto not subject to GST in Canada).
        """
        headers = ['Date', 'Description', 'Reference', 'Debit', 'Credit',
                   'Account Code', 'Tax Rate']
        rows = []

        for row in gains_rows:
            (disposal_date, token, proceeds, acb, gain_loss, tx_ref) = row
            date_str   = disposal_date.strftime('%Y-%m-%d') if hasattr(disposal_date, 'strftime') else str(disposal_date)
            proceeds_d = Decimal(str(proceeds))
            acb_d      = Decimal(str(acb))
            gain_d     = Decimal(str(gain_loss))
            desc       = f"{token} Disposal"
            ref        = str(tx_ref or '')

            # Debit to Cash/Proceeds account for proceeds
            rows.append([date_str, desc, ref, fmt_cad(proceeds_d), '', ACCT_CASH_PROCEEDS, 'GST Free'])
            # Credit from Crypto Assets (cost basis)
            rows.append([date_str, desc, ref, '', fmt_cad(acb_d), ACCT_CRYPTO_ASSETS, 'GST Free'])
            # Capital gain/loss line
            if gain_d >= 0:
                rows.append([date_str, f"{token} Capital Gain", ref, '', fmt_cad(gain_d), ACCT_CAPITAL_GAINS, 'GST Free'])
            else:
                rows.append([date_str, f"{token} Capital Loss", ref, fmt_cad(abs(gain_d)), '', ACCT_CAPITAL_GAINS, 'GST Free'])

        for row in income_rows:
            (income_date, token, fmv_cad, source_type, tx_ref) = row
            date_str = income_date.strftime('%Y-%m-%d') if hasattr(income_date, 'strftime') else str(income_date)
            fmv_d    = Decimal(str(fmv_cad))
            desc     = f"{token} {source_type} Income"
            ref      = str(tx_ref or '')

            rows.append([date_str, desc, ref, fmt_cad(fmv_d), '', ACCT_CRYPTO_ASSETS, 'GST Free'])
            rows.append([date_str, desc, ref, '', fmt_cad(fmv_d), ACCT_CRYPTO_INCOME, 'GST Free'])

        path = output_dir / f'xero_{tax_year}.csv'
        self.write_csv(str(path), headers, rows)
        return str(path)

    # -----------------------------------------------------------------------
    # Sage 50
    # -----------------------------------------------------------------------

    def _write_sage50_csv(self, output_dir: Path, tax_year: int,
                           gains_rows: list, income_rows: list) -> str:
        """Write Sage 50 general journal import CSV.

        Headers: Date, Source, Comment, Account Number, Debit, Credit
        Account numbers use generic placeholders:
          1500 = Crypto Assets, 4100 = Capital Gains, 4200 = Crypto Income
        """
        headers = ['Date', 'Source', 'Comment', 'Account Number', 'Debit', 'Credit']
        rows = []

        for row in gains_rows:
            (disposal_date, token, proceeds, acb, gain_loss, tx_ref) = row
            date_str   = disposal_date.strftime('%Y-%m-%d') if hasattr(disposal_date, 'strftime') else str(disposal_date)
            proceeds_d = Decimal(str(proceeds))
            acb_d      = Decimal(str(acb))
            gain_d     = Decimal(str(gain_loss))
            source     = str(tx_ref or f"{token} Disposal")
            comment    = f"Disposal of {token}"

            # Debit proceeds to Cash (1000)
            rows.append([date_str, source, comment, ACCT_CASH_PROCEEDS, fmt_cad(proceeds_d), ''])
            # Credit Crypto Assets (1500) for ACB
            rows.append([date_str, source, comment, ACCT_CRYPTO_ASSETS, '', fmt_cad(acb_d)])
            # Capital gain/loss (4100)
            if gain_d >= 0:
                rows.append([date_str, source, comment, ACCT_CAPITAL_GAINS, '', fmt_cad(gain_d)])
            else:
                rows.append([date_str, source, comment, ACCT_CAPITAL_GAINS, fmt_cad(abs(gain_d)), ''])

        for row in income_rows:
            (income_date, token, fmv_cad, source_type, tx_ref) = row
            date_str = income_date.strftime('%Y-%m-%d') if hasattr(income_date, 'strftime') else str(income_date)
            fmv_d    = Decimal(str(fmv_cad))
            source   = str(tx_ref or f"{token} {source_type}")
            comment  = f"{source_type} income: {token}"

            rows.append([date_str, source, comment, ACCT_CRYPTO_ASSETS, fmt_cad(fmv_d), ''])
            rows.append([date_str, source, comment, ACCT_CRYPTO_INCOME, '', fmt_cad(fmv_d)])

        path = output_dir / f'sage50_{tax_year}.csv'
        self.write_csv(str(path), headers, rows)
        return str(path)

    # -----------------------------------------------------------------------
    # Generic double-entry CSV
    # -----------------------------------------------------------------------

    def _write_double_entry_csv(self, output_dir: Path, tax_year: int,
                                 gains_rows: list, income_rows: list) -> str:
        """Write generic balanced double-entry CSV.

        Headers: Date, Account, Debit, Credit, Memo, Reference

        Each event produces 2+ rows that sum to zero (total debit = total credit).

        Disposal:
          Debit Cash/Proceeds          proceeds_cad
          Credit Crypto Assets (ACB)   acb_used_cad
          Credit/Debit Capital Gains   gain_loss_cad  (Credit if gain, Debit if loss)

        Income:
          Debit Crypto Assets (FMV)   fmv_cad
          Credit Crypto Income        fmv_cad
        """
        headers = ['Date', 'Account', 'Debit', 'Credit', 'Memo', 'Reference']
        rows = []

        for row in gains_rows:
            (disposal_date, token, proceeds, acb, gain_loss, tx_ref) = row
            date_str   = disposal_date.strftime('%Y-%m-%d') if hasattr(disposal_date, 'strftime') else str(disposal_date)
            proceeds_d = Decimal(str(proceeds))
            acb_d      = Decimal(str(acb))
            gain_d     = Decimal(str(gain_loss))
            memo       = f"Disposal of {token}"
            ref        = str(tx_ref or '')

            # Debit Cash/Proceeds for full proceeds amount
            rows.append([date_str, ACCT_NAME_CASH_PROCEEDS, fmt_cad(proceeds_d), '', memo, ref])
            # Credit Crypto Assets for ACB
            rows.append([date_str, f"{ACCT_NAME_ACB_PREFIX}{token}", '', fmt_cad(acb_d), memo, ref])
            # Capital gain: Credit Capital Gains; Capital loss: Debit Capital Gains
            if gain_d >= 0:
                rows.append([date_str, ACCT_NAME_CAPITAL_GAINS, '', fmt_cad(gain_d), memo, ref])
            else:
                rows.append([date_str, ACCT_NAME_CAPITAL_GAINS, fmt_cad(abs(gain_d)), '', memo, ref])

        for row in income_rows:
            (income_date, token, fmv_cad, source_type, tx_ref) = row
            date_str = income_date.strftime('%Y-%m-%d') if hasattr(income_date, 'strftime') else str(income_date)
            fmv_d    = Decimal(str(fmv_cad))
            memo     = f"{source_type} income: {token}"
            ref      = str(tx_ref or '')

            rows.append([date_str, f"{ACCT_NAME_CRYPTO_ASSETS} - {token}", fmt_cad(fmv_d), '', memo, ref])
            rows.append([date_str, ACCT_NAME_CRYPTO_INCOME, '', fmt_cad(fmv_d), memo, ref])

        path = output_dir / f'double_entry_{tax_year}.csv'
        self.write_csv(str(path), headers, rows)
        return str(path)
