"""
Adaptive Quote Timing

Dynamically adjusts loop interval based on market conditions.

Modes:
- FAST (100ms): High volatility, volume spikes, rapid price moves
- NORMAL (2s): Standard market conditions
- SLEEP (5s): Extended quiet periods
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TimingMode(Enum):
    FAST = "fast"
    NORMAL = "normal"
    SLEEP = "sleep"


@dataclass
class TimingConfig:
    """Timing configuration."""
    base_interval: float = 2.0
    fast_interval: float = 0.1
    sleep_interval: float = 5.0
    volatility_threshold: float = 0.01   # 1% price move triggers fast
    volume_spike_ratio: float = 2.0      # 2x volume triggers fast
    inactivity_threshold: float = 60.0   # 60s quiet triggers sleep
    fast_mode_duration: float = 10.0     # Stay fast for 10s minimum


class AdaptiveTimer:
    """
    Manages adaptive timing for market making loop.

    Usage:
        timer = AdaptiveTimer()

        # In your loop
        while running:
            interval = timer.get_interval()
            await asyncio.sleep(interval)

            # Update timer with market data
            timer.record_price_change(pct_change)
            timer.record_volume(current, avg)
    """

    def __init__(
        self,
        base_interval: float = 2.0,
        fast_interval: float = 0.1,
        sleep_interval: float = 5.0,
        volatility_threshold: float = 0.01,
        volume_spike_ratio: float = 2.0,
        inactivity_threshold: float = 60.0,
        fast_mode_duration: float = 10.0,
    ):
        self.config = TimingConfig(
            base_interval=base_interval,
            fast_interval=fast_interval,
            sleep_interval=sleep_interval,
            volatility_threshold=volatility_threshold,
            volume_spike_ratio=volume_spike_ratio,
            inactivity_threshold=inactivity_threshold,
            fast_mode_duration=fast_mode_duration,
        )

        self._mode = TimingMode.NORMAL
        self._last_fast_trigger: float = 0.0
        self._last_activity: float = time.time()
        self._last_price: Optional[float] = None

    def get_mode(self) -> TimingMode:
        """Get current timing mode."""
        return self._mode

    def get_interval(self) -> float:
        """Get current loop interval in seconds."""
        if self._mode == TimingMode.FAST:
            return self.config.fast_interval
        elif self._mode == TimingMode.SLEEP:
            return self.config.sleep_interval
        return self.config.base_interval

    def record_price_change(self, pct_change: float):
        """Record a price change and update mode."""
        now = time.time()
        self._last_activity = now

        if abs(pct_change) >= self.config.volatility_threshold:
            self._mode = TimingMode.FAST
            self._last_fast_trigger = now
        elif self._mode == TimingMode.FAST:
            # Check if fast mode should expire
            if now - self._last_fast_trigger > self.config.fast_mode_duration:
                self._mode = TimingMode.NORMAL

    def record_volume(self, current: float, avg: float):
        """Record volume and check for spike."""
        self._last_activity = time.time()

        if avg > 0 and current / avg >= self.config.volume_spike_ratio:
            self._mode = TimingMode.FAST
            self._last_fast_trigger = time.time()

    def record_activity(self, seconds_since_last: float):
        """Record activity level."""
        if seconds_since_last >= self.config.inactivity_threshold:
            if self._mode != TimingMode.FAST:
                self._mode = TimingMode.SLEEP
        else:
            if self._mode == TimingMode.SLEEP:
                self._mode = TimingMode.NORMAL
            self._last_activity = time.time()

    def on_feed_update(self, has_data: bool):
        """Called on each feed update."""
        if has_data:
            self._last_activity = time.time()
            if self._mode == TimingMode.SLEEP:
                self._mode = TimingMode.NORMAL

    def update_from_price(self, price: float):
        """Update timer from new price observation."""
        if self._last_price is not None:
            pct_change = abs(price - self._last_price) / self._last_price
            self.record_price_change(pct_change)
        self._last_price = price
