"""
Historical Data

Data structures for backtesting historical order book data.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Iterator


@dataclass
class OrderBookSnapshot:
    """A single order book snapshot."""
    timestamp: int
    token_id: str
    best_bid: Decimal
    best_ask: Decimal
    bid_depth: Decimal
    ask_depth: Decimal


class HistoricalData:
    """
    Container for historical order book data.

    Usage:
        data = HistoricalData()

        # Add snapshots
        data.add_snapshot(OrderBookSnapshot(...))

        # Iterate in chronological order
        for snapshot in data.iterate():
            process(snapshot)
    """

    def __init__(self):
        self._snapshots: List[OrderBookSnapshot] = []
        self._sorted = False

    @property
    def snapshots(self) -> List[OrderBookSnapshot]:
        """Get all snapshots."""
        return self._snapshots

    def add_snapshot(self, snapshot: OrderBookSnapshot):
        """Add a snapshot to the data."""
        self._snapshots.append(snapshot)
        self._sorted = False

    def iterate(self) -> Iterator[OrderBookSnapshot]:
        """Iterate snapshots in chronological order."""
        if not self._sorted:
            self._snapshots.sort(key=lambda s: s.timestamp)
            self._sorted = True

        return iter(self._snapshots)

    def __len__(self) -> int:
        return len(self._snapshots)
