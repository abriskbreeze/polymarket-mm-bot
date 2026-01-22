"""
TDD Tests for Latency Monitoring

Tests latency tracking and alerting.
"""

import pytest
import time
from src.telemetry.latency import LatencyMonitor


class TestLatencyTracking:
    """Test latency measurement."""

    @pytest.fixture
    def monitor(self):
        return LatencyMonitor()

    def test_record_latency(self, monitor):
        """Record and retrieve latency."""
        monitor.record("order_place", 50)  # 50ms
        monitor.record("order_place", 60)

        stats = monitor.get_stats("order_place")
        assert stats.count == 2
        assert stats.avg == 55

    def test_percentiles(self, monitor):
        """Calculate latency percentiles."""
        for i in range(100):
            monitor.record("api_call", i)

        stats = monitor.get_stats("api_call")
        assert stats.p50 == pytest.approx(50, rel=0.1)
        assert stats.p99 == pytest.approx(99, rel=0.1)


class TestLatencyAlerts:
    """Test latency alerting."""

    @pytest.fixture
    def monitor(self):
        return LatencyMonitor(
            thresholds={
                "order_place": {"warn": 100, "critical": 500}
            }
        )

    def test_no_alert_under_threshold(self, monitor):
        """No alert when under threshold."""
        monitor.record("order_place", 50)
        alert = monitor.check_alerts()
        assert alert is None

    def test_warn_alert(self, monitor):
        """Warning alert when over warn threshold."""
        monitor.record("order_place", 150)
        alert = monitor.check_alerts()
        assert alert is not None
        assert alert.level == "warn"

    def test_critical_alert(self, monitor):
        """Critical alert when over critical threshold."""
        monitor.record("order_place", 600)
        alert = monitor.check_alerts()
        assert alert is not None
        assert alert.level == "critical"
