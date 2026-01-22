"""
Latency Monitoring

Tracks execution latency and alerts on degradation.
"""

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class LatencyStats:
    """Statistics for a latency metric."""
    name: str
    count: int
    min: float
    max: float
    avg: float
    p50: float
    p95: float
    p99: float

@dataclass
class LatencyAlert:
    """Latency alert."""
    metric: str
    value: float
    threshold: float
    level: str  # "warn" or "critical"
    message: str

@dataclass
class LatencyThreshold:
    """Threshold configuration."""
    warn: float
    critical: float

class LatencyMonitor:
    """
    Monitors execution latency.

    Usage:
        monitor = LatencyMonitor(thresholds={
            "order_place": {"warn": 100, "critical": 500}
        })

        # Record latencies
        start = time.time()
        place_order(...)
        monitor.record("order_place", (time.time() - start) * 1000)

        # Check for alerts
        alert = monitor.check_alerts()
        if alert:
            logger.warning(alert.message)

        # Get stats
        stats = monitor.get_stats("order_place")
    """

    def __init__(
        self,
        thresholds: Optional[Dict[str, dict]] = None,
        window_size: int = 1000,
    ):
        self.thresholds = {
            k: LatencyThreshold(**v)
            for k, v in (thresholds or {}).items()
        }
        self.window_size = window_size
        self._data: Dict[str, List[float]] = defaultdict(list)
        self._last_values: Dict[str, float] = {}

    def record(self, metric: str, latency_ms: float):
        """Record a latency measurement."""
        self._data[metric].append(latency_ms)
        self._last_values[metric] = latency_ms

        # Keep only recent values
        if len(self._data[metric]) > self.window_size:
            self._data[metric] = self._data[metric][-self.window_size:]

    def get_stats(self, metric: str) -> Optional[LatencyStats]:
        """Get statistics for a metric."""
        values = self._data.get(metric, [])
        if not values:
            return None

        sorted_values = sorted(values)
        n = len(sorted_values)

        return LatencyStats(
            name=metric,
            count=n,
            min=sorted_values[0],
            max=sorted_values[-1],
            avg=sum(values) / n,
            p50=sorted_values[int(n * 0.50)],
            p95=sorted_values[int(n * 0.95)] if n >= 20 else sorted_values[-1],
            p99=sorted_values[int(n * 0.99)] if n >= 100 else sorted_values[-1],
        )

    def check_alerts(self) -> Optional[LatencyAlert]:
        """Check if any metrics are over threshold."""
        for metric, threshold in self.thresholds.items():
            last_value = self._last_values.get(metric)
            if last_value is None:
                continue

            if last_value >= threshold.critical:
                return LatencyAlert(
                    metric=metric,
                    value=last_value,
                    threshold=threshold.critical,
                    level="critical",
                    message=f"CRITICAL: {metric} latency {last_value:.0f}ms > {threshold.critical}ms",
                )
            elif last_value >= threshold.warn:
                return LatencyAlert(
                    metric=metric,
                    value=last_value,
                    threshold=threshold.warn,
                    level="warn",
                    message=f"WARN: {metric} latency {last_value:.0f}ms > {threshold.warn}ms",
                )

        return None

    def get_all_stats(self) -> Dict[str, LatencyStats]:
        """Get stats for all metrics."""
        return {
            metric: stats
            for metric in self._data
            if (stats := self.get_stats(metric)) is not None
        }
