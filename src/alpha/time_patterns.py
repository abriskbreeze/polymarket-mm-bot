"""
Time-of-Day Pattern Analysis

Identifies and exploits predictable time-based patterns.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Dict, Optional
from collections import defaultdict


@dataclass
class HourlyStats:
    """Statistics for an hour of the day."""

    hour: int
    avg_volume: Decimal
    avg_spread: Decimal
    avg_fill_rate: float
    sample_count: int


@dataclass
class TimeAdjustment:
    """Strategy adjustment for time of day."""

    hour: int
    spread_multiplier: float
    size_multiplier: float
    is_peak: bool
    reason: str


class TimePatternAnalyzer:
    """
    Analyzes time-of-day patterns.

    Usage:
        analyzer = TimePatternAnalyzer()

        # Record stats
        analyzer.record_hourly_stats(hour=14, volume=1000, spread=0.02, fill_rate=0.8)

        # Get patterns
        peaks = analyzer.get_peak_hours()

        # Get current adjustment
        adj = analyzer.get_adjustment_for_hour(current_hour)
    """

    def __init__(self):
        self._hourly_data: Dict[int, List[dict]] = defaultdict(list)

    def record_hourly_stats(
        self,
        hour: int,
        volume: Decimal,
        avg_spread: Decimal,
        fill_rate: float,
    ):
        """Record statistics for an hour."""
        self._hourly_data[hour].append(
            {
                "volume": volume,
                "spread": avg_spread,
                "fill_rate": fill_rate,
            }
        )

        # Keep limited history
        if len(self._hourly_data[hour]) > 100:
            self._hourly_data[hour] = self._hourly_data[hour][-100:]

    def get_hourly_stats(self, hour: int) -> Optional[HourlyStats]:
        """Get aggregated stats for an hour."""
        data = self._hourly_data.get(hour, [])
        if not data:
            return None

        n = Decimal(len(data))
        return HourlyStats(
            hour=hour,
            avg_volume=sum((d["volume"] for d in data), Decimal(0)) / n,
            avg_spread=sum((d["spread"] for d in data), Decimal(0)) / n,
            avg_fill_rate=sum(d["fill_rate"] for d in data) / len(data),
            sample_count=len(data),
        )

    def get_peak_hours(self, top_n: int = 5) -> List[int]:
        """Get top N hours by volume."""
        stats: List[HourlyStats] = []
        for h in range(24):
            s = self.get_hourly_stats(h)
            if s is not None:
                stats.append(s)

        stats.sort(key=lambda s: s.avg_volume, reverse=True)
        return [s.hour for s in stats[:top_n]]

    def get_wide_spread_hours(
        self, threshold: Decimal = Decimal("0.04")
    ) -> List[int]:
        """Get hours with wider-than-threshold spreads."""
        wide = []
        for hour in range(24):
            stats = self.get_hourly_stats(hour)
            if stats and stats.avg_spread > threshold:
                wide.append(hour)
        return wide

    def get_adjustment_for_hour(self, hour: int) -> TimeAdjustment:
        """Get strategy adjustment for an hour."""
        stats = self.get_hourly_stats(hour)
        peaks = self.get_peak_hours()

        if stats is None:
            return TimeAdjustment(
                hour=hour,
                spread_multiplier=1.0,
                size_multiplier=1.0,
                is_peak=False,
                reason="No data for hour",
            )

        is_peak = hour in peaks

        # Calculate multipliers relative to average
        all_stats: List[HourlyStats] = []
        for h in range(24):
            s = self.get_hourly_stats(h)
            if s is not None:
                all_stats.append(s)

        if not all_stats:
            return TimeAdjustment(
                hour=hour,
                spread_multiplier=1.0,
                size_multiplier=1.0,
                is_peak=is_peak,
                reason="Insufficient data",
            )

        n = Decimal(len(all_stats))
        avg_volume = sum((s.avg_volume for s in all_stats), Decimal(0)) / n
        avg_spread = sum((s.avg_spread for s in all_stats), Decimal(0)) / n

        # Volume-based size adjustment (high volume = larger size)
        if avg_volume > 0:
            volume_ratio = float(stats.avg_volume / avg_volume)
        else:
            volume_ratio = 1.0
        size_mult = 0.5 + 0.5 * min(2.0, volume_ratio)

        # Volume-based spread adjustment (high volume = tighter spread)
        # Inverse relationship: high volume = can be aggressive = tighter spread
        if volume_ratio >= 1.5:
            spread_mult = 0.8  # 20% tighter during high volume
        elif volume_ratio <= 0.5:
            spread_mult = 1.4  # 40% wider during low volume
        else:
            # Linear interpolation between 0.5-1.5 volume ratio
            spread_mult = 1.4 - 0.6 * (volume_ratio - 0.5)

        reason = "Peak hours - be aggressive" if is_peak else "Off-peak - be conservative"

        return TimeAdjustment(
            hour=hour,
            spread_multiplier=spread_mult,
            size_multiplier=size_mult,
            is_peak=is_peak,
            reason=reason,
        )
