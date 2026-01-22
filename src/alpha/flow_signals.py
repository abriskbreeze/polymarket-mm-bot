"""
Order Flow Signal Generator

Analyzes trade patterns to predict short-term price direction.

Signals:
- Aggressive buy sweep: Large buyer hitting asks
- Aggressive sell sweep: Large seller hitting bids
- Passive accumulation: Patient limit order stacking
- Large cancel: Informed trader backing off
"""

import time
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Deque, Optional, List
from enum import Enum


class FlowSignal(Enum):
    NEUTRAL = "neutral"
    BULLISH = "bullish"
    BEARISH = "bearish"
    STRONGLY_BULLISH = "strongly_bullish"
    STRONGLY_BEARISH = "strongly_bearish"


@dataclass
class TradeEvent:
    """A single trade for flow analysis."""
    timestamp: float
    price: Decimal
    size: Decimal
    side: str          # "BUY" or "SELL"
    is_aggressive: bool  # Did this trade cross the spread?


@dataclass
class FlowState:
    """Current order flow state."""
    signal: FlowSignal
    buy_volume: Decimal
    sell_volume: Decimal
    net_flow: Decimal           # buy - sell
    aggressive_ratio: float     # aggressive / total
    imbalance: float            # -1.0 to +1.0
    trade_count: int
    signal_strength: float      # 0.0 to 1.0
    recommended_skew: Decimal   # Price adjustment based on flow


class FlowAnalyzer:
    """
    Analyzes order flow for trading signals.

    Usage:
        flow = FlowAnalyzer(token_id="abc123", window_seconds=60)

        # Record trades as they happen
        flow.record_trade(price=0.55, size=100, side="BUY", is_aggressive=True)

        # Get current signal
        state = flow.get_state()
        if state.signal == FlowSignal.BULLISH:
            # Expect price up, adjust quotes
            pass
    """

    # Signal thresholds
    IMBALANCE_THRESHOLD = 0.15      # 15% imbalance = signal
    STRONG_THRESHOLD = 0.30         # 30% = strong signal
    MIN_TRADES = 5                  # Need at least 5 trades
    AGGRESSIVE_WEIGHT = 2.0         # Aggressive trades count 2x

    def __init__(
        self,
        token_id: str,
        window_seconds: float = 60.0,
        decay_half_life: float = 30.0,
    ):
        self.token_id = token_id
        self.window_seconds = window_seconds
        self.decay_half_life = decay_half_life

        self._trades: Deque[TradeEvent] = deque(maxlen=1000)

    def record_trade(
        self,
        price: Decimal,
        size: Decimal,
        side: str,
        is_aggressive: bool = False,
    ):
        """Record a trade event."""
        event = TradeEvent(
            timestamp=time.time(),
            price=price,
            size=size,
            side=side.upper(),
            is_aggressive=is_aggressive,
        )
        self._trades.append(event)

    def get_state(self) -> FlowState:
        """Calculate current flow state."""
        now = time.time()
        cutoff = now - self.window_seconds

        # Filter to window and calculate weighted volumes
        buy_volume = Decimal("0")
        sell_volume = Decimal("0")
        aggressive_count = 0
        total_count = 0

        for trade in self._trades:
            if trade.timestamp < cutoff:
                continue

            # Time decay: recent trades matter more
            age = now - trade.timestamp
            decay = 0.5 ** (age / self.decay_half_life)

            # Aggressive trades weighted more
            weight = Decimal(str(decay))
            if trade.is_aggressive:
                weight *= Decimal(str(self.AGGRESSIVE_WEIGHT))
                aggressive_count += 1

            weighted_size = trade.size * weight

            if trade.side == "BUY":
                buy_volume += weighted_size
            else:
                sell_volume += weighted_size

            total_count += 1

        # Calculate imbalance
        total_volume = buy_volume + sell_volume
        if total_volume > 0:
            imbalance = float((buy_volume - sell_volume) / total_volume)
        else:
            imbalance = 0.0

        # Determine signal
        if total_count < self.MIN_TRADES:
            signal = FlowSignal.NEUTRAL
            strength = 0.0
        elif imbalance > self.STRONG_THRESHOLD:
            signal = FlowSignal.STRONGLY_BULLISH
            strength = min(1.0, imbalance / 0.5)
        elif imbalance > self.IMBALANCE_THRESHOLD:
            signal = FlowSignal.BULLISH
            strength = imbalance / self.STRONG_THRESHOLD
        elif imbalance < -self.STRONG_THRESHOLD:
            signal = FlowSignal.STRONGLY_BEARISH
            strength = min(1.0, abs(imbalance) / 0.5)
        elif imbalance < -self.IMBALANCE_THRESHOLD:
            signal = FlowSignal.BEARISH
            strength = abs(imbalance) / self.STRONG_THRESHOLD
        else:
            signal = FlowSignal.NEUTRAL
            strength = 0.0

        # Calculate recommended skew
        # Bullish = raise both quotes, bearish = lower both
        skew = Decimal(str(imbalance * 0.01))  # Max 1 cent skew

        return FlowState(
            signal=signal,
            buy_volume=buy_volume,
            sell_volume=sell_volume,
            net_flow=buy_volume - sell_volume,
            aggressive_ratio=aggressive_count / max(1, total_count),
            imbalance=imbalance,
            trade_count=total_count,
            signal_strength=strength,
            recommended_skew=skew,
        )

    def should_widen_spread(self) -> bool:
        """Check if high flow volatility suggests widening spread."""
        state = self.get_state()
        # High aggressive ratio = informed traders = widen
        return state.aggressive_ratio > 0.5 and state.trade_count > 10
