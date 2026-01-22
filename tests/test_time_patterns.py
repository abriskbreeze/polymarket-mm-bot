"""
TDD Tests for Time-of-Day Patterns

Tests time-based pattern detection.
"""

import pytest
from datetime import datetime, time
from decimal import Decimal
from src.alpha.time_patterns import TimePatternAnalyzer


class TestTimePatternDetection:
    """Test time pattern detection."""

    @pytest.fixture
    def analyzer(self):
        return TimePatternAnalyzer()

    def test_identify_peak_hours(self, analyzer):
        """Identify high-volume hours."""
        # Record higher volume during US hours
        for hour in range(24):
            if 14 <= hour <= 21:  # US market hours
                volume = 1000
            else:
                volume = 200

            analyzer.record_hourly_stats(
                hour=hour,
                volume=Decimal(str(volume)),
                avg_spread=Decimal("0.02"),
                fill_rate=0.7,
            )

        peaks = analyzer.get_peak_hours(top_n=8)  # Get all 8 peak hours

        # Should identify afternoon/evening as peak
        assert 14 in peaks or 15 in peaks
        assert 21 in peaks or 20 in peaks

    def test_identify_wide_spread_hours(self, analyzer):
        """Identify hours with wider spreads."""
        for hour in range(24):
            if 0 <= hour <= 6:  # Overnight
                spread = Decimal("0.05")
            else:
                spread = Decimal("0.02")

            analyzer.record_hourly_stats(
                hour=hour,
                volume=Decimal("500"),
                avg_spread=spread,
                fill_rate=0.5,
            )

        wide_hours = analyzer.get_wide_spread_hours()

        assert 0 in wide_hours or 1 in wide_hours


class TestTimeBasedStrategy:
    """Test time-based strategy adjustments."""

    @pytest.fixture
    def analyzer(self):
        analyzer = TimePatternAnalyzer()
        # Populate with typical patterns
        for hour in range(24):
            if 14 <= hour <= 21:
                analyzer.record_hourly_stats(hour, Decimal("1000"), Decimal("0.02"), 0.8)
            elif 0 <= hour <= 6:
                analyzer.record_hourly_stats(hour, Decimal("100"), Decimal("0.06"), 0.3)
            else:
                analyzer.record_hourly_stats(hour, Decimal("500"), Decimal("0.03"), 0.6)
        return analyzer

    def test_aggressive_during_peak(self, analyzer):
        """More aggressive during peak hours."""
        adj = analyzer.get_adjustment_for_hour(16)  # 4 PM EST

        assert adj.spread_multiplier < 1.0  # Tighter
        assert adj.size_multiplier > 1.0    # Larger

    def test_conservative_overnight(self, analyzer):
        """More conservative overnight."""
        adj = analyzer.get_adjustment_for_hour(3)  # 3 AM

        assert adj.spread_multiplier > 1.0  # Wider
        assert adj.size_multiplier < 1.0    # Smaller
