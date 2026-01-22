"""
Queue Position Optimizer

Analyzes order book queue to optimize placement for fill rate.

Strategy:
- If queue at best price is long, improve by 1 tick
- If queue is short, join at best (save edge)
- Track historical fill rates to calibrate
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, List
from collections import defaultdict


@dataclass
class PlacementDecision:
    """Recommendation for order placement."""
    should_improve: bool
    recommended_price: Decimal
    queue_depth: float
    expected_fill_rate: float
    reason: str


@dataclass
class FillRecord:
    """Record of a fill attempt for learning."""
    queue_position: float
    filled: bool
    time_in_queue: float


class QueueOptimizer:
    """
    Optimizes order placement based on queue analysis.

    Usage:
        optimizer = QueueOptimizer()

        decision = optimizer.analyze_placement(
            side="BUY",
            best_price=Decimal("0.50"),
            queue_depth_at_best=500,
            our_size=Decimal("10"),
        )

        if decision.should_improve:
            place_at = decision.recommended_price
        else:
            place_at = best_price
    """

    # Thresholds
    IMPROVE_THRESHOLD = 100  # $100 queue depth to consider improving
    MIN_EDGE_PRESERVE = Decimal("0.01")  # Never improve more than 1 tick

    def __init__(
        self,
        tick_size: Decimal = Decimal("0.01"),
        improve_threshold: float = 100,
    ):
        self.tick_size = tick_size
        self.improve_threshold = improve_threshold

        # Fill rate tracking by queue position bucket
        self._fill_history: List[FillRecord] = []
        self._fills_by_bucket: defaultdict = defaultdict(lambda: {"filled": 0, "total": 0})

    def analyze_placement(
        self,
        side: str,
        best_price: Decimal,
        queue_depth_at_best: float,
        our_size: Decimal,
        opposite_best: Optional[Decimal] = None,
    ) -> PlacementDecision:
        """
        Analyze queue and recommend placement.

        Args:
            side: "BUY" or "SELL"
            best_price: Current best bid/ask
            queue_depth_at_best: Total size at best price
            our_size: Our order size
            opposite_best: Best price on other side (to avoid crossing)

        Returns:
            PlacementDecision with recommendation
        """
        should_improve = False
        recommended_price = best_price
        reason = "Join at best price"

        # Check if queue is long enough to justify improving
        if queue_depth_at_best >= self.improve_threshold:
            should_improve = True

            if side == "BUY":
                improved_price = best_price + self.tick_size
                # Don't cross the spread
                if opposite_best and improved_price >= opposite_best:
                    should_improve = False
                    reason = "Would cross spread"
                else:
                    recommended_price = improved_price
                    reason = f"Queue ${queue_depth_at_best:.0f} deep, improve +1 tick"

            else:  # SELL
                improved_price = best_price - self.tick_size
                if opposite_best and improved_price <= opposite_best:
                    should_improve = False
                    reason = "Would cross spread"
                else:
                    recommended_price = improved_price
                    reason = f"Queue ${queue_depth_at_best:.0f} deep, improve -1 tick"
        else:
            reason = f"Queue only ${queue_depth_at_best:.0f}, join at best"

        # Estimate fill rate
        expected_fill_rate = self._estimate_fill_rate(
            queue_depth_at_best if not should_improve else 0
        )

        return PlacementDecision(
            should_improve=should_improve,
            recommended_price=recommended_price,
            queue_depth=queue_depth_at_best,
            expected_fill_rate=expected_fill_rate,
            reason=reason,
        )

    def record_fill(
        self,
        queue_position: float,
        filled: bool,
        time_in_queue: float = 0,
    ):
        """Record a fill/no-fill for learning."""
        record = FillRecord(
            queue_position=queue_position,
            filled=filled,
            time_in_queue=time_in_queue,
        )
        self._fill_history.append(record)

        # Bucket by queue position (0-50, 50-100, 100-200, etc.)
        bucket = self._get_bucket(queue_position)
        self._fills_by_bucket[bucket]["total"] += 1
        if filled:
            self._fills_by_bucket[bucket]["filled"] += 1

    def get_fill_rate(self, queue_position: float) -> float:
        """Get historical fill rate for queue position."""
        bucket = self._get_bucket(queue_position)
        data = self._fills_by_bucket[bucket]
        if data["total"] == 0:
            return 0.5  # Default assumption
        return data["filled"] / data["total"]

    def get_optimal_position(self) -> float:
        """Get optimal queue position based on history."""
        if not self._fills_by_bucket:
            return 50  # Default

        # Find bucket with best fill rate
        best_bucket = 0
        best_rate = 0

        for bucket, data in self._fills_by_bucket.items():
            if data["total"] >= 5:  # Minimum sample size
                rate = data["filled"] / data["total"]
                if rate > best_rate:
                    best_rate = rate
                    best_bucket = bucket

        return best_bucket

    def _get_bucket(self, queue_position: float) -> int:
        """Map queue position to bucket."""
        if queue_position < 50:
            return 0
        elif queue_position < 100:
            return 50
        elif queue_position < 200:
            return 100
        elif queue_position < 500:
            return 200
        return 500

    def _estimate_fill_rate(self, queue_position: float) -> float:
        """Estimate fill rate for queue position."""
        # Simple model: fill rate decreases with queue depth
        # Front of queue: ~80% fill rate
        # Back of queue (500+): ~20% fill rate
        base_rate = 0.8
        decay_per_100 = 0.1
        buckets = queue_position / 100
        return max(0.2, base_rate - decay_per_100 * buckets)
