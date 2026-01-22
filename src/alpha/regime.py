"""
Liquidity Regime Detection

Classifies market liquidity state for strategy adaptation.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional
from enum import Enum
from collections import deque


class LiquidityRegime(Enum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    CRISIS = "crisis"


@dataclass
class LiquiditySnapshot:
    """Point-in-time liquidity measurement."""

    spread: Decimal
    bid_depth: Decimal
    ask_depth: Decimal
    volume: Decimal
    score: float = 0.0


@dataclass
class RegimeTransition:
    """A regime change event."""

    from_regime: LiquidityRegime
    to_regime: LiquidityRegime
    timestamp: int


@dataclass
class StrategyAdjustment:
    """Strategy adjustments for current regime."""

    regime: LiquidityRegime
    spread_multiplier: float
    size_multiplier: float
    should_pause: bool
    reason: str


class RegimeDetector:
    """
    Detects liquidity regime changes.

    Usage:
        detector = RegimeDetector()

        # Record market snapshots
        detector.record_snapshot(spread, bid_depth, ask_depth, volume)

        # Get current regime
        regime = detector.get_regime()

        # Get strategy adjustment
        adj = detector.get_strategy_adjustment()
    """

    # Thresholds for regime classification
    HIGH_LIQUIDITY_SCORE = 0.7
    LOW_LIQUIDITY_SCORE = 0.3
    CRISIS_SCORE = 0.1

    # Scoring weights
    SPREAD_WEIGHT = 0.3
    DEPTH_WEIGHT = 0.4
    VOLUME_WEIGHT = 0.3

    def __init__(self, window_size: int = 50):
        self.window_size = window_size
        self._snapshots: deque = deque(maxlen=window_size)
        self._regime_history: List[LiquidityRegime] = []

    def record_snapshot(
        self,
        spread: Decimal,
        bid_depth: Decimal,
        ask_depth: Decimal,
        volume: Decimal,
    ):
        """Record a liquidity snapshot."""
        score = self._calculate_score(spread, bid_depth, ask_depth, volume)

        snapshot = LiquiditySnapshot(
            spread=spread,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
            volume=volume,
            score=score,
        )

        self._snapshots.append(snapshot)

        # Track regime history
        regime = self._classify_regime(score)
        self._regime_history.append(regime)
        if len(self._regime_history) > 100:
            self._regime_history = self._regime_history[-100:]

    def get_regime(self) -> LiquidityRegime:
        """Get current liquidity regime."""
        if not self._snapshots:
            return LiquidityRegime.NORMAL

        # Use recent average score
        recent = list(self._snapshots)[-10:]
        avg_score = sum(s.score for s in recent) / len(recent)

        return self._classify_regime(avg_score)

    def detect_transition(self) -> Optional[RegimeTransition]:
        """Detect if regime just changed."""
        if len(self._regime_history) < 10:
            return None

        recent = self._regime_history[-5:]
        previous = self._regime_history[-10:-5]

        # Most common regime in each period
        def most_common(lst):
            return max(set(lst), key=lst.count)

        current_regime = most_common(recent)
        prev_regime = most_common(previous)

        if current_regime != prev_regime:
            return RegimeTransition(
                from_regime=prev_regime,
                to_regime=current_regime,
                timestamp=0,
            )

        return None

    def get_strategy_adjustment(self) -> StrategyAdjustment:
        """Get strategy adjustment for current regime."""
        regime = self.get_regime()
        transition = self.detect_transition()

        # Pause during transitions
        if transition is not None:
            return StrategyAdjustment(
                regime=regime,
                spread_multiplier=1.5,
                size_multiplier=0.3,
                should_pause=True,
                reason=f"Regime transition: {transition.from_regime.value} -> {transition.to_regime.value}",
            )

        # Regime-specific adjustments
        if regime == LiquidityRegime.HIGH:
            return StrategyAdjustment(
                regime=regime,
                spread_multiplier=0.8,
                size_multiplier=1.5,
                should_pause=False,
                reason="High liquidity - tighten spread, increase size",
            )

        elif regime == LiquidityRegime.LOW:
            return StrategyAdjustment(
                regime=regime,
                spread_multiplier=1.5,
                size_multiplier=0.5,
                should_pause=False,
                reason="Low liquidity - widen spread, reduce size",
            )

        elif regime == LiquidityRegime.CRISIS:
            return StrategyAdjustment(
                regime=regime,
                spread_multiplier=2.0,
                size_multiplier=0.2,
                should_pause=True,
                reason="Crisis liquidity - pause trading",
            )

        # Normal
        return StrategyAdjustment(
            regime=regime,
            spread_multiplier=1.0,
            size_multiplier=1.0,
            should_pause=False,
            reason="Normal liquidity",
        )

    def _calculate_score(
        self,
        spread: Decimal,
        bid_depth: Decimal,
        ask_depth: Decimal,
        volume: Decimal,
    ) -> float:
        """Calculate liquidity score (0-1)."""
        # Spread score: 1c = 1.0, 10c = 0.0
        spread_score = max(0, 1 - float(spread) / 0.10)

        # Depth score: $1000 = 1.0, $50 = 0.0
        total_depth = bid_depth + ask_depth
        depth_score = min(1.0, float(total_depth) / 2000)

        # Volume score: $5000 = 1.0, $100 = 0.0
        volume_score = min(1.0, float(volume) / 5000)

        return (
            self.SPREAD_WEIGHT * spread_score
            + self.DEPTH_WEIGHT * depth_score
            + self.VOLUME_WEIGHT * volume_score
        )

    def _classify_regime(self, score: float) -> LiquidityRegime:
        """Classify regime from score."""
        if score >= self.HIGH_LIQUIDITY_SCORE:
            return LiquidityRegime.HIGH
        elif score >= self.LOW_LIQUIDITY_SCORE:
            return LiquidityRegime.NORMAL
        elif score >= self.CRISIS_SCORE:
            return LiquidityRegime.LOW
        else:
            return LiquidityRegime.CRISIS
