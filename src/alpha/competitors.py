"""
Competitor Detection

Identifies and analyzes other market makers in the order book.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Dict, Optional
from collections import defaultdict


@dataclass
class OrderPattern:
    """A recurring order pattern (likely from a single MM)."""

    size: Decimal
    offset: Decimal  # From mid price
    side: str
    frequency: int
    consistency: float  # How consistent the pattern is


@dataclass
class CompetitorProfile:
    """Profile of a competitor."""

    estimated_capital: Decimal
    aggression: float  # 0-1 (tight spreads = aggressive)
    avg_size: Decimal
    avg_spread: Decimal
    patterns: List[OrderPattern]


@dataclass
class StrategyResponse:
    """Recommended strategy response to competitors."""

    should_compete: bool
    spread_multiplier: float
    size_multiplier: float
    recommended_offset: Decimal
    reason: str


class CompetitorDetector:
    """
    Detects and analyzes competing market makers.

    Usage:
        detector = CompetitorDetector()

        # Record orders as they appear
        detector.record_order(price, size, side, mid_price)

        # Analyze competitors
        patterns = detector.get_patterns()
        response = detector.get_strategy_response()
    """

    # Clustering thresholds
    SIZE_TOLERANCE = Decimal("0.1")  # 10% size variation = same MM
    OFFSET_TOLERANCE = Decimal("0.005")  # 0.5c offset variation

    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self._orders: List[dict] = []
        self._patterns: List[OrderPattern] = []

    def record_order(
        self,
        price: Decimal,
        size: Decimal,
        side: str,
        mid_price: Decimal,
    ):
        """Record an observed order."""
        offset = price - mid_price

        self._orders.append(
            {
                "price": price,
                "size": size,
                "side": side,
                "offset": offset,
                "mid": mid_price,
            }
        )

        # Keep window
        if len(self._orders) > self.window_size:
            self._orders = self._orders[-self.window_size :]

        # Recompute patterns periodically
        if len(self._orders) % 50 == 0:
            self._compute_patterns()

    def get_patterns(self) -> List[OrderPattern]:
        """Get detected order patterns."""
        if not self._patterns:
            self._compute_patterns()
        return self._patterns

    def estimate_competitor_capital(self) -> Decimal:
        """Estimate total competitor capital from order sizes."""
        if not self._orders:
            return Decimal("0")

        # Use max observed size as proxy
        max_size = max(o["size"] for o in self._orders)

        # Assume MM exposes ~10% of capital
        return max_size * 10

    def get_aggression_level(self) -> float:
        """Get competitor aggression level (0-1)."""
        if not self._orders:
            return 0.5

        # Calculate average offset from mid
        buy_offsets = [abs(o["offset"]) for o in self._orders if o["side"] == "BUY"]
        sell_offsets = [abs(o["offset"]) for o in self._orders if o["side"] == "SELL"]

        if not buy_offsets and not sell_offsets:
            return 0.5

        # Use whichever side has data
        offsets = buy_offsets or sell_offsets
        avg_offset = sum(offsets) / len(offsets)

        # Smaller spread = more aggressive
        # 1c spread = very aggressive (1.0)
        # 5c spread = passive (0.0)
        aggression = max(0, 1 - float(avg_offset) / 0.05)
        return min(1.0, aggression)

    def get_strategy_response(self) -> StrategyResponse:
        """Get recommended strategy response."""
        capital = self.estimate_competitor_capital()
        aggression = self.get_aggression_level()

        # Large, aggressive competitor = back off
        if capital > Decimal("5000") and aggression > 0.7:
            return StrategyResponse(
                should_compete=False,
                spread_multiplier=1.5,
                size_multiplier=0.5,
                recommended_offset=Decimal("0.03"),
                reason="Large aggressive competitor - widen spread",
            )

        # Small competitor = compete
        if capital < Decimal("500"):
            return StrategyResponse(
                should_compete=True,
                spread_multiplier=0.9,
                size_multiplier=1.2,
                recommended_offset=Decimal("0.015"),
                reason="Small competitor - tighten spread",
            )

        # Default: normal behavior
        return StrategyResponse(
            should_compete=True,
            spread_multiplier=1.0,
            size_multiplier=1.0,
            recommended_offset=Decimal("0.02"),
            reason="Normal competition",
        )

    def _compute_patterns(self):
        """Compute order patterns from history."""
        if len(self._orders) < 20:
            return

        # Group by (rounded size, rounded offset, side)
        clusters: Dict[tuple, List[dict]] = defaultdict(list)

        for order in self._orders:
            # Round to cluster similar orders
            size_bucket = (order["size"] / Decimal("10")).quantize(Decimal("1")) * 10
            offset_bucket = (order["offset"] * 100).quantize(Decimal("1")) / 100
            key = (size_bucket, offset_bucket, order["side"])
            clusters[key].append(order)

        # Convert clusters to patterns
        self._patterns = []
        for (size, offset, side), orders in clusters.items():
            if len(orders) >= 5:  # Minimum occurrences
                self._patterns.append(
                    OrderPattern(
                        size=size,
                        offset=offset,
                        side=side,
                        frequency=len(orders),
                        consistency=len(orders) / len(self._orders),
                    )
                )

        # Sort by frequency
        self._patterns.sort(key=lambda p: p.frequency, reverse=True)
