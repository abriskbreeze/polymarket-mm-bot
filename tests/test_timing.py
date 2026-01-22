"""
TDD Tests for Adaptive Timing Module

Run: pytest tests/test_timing.py -v
"""

import pytest
import time
from decimal import Decimal
from unittest.mock import Mock, patch

# Import will fail until we implement - that's expected in TDD
from src.strategy.timing import AdaptiveTimer, TimingMode


class TestAdaptiveTimerModes:
    """Test timing mode selection."""

    @pytest.fixture
    def timer(self):
        return AdaptiveTimer(
            base_interval=2.0,
            fast_interval=0.1,
            sleep_interval=5.0,
        )

    def test_initial_mode_is_normal(self, timer):
        """Timer starts in normal mode."""
        assert timer.get_mode() == TimingMode.NORMAL
        assert timer.get_interval() == 2.0

    def test_fast_mode_on_high_volatility(self, timer):
        """Switch to fast mode when volatility spikes."""
        # Simulate high volatility
        timer.record_price_change(pct_change=0.02)  # 2% move

        assert timer.get_mode() == TimingMode.FAST
        assert timer.get_interval() == 0.1

    def test_fast_mode_on_volume_spike(self, timer):
        """Switch to fast mode on unusual volume."""
        # Simulate volume spike (3x normal)
        timer.record_volume(current=1000, avg=300)

        assert timer.get_mode() == TimingMode.FAST

    def test_sleep_mode_on_inactivity(self, timer):
        """Switch to sleep mode after extended quiet period."""
        # Simulate 60+ seconds of no activity
        timer.record_activity(seconds_since_last=65)

        assert timer.get_mode() == TimingMode.SLEEP
        assert timer.get_interval() == 5.0

    def test_mode_persistence(self, timer):
        """Mode should persist for minimum duration."""
        timer.record_price_change(pct_change=0.02)  # Trigger fast mode
        assert timer.get_mode() == TimingMode.FAST

        # Small move shouldn't immediately exit fast mode
        timer.record_price_change(pct_change=0.001)
        assert timer.get_mode() == TimingMode.FAST  # Still fast

    def test_fast_mode_timeout(self, timer):
        """Fast mode expires after timeout."""
        timer.record_price_change(pct_change=0.02)
        assert timer.get_mode() == TimingMode.FAST

        # Simulate time passing (mock)
        with patch.object(timer, '_last_fast_trigger', time.time() - 30):
            timer.record_price_change(pct_change=0.001)
            assert timer.get_mode() == TimingMode.NORMAL


class TestAdaptiveTimerThresholds:
    """Test threshold configuration."""

    def test_custom_thresholds(self):
        """Timer respects custom thresholds."""
        timer = AdaptiveTimer(
            volatility_threshold=0.05,  # 5% for fast mode
            inactivity_threshold=120,   # 2 min for sleep
        )

        # 2% move shouldn't trigger fast with 5% threshold
        timer.record_price_change(pct_change=0.02)
        assert timer.get_mode() == TimingMode.NORMAL

        # 6% move should trigger
        timer.record_price_change(pct_change=0.06)
        assert timer.get_mode() == TimingMode.FAST

    def test_interval_bounds(self):
        """Intervals stay within configured bounds."""
        timer = AdaptiveTimer(
            fast_interval=0.05,
            sleep_interval=10.0,
        )

        # Fast mode
        timer.record_price_change(pct_change=0.1)
        assert timer.get_interval() >= 0.05

        # Sleep mode
        timer.record_activity(seconds_since_last=300)
        assert timer.get_interval() <= 10.0


class TestAdaptiveTimerIntegration:
    """Integration tests with market maker."""

    def test_timer_used_in_loop(self):
        """Market maker uses timer interval."""
        timer = AdaptiveTimer()
        mock_mm = Mock()
        mock_mm.loop_interval = timer.get_interval()

        # Timer change should be usable by MM
        timer.record_price_change(pct_change=0.03)
        new_interval = timer.get_interval()

        assert new_interval < mock_mm.loop_interval

    def test_activity_tracking_from_feed(self):
        """Timer tracks activity from feed updates."""
        timer = AdaptiveTimer()

        # Simulate feed updates
        timer.on_feed_update(has_data=True)
        timer.on_feed_update(has_data=True)

        # Should stay in normal mode with regular updates
        assert timer.get_mode() == TimingMode.NORMAL
