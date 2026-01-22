"""
Partial Fill Handler

Detects and responds to partial fills to manage inventory risk.

Strategies:
- Tighten opposite quote after partial fill (encourage hedge)
- Track partial fill rates for strategy tuning
- Cancel and replace remainders when appropriate
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Optional, List


@dataclass
class TrackedOrder:
    """An order being tracked for fills."""
    order_id: str
    side: str
    original_size: Decimal
    price: Decimal
    filled_size: Decimal = Decimal("0")


@dataclass
class FillEvent:
    """A fill event notification."""
    order_id: str
    side: str
    price: Decimal
    filled_size: Decimal
    total_filled: Decimal
    remaining_size: Decimal
    is_partial: bool


@dataclass
class FillResponse:
    """Recommended response to a fill."""
    tighten_opposite_spread: bool
    spread_adjustment: Decimal
    hedge_urgency: float  # 0.0 to 1.0
    cancel_remainder: bool
    reason: str


@dataclass
class FillStatistics:
    """Statistics about fill behavior."""
    total_orders: int
    full_fills: int
    partial_fills: int
    partial_fill_rate: float
    avg_fill_percentage: float


class PartialFillHandler:
    """
    Handles partial fill detection and response.

    Usage:
        handler = PartialFillHandler()

        # Track orders as placed
        handler.track_order("order-1", "BUY", Decimal("100"), Decimal("0.50"))

        # Record fills as they happen
        event = handler.record_fill("order-1", Decimal("30"))

        if event.is_partial:
            response = handler.get_response(event)
            # Apply recommended adjustments
    """

    # Thresholds
    SMALL_FILL_THRESHOLD = 0.1  # <10% = small partial
    LARGE_FILL_THRESHOLD = 0.5  # >50% = significant partial

    def __init__(self):
        self._orders: Dict[str, TrackedOrder] = {}
        self._fill_history: List[FillEvent] = []

    def track_order(
        self,
        order_id: str,
        side: str,
        size: Decimal,
        price: Decimal,
    ):
        """Start tracking an order for fills."""
        self._orders[order_id] = TrackedOrder(
            order_id=order_id,
            side=side,
            original_size=size,
            price=price,
        )

    def record_fill(
        self,
        order_id: str,
        filled_size: Decimal,
    ) -> Optional[FillEvent]:
        """Record a fill and return fill event."""
        order = self._orders.get(order_id)
        if not order:
            return None

        order.filled_size += filled_size
        remaining = order.original_size - order.filled_size

        event = FillEvent(
            order_id=order_id,
            side=order.side,
            price=order.price,
            filled_size=filled_size,
            total_filled=order.filled_size,
            remaining_size=max(Decimal("0"), remaining),
            is_partial=remaining > Decimal("0"),
        )

        self._fill_history.append(event)

        # Clean up fully filled orders
        if remaining <= 0:
            del self._orders[order_id]

        return event

    def get_response(self, event: FillEvent) -> FillResponse:
        """Get recommended response to a fill."""
        fill_pct = float(event.total_filled / (event.total_filled + event.remaining_size))

        # Small partial - low urgency
        if fill_pct < self.SMALL_FILL_THRESHOLD:
            return FillResponse(
                tighten_opposite_spread=False,
                spread_adjustment=Decimal("0"),
                hedge_urgency=0.2,
                cancel_remainder=False,
                reason="Small partial fill, continue normally",
            )

        # Large partial - hedge more aggressively
        if fill_pct > self.LARGE_FILL_THRESHOLD:
            return FillResponse(
                tighten_opposite_spread=True,
                spread_adjustment=Decimal("0.005"),  # Tighten by half cent
                hedge_urgency=0.8,
                cancel_remainder=False,
                reason="Large partial fill, tighten opposite to hedge",
            )

        # Medium partial
        return FillResponse(
            tighten_opposite_spread=True,
            spread_adjustment=Decimal("0.002"),
            hedge_urgency=0.5,
            cancel_remainder=False,
            reason="Medium partial fill, moderate hedge urgency",
        )

    def get_statistics(self) -> FillStatistics:
        """Get fill statistics."""
        if not self._fill_history:
            return FillStatistics(
                total_orders=0,
                full_fills=0,
                partial_fills=0,
                partial_fill_rate=0.0,
                avg_fill_percentage=0.0,
            )

        # Group by order
        order_results: Dict[str, bool] = {}  # order_id -> was_partial
        fill_percentages: List[float] = []

        for event in self._fill_history:
            if event.order_id not in order_results:
                order_results[event.order_id] = event.is_partial

            if not event.is_partial:
                order_results[event.order_id] = False

        full = sum(1 for partial in order_results.values() if not partial)
        partial = sum(1 for partial in order_results.values() if partial)

        return FillStatistics(
            total_orders=len(order_results),
            full_fills=full,
            partial_fills=partial,
            partial_fill_rate=partial / max(1, len(order_results)),
            avg_fill_percentage=sum(fill_percentages) / max(1, len(fill_percentages)) if fill_percentages else 0,
        )
