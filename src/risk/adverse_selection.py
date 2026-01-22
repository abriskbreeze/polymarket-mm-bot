"""
Adverse Selection Detection

Detects when our fills systematically precede adverse price moves,
indicating we're trading against informed flow.

Toxicity = (adverse fills) / (total fills)

An adverse fill is one where price moves against us shortly after.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, List, Dict
import time

from src.config import (
    ADVERSE_LOOKBACK_SECONDS,
    ADVERSE_TOXIC_THRESHOLD,
    ADVERSE_HIGHLY_TOXIC_THRESHOLD,
    ADVERSE_PRICE_THRESHOLD,
    ADVERSE_OBSERVATION_WINDOW,
)


@dataclass
class FillRecord:
    """Record of a fill for analysis."""
    fill_id: int
    timestamp: float
    price: Decimal
    side: str
    size: Decimal
    price_after: Optional[Decimal] = None
    seconds_to_price_after: float = 0


@dataclass
class FillAnalysis:
    """Analysis of a single fill."""
    fill_id: int
    was_adverse: bool
    adverse_move: Decimal
    seconds_to_adverse: float


@dataclass
class AdverseSelectionResponse:
    """Recommended response to adverse selection."""
    widen_spread: bool
    spread_multiplier: float
    reduce_size: bool
    size_multiplier: float
    skip_side: Optional[str]  # "BUY" or "SELL" if one side is toxic
    reason: str


class AdverseSelectionDetector:
    """
    Detects adverse selection in our fills.

    Usage:
        detector = AdverseSelectionDetector()

        # Record fills as they happen
        detector.record_fill(price, side, size)

        # Later, record price movement
        detector.record_price_after(fill_id, price_after)

        # Get toxicity score
        toxicity = detector.get_toxicity()

        # Get recommended response
        response = detector.get_response()
    """

    # Thresholds (from config)
    ADVERSE_THRESHOLD = ADVERSE_PRICE_THRESHOLD
    TOXIC_THRESHOLD = ADVERSE_TOXIC_THRESHOLD
    HIGHLY_TOXIC = ADVERSE_HIGHLY_TOXIC_THRESHOLD
    OBSERVATION_WINDOW = ADVERSE_OBSERVATION_WINDOW

    def __init__(self, lookback_window: float = ADVERSE_LOOKBACK_SECONDS):
        self.lookback_window = lookback_window  # 5 minutes default
        self._fills: List[FillRecord] = []
        self._next_id = 0

    def record_fill(
        self,
        price: Decimal,
        side: str,
        size: Decimal,
    ) -> int:
        """Record a new fill. Returns fill_id."""
        fill = FillRecord(
            fill_id=self._next_id,
            timestamp=time.time(),
            price=price,
            side=side.upper(),
            size=size,
        )
        self._fills.append(fill)
        self._next_id += 1

        # Cleanup old fills
        self._cleanup_old_fills()

        return fill.fill_id

    def record_price_after(
        self,
        fill_id: int,
        price_after: Decimal,
        seconds_after: float = 0,
    ):
        """Record price after a fill."""
        for fill in self._fills:
            if fill.fill_id == fill_id:
                fill.price_after = price_after
                fill.seconds_to_price_after = seconds_after or (time.time() - fill.timestamp)
                break

    def get_toxicity(self, side: Optional[str] = None) -> float:
        """
        Calculate toxicity score.

        Args:
            side: Optional filter for "BUY" or "SELL"

        Returns:
            Toxicity score 0.0-1.0
        """
        fills = self._get_fills_with_outcome(side)
        if not fills:
            return 0.0

        adverse_count = sum(1 for f in fills if self._is_adverse(f))
        return adverse_count / len(fills)

    def get_response(self) -> AdverseSelectionResponse:
        """Get recommended response based on toxicity."""
        toxicity = self.get_toxicity()
        buy_toxicity = self.get_toxicity("BUY")
        sell_toxicity = self.get_toxicity("SELL")

        # Default: no changes
        if toxicity < self.TOXIC_THRESHOLD:
            return AdverseSelectionResponse(
                widen_spread=False,
                spread_multiplier=1.0,
                reduce_size=False,
                size_multiplier=1.0,
                skip_side=None,
                reason="Healthy fill profile",
            )

        # Toxic: widen and reduce
        spread_mult = 1.0 + (toxicity - self.TOXIC_THRESHOLD)
        size_mult = 1.0 - (toxicity - self.TOXIC_THRESHOLD) * 0.5

        # Check if one side is particularly toxic
        skip_side = None
        if buy_toxicity > self.HIGHLY_TOXIC and sell_toxicity < self.TOXIC_THRESHOLD:
            skip_side = "BUY"
        elif sell_toxicity > self.HIGHLY_TOXIC and buy_toxicity < self.TOXIC_THRESHOLD:
            skip_side = "SELL"

        return AdverseSelectionResponse(
            widen_spread=True,
            spread_multiplier=min(2.0, spread_mult),
            reduce_size=True,
            size_multiplier=max(0.3, size_mult),
            skip_side=skip_side,
            reason=f"Toxicity {toxicity:.1%}",
        )

    def analyze_fill(self, fill_id: int) -> Optional[FillAnalysis]:
        """Analyze a specific fill."""
        for fill in self._fills:
            if fill.fill_id == fill_id:
                if fill.price_after is None:
                    return None

                was_adverse = self._is_adverse(fill)
                adverse_move = self._calculate_adverse_move(fill)

                return FillAnalysis(
                    fill_id=fill_id,
                    was_adverse=was_adverse,
                    adverse_move=adverse_move,
                    seconds_to_adverse=fill.seconds_to_price_after,
                )
        return None

    def _is_adverse(self, fill: FillRecord) -> bool:
        """Check if fill was adverse."""
        if fill.price_after is None:
            return False

        move = fill.price_after - fill.price

        if fill.side == "BUY":
            # Adverse if price dropped after our buy
            return move < -self.ADVERSE_THRESHOLD
        else:
            # Adverse if price rose after our sell
            return move > self.ADVERSE_THRESHOLD

    def _calculate_adverse_move(self, fill: FillRecord) -> Decimal:
        """Calculate adverse move amount."""
        if fill.price_after is None:
            return Decimal("0")

        move = fill.price_after - fill.price

        if fill.side == "BUY":
            return move  # Negative = adverse for buyer
        else:
            return -move  # Positive move = adverse for seller

    def _get_fills_with_outcome(self, side: Optional[str] = None) -> List[FillRecord]:
        """Get fills that have outcome recorded."""
        fills = [f for f in self._fills if f.price_after is not None]
        if side:
            fills = [f for f in fills if f.side == side.upper()]
        return fills

    def _cleanup_old_fills(self):
        """Remove fills outside lookback window."""
        cutoff = time.time() - self.lookback_window
        self._fills = [f for f in self._fills if f.timestamp > cutoff]
