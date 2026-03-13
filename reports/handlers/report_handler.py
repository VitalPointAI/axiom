"""
ReportHandler — IndexerService job type for async report generation.

Job type: ``generate_reports``

Registered in IndexerService with priority=3 (lower than verify_balances=4,
higher than standard indexing jobs).

The cursor field on the job row is a JSON string containing:
  - tax_year: int
  - tax_treatment: str ('capital' | 'business_inventory' | 'hybrid')
  - year_end_month: int (default 12)
  - specialist_override: bool (default False)
  - excluded_wallet_ids: list[int] (default [])

On ReportBlockedError: returns {error: str, blocked: True} — does NOT raise.
Job is marked failed by IndexerService with the error message.
"""

import json
import logging
from typing import Optional

from reports.generate import PackageBuilder
from reports.engine import ReportBlockedError

logger = logging.getLogger(__name__)


class ReportHandler:
    """Handles generate_reports job type for IndexerService.

    Instantiates PackageBuilder and calls build() with parameters extracted
    from the job cursor JSON. Handles ReportBlockedError gracefully.

    Args:
        pool: psycopg2 connection pool (stored for PackageBuilder instantiation).
    """

    def __init__(self, pool):
        self.pool = pool

    def run(self, job_row: dict, conn) -> dict:
        """Execute a generate_reports job.

        Args:
            job_row: Dict with at least: user_id, cursor (JSON string).
            conn: Database connection (unused; PackageBuilder manages its own pool).

        Returns:
            On success: dict with keys files_generated (int) and output_dir (str).
            On ReportBlockedError: dict with keys error (str) and blocked (True).
        """
        user_id = job_row['user_id']

        # Parse cursor JSON for parameters
        cursor_raw = job_row.get('cursor') or '{}'
        try:
            params = json.loads(cursor_raw)
        except (json.JSONDecodeError, TypeError):
            params = {}

        tax_year = params.get('tax_year')
        if tax_year is None:
            from datetime import datetime
            tax_year = datetime.now().year - 1
        tax_year = int(tax_year)

        tax_treatment = params.get('tax_treatment', 'capital')
        year_end_month = int(params.get('year_end_month', 12))
        specialist_override = bool(params.get('specialist_override', False))
        excluded_wallet_ids = params.get('excluded_wallet_ids') or []

        logger.info(
            "ReportHandler.run: user_id=%s tax_year=%s tax_treatment=%s "
            "specialist_override=%s",
            user_id, tax_year, tax_treatment, specialist_override,
        )

        try:
            builder = PackageBuilder(self.pool, specialist_override=specialist_override)
            manifest = builder.build(
                user_id=user_id,
                tax_year=tax_year,
                year_end_month=year_end_month,
                tax_treatment=tax_treatment,
                excluded_wallet_ids=excluded_wallet_ids or None,
            )
            files_generated = len(manifest.get('files', []))
            output_dir = manifest.get('output_dir', '')
            logger.info(
                "ReportHandler complete: user_id=%s tax_year=%s files=%d output=%s",
                user_id, tax_year, files_generated, output_dir,
            )
            return {
                'files_generated': files_generated,
                'output_dir': output_dir,
            }

        except ReportBlockedError as e:
            logger.warning(
                "ReportHandler blocked: user_id=%s tax_year=%s error=%s",
                user_id, tax_year, str(e),
            )
            return {
                'error': str(e),
                'blocked': True,
            }
