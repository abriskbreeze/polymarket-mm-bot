"""
Volatility tracker - measures realized volatility for dynamic spread sizing.

Samples price periodically and calculates rolling volatility.
Outputs a multiplier for spread adjustment.
"""

import time
import math
from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Deque, Tuple

from src.config import (
    VOL_SAMPLE_INTERVAL,
    VOL_WINDOW_SECONDS,
    VOL_MIN_SAMPLES,
    VOL_MULT_MIN,
    VOL_MULT_MAX,
)
from src.utils import setup_logging

logger = setup_logging()


@dataclass
class VolatilityState:
    """Current volatility state for display."""
    realized_vol: float          # Annualized volatility (0.0-1.0+)
    multiplier: float            # Spread multiplier (0.7-2.0)
    sample_count: int            # Number of samples in window
    level: str                   # "LOW", "NORMAL", "HIGH", "EXTREME"
    last_price: Optional[float]  # Most recent sampled price


class VolatilityTracker:
    """
    Tracks realized volatility using price samples.

    Samples price every N seconds, maintains rolling window,
    calculates realized volatility as standard deviation of returns.

    Usage:
        vol = VolatilityTracker(token_id="abc123")

        # In your loop, call update with current price:
        vol.update(mid_price)

        # Get current volatility multiplier:
        mult = vol.get_multiplier()  # 0.7 (calm) to 2.0 (volatile)

        # Get full state for display:
        state = vol.get_state()
    """

    # Volatility thresholds for level classification
    VOL_LOW = 0.05       # < 5% annualized = calm
    VOL_NORMAL = 0.15    # 5-15% = normal
    VOL_HIGH = 0.30      # 15-30% = elevated
    # > 30% = extreme

    def __init__(
        self,
        token_id: str,
        sample_interval: float = VOL_SAMPLE_INTERVAL,
        window_seconds: float = VOL_WINDOW_SECONDS,
        min_samples: int = VOL_MIN_SAMPLES,
        mult_min: float = VOL_MULT_MIN,
        mult_max: float = VOL_MULT_MAX,
    ):
        """
        Args:
            token_id: Token being tracked
            sample_interval: Seconds between samples (default 5)
            window_seconds: Rolling window size (default 1800 = 30 min)
            min_samples: Minimum samples before calculating vol (default 10)
            mult_min: Minimum spread multiplier (default 0.7)
            mult_max: Maximum spread multiplier (default 2.0)
        """
        self.token_id = token_id
        self.sample_interval = sample_interval
        self.window_seconds = window_seconds
        self.min_samples = min_samples
        self.mult_min = mult_min
        self.mult_max = mult_max

        # Calculate max samples in window
        max_samples = int(window_seconds / sample_interval) + 10
        self._samples: Deque[Tuple[float, float]] = deque(maxlen=max_samples)

        self._last_sample_time: float = 0.0
        self._last_price: Optional[float] = None
        self._realized_vol: float = 0.0

    def update(self, price: float) -> bool:
        """
        Update with current price. Samples if enough time has passed.

        Args:
            price: Current mid price

        Returns:
            True if a new sample was taken
        """
        if price <= 0:
            return False

        now = time.time()

        # Check if it's time to sample
        if now - self._last_sample_time < self.sample_interval:
            return False

        # Take sample
        self._samples.append((now, price))
        self._last_sample_time = now
        self._last_price = price

        # Prune old samples outside window
        cutoff = now - self.window_seconds
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

        # Recalculate volatility if we have enough samples
        if len(self._samples) >= self.min_samples:
            self._realized_vol = self._calculate_volatility()

        return True

    def get_multiplier(self) -> float:
        """
        Get spread multiplier based on current volatility.

        Returns:
            Multiplier between mult_min (calm) and mult_max (volatile)
        """
        if len(self._samples) < self.min_samples:
            # Not enough data - use neutral multiplier
            return 1.0

        # Map volatility to multiplier
        # Low vol (< 5%) -> mult_min (0.7)
        # Normal vol (5-15%) -> 1.0
        # High vol (15-30%) -> 1.5
        # Extreme (> 30%) -> mult_max (2.0)

        vol = self._realized_vol

        if vol < self.VOL_LOW:
            # Calm - tighten spread
            return self.mult_min

        if vol < self.VOL_NORMAL:
            # Transition from calm to normal
            ratio = (vol - self.VOL_LOW) / (self.VOL_NORMAL - self.VOL_LOW)
            return self.mult_min + ratio * (1.0 - self.mult_min)

        if vol < self.VOL_HIGH:
            # Transition from normal to high
            ratio = (vol - self.VOL_NORMAL) / (self.VOL_HIGH - self.VOL_NORMAL)
            return 1.0 + ratio * 0.5  # 1.0 -> 1.5

        # Extreme volatility
        ratio = min(1.0, (vol - self.VOL_HIGH) / 0.20)  # Cap at 50% annualized
        return 1.5 + ratio * (self.mult_max - 1.5)  # 1.5 -> mult_max

    def get_level(self) -> str:
        """Get volatility level as string."""
        if len(self._samples) < self.min_samples:
            return "UNKNOWN"

        vol = self._realized_vol
        if vol < self.VOL_LOW:
            return "LOW"
        if vol < self.VOL_NORMAL:
            return "NORMAL"
        if vol < self.VOL_HIGH:
            return "HIGH"
        return "EXTREME"

    def get_state(self) -> VolatilityState:
        """Get full volatility state for display."""
        return VolatilityState(
            realized_vol=self._realized_vol,
            multiplier=self.get_multiplier(),
            sample_count=len(self._samples),
            level=self.get_level(),
            last_price=self._last_price,
        )

    def get_realized_vol(self) -> float:
        """Get current realized volatility (annualized)."""
        return self._realized_vol

    def _calculate_volatility(self) -> float:
        """
        Calculate realized volatility from samples.

        Uses standard deviation of log returns, annualized.
        """
        if len(self._samples) < 2:
            return 0.0

        # Calculate log returns
        returns = []
        samples_list = list(self._samples)

        for i in range(1, len(samples_list)):
            _, price_prev = samples_list[i - 1]
            _, price_curr = samples_list[i]

            if price_prev > 0 and price_curr > 0:
                log_return = math.log(price_curr / price_prev)
                returns.append(log_return)

        if len(returns) < 2:
            return 0.0

        # Calculate standard deviation
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        std_dev = math.sqrt(variance)

        # Annualize: multiply by sqrt(periods per year)
        # With 5-second samples: 365 * 24 * 60 * 60 / 5 = 6,307,200 periods/year
        periods_per_year = 365 * 24 * 3600 / self.sample_interval
        annualized_vol = std_dev * math.sqrt(periods_per_year)

        return annualized_vol

    def reset(self):
        """Clear all samples and reset state."""
        self._samples.clear()
        self._last_sample_time = 0.0
        self._last_price = None
        self._realized_vol = 0.0


class MultiTokenVolatilityTracker:
    """
    Track volatility for multiple tokens.

    Usage:
        tracker = MultiTokenVolatilityTracker()
        tracker.update("token1", 0.55)
        tracker.update("token2", 0.40)

        mult1 = tracker.get_multiplier("token1")
    """

    def __init__(self, **kwargs):
        """kwargs are passed to each VolatilityTracker."""
        self._trackers: dict[str, VolatilityTracker] = {}
        self._kwargs = kwargs

    def update(self, token_id: str, price: float) -> bool:
        """Update price for a token."""
        if token_id not in self._trackers:
            self._trackers[token_id] = VolatilityTracker(token_id, **self._kwargs)
        return self._trackers[token_id].update(price)

    def get_multiplier(self, token_id: str) -> float:
        """Get spread multiplier for a token."""
        if token_id not in self._trackers:
            return 1.0
        return self._trackers[token_id].get_multiplier()

    def get_state(self, token_id: str) -> Optional[VolatilityState]:
        """Get volatility state for a token."""
        if token_id not in self._trackers:
            return None
        return self._trackers[token_id].get_state()

    def get_all_states(self) -> dict[str, VolatilityState]:
        """Get volatility states for all tracked tokens."""
        return {tid: t.get_state() for tid, t in self._trackers.items()}
