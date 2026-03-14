"""
ACBPool — per-token in-memory pool using Canadian average cost method.

Thread-safe only if used from a single thread; no locking implemented.
All monetary values are Decimal; no float arithmetic permitted.
"""

import logging
from decimal import Decimal, ROUND_HALF_UP

_EIGHT_PLACES = Decimal("0.00000001")

logger = logging.getLogger(__name__)


class ACBPool:
    """Per-token ACB pool using Decimal arithmetic (Canadian average cost method)."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.total_units: Decimal = Decimal("0")
        self.total_cost_cad: Decimal = Decimal("0")

    @property
    def acb_per_unit(self) -> Decimal:
        """Current ACB per unit, quantized to 8 decimal places."""
        if self.total_units <= Decimal("0"):
            return Decimal("0")
        return (self.total_cost_cad / self.total_units).quantize(
            _EIGHT_PLACES, rounding=ROUND_HALF_UP
        )

    def acquire(
        self,
        units: Decimal,
        cost_cad: Decimal,
        fee_cad: Decimal = Decimal("0"),
    ) -> dict:
        """Record an acquisition.

        Fees increase the total cost (per CRA: acquisition cost includes fees).

        Returns snapshot dict with post-acquire pool state.
        """
        total_cost = cost_cad + fee_cad
        self.total_units += units
        self.total_cost_cad += total_cost

        return {
            "event_type": "acquire",
            "units_delta": units,
            "cost_cad_delta": total_cost,
            "total_units": self.total_units,
            "total_cost_cad": self.total_cost_cad,
            "acb_per_unit": self.acb_per_unit,
        }

    def dispose(
        self,
        units: Decimal,
        proceeds_cad: Decimal,
        fee_cad: Decimal = Decimal("0"),
    ) -> dict:
        """Record a disposal.

        Fees reduce proceeds (per CRA: fees on disposals reduce proceeds).
        If units > total_units (oversell), clamp to total_units and set needs_review=True.

        Returns snapshot dict with gain/loss calculation.
        """
        needs_review = False
        if units > self.total_units:
            needs_review = True
            units = self.total_units

        acb_per_unit_at_disposal = self.acb_per_unit
        acb_used_cad = (units * acb_per_unit_at_disposal).quantize(
            _EIGHT_PLACES, rounding=ROUND_HALF_UP
        )
        net_proceeds_cad = proceeds_cad - fee_cad
        gain_loss_cad = (net_proceeds_cad - acb_used_cad).quantize(
            _EIGHT_PLACES, rounding=ROUND_HALF_UP
        )

        # Update pool
        self.total_units -= units
        self.total_cost_cad -= acb_used_cad

        # Guard against floating-point residuals that could make total_cost negative
        if self.total_units <= Decimal("0"):
            self.total_units = Decimal("0")
            self.total_cost_cad = Decimal("0")

        return {
            "event_type": "dispose",
            "units_delta": units,
            "acb_used_cad": acb_used_cad,
            "net_proceeds_cad": net_proceeds_cad,
            "gain_loss_cad": gain_loss_cad,
            "acb_per_unit": acb_per_unit_at_disposal,
            "total_units": self.total_units,
            "total_cost_cad": self.total_cost_cad,
            "needs_review": needs_review,
        }


def check_acb_pool_invariants(pool, conn=None, user_id=None, context=""):
    """Check ACB pool consistency invariants.

    Returns True if no violations, False if violations found.
    Violations are logged and written to audit_log but never raise.
    """
    violations = []

    if pool.total_cost_cad < Decimal("0"):
        violations.append(f"negative total_cost_cad={pool.total_cost_cad}")

    if pool.total_units < Decimal("0"):
        violations.append(f"negative total_units={pool.total_units}")

    if pool.total_units > Decimal("0") and pool.total_cost_cad < Decimal("0"):
        violations.append(
            f"units={pool.total_units} but cost={pool.total_cost_cad} (inconsistent)"
        )

    if violations:
        logger.warning(
            "ACB pool invariant violation for %s: %s (context: %s)",
            pool.symbol, violations, context,
        )
        if conn is not None:
            try:
                from db.audit import write_audit

                write_audit(
                    conn,
                    user_id=user_id,
                    entity_type="acb_pool",
                    action="invariant_violation",
                    new_value={
                        "symbol": pool.symbol,
                        "violations": violations,
                        "context": context,
                    },
                    actor_type="system",
                )
            except Exception:
                logger.warning("Failed to write ACB invariant audit", exc_info=True)
        return False

    return True
