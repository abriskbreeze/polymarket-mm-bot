"""
TDD Tests for Competitor Detection

Tests identification of other market makers.
"""

import pytest
from decimal import Decimal
from src.alpha.competitors import CompetitorDetector, OrderPattern


class TestPatternRecognition:
    """Test order pattern recognition."""

    @pytest.fixture
    def detector(self):
        return CompetitorDetector()

    def test_detect_recurring_orders(self, detector):
        """Detect recurring order patterns."""
        # Same size, same offset from mid repeatedly
        for _ in range(20):
            detector.record_order(
                price=Decimal("0.50"),
                size=Decimal("100"),
                side="BUY",
                mid_price=Decimal("0.52"),
            )

        patterns = detector.get_patterns()

        assert len(patterns) > 0
        assert patterns[0].size == Decimal("100")
        assert patterns[0].offset == Decimal("-0.02")

    def test_distinguish_multiple_mms(self, detector):
        """Distinguish multiple market makers."""
        # MM A: 100 size, 2c offset
        for _ in range(20):
            detector.record_order(
                price=Decimal("0.50"),
                size=Decimal("100"),
                side="BUY",
                mid_price=Decimal("0.52"),
            )

        # MM B: 50 size, 1c offset
        for _ in range(20):
            detector.record_order(
                price=Decimal("0.51"),
                size=Decimal("50"),
                side="BUY",
                mid_price=Decimal("0.52"),
            )

        patterns = detector.get_patterns()

        # Should identify 2 distinct patterns
        assert len(patterns) >= 2


class TestCompetitorAnalysis:
    """Test competitor behavior analysis."""

    @pytest.fixture
    def detector(self):
        return CompetitorDetector()

    def test_estimate_competitor_size(self, detector):
        """Estimate total competitor capital."""
        # Record large, consistent orders
        for _ in range(50):
            detector.record_order(
                price=Decimal("0.50"),
                size=Decimal("500"),
                side="BUY",
                mid_price=Decimal("0.52"),
            )

        estimate = detector.estimate_competitor_capital()

        # Should estimate significant capital
        assert estimate > Decimal("1000")

    def test_competitor_aggression_level(self, detector):
        """Measure competitor aggressiveness."""
        # Tight spreads = aggressive
        for _ in range(20):
            detector.record_order(
                price=Decimal("0.515"),  # Very close to mid
                size=Decimal("100"),
                side="BUY",
                mid_price=Decimal("0.52"),
            )

        aggression = detector.get_aggression_level()

        assert aggression > 0.7  # High aggression


class TestCompetitorResponse:
    """Test strategy response to competitors."""

    @pytest.fixture
    def detector(self):
        return CompetitorDetector()

    def test_recommend_wider_spread_vs_large_competitor(self, detector):
        """Recommend wider spread against well-funded competitor."""
        # Large competitor with tight spreads
        for _ in range(50):
            detector.record_order(
                price=Decimal("0.515"),
                size=Decimal("1000"),
                side="BUY",
                mid_price=Decimal("0.52"),
            )

        response = detector.get_strategy_response()

        # Should recommend backing off
        assert response.spread_multiplier > 1.0
        assert response.should_compete is False

    def test_recommend_competing_vs_small_competitor(self, detector):
        """Recommend competing against small competitor."""
        # Small competitor with wide spreads
        for _ in range(20):
            detector.record_order(
                price=Decimal("0.48"),  # 4c from mid
                size=Decimal("20"),
                side="BUY",
                mid_price=Decimal("0.52"),
            )

        response = detector.get_strategy_response()

        # Should recommend competing
        assert response.should_compete is True
