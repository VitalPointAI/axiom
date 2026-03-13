"""
FIFOTracker — lot-level FIFO inventory valuation for business tax treatment.

Used when tax_treatment='business_inventory' to track individual acquisition lots
and apply First-In, First-Out disposal ordering.

Key differences from ACB average cost:
  - Each acquisition creates a separate lot (not pooled average)
  - Disposals consume the oldest lots first (FIFO order)
  - Produces different gain/loss results than ACB when lots have different costs

Canada CRA supports FIFO for business inventory per ITA s.10.
"""

from collections import defaultdict, deque
from decimal import Decimal
from typing import Optional
import datetime
import logging

logger = logging.getLogger(__name__)


def _to_decimal(value) -> Decimal:
    """Convert any value to Decimal safely. Uses str() conversion to avoid float errors."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


class FIFOTracker:
    """Lot-level FIFO inventory tracker for business tax treatment.

    Maintains per-token queues of acquisition lots. Disposals consume lots
    in FIFO order (oldest first). All arithmetic uses Decimal.

    Usage:
        tracker = FIFOTracker()
        tracker.acquire('NEAR', Decimal('10'), Decimal('5.00'), timestamp=1000)
        tracker.acquire('NEAR', Decimal('5'), Decimal('10.00'), timestamp=2000)
        disposals = tracker.dispose('NEAR', Decimal('8'), Decimal('12.00'), timestamp=3000)

    The result is a list of LotDisposal dicts, one per lot consumed.
    """

    def __init__(self):
        # Per-token deque of lot dicts. Each lot:
        #   {'timestamp': int, 'units': Decimal, 'cost_per_unit_cad': Decimal, 'total_cost_cad': Decimal}
        self._lots: dict[str, deque] = defaultdict(deque)
        # Disposal history for COGS calculation: list of {'timestamp', 'token_symbol', 'cost_cad'}
        self._disposals: list[dict] = []

    # -------------------------------------------------------------------------
    # Core operations
    # -------------------------------------------------------------------------

    def acquire(
        self,
        token_symbol: str,
        units,
        cost_per_unit_cad,
        timestamp: int,
    ) -> None:
        """Append a new lot to the token's queue.

        Args:
            token_symbol: Token identifier (e.g. 'NEAR', 'ETH').
            units: Number of units acquired.
            cost_per_unit_cad: Cost per unit in CAD.
            timestamp: Unix timestamp of acquisition.
        """
        units = _to_decimal(units)
        cost_per_unit_cad = _to_decimal(cost_per_unit_cad)
        total_cost_cad = units * cost_per_unit_cad

        lot = {
            'timestamp': timestamp,
            'units': units,
            'cost_per_unit_cad': cost_per_unit_cad,
            'total_cost_cad': total_cost_cad,
        }
        self._lots[token_symbol].append(lot)

    def dispose(
        self,
        token_symbol: str,
        units,
        proceeds_per_unit_cad,
        timestamp: int,
    ) -> list[dict]:
        """Pop lots from the front of the queue (FIFO) until units are consumed.

        Args:
            token_symbol: Token identifier.
            units: Number of units to dispose.
            proceeds_per_unit_cad: Proceeds per unit in CAD.
            timestamp: Unix timestamp of disposal.

        Returns:
            List of LotDisposal dicts. Each dict contains:
                - lot: the original lot dict
                - units_from_lot: units consumed from this lot
                - cost_cad: cost basis consumed from this lot
                - proceeds_cad: proceeds for units from this lot
                - gain_loss_cad: gain or loss for this portion
                - timestamp: disposal timestamp
                - needs_review: True if queue was exhausted before all units consumed
        """
        units = _to_decimal(units)
        proceeds_per_unit_cad = _to_decimal(proceeds_per_unit_cad)
        remaining = units
        disposals = []
        queue = self._lots[token_symbol]
        needs_review = False

        while remaining > Decimal('0') and queue:
            lot = queue[0]
            take = min(remaining, lot['units'])
            cost_cad = take * lot['cost_per_unit_cad']
            proceeds_cad = take * proceeds_per_unit_cad
            gain_loss_cad = proceeds_cad - cost_cad

            disposal = {
                'lot': lot,
                'units_from_lot': take,
                'cost_cad': cost_cad,
                'proceeds_cad': proceeds_cad,
                'gain_loss_cad': gain_loss_cad,
                'timestamp': timestamp,
                'token_symbol': token_symbol,
                'needs_review': False,
            }
            disposals.append(disposal)
            self._disposals.append({
                'timestamp': timestamp,
                'token_symbol': token_symbol,
                'cost_cad': cost_cad,
                'units': take,
            })

            # Update lot quantity
            lot['units'] -= take
            lot['total_cost_cad'] = lot['units'] * lot['cost_per_unit_cad']

            # Remove fully consumed lot
            if lot['units'] <= Decimal('0'):
                queue.popleft()

            remaining -= take

        # If queue exhausted but units remain: partial disposal, flag for review
        if remaining > Decimal('0'):
            needs_review = True
            logger.warning(
                "FIFOTracker oversell: %s wants to dispose %s more units than held for %s",
                token_symbol, remaining, token_symbol,
            )
            # Add a partial disposal record for the residual
            disposal = {
                'lot': None,
                'units_from_lot': Decimal('0'),
                'cost_cad': Decimal('0'),
                'proceeds_cad': Decimal('0'),
                'gain_loss_cad': Decimal('0'),
                'timestamp': timestamp,
                'token_symbol': token_symbol,
                'needs_review': True,
            }
            disposals.append(disposal)

        # Mark all disposals with needs_review if oversell occurred
        if needs_review:
            for d in disposals:
                d['needs_review'] = True

        return disposals

    # -------------------------------------------------------------------------
    # Holdings / COGS queries
    # -------------------------------------------------------------------------

    def get_holdings(self, token_symbol: Optional[str] = None) -> list[dict]:
        """Return remaining lots for a token or all tokens.

        Args:
            token_symbol: If provided, returns lots for that token only.
                         If None, returns lots for all tokens.

        Returns:
            List of lot dicts with keys:
                token_symbol, units, cost_per_unit_cad, total_cost_cad, acquisition_timestamp
        """
        result = []
        if token_symbol is not None:
            tokens = [token_symbol]
        else:
            tokens = list(self._lots.keys())

        for sym in tokens:
            for lot in self._lots[sym]:
                if lot['units'] > Decimal('0'):
                    result.append({
                        'token_symbol': sym,
                        'units': lot['units'],
                        'cost_per_unit_cad': lot['cost_per_unit_cad'],
                        'total_cost_cad': lot['total_cost_cad'],
                        'acquisition_timestamp': lot['timestamp'],
                    })
        return result

    def get_total_cost(self, token_symbol: Optional[str] = None) -> Decimal:
        """Sum of total_cost_cad across all remaining lots.

        Args:
            token_symbol: If provided, sums only for that token.
                         If None, sums across all tokens.

        Returns:
            Total cost in CAD as Decimal.
        """
        total = Decimal('0')
        if token_symbol is not None:
            for lot in self._lots[token_symbol]:
                total += lot['total_cost_cad']
        else:
            for sym in self._lots:
                for lot in self._lots[sym]:
                    total += lot['total_cost_cad']
        return total

    def get_cogs(self, year: int) -> Decimal:
        """Return total cost of lots disposed during the given calendar year.

        Args:
            year: Calendar year (e.g. 2024).

        Returns:
            Total COGS in CAD as Decimal.
        """
        total = Decimal('0')
        year_start = int(datetime.datetime(year, 1, 1, tzinfo=datetime.timezone.utc).timestamp())
        year_end = int(datetime.datetime(year, 12, 31, 23, 59, 59, tzinfo=datetime.timezone.utc).timestamp())
        for d in self._disposals:
            if year_start <= d['timestamp'] <= year_end:
                total += d['cost_cad']
        return total

    # -------------------------------------------------------------------------
    # Replay from acb_snapshots rows
    # -------------------------------------------------------------------------

    def replay_from_snapshots(self, rows) -> None:
        """Replay a sequence of acb_snapshot-like rows through acquire/dispose.

        Each row must have:
            token_symbol: str
            event_type: 'acquire' or 'dispose'
            units_delta: Decimal (positive units)
            cost_cad_delta: Decimal (total cost for acquire; proceeds for dispose)
            block_timestamp: int (Unix seconds)

        This is how the report module feeds data to FIFOTracker.

        Args:
            rows: Iterable of dicts or dict-like objects with the above keys.
        """
        for row in rows:
            # Support both dict and object with attribute access
            if isinstance(row, dict):
                token_symbol = row['token_symbol']
                event_type = row['event_type']
                units_delta = _to_decimal(row['units_delta'])
                cost_cad_delta = _to_decimal(row['cost_cad_delta'])
                block_timestamp = row['block_timestamp']
            else:
                token_symbol = row.token_symbol
                event_type = row.event_type
                units_delta = _to_decimal(row.units_delta)
                cost_cad_delta = _to_decimal(row.cost_cad_delta)
                block_timestamp = row.block_timestamp

            if units_delta <= Decimal('0'):
                continue

            if event_type == 'acquire':
                # Derive cost_per_unit from total cost / units
                cost_per_unit = cost_cad_delta / units_delta if units_delta > 0 else Decimal('0')
                self.acquire(
                    token_symbol,
                    units_delta,
                    cost_per_unit,
                    timestamp=block_timestamp,
                )
            elif event_type == 'dispose':
                # For dispose, cost_cad_delta is proceeds; use $0 proceeds_per_unit
                # since we only care about FIFO cost basis from the lots
                proceeds_per_unit = cost_cad_delta / units_delta if units_delta > 0 else Decimal('0')
                self.dispose(
                    token_symbol,
                    units_delta,
                    proceeds_per_unit,
                    timestamp=block_timestamp,
                )
            else:
                logger.debug("FIFOTracker.replay: unknown event_type=%s, skipping", event_type)
