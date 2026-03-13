"""Discrepancy report generator for Axiom verification pipeline.

Queries verification_results with status='open' and generates a formatted
DISCREPANCIES.md report for specialist review.
"""
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class DiscrepancyReporter:
    """Generates DISCREPANCIES.md reports from verification_results.

    Queries all open/flagged verification results for a user and formats
    them into a structured markdown report grouped by category.

    Args:
        pool: psycopg2 connection pool
    """

    def __init__(self, pool):
        self.pool = pool

    def generate_report(
        self, user_id: int, output_path: str = "DISCREPANCIES.md",
    ) -> str:
        """Generate a discrepancy report for a user.

        Queries verification_results and account_verification_status,
        then writes a formatted markdown report.

        Args:
            user_id: User to report on
            output_path: File path to write report (default: DISCREPANCIES.md)

        Returns:
            The path written
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # Query all open/flagged verification results
            cur.execute(
                """
                SELECT vr.id, vr.user_id, vr.wallet_id, vr.chain,
                       vr.token_symbol, vr.expected_balance_acb,
                       vr.expected_balance_replay, vr.actual_balance,
                       vr.manual_balance, vr.manual_balance_date,
                       vr.difference, vr.tolerance,
                       vr.onchain_liquid, vr.onchain_locked, vr.onchain_staked,
                       vr.status, vr.diagnosis_category, vr.diagnosis_detail,
                       vr.diagnosis_confidence, vr.rpc_error, vr.notes,
                       vr.verified_at,
                       w.account_id, w.chain
                FROM verification_results vr
                JOIN wallets w ON vr.wallet_id = w.id
                WHERE vr.user_id = %s AND vr.status IN ('open', 'flagged')
                ORDER BY vr.chain, w.account_id, vr.token_symbol
                """,
                (user_id,),
            )
            columns = [desc[0] for desc in cur.description]
            results = [dict(zip(columns, row)) for row in cur.fetchall()]

            # Query account verification status summary
            cur.execute(
                """
                SELECT avs.status, COUNT(*) as cnt
                FROM account_verification_status avs
                WHERE avs.user_id = %s
                GROUP BY avs.status
                """,
                (user_id,),
            )
            status_counts = dict(cur.fetchall())

            # Query detailed account status
            cur.execute(
                """
                SELECT avs.wallet_id, avs.status, avs.last_checked_at,
                       avs.open_issues, avs.notes,
                       w.account_id, w.chain
                FROM account_verification_status avs
                JOIN wallets w ON avs.wallet_id = w.id
                WHERE avs.user_id = %s
                ORDER BY avs.status DESC, w.chain, w.account_id
                """,
                (user_id,),
            )
            acct_columns = [desc[0] for desc in cur.description]
            account_statuses = [dict(zip(acct_columns, row)) for row in cur.fetchall()]

            cur.close()
        finally:
            self.pool.putconn(conn)

        # Generate the report
        report = self._format_report(
            user_id, results, status_counts, account_statuses,
        )

        # Write to file
        with open(output_path, "w") as f:
            f.write(report)

        logger.info(
            "Discrepancy report written to %s (%d open issues for user_id=%s)",
            output_path, len(results), user_id,
        )
        return output_path

    def _format_report(
        self,
        user_id: int,
        results: list,
        status_counts: dict,
        account_statuses: list,
    ) -> str:
        """Format the discrepancy report as markdown.

        Args:
            user_id: User ID
            results: List of verification_results dicts
            status_counts: Dict of status -> count
            account_statuses: List of account_verification_status dicts

        Returns:
            Formatted markdown string
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        lines = []
        lines.append("# Discrepancy Report")
        lines.append(f"Generated: {now}")
        lines.append(f"User ID: {user_id}")
        lines.append("")

        # Summary table
        lines.append("## Summary")
        lines.append("")
        lines.append("| Status | Count |")
        lines.append("|--------|-------|")
        lines.append(f"| Verified | {status_counts.get('verified', 0)} |")
        lines.append(f"| Flagged | {status_counts.get('flagged', 0)} |")
        lines.append(f"| Unverified | {status_counts.get('unverified', 0)} |")
        lines.append("")

        # Account status detail
        if account_statuses:
            lines.append("### Account Status Detail")
            lines.append("")
            lines.append("| Chain | Account | Status | Open Issues | Last Checked |")
            lines.append("|-------|---------|--------|-------------|--------------|")
            for acct in account_statuses:
                last_checked = (
                    acct["last_checked_at"].strftime("%Y-%m-%d %H:%M")
                    if acct.get("last_checked_at")
                    else "Never"
                )
                lines.append(
                    f"| {acct['chain']} | {acct['account_id']} | "
                    f"{acct['status']} | {acct['open_issues']} | {last_checked} |"
                )
            lines.append("")

        # Separate results by category
        reconciliation = [
            r for r in results
            if r.get("diagnosis_category") not in (
                "duplicate_merged", "unindexed_period",
            )
        ]
        duplicates = [
            r for r in results
            if r.get("diagnosis_category") == "duplicate_merged"
        ]
        gaps = [
            r for r in results
            if r.get("diagnosis_category") == "unindexed_period"
        ]

        # Open Discrepancies (reconciliation issues)
        if reconciliation:
            lines.append("## Open Discrepancies")
            lines.append("")
            for r in reconciliation:
                lines.extend(self._format_result(r))
                lines.append("")

        # Duplicate Merge Log
        lines.append("## Duplicate Merge Log")
        lines.append("")
        if duplicates:
            for r in duplicates:
                lines.extend(self._format_duplicate(r))
                lines.append("")
        else:
            lines.append("_No duplicate merges recorded._")
            lines.append("")

        # Gap Detection Results
        lines.append("## Gap Detection Results")
        lines.append("")
        if gaps:
            for r in gaps:
                lines.extend(self._format_gap(r))
                lines.append("")
        else:
            lines.append("_No gaps detected._")
            lines.append("")

        # Investigation Notes section
        lines.append("## Investigation Notes")
        lines.append("")
        lines.append("_Add manual investigation notes below:_")
        lines.append("")

        return "\n".join(lines)

    def _format_result(self, r: dict) -> list:
        """Format a single reconciliation discrepancy."""
        lines = []
        chain = r.get("chain", "unknown")
        account_id = r.get("account_id", "unknown")

        lines.append(f"### {chain} - {account_id}")
        lines.append(f"**Token:** {r.get('token_symbol', 'N/A')}")

        if r.get("expected_balance_acb") is not None:
            lines.append(f"**Expected (ACB):** {r['expected_balance_acb']}")
        if r.get("expected_balance_replay") is not None:
            lines.append(f"**Expected (Replay):** {r['expected_balance_replay']}")
        if r.get("actual_balance") is not None:
            lines.append(f"**Actual (On-chain):** {r['actual_balance']}")
        if r.get("manual_balance") is not None:
            lines.append(f"**Manual Balance:** {r['manual_balance']}")
        if r.get("difference") is not None:
            lines.append(f"**Difference:** {r['difference']}")
        if r.get("tolerance") is not None:
            lines.append(f"**Tolerance:** {r['tolerance']}")

        lines.append(f"**Status:** {r.get('status', 'open')}")
        lines.append("")

        if r.get("diagnosis_category"):
            lines.append(f"**Diagnosis:** {r['diagnosis_category']}")
        if r.get("diagnosis_confidence") is not None:
            lines.append(f"**Confidence:** {r['diagnosis_confidence']}")
        if r.get("diagnosis_detail"):
            detail = r["diagnosis_detail"]
            if isinstance(detail, str):
                try:
                    detail = json.loads(detail)
                except (json.JSONDecodeError, TypeError):
                    pass
            if isinstance(detail, dict):
                lines.append("**Detail:**")
                for k, v in detail.items():
                    lines.append(f"  - {k}: {v}")
            else:
                lines.append(f"**Detail:** {detail}")

        # NEAR decomposed components
        if r.get("onchain_liquid") is not None or r.get("onchain_locked") is not None:
            lines.append("")
            lines.append("**NEAR Components:**")
            if r.get("onchain_liquid") is not None:
                lines.append(f"- Liquid: {r['onchain_liquid']}")
            if r.get("onchain_locked") is not None:
                lines.append(f"- Locked: {r['onchain_locked']}")
            if r.get("onchain_staked") is not None:
                lines.append(f"- Staked: {r['onchain_staked']}")

        if r.get("rpc_error"):
            lines.append(f"**RPC Error:** {r['rpc_error']}")
        if r.get("notes"):
            lines.append(f"**Notes:** {r['notes']}")

        lines.append("")
        lines.append("---")
        return lines

    def _format_duplicate(self, r: dict) -> list:
        """Format a duplicate detection entry."""
        lines = []
        account_id = r.get("account_id", "unknown")
        chain = r.get("chain", "unknown")

        lines.append(f"### {chain} - {account_id}")
        lines.append(f"**Token:** {r.get('token_symbol', 'N/A')}")
        lines.append(f"**Status:** {r.get('status', 'open')}")

        if r.get("diagnosis_confidence") is not None:
            lines.append(f"**Confidence:** {r['diagnosis_confidence']}")

        if r.get("diagnosis_detail"):
            detail = r["diagnosis_detail"]
            if isinstance(detail, str):
                try:
                    detail = json.loads(detail)
                except (json.JSONDecodeError, TypeError):
                    pass
            if isinstance(detail, dict):
                lines.append("**Detail:**")
                for k, v in detail.items():
                    lines.append(f"  - {k}: {v}")

        if r.get("notes"):
            lines.append(f"**Notes:** {r['notes']}")

        lines.append("---")
        return lines

    def _format_gap(self, r: dict) -> list:
        """Format a gap detection entry."""
        lines = []
        account_id = r.get("account_id", "unknown")
        chain = r.get("chain", "unknown")

        lines.append(f"### {chain} - {account_id}")
        lines.append(f"**Token:** {r.get('token_symbol', 'N/A')}")
        lines.append(f"**Status:** {r.get('status', 'open')}")

        if r.get("diagnosis_confidence") is not None:
            lines.append(f"**Confidence:** {r['diagnosis_confidence']}")

        if r.get("diagnosis_detail"):
            detail = r["diagnosis_detail"]
            if isinstance(detail, str):
                try:
                    detail = json.loads(detail)
                except (json.JSONDecodeError, TypeError):
                    pass
            if isinstance(detail, dict):
                gap_month = detail.get("gap_month", "N/A")
                gap_amount = detail.get("gap_amount", "N/A")
                lines.append(f"**Gap Month:** {gap_month}")
                lines.append(f"**Gap Amount:** {gap_amount} NEAR")
                lines.append("**Detail:**")
                for k, v in detail.items():
                    lines.append(f"  - {k}: {v}")

        if r.get("notes"):
            lines.append(f"**Notes:** {r['notes']}")

        lines.append("---")
        return lines
