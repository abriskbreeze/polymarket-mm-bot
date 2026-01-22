"""
Dynamic Position Limits

Adjusts position limits based on market conditions and performance.

Formula:
    adjusted_limit = base_limit * confidence_mult * (1 - drawdown_penalty)

Where:
- confidence_mult: 0.5 (uncertain) to 2.0 (high conviction)
- drawdown_penalty: 0 (no drawdown) to 0.5 (at daily loss limit)
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, List
import time


@dataclass
class MarketConditions:
    """Current market conditions for limit calculation."""
    confidence: float = 0.5           # Overall confidence 0-1
    volatility_level: str = "NORMAL"  # LOW, NORMAL, HIGH, EXTREME
    fill_rate: float = 0.5            # Recent fill rate
    spread_quality: float = 0.5       # How good are our spreads vs market


@dataclass
class LimitSnapshot:
    """Point-in-time limit state."""
    timestamp: float
    base_limit: Decimal
    adjusted_limit: Decimal
    confidence_mult: float
    drawdown_penalty: float
    reason: str


class DynamicLimitManager:
    """
    Manages dynamic position limits.

    Usage:
        manager = DynamicLimitManager(base_limit=Decimal("100"))

        # Update conditions
        manager.set_conditions(MarketConditions(confidence=0.8))

        # Record P&L
        manager.record_pnl(Decimal("-10"))

        # Get current limit
        limit = manager.get_limit()
    """

    # Multiplier bounds
    CONFIDENCE_MIN = 0.5
    CONFIDENCE_MAX = 2.0

    # Limit bounds (relative to base)
    LIMIT_FLOOR_PCT = 0.2   # Never below 20% of base
    LIMIT_CEILING_PCT = 2.0  # Never above 200% of base

    # Smoothing
    SMOOTHING_FACTOR = 0.3  # How fast to adjust (0=instant, 1=never)

    def __init__(
        self,
        base_limit: Decimal = Decimal("100"),
        max_daily_loss: Decimal = Decimal("50"),
        min_limit: Optional[Decimal] = None,
        max_limit: Optional[Decimal] = None,
    ):
        self.base_limit = base_limit
        self.max_daily_loss = max_daily_loss
        self.min_limit = min_limit or (base_limit * Decimal(str(self.LIMIT_FLOOR_PCT)))
        self.max_limit = max_limit or (base_limit * Decimal(str(self.LIMIT_CEILING_PCT)))

        self._conditions = MarketConditions()
        self._daily_pnl = Decimal("0")
        self._last_limit = base_limit
        self._history: List[LimitSnapshot] = []

    def set_conditions(self, conditions: MarketConditions):
        """Update market conditions."""
        self._conditions = conditions

    def record_pnl(self, pnl: Decimal):
        """Record P&L change."""
        self._daily_pnl += pnl

    def reset_daily_pnl(self):
        """Reset daily P&L (call at start of day)."""
        self._daily_pnl = Decimal("0")

    def get_limit(self) -> Decimal:
        """Calculate current position limit."""
        # 1. Calculate confidence multiplier
        confidence_mult = self._calculate_confidence_mult()

        # 2. Calculate drawdown penalty
        drawdown_penalty = self.get_drawdown_penalty()

        # 3. Apply formula
        raw_limit = self.base_limit * Decimal(str(confidence_mult)) * Decimal(str(1 - drawdown_penalty))

        # 4. Apply bounds
        bounded = max(self.min_limit, min(self.max_limit, raw_limit))

        # 5. Smooth transition
        smoothed = self._smooth_limit(bounded)

        # 6. Record history
        self._history.append(LimitSnapshot(
            timestamp=time.time(),
            base_limit=self.base_limit,
            adjusted_limit=smoothed,
            confidence_mult=confidence_mult,
            drawdown_penalty=drawdown_penalty,
            reason=self._get_reason(confidence_mult, drawdown_penalty),
        ))

        self._last_limit = smoothed
        return smoothed

    def get_drawdown_penalty(self) -> float:
        """Calculate drawdown penalty based on daily P&L."""
        if self._daily_pnl >= 0:
            return 0.0

        # Linear penalty up to 50%
        loss_ratio = abs(self._daily_pnl) / self.max_daily_loss
        return min(0.5, float(loss_ratio) * 0.5)

    def get_limit_history(self) -> List[LimitSnapshot]:
        """Get history of limit changes."""
        return self._history[-100:]  # Last 100 snapshots

    def _calculate_confidence_mult(self) -> float:
        """Calculate confidence multiplier from conditions."""
        c = self._conditions

        # Start at 1.0
        mult = 1.0

        # Volatility adjustment
        if c.volatility_level == "LOW":
            mult *= 1.2
        elif c.volatility_level == "HIGH":
            mult *= 0.7
        elif c.volatility_level == "EXTREME":
            mult *= 0.5

        # Fill rate adjustment
        if c.fill_rate > 0.7:
            mult *= 1.1
        elif c.fill_rate < 0.3:
            mult *= 0.8

        # Overall confidence
        mult *= (0.5 + c.confidence)  # 0.5 to 1.5x

        # Bound the multiplier
        return max(self.CONFIDENCE_MIN, min(self.CONFIDENCE_MAX, mult))

    def _smooth_limit(self, target: Decimal) -> Decimal:
        """Smooth transition to target limit."""
        if self._last_limit == Decimal("0"):
            return target

        # Exponential smoothing
        alpha = Decimal(str(1 - self.SMOOTHING_FACTOR))
        smoothed = alpha * target + (1 - alpha) * self._last_limit

        return smoothed.quantize(Decimal("0.01"))

    def _get_reason(self, conf_mult: float, dd_penalty: float) -> str:
        """Generate human-readable reason for limit."""
        parts = []

        if conf_mult > 1.1:
            parts.append("high confidence")
        elif conf_mult < 0.9:
            parts.append("low confidence")

        if dd_penalty > 0.1:
            parts.append(f"{dd_penalty:.0%} drawdown penalty")

        return ", ".join(parts) if parts else "normal conditions"
