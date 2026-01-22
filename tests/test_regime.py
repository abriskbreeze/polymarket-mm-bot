"""
TDD Tests for Regime Detection

Tests liquidity regime classification.
"""

import pytest
from decimal import Decimal
from src.alpha.regime import RegimeDetector, LiquidityRegime


class TestRegimeClassification:
    """Test regime classification."""

    @pytest.fixture
    def detector(self):
        return RegimeDetector()

    def test_detect_high_liquidity(self, detector):
        """Detect high liquidity regime."""
        # Tight spreads, deep book
        for _ in range(20):
            detector.record_snapshot(
                spread=Decimal("0.01"),
                bid_depth=Decimal("1000"),
                ask_depth=Decimal("1000"),
                volume=Decimal("5000"),
            )

        regime = detector.get_regime()
        assert regime == LiquidityRegime.HIGH

    def test_detect_low_liquidity(self, detector):
        """Detect low liquidity regime."""
        # Wide spreads, thin book (but not extreme enough for CRISIS)
        for _ in range(20):
            detector.record_snapshot(
                spread=Decimal("0.05"),
                bid_depth=Decimal("200"),
                ask_depth=Decimal("200"),
                volume=Decimal("500"),
            )

        regime = detector.get_regime()
        assert regime == LiquidityRegime.LOW

    def test_detect_transition(self, detector):
        """Detect regime transition."""
        # Start high
        for _ in range(10):
            detector.record_snapshot(
                spread=Decimal("0.01"),
                bid_depth=Decimal("1000"),
                ask_depth=Decimal("1000"),
                volume=Decimal("5000"),
            )

        # Suddenly low (but not crisis)
        for _ in range(5):
            detector.record_snapshot(
                spread=Decimal("0.05"),
                bid_depth=Decimal("200"),
                ask_depth=Decimal("200"),
                volume=Decimal("500"),
            )

        transition = detector.detect_transition()
        assert transition is not None
        assert transition.from_regime == LiquidityRegime.HIGH
        assert transition.to_regime == LiquidityRegime.LOW


class TestRegimeResponse:
    """Test strategy response to regimes."""

    @pytest.fixture
    def detector(self):
        return RegimeDetector()

    def test_tighten_in_high_liquidity(self, detector):
        """Tighter spreads in high liquidity."""
        for _ in range(20):
            detector.record_snapshot(
                spread=Decimal("0.01"),
                bid_depth=Decimal("1000"),
                ask_depth=Decimal("1000"),
                volume=Decimal("5000"),
            )

        response = detector.get_strategy_adjustment()
        assert response.spread_multiplier < 1.0

    def test_widen_in_low_liquidity(self, detector):
        """Wider spreads in low liquidity."""
        for _ in range(20):
            detector.record_snapshot(
                spread=Decimal("0.10"),
                bid_depth=Decimal("50"),
                ask_depth=Decimal("50"),
                volume=Decimal("100"),
            )

        response = detector.get_strategy_adjustment()
        assert response.spread_multiplier > 1.0

    def test_pause_during_transition(self, detector):
        """Recommend pausing during regime transition."""
        # Create transition
        for _ in range(10):
            detector.record_snapshot(
                spread=Decimal("0.01"),
                bid_depth=Decimal("1000"),
                ask_depth=Decimal("1000"),
                volume=Decimal("5000"),
            )

        for _ in range(3):
            detector.record_snapshot(
                spread=Decimal("0.10"),
                bid_depth=Decimal("50"),
                ask_depth=Decimal("50"),
                volume=Decimal("100"),
            )

        response = detector.get_strategy_adjustment()
        assert response.should_pause is True
